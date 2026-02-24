from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from notes_grpc.config import settings
from notes_grpc.extractor import extract_note_segmented
from notes_grpc.siliconflow_client import SiliconFlowClient
from notes_grpc.storage import Storage

def _ensure_proto_generated() -> None:
    """Generate proto stubs locally if they are missing.

    This keeps the repo minimal while remaining runnable after `pip install -r requirements.txt`.
    """

    repo_root = Path(__file__).resolve().parents[1]
    proto_dir = repo_root / "proto"
    proto_file = proto_dir / "notes.proto"
    py_out = proto_dir / "notes_pb2.py"
    grpc_out = proto_dir / "notes_pb2_grpc.py"

    if py_out.exists() and grpc_out.exists():
        return

    if not proto_file.exists():
        raise RuntimeError(f"Missing proto file: {proto_file}")

    import subprocess

    cmd = [
        sys.executable,
        "-m",
        "grpc_tools.protoc",
        f"-I{proto_dir}",
        f"--python_out={proto_dir}",
        f"--grpc_python_out={proto_dir}",
        str(proto_file),
    ]

    res = subprocess.run(cmd, cwd=str(repo_root), capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            "Failed generating protobuf stubs. "
            f"stdout={res.stdout!r} stderr={res.stderr!r}"
        )


_ensure_proto_generated()

# Generated from proto/notes.proto (created via grpc_tools.protoc)
notes_pb2 = importlib.import_module("proto.notes_pb2")
notes_pb2_grpc = importlib.import_module("proto.notes_pb2_grpc")


def _dt_to_ts(dt: datetime) -> Timestamp:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc)
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def _ts_to_dt(ts: Timestamp) -> datetime:
    return ts.ToDatetime().replace(tzinfo=timezone.utc)


