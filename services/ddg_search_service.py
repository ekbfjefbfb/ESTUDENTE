import asyncio
import logging
import os
import re
from urllib.parse import unquote, urlparse, parse_qs
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
                if not result:
                    # Fallback: HTML scrape (no API keys) para ambientes donde DDGS suele fallar (403/rate-limit)
                    result = await self._search_http_fallback(q)

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

        # Importante: Render a veces no imprime el `extra`, así que incluirlo en el mensaje.
        logger.warning(
            f"ddg_search_failed status={last_status} error={str(last_error or '')}",
            extra={"query": q, "status": last_status, "error": str(last_error or "")},
        )
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

    async def _search_http_fallback(self, query: str) -> List[Dict[str, str]]:
        """Fallback sin dependencia DDGS: scrape simple de DuckDuckGo Lite.

        Nota: No pretende ser perfecto; busca robustez y entregar *algo*.
        """
        try:
            import httpx
        except Exception:
            return []

        url = "https://lite.duckduckgo.com/lite/"
        timeout_s = max(2.0, float(self.timeout_ms) / 1000.0)

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }

        async with httpx.AsyncClient(timeout=timeout_s, headers=headers, follow_redirects=True) as client:
            r = await client.get(url, params={"q": query})
            if r.status_code >= 400:
                return []
            html = r.text or ""

        # DuckDuckGo lite suele renderizar links como /l/?uddg=<encoded>
        # Capturamos anchors y tratamos de recuperar el uddg.
        anchor_re = re.compile(r"<a[^>]+href=\"(?P<href>[^\"]+)\"[^>]*>(?P<title>.*?)</a>", re.IGNORECASE)

        def _strip_tags(s: str) -> str:
            s = re.sub(r"<[^>]+>", " ", s)
            s = re.sub(r"\s+", " ", s)
            return s.strip()

        out: List[Dict[str, str]] = []
        seen: set[str] = set()

        for m in anchor_re.finditer(html):
            href = (m.group("href") or "").strip()
            title = _strip_tags(m.group("title") or "")
            if not href:
                continue

            final_url = href
            if href.startswith("/l/?") or "uddg=" in href:
                try:
                    parsed = urlparse(href)
                    qs = parse_qs(parsed.query)
                    uddg = (qs.get("uddg") or [""])[0]
                    if uddg:
                        final_url = unquote(uddg)
                except Exception:
                    pass

            if final_url.startswith("/"):
                # Evitar URLs internas sin interés
                continue

            key = final_url.strip()
            if not key or key in seen:
                continue
            seen.add(key)

            if "duckduckgo.com" in key and "lite" in key:
                continue

            if title:
                out.append({"title": title[:160], "url": key[:500], "image": "", "snippet": ""})
            else:
                out.append({"title": "Resultado", "url": key[:500], "image": "", "snippet": ""})

            if len(out) >= max(1, int(self.max_results)):
                break

        return out

ddg_search_service = DDGSearchService()
