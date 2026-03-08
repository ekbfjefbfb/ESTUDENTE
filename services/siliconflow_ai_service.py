from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any, Dict, List, Optional
from datetime import datetime

import httpx


SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "").strip()
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").strip().rstrip("/")
SILICONFLOW_LLM_MODEL = os.getenv("SILICONFLOW_LLM_MODEL", "Qwen/Qwen3-VL-32B-Instruct").strip()

CONTEXT_THRESHOLD = 0.85
MAX_CONTEXT_TOKENS = 32000

user_contexts: Dict[str, Dict] = {}

def calculate_context_usage(messages: List[Dict[str, Any]]) -> float:
    total_chars = sum(len(m.get("content", "")) for m in messages)
    estimated_tokens = total_chars / 4
    return min(estimated_tokens / MAX_CONTEXT_TOKENS, 1.0)

def should_refresh_context(user_id: str, messages: List[Dict[str, Any]]) -> bool:
    usage = calculate_context_usage(messages)
    user_contexts[user_id] = {
        "usage": usage,
        "last_check": datetime.utcnow(),
        "messages_count": len(messages)
    }
    return usage >= CONTEXT_THRESHOLD

def get_context_info(user_id: str) -> Dict[str, Any]:
    return user_contexts.get(user_id, {"usage": 0.0, "messages_count": 0})


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    fast_reasoning: bool = True,
    friendly: bool = False,
    stream: bool = False,
) -> Any:
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is not set")

    url = f"{SILICONFLOW_BASE_URL}/chat/completions"

    body: Dict[str, Any] = {
        "model": SILICONFLOW_LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }

    # Prefer non-thinking mode for speed where supported.
    if fast_reasoning:
        body["thinking"] = False

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }

    # Si es streaming, retornar el generador directamente (sin retry loop)
    if stream:
        return _stream_generator(url, headers, body)

    # Implementación de reintentos con backoff exponencial para SiliconFlow
    max_retries = 3
    retry_delay = 1.0
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.post(url, headers=headers, json=body)
                
                if resp.status_code == 429:  # Rate Limit
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                
                resp.raise_for_status()
                payload = resp.json()
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise RuntimeError(f"SiliconFlow API error after {max_retries} attempts: {str(e)}") from e


    try:
        content = payload["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Unexpected SiliconFlow response: {json.dumps(payload)[:2000]}") from e

    if not isinstance(content, str):
        raise RuntimeError("SiliconFlow returned non-text content")

    return content.strip()

async def transcribe_audio(audio_bytes: bytes) -> str:
    """Transcribe audio usando Whisper de SiliconFlow"""
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is not set")
    
    import base64
    
    url = f"{SILICONFLOW_BASE_URL}/audio/transcriptions"
    
    # Implementación de reintentos con backoff exponencial para Transcripción
    max_retries = 3
    retry_delay = 1.0
    
    audio_b64 = base64.b64encode(audio_bytes).decode()
    
    body = {
        "model": "openai/whisper-1",
        "file": audio_b64,
        "response_format": "json"
    }
    
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                resp = await client.post(url, headers=headers, json=body)
                
                if resp.status_code == 429:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                
                resp.raise_for_status()
                result = resp.json()
                break
            except (httpx.HTTPStatusError, httpx.RequestError) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                raise RuntimeError(f"SiliconFlow Transcription error after {max_retries} attempts: {str(e)}") from e
    
    return result.get("text", "")

async def text_to_speech(text: str) -> str:
    """Convierte texto a voz usando API de SiliconFlow (retorna URL o base64)"""
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is not set")
    
    url = f"{SILICONFLOW_BASE_URL}/audio/speech"
    
    body = {
        "model": "sixteenlabs/valle-medium",
        "input": text,
        "voice": "male_1",
        "response_format": "mp3"
    }
    
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
    
    import base64
    audio_b64 = base64.b64encode(resp.content).decode()
    return f"data:audio/mp3;base64,{audio_b64}"

async def _stream_generator(url: str, headers: Dict[str, str], body: Dict[str, Any]):
    """Generador para streaming de respuestas de IA"""
    async with httpx.AsyncClient(timeout=60.0) as client:
        async with client.stream("POST", url, headers=headers, json=body) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    line = line[6:]
                    if line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(line)
                        if "choices" in chunk and len(chunk["choices"]) > 0:
                            content = chunk["choices"][0].get("delta", {}).get("content", "")
                            if content:
                                yield content
                    except json.JSONDecodeError:
                        continue
