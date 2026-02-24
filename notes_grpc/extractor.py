from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

import asyncio
import re

from notes_grpc.siliconflow_client import SiliconFlowClient


@dataclass
class ExtractedTask:
    text: str
    due_date: Optional[datetime]
    priority: int


@dataclass
class ExtractedNote:
    title: str
    summary: str
    key_points: List[str]
    tasks: List[ExtractedTask]


SYSTEM_PROMPT = (
    "You extract study notes. Return STRICT JSON object only. "
    "Dates: if transcript mentions a due date, output ISO-8601 date-time in UTC if possible, "
    "otherwise omit due_date. If relative date like 'tomorrow', assume user's timezone is UTC and convert. "
    "Schema: {title:string, summary:string, key_points:[string], tasks:[{text:string, due_date?:string, priority:int}]}"
)


def _parse_due_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


async def extract_note_from_text(*, client: SiliconFlowClient, transcript: str, title_hint: str = "") -> ExtractedNote:
    user_prompt = (
        f"Transcript:\n{transcript}\n\n"
        f"Title hint (optional): {title_hint}\n\n"
        "Generate title (short), summary (short), key points (bullets), and tasks with due dates if present."
    )

    data = await client.chat_json(system=SYSTEM_PROMPT, user=user_prompt)

    title = data.get("title") or title_hint or "Untitled"
    if not isinstance(title, str):
        title = title_hint or "Untitled"

    summary = data.get("summary")
    if not isinstance(summary, str):
        summary = ""

    key_points_raw = data.get("key_points")
    key_points: List[str] = []
    if isinstance(key_points_raw, list):
        key_points = [str(x) for x in key_points_raw if str(x).strip()]

    tasks_raw = data.get("tasks")
    tasks: List[ExtractedTask] = []
    if isinstance(tasks_raw, list):
        for t in tasks_raw:
            if not isinstance(t, dict):
                continue
            text = t.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            due_date = _parse_due_date(t.get("due_date"))
            priority = t.get("priority")
            if not isinstance(priority, int):
                priority = 0
            tasks.append(ExtractedTask(text=text.strip(), due_date=due_date, priority=priority))

    return ExtractedNote(
        title=title.strip()[:200],
        summary=summary.strip(),
        key_points=key_points[:50],
        tasks=tasks[:50],
    )


def _chunk_text(text: str, *, max_chars: int = 1800) -> List[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    if len(cleaned) <= max_chars:
        return [cleaned]

    # Prefer sentence boundaries.
    sentences = re.split(r"(?<=[\.!?])\s+", cleaned)
    chunks: List[str] = []
    current = ""

    for s in sentences:
        s = s.strip()
        if not s:
            continue

        if not current:
            current = s
            continue

        if len(current) + 1 + len(s) <= max_chars:
            current = f"{current} {s}"
        else:
            chunks.append(current)
            current = s

    if current:
        chunks.append(current)

    # Fallback: if a single sentence is huge, hard-split.
    final: List[str] = []
    for c in chunks:
        if len(c) <= max_chars:
            final.append(c)
            continue
        for i in range(0, len(c), max_chars):
            final.append(c[i : i + max_chars])
    return final


def _dedupe_keep_order(items: List[str], *, max_items: int) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        key = it.strip()
        if not key:
            continue
        if key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
        if len(out) >= max_items:
            break
    return out


async def extract_note_segmented(
    *,
    client: SiliconFlowClient,
    transcript: str,
    title_hint: str = "",
    max_chunk_chars: int = 1800,
) -> ExtractedNote:
    """Extract annotations by splitting the transcript into chunks and merging results.

    Intended for the UX of "user records audio -> presses stop".
    """

    chunks = _chunk_text(transcript, max_chars=max_chunk_chars)
    if not chunks:
        return ExtractedNote(title=title_hint or "Untitled", summary="", key_points=[], tasks=[])

    # Run per-chunk extraction in parallel for speed.
    tasks = [
        extract_note_from_text(client=client, transcript=chunk, title_hint=title_hint)
        for chunk in chunks
    ]
    parts = await asyncio.gather(*tasks)

    merged_title = title_hint.strip() if title_hint.strip() else (parts[0].title if parts else "Untitled")
    merged_summary = "\n".join([p.summary for p in parts if p.summary.strip()]).strip()

    merged_key_points: List[str] = []
    for p in parts:
        merged_key_points.extend(p.key_points)
    merged_key_points = _dedupe_keep_order(merged_key_points, max_items=60)

    merged_tasks: List[ExtractedTask] = []
    for p in parts:
        merged_tasks.extend(p.tasks)
    merged_tasks = merged_tasks[:80]

    return ExtractedNote(
        title=merged_title[:200],
        summary=merged_summary,
        key_points=merged_key_points,
        tasks=merged_tasks,
    )
