"""
Chat WebSocket Utils - WebSocket utilities for chat
Separado de unified_chat_router.py para reducir responsabilidades
"""
import asyncio
import json
import logging
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from urllib.parse import urlparse

from fastapi import WebSocket, HTTPException
from utils.bounded_dict import BoundedDict

logger = logging.getLogger("chat_ws_utils")

# Rate limiting — BoundedDict evita memory leak con usuarios móviles que reconectan
_WS_AUTH_FAILURE_TRACKER: BoundedDict = BoundedDict(max_size=10000, ttl_seconds=300)
_WS_MAX_AUTH_FAILURES = 10
_WS_AUTH_FAILURE_WINDOW_S = 120
_WS_BACKOFF_MIN_S = 1
_WS_BACKOFF_MAX_S = 60

# Conexiones activas — max 10000 usuarios concurrentes
_USER_WS_CONNECTION_LOCKS: BoundedDict = BoundedDict(max_size=10000, ttl_seconds=3600)
_USER_ACTIVE_WS: BoundedDict = BoundedDict(max_size=10000, ttl_seconds=3600)

# Image content type cache
_image_ct_cache: Dict[str, Dict[str, Any]] = {}
_image_ct_sem = asyncio.Semaphore(int(os.getenv("IMAGE_CONTENT_TYPE_CHECK_CONCURRENCY", "6")))


async def _ws_auth_user_id(websocket) -> str:
    """Authenticate WebSocket connection and return user_id"""
    from utils.auth import verify_token
    token = websocket.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="missing_token")
    payload = await verify_token(token, allow_expired_grace=True)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="invalid_token")
    return str(user_id)


def _ws_now_iso() -> str:
    return datetime.utcnow().isoformat()


def _estimate_duration_ms_from_bytes(audio_len: int) -> int:
    """Heurística: PCM16 mono 16kHz => 32000 bytes/s"""
    return int((audio_len / 32000.0) * 1000)


def _tail_bytes_for_pcm16(*, buf: bytearray, sample_rate: int, tail_window_ms: int) -> bytes:
    bytes_per_second = sample_rate * 2
    tail_len = int((tail_window_ms / 1000.0) * bytes_per_second)
    if tail_len <= 0:
        return bytes(buf)
    if tail_len >= len(buf):
        return bytes(buf)
    return bytes(buf[-tail_len:])


async def _ws_send_json(websocket: WebSocket, payload: Dict[str, Any]) -> None:
    """Send JSON payload to WebSocket with error handling"""
    try:
        from starlette.websockets import WebSocketState
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        timeout_s = float(os.getenv("WS_SEND_TIMEOUT_S", "3"))
        await asyncio.wait_for(
            websocket.send_text(json.dumps(payload, ensure_ascii=False)),
            timeout=timeout_s,
        )
    except Exception as e:
        try:
            from websockets.exceptions import ConnectionClosed
        except Exception:
            ConnectionClosed = None
        if ConnectionClosed is not None and isinstance(e, ConnectionClosed):
            return
        try:
            from starlette.websockets import WebSocketDisconnect
        except Exception:
            WebSocketDisconnect = None
        if WebSocketDisconnect is not None and isinstance(e, WebSocketDisconnect):
            return
        if isinstance(e, asyncio.TimeoutError):
            try:
                await websocket.close(code=1011)
            except Exception:
                pass
            return
        logger.error(f"Error sending WebSocket JSON: {e}")
        raise


def _ws_status_enabled() -> bool:
    raw = os.getenv("WS_STATUS_ENABLED")
    if raw is None:
        return True
    return str(raw).strip() in {"1", "true", "True"}


async def _ws_send_status(websocket: WebSocket, content: str, *, request_id: Optional[str] = None) -> None:
    """Send status message to WebSocket"""
    if not _ws_status_enabled():
        return
    await _ws_send_json(
        websocket,
        {
            "type": "status",
            "content": str(content or "")[:200],
            **({"request_id": str(request_id)} if request_id else {}),
        },
    )


