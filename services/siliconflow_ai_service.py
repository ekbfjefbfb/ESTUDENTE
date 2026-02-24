from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import httpx


SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "").strip()
SILICONFLOW_BASE_URL = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").strip().rstrip("/")
SILICONFLOW_LLM_MODEL = os.getenv("SILICONFLOW_LLM_MODEL", "deepseek-ai/DeepSeek-V3.2-Exp").strip()


async def chat_with_ai(
    messages: List[Dict[str, Any]],
    user: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    fast_reasoning: bool = True,
    friendly: bool = False,
) -> str:
    if not SILICONFLOW_API_KEY:
        raise RuntimeError("SILICONFLOW_API_KEY is not set")

    url = f"{SILICONFLOW_BASE_URL}/chat/completions"

    body: Dict[str, Any] = {
        "model": SILICONFLOW_LLM_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    # Prefer non-thinking mode for speed where supported.
    if fast_reasoning:
        body["thinking"] = False

    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, headers=headers, json=body)
        resp.raise_for_status()
        payload = resp.json()

    try:
        content = payload["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Unexpected SiliconFlow response: {json.dumps(payload)[:2000]}") from e

    if not isinstance(content, str):
        raise RuntimeError("SiliconFlow returned non-text content")

    return content.strip()
