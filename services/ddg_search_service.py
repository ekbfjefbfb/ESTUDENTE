import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from duckduckgo_search import DDGS

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
        self.timeout_ms = int(os.getenv("DDG_TIMEOUT_MS", "500"))
        self.region = os.getenv("DDG_REGION", "wt-wt").strip() or "wt-wt"
        self.safesearch = os.getenv("DDG_SAFESEARCH", "moderate").strip() or "moderate"

    async def search(self, query: str) -> List[Dict[str, str]]:
        q = (query or "").strip()
        if not q:
            return []

        try:
            return await asyncio.wait_for(self._search_sync(q), timeout=self.timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            logger.warning("ddg_search_timeout", extra={"query": q, "timeout_ms": self.timeout_ms})
            return []
        except Exception as e:
            logger.warning("ddg_search_failed", extra={"query": q, "error": str(e)})
            return []

    async def _search_sync(self, query: str) -> List[Dict[str, str]]:
        def _run() -> List[Dict[str, str]]:
            sources: List[SearchSource] = []
            with DDGS() as ddgs:
                # Prefer 'images' first so we get image urls, then fall back to 'text' results.
                try:
                    for r in ddgs.images(query, region=self.region, safesearch=self.safesearch, max_results=self.max_results):
                        title = str(r.get("title") or r.get("source") or "").strip()
                        url = str(r.get("url") or r.get("image") or "").strip()
                        image = str(r.get("image") or r.get("thumbnail") or "").strip()
                        snippet = str(r.get("description") or "").strip()
                        if url or image:
                            sources.append(SearchSource(title=title or url, url=url, image=image, snippet=snippet))
                        if len(sources) >= self.max_results:
                            break
                except Exception:
                    pass

                if len(sources) < self.max_results:
                    try:
                        for r in ddgs.text(query, region=self.region, safesearch=self.safesearch, max_results=self.max_results):
                            title = str(r.get("title") or "").strip()
                            url = str(r.get("href") or r.get("url") or "").strip()
                            snippet = str(r.get("body") or r.get("snippet") or "").strip()
                            sources.append(SearchSource(title=title or url, url=url, image="", snippet=snippet))
                            if len(sources) >= self.max_results:
                                break
                    except Exception:
                        pass

            # Deduplicate by url
            seen = set()
            out: List[Dict[str, str]] = []
            for s in sources:
                key = (s.url or s.image or s.title).strip()
                if not key or key in seen:
                    continue
                seen.add(key)
                out.append(s.to_dict())
                if len(out) >= self.max_results:
                    break
            return out

        return await asyncio.to_thread(_run)


ddg_search_service = DDGSearchService()