async def _ws_heartbeat(websocket: WebSocket, user_id: str):
    """
    Background task to keep WebSocket connection alive
    Envía ping cada 25s y espera pong del cliente (móviles necesitan esto)
    """
    ping_interval = float(os.getenv("WS_PING_INTERVAL_S", "25"))  # iOS: 30s timeout
    pong_timeout = float(os.getenv("WS_PONG_TIMEOUT_S", "5"))
    
    try:
        while True:
            await asyncio.sleep(ping_interval)
            
            try:
                from starlette.websockets import WebSocketState
                if websocket.client_state != WebSocketState.CONNECTED:
                    logger.debug(f"WS heartbeat: not connected for user_id={user_id}")
                    break
                
                # Enviar ping y esperar pong
                await _ws_send_json(websocket, {"type": "ping", "timestamp": datetime.utcnow().isoformat()})
                
                # El cliente debe responder con {"type": "pong"}
                # El loop principal en chat_ws_handlers.py ya maneja esto en línea 142
                
            except Exception as e:
                logger.debug(f"WS heartbeat failed for user_id={user_id}: {e}")
                break
                
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.warning(f"WS heartbeat error for user_id={user_id}: {e}")


# Rate limiting functions
def _track_ws_auth_failure(user_id: str) -> int:
    """Track auth failure and return failure count in window"""
    now = time.monotonic()
    if user_id not in _WS_AUTH_FAILURE_TRACKER:
        _WS_AUTH_FAILURE_TRACKER[user_id] = []
    _WS_AUTH_FAILURE_TRACKER[user_id] = [
        ts for ts in _WS_AUTH_FAILURE_TRACKER[user_id]
        if (now - ts) < _WS_AUTH_FAILURE_WINDOW_S
    ]
    _WS_AUTH_FAILURE_TRACKER[user_id].append(now)
    return len(_WS_AUTH_FAILURE_TRACKER[user_id])


def _get_ws_backoff_seconds(user_id: str) -> float:
    """Calculate exponential backoff based on recent failures"""
    failure_count = len(_WS_AUTH_FAILURE_TRACKER.get(user_id, []))
    if failure_count == 0:
        return 0
    backoff = _WS_BACKOFF_MIN_S * (2 ** (failure_count - 1))
    return min(backoff, _WS_BACKOFF_MAX_S)


def _clear_ws_auth_failures(user_id: str):
    """Clear failures on successful auth"""
    _WS_AUTH_FAILURE_TRACKER.pop(user_id, None)


def _ws_replace_existing_enabled() -> bool:
    return str(os.getenv("WS_REPLACE_EXISTING", "true") or "").strip().lower() in {"1", "true", "t", "yes"}


# Connection management
def get_user_ws_lock(user_id: str) -> asyncio.Lock:
    """Get or create WebSocket lock for user"""
    if user_id not in _USER_WS_CONNECTION_LOCKS:
        _USER_WS_CONNECTION_LOCKS[user_id] = asyncio.Lock()
    return _USER_WS_CONNECTION_LOCKS[user_id]


def set_active_ws(user_id: str, websocket: WebSocket):
    """Set active WebSocket for user"""
    _USER_ACTIVE_WS[user_id] = websocket


def get_active_ws(user_id: str) -> Optional[WebSocket]:
    """Get active WebSocket for user"""
    return _USER_ACTIVE_WS.get(user_id)


def remove_active_ws(user_id: str, websocket: WebSocket):
    """Remove active WebSocket if it matches"""
    current = _USER_ACTIVE_WS.get(user_id)
    if current is websocket:
        _USER_ACTIVE_WS.pop(user_id, None)


# Image utilities
def _host_label(url: str) -> str:
    try:
        host = (urlparse(url).netloc or "").strip()
        if host.startswith("www."):
            host = host[4:]
        return host or ""
    except Exception:
        return ""


def _is_supported_image_url(url: Optional[str]) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    try:
        p = urlparse(raw)
        if p.scheme not in {"http", "https"}:
            return False
        path = (p.path or "").lower()
        if "." not in path.rsplit("/", 1)[-1]:
            return True
        ext = path.rsplit(".", 1)[-1]
        return ext in {"jpg", "jpeg", "png", "webp", "gif"}
    except Exception:
        return False


def _image_content_type_check_enabled() -> bool:
    raw = os.getenv("IMAGE_CONTENT_TYPE_CHECK_ENABLED")
    if raw is None:
        return True
    return str(raw).strip() in {"1", "true", "True"}


def _image_content_type_check_timeout_s() -> float:
    try:
        return float(os.getenv("IMAGE_CONTENT_TYPE_CHECK_TIMEOUT_S", "1.8"))
    except Exception:
        return 1.8