class NotesService(notes_pb2_grpc.NotesServiceServicer):
    def __init__(self, *, storage: Storage, sf: SiliconFlowClient):
        self._storage = storage
        self._sf = sf

    async def CreateNoteFromAudio(self, request, context):
        tr = await self._sf.transcribe(
            audio_bytes=request.audio,
            audio_mime=request.audio_mime or "application/octet-stream",
            language=request.language or None,
        )
        return await self._create_note(transcript=tr.text, title_hint=request.title or "")

    async def CreateNoteFromText(self, request, context):
        return await self._create_note(transcript=request.text, title_hint=request.title or "")

    async def _create_note(self, *, transcript: str, title_hint: str):
        extracted = await extract_note_segmented(client=self._sf, transcript=transcript, title_hint=title_hint)

        note_row, task_rows = await self._storage.create_note(
            title=extracted.title,
            transcript=transcript,
            summary=extracted.summary,
            key_points=extracted.key_points,
            tasks=[
                {
                    "text": t.text,
                    "due_date": t.due_date,
                    "done": False,
                    "priority": t.priority,
                }
                for t in extracted.tasks
            ],
        )

        note_msg = await self._note_row_to_proto(note_row.id)
        return notes_pb2.CreateNoteResponse(note=note_msg)

    async def GetNote(self, request, context):
        data = await self._storage.get_note(note_id=request.id)
        if not data:
            await context.abort(grpc.StatusCode.NOT_FOUND, "note_not_found")
        note, tasks = data

        note_msg = notes_pb2.Note(
            id=note.id,
            title=note.title,
            transcript=note.transcript,
            summary=note.summary,
            key_points=note.key_points,
            created_at=_dt_to_ts(note.created_at),
            tasks=[self._task_row_to_proto(t) for t in tasks],
        )
        return notes_pb2.GetNoteResponse(note=note_msg)

    async def ListNotes(self, request, context):
        from_ts: Optional[datetime] = _ts_to_dt(request.from_ts) if request.has_from else None
        to_ts: Optional[datetime] = _ts_to_dt(request.to_ts) if request.has_to else None
        limit = int(request.limit) if request.limit > 0 else 50
        offset = int(request.offset) if request.offset > 0 else 0

        notes = await self._storage.list_notes(from_ts=from_ts, to_ts=to_ts, limit=limit, offset=offset)

        note_msgs = []
        for n in notes:
            # For speed, ListNotes returns notes WITHOUT tasks
            note_msgs.append(
                notes_pb2.Note(
                    id=n.id,
                    title=n.title,
                    transcript="",
                    summary=n.summary,
                    key_points=n.key_points,
                    created_at=_dt_to_ts(n.created_at),
                )
            )

        return notes_pb2.ListNotesResponse(notes=note_msgs)

    async def ListTasks(self, request, context):
        due_before = _ts_to_dt(request.due_before_ts) if request.has_due_before else None
        limit = int(request.limit) if request.limit > 0 else 50
        offset = int(request.offset) if request.offset > 0 else 0

        tasks = await self._storage.list_tasks(
            only_pending=bool(request.only_pending),
            only_with_due_date=bool(request.only_with_due_date),
            due_before=due_before,
            limit=limit,
            offset=offset,
        )

        return notes_pb2.ListTasksResponse(tasks=[self._task_row_to_proto(t) for t in tasks])

    async def UpdateTask(self, request, context):
        done = bool(request.done) if request.has_done else None
        due_date = _ts_to_dt(request.due_date) if request.has_due_date else None
        priority = int(request.priority) if request.has_priority else None

        try:
            t = await self._storage.update_task(task_id=request.id, done=done, due_date=due_date, priority=priority)
        except KeyError:
            await context.abort(grpc.StatusCode.NOT_FOUND, "task_not_found")

        return self._task_row_to_proto(t)

    async def SummarizeRange(self, request, context):
        from_ts: Optional[datetime] = _ts_to_dt(request.from_ts) if request.has_from else None
        to_ts: Optional[datetime] = _ts_to_dt(request.to_ts) if request.has_to else None

        notes = await self._storage.list_notes(from_ts=from_ts, to_ts=to_ts, limit=200, offset=0)
        tasks = await self._storage.list_tasks(
            only_pending=True,
            only_with_due_date=False,
            due_before=None,
            limit=200,
            offset=0,
        )

        # Build a short text and ask LLM for a compact summary
        notes_text = "\n\n".join([f"- {n.title}: {n.summary}" for n in notes])

        system = (
            "You summarize study notes. Return STRICT JSON object only. "
            "Schema: {summary:string, key_points:[string]}"
        )
        user = f"Summarize these notes:\n{notes_text}" if notes_text else "No notes. Return empty summary."
        data = await self._sf.chat_json(system=system, user=user)

        summary = data.get("summary") if isinstance(data.get("summary"), str) else ""
        key_points_raw = data.get("key_points")
        key_points = [str(x) for x in key_points_raw] if isinstance(key_points_raw, list) else []

        return notes_pb2.SummarizeRangeResponse(
            summary=summary,
            key_points=key_points[:50],
            pending_tasks=[self._task_row_to_proto(t) for t in tasks],
        )

    async def _note_row_to_proto(self, note_id: str) -> notes_pb2.Note:
        data = await self._storage.get_note(note_id=note_id)
        if not data:
            return notes_pb2.Note(id=note_id)
        note, tasks = data
        return notes_pb2.Note(
            id=note.id,
            title=note.title,
            transcript=note.transcript,
            summary=note.summary,
            key_points=note.key_points,
            tasks=[self._task_row_to_proto(t) for t in tasks],
            created_at=_dt_to_ts(note.created_at),
        )

    def _task_row_to_proto(self, t) -> notes_pb2.Task:
        if t.due_date is not None:
            due_ts = _dt_to_ts(t.due_date)
            has_due = True
        else:
            due_ts = Timestamp()
            has_due = False

        return notes_pb2.Task(
            id=t.id,
            note_id=t.note_id,
            text=t.text,
            due_date=due_ts,
            has_due_date=has_due,
            done=bool(t.done),
            priority=int(t.priority),
        )


async def serve() -> None:
    storage = Storage(settings.SQLITE_PATH)
    await storage.init()

    sf = SiliconFlowClient()

    server = grpc.aio.server(options=[("grpc.max_receive_message_length", 20 * 1024 * 1024)])
    notes_pb2_grpc.add_NotesServiceServicer_to_server(NotesService(storage=storage, sf=sf), server)

    listen_addr = f"{settings.GRPC_HOST}:{settings.GRPC_PORT}"
    server.add_insecure_port(listen_addr)

    await server.start()
    await server.wait_for_termination()


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
