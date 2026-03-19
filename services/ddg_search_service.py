import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from ddgs import DDGS
except ImportError:
    try:
        from duckduckgo_search import DDGS
    except Exception:
        DDGS = None

logger = logging.getLogger("ddg_search_service")

@dataclass
class SearchSource:
    title: str
    url: str
    image: str
    snippet: str

    def to_dict(self) -> Dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "image": self.image,
            "snippet": self.snippet,
        }

class DDGSearchService:
    def __init__(self):
        self.max_results = int(os.getenv("DDG_MAX_RESULTS", "3"))
        self.timeout_ms = int(os.getenv("DDG_TIMEOUT_MS", "2500"))
        self.region = os.getenv("DDG_REGION", "wt-wt").strip() or "wt-wt"
        self.safesearch = os.getenv("DDG_SAFESEARCH", "moderate").strip() or "moderate"
        self.cache_ttl_s = int(os.getenv("DDG_CACHE_TTL_S", "120"))
        self.retries = int(os.getenv("DDG_RETRIES", "2"))
        self.retry_backoff_ms = int(os.getenv("DDG_RETRY_BACKOFF_MS", "350"))
        self._cache: Dict[str, Tuple[float, List[Dict[str, str]]]] = {}

    async def search(self, query: str) -> List[Dict[str, str]]:
        sources, _meta = await self.search_with_meta(query)
        return sources

    async def search_with_meta(self, query: str) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return [], {"status": "empty_query"}

        if DDGS is None:
            return [], {"status": "unavailable", "error": "ddgs_not_installed"}

        loop = asyncio.get_event_loop()
        now = loop.time()
        cached = self._cache.get(q)
        if cached is not None:
            ts, payload = cached
            if now - ts <= float(self.cache_ttl_s):
                return list(payload), {"status": "cache_hit"}

        last_error: Optional[str] = None
        last_status: str = "failed"
        attempts = max(1, int(self.retries) + 1)
        
        for i in range(attempts):
            try:
                result = await asyncio.wait_for(self._search_sync(q), timeout=self.timeout_ms / 1000.0)
                self._cache[q] = (loop.time(), list(result))
                status = "ok" if result else "no_results"
                return list(result), {"status": status, "attempt": i + 1}
            except asyncio.TimeoutError:
                last_status = "timeout"
                last_error = f"timeout_ms={self.timeout_ms}"
            except Exception as e:
                msg = str(e)
                last_error = f"{type(e).__name__}: {msg}" if msg else type(e).__name__
                low = msg.lower()
                if "ratelimit" in msg or ("rate" in low and "limit" in low) or "202" in msg or "403" in msg:
                    last_status = "rate_limited"
                else:
                    last_status = "failed"

            if i < attempts - 1:
                await asyncio.sleep((self.retry_backoff_ms / 1000.0) * (i + 1))

        logger.warning("ddg_search_failed", extra={"query": q, "status": last_status, "error": str(last_error or "")})
        return [], {"status": last_status, "error": str(last_error or ""), "attempts": attempts}

    async def _search_sync(self, query: str) -> List[Dict[str, str]]:
        def _run() -> List[Dict[str, str]]:
            sources: List[SearchSource] = []
            with DDGS() as ddgs:
                # 1. Noticias (News)
                try:
                    for r in ddgs.news(query, region=self.region, safesearch=self.safesearch, max_results=self.max_results):
                        title = str(r.get("title") or "").strip()
                        url = str(r.get("url") or "").strip()
                        snippet = str(r.get("body") or "").strip()
                        image = str(r.get("image") or "").strip()
                        if url:
                            sources.append(SearchSource(title=title, url=url, image=image, snippet=snippet))
                        if len(sources) >= self.max_results:
                            break
                except Exception:
                    pass

                # 2. Texto (Text)
                if len(sources) < self.max_results:
                    try:
                        for r in ddgs.text(query, region=self.region, safesearch=self.safesearch, max_results=self.max_results):
                            title = str(r.get("title") or "").strip()
                            url = str(r.get("href") or "").strip()
                            snippet = str(r.get("body") or "").strip()
                            if url:
                                sources.append(SearchSource(title=title, url=url, image="", snippet=snippet))
                            if len(sources) >= self.max_results:
                                break
                    except Exception:
                        pass

                # 3. Imágenes (Images)
                low_query = query.lower()
                if len(sources) < self.max_results or "foto" in low_query or "imagen" in low_query or "muestrame" in low_query:
                    try:
                        img_gen = ddgs.images(query, region=self.region, safesearch=self.safesearch, max_results=self.max_results)
                        for r in img_gen:
                            title = str(r.get("title") or "").strip()
                            url = str(r.get("url") or "").strip()
                            image = str(r.get("image") or "").strip()
                            if image:
                                sources.append(SearchSource(title=title or "Imagen", url=url or image, image=image, snippet=""))
                            if len(sources) >= self.max_results + 2:
                                break
                    except Exception:
                        pass

            seen = set()
            out: List[Dict[str, str]] = []
            for s in sources:
                key = (s.url or s.image or s.title).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(s.to_dict())
                if len(out) >= self.max_results + 2:
                    break
            return out

        return await asyncio.to_thread(_run)

ddg_search_service = DDGSearchService()
