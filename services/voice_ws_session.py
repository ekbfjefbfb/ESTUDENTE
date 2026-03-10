from __future__ import annotations

import asyncio
from array import array
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional

from services.groq_voice_service import normalize_voice, text_to_speech_groq, transcribe_audio_groq


SendJson = Callable[[Dict[str, Any]], Awaitable[None]]


@dataclass
class VoiceWsConfig:
    max_audio_bytes: int = 10 * 1024 * 1024
    partial_interval_ms: int = 700
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

    vad_enabled: bool = False
    vad_silence_ms: int = 900
    vad_threshold: int = 600
    last_voice_at: float = 0.0
    ending: bool = False

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
        self.audio_buf = bytearray()
        self.last_partial_text = ""
        self.last_voice_at = asyncio.get_running_loop().time()
        self.ending = False

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

        if len(self.audio_buf) + len(chunk) > self.config.max_audio_bytes:
            await self.send_json({"type": "error", "code": "AUDIO_TOO_LARGE", "message": "max_10mb", "ts": self.now_ts()})
            raise ValueError("audio_too_large")

        self.audio_buf.extend(chunk)
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
            avg_abs = int(sum((abs(x) for x in pcm)) / len(pcm))
        except Exception:
            return

        if avg_abs >= self.vad_threshold:
            self.last_voice_at = now
            return

        if self.last_voice_at <= 0.0:
            self.last_voice_at = now
            return

        if (now - self.last_voice_at) * 1000.0 < float(self.vad_silence_ms):
            return

        min_bytes = int(0.4 * self.sample_rate * 2)
        if len(self.audio_buf) < min_bytes:
            return

        await self.send_json({"type": "vad_silence", "silence_ms": self.vad_silence_ms, "ts": self.now_ts()})
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

    async def _emit_final_and_reply(self, *, user_id: str) -> None:
        if not self.audio_buf:
            await self.send_json({"type": "stt_final", "text": "", "language": self.language, "duration_ms": 0, "ts": self.now_ts()})
            return

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
            await self.send_json({"type": "error", "code": "STT_ERROR", "message": str(e), "ts": self.now_ts()})
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

        if self.mode == "stt_only":
            return

        # LLM
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
                    await self.send_json({"type": "llm_partial", "delta": delta})
                llm_text = "".join(llm_parts).strip()
            else:
                llm_text = await self.chat_with_ai(
                    messages=[{"role": "user", "content": final_text}],
                    user=user_id,
                    stream=False,
                )
                llm_text = (llm_text or "").strip()

            await self.send_json({"type": "llm_final", "text": llm_text})
        except Exception as e:
            await self.send_json({"type": "error", "code": "LLM_ERROR", "message": str(e), "ts": self.now_ts()})
            return

        # TTS
        try:
            voice = normalize_voice(self.voice_name)
            audio_data = await text_to_speech_groq(llm_text, voice=voice, speed=1.0)
            await self.send_json({"type": "tts_audio", "audio": audio_data, "text": llm_text, "voice": voice, "ts": self.now_ts()})
        except Exception as e:
            await self.send_json({"type": "error", "code": "TTS_ERROR", "message": str(e), "ts": self.now_ts()})
