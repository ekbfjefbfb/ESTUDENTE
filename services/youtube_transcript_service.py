import asyncio
import re
from typing import Any, Dict, Optional


_YT_ID_RE = re.compile(
    r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/))([A-Za-z0-9_-]{11})"
)


class YouTubeTranscriptService:
    def __init__(self, *, timeout_seconds: float = 2.0, max_chars: int = 5000):
        self.timeout_seconds = timeout_seconds
        self.max_chars = max_chars

    def extract_video_id(self, text: str) -> Optional[str]:
        if not text:
            return None
        m = _YT_ID_RE.search(text)
        if not m:
            return None
        return m.group(1)

    async def fetch_transcript_text(
        self,
        *,
        video_id: str,
        languages: Optional[list[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        if not video_id:
            return None

        from youtube_transcript_api import YouTubeTranscriptApi

        langs = languages or ["es", "en"]

        def _fetch_sync() -> Dict[str, Any]:
            api = YouTubeTranscriptApi()
            fetched = api.fetch(video_id, languages=langs)
            raw = fetched.to_raw_data()
            parts = []
            for s in raw:
                t = (s.get("text") or "").strip()
                if t:
                    parts.append(t)
            text = " ".join(parts)
            if self.max_chars and len(text) > self.max_chars:
                text = text[: self.max_chars].rstrip()
            return {
                "video_id": video_id,
                "language_code": getattr(fetched, "language_code", None),
                "is_generated": getattr(fetched, "is_generated", None),
                "text": text,
            }

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(_fetch_sync),
                timeout=self.timeout_seconds,
            )
        except Exception:
            return None

    def build_source(self, *, video_id: str, snippet: str) -> Dict[str, str]:
        url = f"https://www.youtube.com/watch?v={video_id}"
        image = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return {
            "title": "YouTube",
            "url": url,
            "image": image,
            "snippet": (snippet or "")[:500],
        }


youtube_transcript_service = YouTubeTranscriptService()
