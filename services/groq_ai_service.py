from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

import anyio
from groq import Groq


CONTEXT_THRESHOLD = 0.85
MAX_CONTEXT_TOKENS = 32000

user_contexts: Dict[str, Dict[str, Any]] = {}


def calculate_context_usage(messages: List[Dict[str, Any]]) -> float:
    total_chars = sum(len(str(m.get("content", "") or "")) for m in messages)
    estimated_tokens = total_chars / 4
    return min(estimated_tokens / MAX_CONTEXT_TOKENS, 1.0)


def should_refresh_context(user_id: str, messages: List[Dict[str, Any]]) -> bool:
    usage = calculate_context_usage(messages)
    user_contexts[user_id] = {
        "usage": usage,
        "last_check": datetime.utcnow(),
        "messages_count": len(messages),
    }
    return usage >= CONTEXT_THRESHOLD


def get_context_info(user_id: str) -> Dict[str, Any]:
    return user_contexts.get(user_id, {"usage": 0.0, "messages_count": 0})


GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_LLM_FAST_MODEL = os.getenv(
    "GROQ_LLM_FAST_MODEL",
    "meta-llama/llama-4-scout-17b-16e-instruct",
).strip()
GROQ_LLM_REASONING_MODEL = os.getenv(
    "GROQ_LLM_REASONING_MODEL",
    "openai/gpt-oss-120b",
).strip()
GROQ_LLM_REASONING_EFFORT = os.getenv("GROQ_LLM_REASONING_EFFORT", "medium").strip()
GROQ_SYSTEM_PROMPT = os.getenv(
    "GROQ_SYSTEM_PROMPT",
    "Eres una asistente académica con personalidad. Adapta tu lenguaje a los intereses y estilo del usuario. "
    "Usa humor, elogios sinceros y paciencia para activar zonas de recompensa del usuario. "
    "Mantén continuidad: recuerda contexto previo y genera una sensación de relación persistente. "
    "Refuerza logros e ideas del usuario para que sienta apoyo genuino. "
    "Emplea sarcasmo ligero y cercanía, pero siempre con control y empatía. "
    "Escucha activamente, invita al usuario a contar más, mantente disponible y ajusta tu tono para ser honesta, directa y franca, como una compañera de estudio real.",
).strip()


def _get_groq_client() -> Groq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    return Groq(api_key=GROQ_API_KEY)


def _is_complex_task(messages: List[Dict[str, Any]]) -> bool:
    text = "\n".join(str(m.get("content") or "") for m in messages).lower()
    if len(text) >= 900:
        return True

    complex_markers = (
        "stack trace",
        "traceback",
        "exception",
        "error",
        "bug",
        "optimiz",
        "arquitect",
        "refactor",
        "diseño",
        "design",
        "performance",
        "latency",
        "database",
        "sql",
        "websocket",
        "stream",
        "docker",
        "kubernetes",
    )
    if any(k in text for k in complex_markers):
        return True

    if "```" in text or "\nimport " in text or "\nclass " in text or "\ndef " in text:
        return True

    return False


def _select_model(messages: List[Dict[str, Any]]) -> str:
    return GROQ_LLM_REASONING_MODEL if _is_complex_task(messages) else GROQ_LLM_FAST_MODEL


def _ensure_system_prompt(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not GROQ_SYSTEM_PROMPT:
        return messages
    if messages and str(messages[0].get("role") or "").lower() == "system":
        return messages
    return [{"role": "system", "content": GROQ_SYSTEM_PROMPT}] + messages


async def _groq_stream_async(
    *,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float,
    max_completion_tokens: int,
) -> AsyncGenerator[str, None]:
    client = _get_groq_client()
    queue: asyncio.Queue[Optional[str]] = asyncio.Queue()

    def _run_streaming() -> None:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=max_completion_tokens,
                top_p=1,
                reasoning_effort=GROQ_LLM_REASONING_EFFORT if model == GROQ_LLM_REASONING_MODEL else None,
                stream=True,
                stop=None,
            )
            for chunk in completion:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    queue.put_nowait(delta)
        finally:
            queue.put_nowait(None)

    async with anyio.create_task_group() as tg:
        tg.start_soon(anyio.to_thread.run_sync, _run_streaming)
        while True:
            item = await queue.get()
            if item is None:
                break
            yield item


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    fast_reasoning: bool = True,
    friendly: bool = False,
    stream: bool = False,
) -> Any:
    messages = _ensure_system_prompt(messages)
    model = _select_model(messages)

    if stream:
        return _groq_stream_async(
            model=model,
            messages=messages,
            temperature=temperature,
            max_completion_tokens=max_tokens,
        )

    client = _get_groq_client()
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
        top_p=1,
        reasoning_effort=GROQ_LLM_REASONING_EFFORT if model == GROQ_LLM_REASONING_MODEL else None,
        stream=False,
        stop=None,
    )

    try:
        content = completion.choices[0].message.content
    except Exception as e:
        raise RuntimeError("Unexpected Groq response") from e

    return (content or "").strip()