def _image_content_type_cache_ttl_s() -> int:
    try:
        return int(os.getenv("IMAGE_CONTENT_TYPE_CACHE_TTL_S", "86400"))
    except Exception:
        return 86400


def _image_content_type_cache_max_entries() -> int:
    try:
        return int(os.getenv("IMAGE_CONTENT_TYPE_CACHE_MAX_ENTRIES", "2000"))
    except Exception:
        return 2000


def _prune_image_ct_cache_if_needed() -> None:
    max_entries = _image_content_type_cache_max_entries()
    if max_entries <= 0:
        return
    if len(_image_ct_cache) <= max_entries:
        return
    try:
        items = list(_image_ct_cache.items())
        items.sort(key=lambda kv: float((kv[1] or {}).get("ts") or 0.0))
        to_remove = max(1, len(_image_ct_cache) - max_entries)
        for k, _ in items[:to_remove]:
            _image_ct_cache.pop(k, None)
    except Exception:
        _image_ct_cache.clear()


async def _is_supported_image_by_content_type(url: Optional[str]) -> bool:
    raw = str(url or "").strip()
    if not raw:
        return False
    if not _image_content_type_check_enabled():
        return _is_supported_image_url(raw)
    if not _is_supported_image_url(raw):
        return False

    now = time.monotonic()
    cached = _image_ct_cache.get(raw)
    if isinstance(cached, dict):
        ts = float(cached.get("ts") or 0.0)
        ok = cached.get("ok")
        if ok is not None and (now - ts) <= float(_image_content_type_cache_ttl_s()):
            return bool(ok)

    timeout_s = _image_content_type_check_timeout_s()
    try:
        import httpx
    except Exception:
        ok = True
        _image_ct_cache[raw] = {"ts": now, "ok": ok}
        _prune_image_ct_cache_if_needed()
        return ok

    async with _image_ct_sem:
        try:
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
                resp = await client.head(raw, headers={"Accept": "image/*"})
                if resp.status_code == 405 or resp.status_code == 403 or resp.status_code >= 500:
                    resp = await client.get(raw, headers={"Range": "bytes=0-2047", "Accept": "image/*"})
                ct = str(resp.headers.get("content-type") or "").lower().split(";")[0].strip()
                ok = ct in {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}
                _image_ct_cache[raw] = {"ts": now, "ok": ok, "ct": ct, "status": int(resp.status_code)}
                _prune_image_ct_cache_if_needed()
                return bool(ok)
        except Exception:
            ok = True
            _image_ct_cache[raw] = {"ts": now, "ok": ok}
            _prune_image_ct_cache_if_needed()
            return ok


async def _sanitize_sources_images(sources) -> list:
    if not sources:
        return []
    out = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        img = str(s.get("image") or s.get("image_url") or "").strip()
        if img:
            ok = await _is_supported_image_by_content_type(img)
            if not ok:
                s = dict(s)
                if "image" in s:
                    s["image"] = ""
                if "image_url" in s:
                    s["image_url"] = ""
        out.append(s)
    return out


def _build_rich_response(*, text: str, memory_id: Optional[str], sources: Optional[list]) -> Optional[Any]:
    """Build rich response with gallery from sources"""
    if not sources:
        return None
    
    from routers.chat_schemas import RichResponse, RichGalleryItem
    
    gallery = []
    for s in sources:
        if not isinstance(s, dict):
            continue
        url = str(s.get("url") or "").strip()
        if not url:
            continue
        title = str(s.get("title") or s.get("name") or s.get("snippet") or "").strip() or url
        image_candidate = str(s.get("image") or s.get("image_url") or "").strip() or None
        image_url = image_candidate if _is_supported_image_url(image_candidate) else None
        source_label = str(s.get("source") or "").strip() or None
        if not source_label:
            host = _host_label(url)
            source_label = host or None
        style = str(s.get("style") or "").strip() or None
        gallery.append(
            RichGalleryItem(
                title=title,
                source=source_label,
                url=url,
                image_url=image_url,
                style=style,
            )
        )
    
    if not gallery:
        return None
    
    return RichResponse(
        text=str(text or "").strip(),
        memory_id=str(memory_id) if memory_id else None,
        gallery=gallery,
        suggestions=None,
    )
