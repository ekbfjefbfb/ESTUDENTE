import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("tavily_search_service")


@dataclass
class TavilyResult:
    title: str
    url: str
    snippet: str
    image: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "image": self.image,
            "snippet": self.snippet,
        }


class TavilySearchService:
    def __init__(self) -> None:
        self.base_url = (os.getenv("TAVILY_BASE_URL") or "https://api.tavily.com").rstrip("/")
        self.timeout_s = float(os.getenv("TAVILY_TIMEOUT_S", "8"))
        self.max_results = int(os.getenv("TAVILY_MAX_RESULTS", "5"))
        self.search_depth = (os.getenv("TAVILY_SEARCH_DEPTH") or "advanced").strip() or "advanced"

        # Comma-separated keys. Example: TAVILY_API_KEYS=tvly-xxx,tvly-yyy
        raw_keys = os.getenv("TAVILY_API_KEYS") or ""
        keys = [k.strip() for k in raw_keys.split(",") if k.strip()]
        self._api_keys: List[str] = keys

        # in-process cooldown for keys that returned rate-limit / quota errors
        self._key_cooldown_until: Dict[str, float] = {}
        self._cooldown_s = float(os.getenv("TAVILY_KEY_COOLDOWN_S", "60"))

    def enabled(self) -> bool:
        return len(self._api_keys) > 0

    def _pick_key_indices(self, *, user_id: str) -> List[int]:
        n = len(self._api_keys)
        if n <= 0:
            return []
        # Deterministic shard by user_id to spread load, then try others for failover
        h = int(hashlib.sha256(str(user_id).encode("utf-8")).hexdigest(), 16)
        start = h % n
        return list(range(start, n)) + list(range(0, start))

    def _is_key_in_cooldown(self, key: str) -> bool:
        until = float(self._key_cooldown_until.get(key) or 0.0)
        return time.time() < until

    def _cooldown_key(self, key: str) -> None:
        self._key_cooldown_until[key] = time.time() + self._cooldown_s

    async def search_with_meta(
        self,
        *,
        query: str,
        user_id: str,
        include_images: bool = False,
    ) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return [], {"status": "empty_query"}

        if not self.enabled():
            return [], {"status": "disabled"}

        indices = self._pick_key_indices(user_id=str(user_id))
        if not indices:
            return [], {"status": "disabled"}

        last_error: Optional[str] = None
        last_status: str = "failed"

        for attempt, idx in enumerate(indices, start=1):
            key = self._api_keys[idx]
            if self._is_key_in_cooldown(key):
                continue

            try:
                results = await self._search_once(
                    api_key=key,
                    query=q,
                    include_images=include_images,
                )
                return results, {"status": "ok", "attempt": attempt, "key_index": idx}
            except httpx.TimeoutException:
                last_status = "timeout"
                last_error = "timeout"
            except httpx.HTTPStatusError as e:
                code = int(e.response.status_code)
                body = ""
                try:
                    body = e.response.text or ""
                except Exception:
                    body = ""

                if code in (401, 403):
                    last_status = "unauthorized"
                    last_error = f"http_{code}"
                    self._cooldown_key(key)
                elif code in (402, 429):
                    last_status = "rate_limited"
                    last_error = f"http_{code}"
                    self._cooldown_key(key)
                else:
                    last_status = "http_error"
                    last_error = f"http_{code}" + (f":{body[:160]}" if body else "")
            except Exception as e:
                msg = str(e)
                low = msg.lower()
                if "rate" in low and "limit" in low:
                    last_status = "rate_limited"
                    self._cooldown_key(key)
                elif "credit" in low or "quota" in low or "insufficient" in low:
                    last_status = "rate_limited"
                    self._cooldown_key(key)
                else:
                    last_status = "failed"
                last_error = f"{type(e).__name__}: {msg}" if msg else type(e).__name__

        logger.warning(f"tavily_search_failed status={last_status} error={str(last_error or '')}")
        return [], {"status": last_status, "error": str(last_error or "")}

    async def _search_once(
        self,
        *,
        api_key: str,
        query: str,
        include_images: bool,
    ) -> List[Dict[str, str]]:
        url = f"{self.base_url}/search"

        payload: Dict[str, Any] = {
            "api_key": api_key,
            "query": query,
            "search_depth": self.search_depth,
            "max_results": self.max_results,
            "include_answer": False,
            "include_raw_content": False,
        }

        # Tavily supports include_images on many plans; keep it optional.
        if include_images:
            payload["include_images"] = True

        timeout = httpx.Timeout(self.timeout_s)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json() if resp.content else {}

        out: List[TavilyResult] = []

        results = data.get("results")
        if isinstance(results, list):
            for r in results:
                if not isinstance(r, dict):
                    continue
                title = str(r.get("title") or "").strip()
                link = str(r.get("url") or "").strip()
                snippet = str(r.get("content") or r.get("snippet") or "").strip()
                if link:
                    out.append(TavilyResult(title=title[:200], url=link[:500], snippet=snippet[:400]))

        # Some responses include an `images` list. Convert them into sources if requested.
        if include_images:
            images = data.get("images")
            if isinstance(images, list):
                for img in images:
                    if not isinstance(img, dict):
                        continue
                    img_url = str(img.get("url") or img.get("image") or "").strip()
                    if not img_url:
                        continue
                    title = str(img.get("title") or img.get("description") or "Imagen").strip()
                    page = str(img.get("source") or img.get("link") or img_url).strip()
                    out.append(TavilyResult(title=title[:200], url=page[:500], snippet="", image=img_url[:500]))

        # de-dup
        seen = set()
        final: List[Dict[str, str]] = []
        for r in out:
            key = (r.url or r.image or r.title).strip()
            if not key or key in seen:
                continue
            seen.add(key)
            final.append(r.to_dict())
            if len(final) >= max(1, int(self.max_results)) + 2:
                break

        return final


tavily_search_service = TavilySearchService()
