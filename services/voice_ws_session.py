from __future__ import annotations

import asyncio
import logging
from array import array
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List

from services.groq_voice_service import normalize_voice, text_to_speech_groq, transcribe_audio_groq

logger = logging.getLogger("voice_ws_session")


SendJson = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class VoiceWsConfig:
    max_audio_bytes: int = 30 * 1024 * 1024  # 30MB
    partial_interval_ms: int = 400
    tail_window_ms: int = 4500


@dataclass
class VoiceWsSession:
    send_json: SendJson
    chat_with_ai: Callable[..., Awaitable[Any]]
    now_ts: Callable[[], str]
    estimate_duration_ms: Callable[[int], int]
    tail_bytes_for_pcm16: Callable[..., bytes]
    config: VoiceWsConfig = field(default_factory=VoiceWsConfig)

    # state
    audio_buf: bytearray = field(default_factory=bytearray)
    started: bool = False
    format_name: str = "pcm16"
    sample_rate: int = 16000
    language: str = "es"
    mode: str = "voice_chat"  # stt_only | voice_chat
    stream_llm: bool = True
    stream_tts: bool = False
    voice_name: str = ""

    current_user_id: str = ""

    # VAD configuration (refined for background noise resilience)
    vad_enabled: bool = False
    vad_silence_ms: int = 900
    vad_threshold: int = 600
    vad_min_amplitude: int = 300  # Minimum amplitude to consider as voice (noise floor)
    vad_hysteresis: int = 100     # Hysteresis to prevent oscillation
    vad_frames_processed: int = 0
    vad_frames_voice: int = 0
    vad_consecutive_silence: int = 0

    last_partial_sent_at: float = 0.0
    last_partial_text: str = ""

    def reset_turn(self) -> None:
        self.audio_buf = bytearray()
        self.started = False
        self.last_partial_text = ""
        self.last_partial_sent_at = 0.0
        self.last_voice_at = 0.0
        self.ending = False
        self.current_user_id = ""

    async def start_turn(self, data: Dict[str, Any], *, user_id: str) -> None:
        self.started = True
        self.current_user_id = str(user_id)
        self.format_name = str(data.get("format") or "pcm16")
        self.sample_rate = int(data.get("sample_rate") or 16000)
        self.language = str(data.get("language") or "es")
        self.mode = str(data.get("mode") or "voice_chat")
        self.stream_llm = bool(data.get("stream_llm", True))
        self.stream_tts = bool(data.get("stream_tts", False))
        self.voice_name = str(data.get("voice") or "")
        self.vad_enabled = bool(data.get("vad", False))
        self.vad_silence_ms = int(data.get("vad_silence_ms") or 900)
        self.vad_threshold = int(data.get("vad_threshold") or 600)
        self.vad_min_amplitude = int(data.get("vad_min_amplitude") or 300)
        self.audio_buf = bytearray()
        self.last_partial_text = ""
        self.last_voice_at = asyncio.get_running_loop().time()
        self.ending = False
        self.vad_frames_processed = 0
        self.vad_frames_voice = 0
        self.vad_consecutive_silence = 0

        logger.info(f"Voice turn started for user={user_id}, format={self.format_name}, vad={self.vad_enabled}, threshold={self.vad_threshold}")

        await self.send_json(
            {
                "type": "ready",
                "user_id": user_id,
                "format": self.format_name,
                "sample_rate": self.sample_rate,
                "language": self.language,
                "mode": self.mode,
                "stream_llm": self.stream_llm,
                "stream_tts": self.stream_tts,
                "voice": self.voice_name,
                "ts": self.now_ts(),
            }
        )

    async def add_audio_chunk(self, chunk: bytes) -> None:
        if not self.started:
            await self.send_json({"type": "error", "code": "NOT_STARTED", "message": "send_start_first", "ts": self.now_ts()})
            return

        if self.ending:
            return

        current_size = len(self.audio_buf)
        chunk_size = len(chunk)
        max_size = self.config.max_audio_bytes
        
        if current_size + chunk_size > max_size:
            logger.error(f"Audio buffer overflow: current={current_size}, chunk={chunk_size}, max={max_size}")
            await self.send_json({"type": "error", "code": "AUDIO_TOO_LARGE", "message": f"max_{max_size//1024//1024}mb_exceeded", "ts": self.now_ts()})
            raise ValueError(f"audio_too_large: {current_size + chunk_size} > {max_size}")

        self.audio_buf.extend(chunk)
        
        # Log cada MB acumulado para debuggear
        new_size = len(self.audio_buf)
        if new_size // (1024*1024) > current_size // (1024*1024):
            logger.info(f"Audio buffer: {new_size//1024}KB accumulated")
        
        await self._maybe_vad_auto_end(chunk)
        await self._maybe_emit_partial()

    async def end_turn(self, *, user_id: str) -> None:
        if not self.started:
            await self.send_json({"type": "error", "code": "NOT_STARTED", "message": "send_start_first", "ts": self.now_ts()})
            return

        if self.ending:
            return

        self.ending = True
        await self._emit_final_and_reply(user_id=user_id)
        self.reset_turn()

    async def _maybe_vad_auto_end(self, chunk: bytes) -> None:
        if not self.vad_enabled:
            return
        if not self.started or self.ending:
            return
        if self.format_name != "pcm16":
            return
        if not chunk:
            return

        now = asyncio.get_running_loop().time()

        try:
            pcm = array("h")
            pcm.frombytes(chunk)
            if not pcm:
                return
            
            # Calculate energy metrics
            samples = list(pcm)
            abs_samples = [abs(x) for x in samples]
            avg_abs = int(sum(abs_samples) / len(abs_samples))
            
            # Refined VAD logic with hysteresis and noise floor
            is_voice = False
            if avg_abs > self.vad_min_amplitude:
                if avg_abs >= (self.vad_threshold + self.vad_hysteresis):
                    is_voice = True
                elif avg_abs >= self.vad_threshold and self.last_voice_at > 0:
                    # Continue voice state if recently had voice (hysteresis)
                    if (now - self.last_voice_at) * 1000.0 < 200:
                        is_voice = True
            
            self.vad_frames_processed += 1
            
        except Exception as e:
            logger.warning(f"VAD processing error: {e}")
            return

        if is_voice:
            self.last_voice_at = now
            self.vad_frames_voice += 1
            self.vad_consecutive_silence = 0
            return

        if self.last_voice_at <= 0.0:
            self.last_voice_at = now
            return

        # Count consecutive silence frames
        self.vad_consecutive_silence += 1
        silence_duration_ms = (now - self.last_voice_at) * 1000.0

        if silence_duration_ms < float(self.vad_silence_ms):
            return

        # Require minimum voice activity before allowing auto-end
        min_voice_frames = max(3, int(self.vad_frames_processed * 0.1))  # At least 10% frames with voice
        if self.vad_frames_voice < min_voice_frames:
            logger.debug(f"VAD: not enough voice frames ({self.vad_frames_voice}/{min_voice_frames})")
            return

        min_bytes = int(0.4 * self.sample_rate * 2)
        if len(self.audio_buf) < min_bytes:
            return

        logger.info(f"VAD auto-end triggered: silence={silence_duration_ms:.0f}ms, voice_frames={self.vad_frames_voice}/{self.vad_frames_processed}")
        await self.send_json({"type": "vad_silence", "silence_ms": int(silence_duration_ms), "ts": self.now_ts()})
        await self.end_turn(user_id=self.current_user_id)

    async def _maybe_emit_partial(self) -> None:
        now = asyncio.get_running_loop().time()
        if (now - self.last_partial_sent_at) * 1000 < self.config.partial_interval_ms:
            return
        if not self.audio_buf:
            return

        # Parciales solo con PCM16 (sin decodificación)
        if self.format_name != "pcm16":
            return

        tail_bytes = self.tail_bytes_for_pcm16(
            buf=self.audio_buf,
            sample_rate=self.sample_rate,
            tail_window_ms=self.config.tail_window_ms,
        )

        try:
            text = await transcribe_audio_groq(
                tail_bytes,
                language=self.language,
                audio_format="pcm16",
                sample_rate=self.sample_rate,
            )
        except Exception as e:
            await self.send_json({"type": "error", "code": "STT_ERROR", "message": str(e), "ts": self.now_ts()})
            self.last_partial_sent_at = now
            return

        if not isinstance(text, str):
            self.last_partial_sent_at = now
            return

        text = text.strip()
        if not text or text == self.last_partial_text:
            self.last_partial_sent_at = now
            return

        self.last_partial_text = text
        self.last_partial_sent_at = now

        await self.send_json(
            {
                "type": "stt_partial",
                "text": text,
                "language": self.language,
                "duration_ms": self.estimate_duration_ms(len(self.audio_buf)),
                "ts": self.now_ts(),
            }
        )
        logger.debug(f"STT partial sent: '{text[:50]}...'")

    async def _emit_final_and_reply(self, *, user_id: str) -> None:
        if not self.audio_buf:
            await self.send_json({"type": "stt_final", "text": "", "language": self.language, "duration_ms": 0, "ts": self.now_ts()})
            return

        # 1. STT con reintento/captura de error
        try:
            final_text = (
                await transcribe_audio_groq(
                    bytes(self.audio_buf),
                    language=self.language,
                    audio_format=self.format_name,
                    sample_rate=self.sample_rate,
                )
            ).strip()
        except Exception as e:
            logger.error(f"STT final error for user={user_id}: {e}")
            await self.send_json({"type": "error", "code": "STT_ERROR", "message": "No pude entender el audio, intenta de nuevo.", "ts": self.now_ts()})
            return

        await self.send_json(
            {
                "type": "stt_final",
                "text": final_text,
                "language": self.language,
                "duration_ms": self.estimate_duration_ms(len(self.audio_buf)),
                "ts": self.now_ts(),
            }
        )
        logger.info(f"STT final: '{final_text[:100]}...' ({len(final_text)} chars)")

        if self.mode == "stt_only" or not final_text:
            return

        # 2. LLM con captura de error
        llm_text = ""
        logger.info(f"Starting LLM for user={user_id}, text_len={len(final_text)}")
        try:
            if self.stream_llm:
                gen = await self.chat_with_ai(
                    messages=[{"role": "user", "content": final_text}],
                    user=user_id,
                    stream=True,
                )
                llm_parts: List[str] = []
                async for delta in gen:
                    if not isinstance(delta, str) or not delta:
                        continue
                    llm_parts.append(delta)
                    await self.send_json({"type": "llm_partial", "delta": delta, "content": delta, "ts": self.now_ts()})
                llm_text = "".join(llm_parts).strip()
                logger.info(f"LLM streaming complete: {len(llm_text)} chars")
            else:
                llm_text = await self.chat_with_ai(
                    messages=[{"role": "user", "content": final_text}],
                    user=user_id,
                    stream=False,
                )
                llm_text = (llm_text or "").strip()
                logger.info(f"LLM non-stream complete: {len(llm_text)} chars")

            if llm_text:
                await self.send_json({"type": "llm_final", "text": llm_text, "content": llm_text, "ts": self.now_ts()})
            else:
                logger.warning(f"LLM returned empty text for user={user_id}")
                return
        except Exception as e:
            logger.exception(f"LLM error for user={user_id}: {e}")
            await self.send_json({"type": "error", "code": "LLM_ERROR", "message": "Error al procesar tu mensaje con la IA.", "ts": self.now_ts()})
            return

        # 3. TTS con captura de error
        logger.info(f"Starting TTS for user={user_id}, text_len={len(llm_text)}, voice={self.voice_name}")
        try:
            voice = normalize_voice(self.voice_name)
            audio_data = await text_to_speech_groq(llm_text, voice=voice, speed=1.0)
            await self.send_json({
                "type": "tts_audio",
                "audio": audio_data,
                "audio_url": audio_data,
                "text": llm_text[:200],
                "voice": voice,
                "ts": self.now_ts(),
            })
            logger.info(f"TTS complete: {len(audio_data)} chars of base64 audio")
        except Exception as e:
            logger.exception(f"TTS error for user={user_id}: {e}")
            # Si falla el TTS, al menos el usuario recibió el texto (llm_final)
            await self.send_json({"type": "error", "code": "TTS_ERROR", "message": "No pude generar el audio de respuesta.", "ts": self.now_ts()})
