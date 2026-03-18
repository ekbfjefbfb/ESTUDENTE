import asyncio
import os
import re
from typing import Any, Dict, Optional
from urllib.parse import urlparse


_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


class BrowserMcpService:
    def __init__(
        self,
        *,
        timeout_seconds: float = 4.0,
        nav_timeout_ms: int = 3500,
        max_chars: int = 5000,
    ):
        self.timeout_seconds = timeout_seconds
        self.nav_timeout_ms = nav_timeout_ms
        self.max_chars = max_chars

    def enabled(self) -> bool:
        return str(os.getenv("MCP_BROWSER_ENABLED", "0")).strip() in {"1", "true", "True"}

    def extract_first_url(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = _URL_RE.search(text)
        if not m:
            return None
        url = m.group(0).strip().rstrip(")].,;\"")
        return url or None

    def build_source(self, *, url: str, title: str, snippet: str) -> Dict[str, str]:
        host = ""
        try:
            host = urlparse(url).netloc
        except Exception:
            host = ""
        return {
            "title": (title or host or "Web")[:120],
            "url": url,
            "image": "",
            "snippet": (snippet or "")[:500],
        }

    async def fetch_page_extract(self, *, url: str) -> Optional[Dict[str, Any]]:
        if not url:
            return None

        async def _run() -> Optional[Dict[str, Any]]:
            try:
                from playwright.async_api import async_playwright
            except Exception:
                return None

            try:
                async with async_playwright() as p:
                    browser = await p.chromium.launch(
                        headless=True,
                        args=[
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                            "--disable-gpu",
                        ],
                    )
                    try:
                        page = await browser.new_page()
                        page.set_default_navigation_timeout(self.nav_timeout_ms)
                        page.set_default_timeout(self.nav_timeout_ms)
                        await page.goto(url, wait_until="domcontentloaded")

                        title = (await page.title()) or ""
                        text = await page.evaluate(
                            """
                            () => {
                              const t = document.body ? document.body.innerText : '';
                              return t || '';
                            }
                            """
                        )
                        text = (text or "").strip()
                        if self.max_chars and len(text) > self.max_chars:
                            text = text[: self.max_chars].rstrip()

                        return {
                            "url": url,
                            "title": title.strip(),
                            "text": text,
                        }
                    finally:
                        try:
                            await browser.close()
                        except Exception:
                            pass
            except Exception:
                return None

        try:
            return await asyncio.wait_for(_run(), timeout=self.timeout_seconds)
        except Exception:
            return None


browser_mcp_service = BrowserMcpService()
