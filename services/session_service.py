import json
import logging
import asyncio
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from aiolimiter import AsyncLimiter
import json_log_formatter

from services.redis_service import get_redis

# ---------------- Config ----------------
SESSION_EXPIRE = 3600  # 1 hora
CLEAN_INTERVAL = 3600  # 1 hora
REDIS_CLEAN_LOCK_KEY = "session_cleanup_lock"
LOCK_EXPIRE = 300  # 5 min
MEMORY_FLUSH_INTERVAL = 300  # 5 min, sincronizar memoria -> Redis

# ---------------- Logging ----------------
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("session_service")
logger.addHandler(handler)
logger.setLevel("INFO")

# ---------------- Memoria y Locks ----------------
memory_sessions: Dict[str, dict] = {}  # caché en memoria
_session_locks: Dict[str, asyncio.Lock] = {}
session_limiters: Dict[str, AsyncLimiter] = {}

# ---------------- Locks y limiters ----------------
def get_session_lock(user_id: int, session_id: str) -> asyncio.Lock:
    key = f"{user_id}:{session_id}"
    if key not in _session_locks:
        _session_locks[key] = asyncio.Lock()
    return _session_locks[key]

def get_session_limiter(user_id: int, session_id: str, max_messages: int = 50, per_seconds: int = 60) -> AsyncLimiter:
    key = f"{user_id}:{session_id}"
    if key not in session_limiters:
        session_limiters[key] = AsyncLimiter(max_messages, per_seconds)
    return session_limiters[key]

# ---------------- Helpers ----------------
def _session_key(user_id: int, session_id: str) -> str:
    return f"user:{user_id}:session:{session_id}"

def _is_expired(session: dict) -> bool:
    return session.get("expire_at") and datetime.fromisoformat(session["expire_at"]) < datetime.utcnow()

# ---------------- Acceso a sesión ----------------
async def _get_session(user_id: int, session_id: str) -> dict:
    key = _session_key(user_id, session_id)
    # Primero buscar en memoria
    session = memory_sessions.get(key)
    if session:
        return session

    # Luego buscar en Redis
    redis = await get_redis()
    if redis:
        data = await redis.get(key)
        if data:
            session = json.loads(data)
            memory_sessions[key] = session  # cache en memoria
            return session

    # Si no existe, crear nueva sesión
    session = {"messages": [], "expire_at": (datetime.utcnow() + timedelta(seconds=SESSION_EXPIRE)).isoformat()}
    memory_sessions[key] = session
    return session

async def _set_session(user_id: int, session_id: str, session: dict):
    key = _session_key(user_id, session_id)
    memory_sessions[key] = session  # siempre actualizar memoria
    redis = await get_redis()
    if redis:
        await redis.set(key, json.dumps(session), ex=SESSION_EXPIRE)

# ---------------- Funciones de sesión ----------------
async def create_session(user_id: int, session_id: str):
    lock = get_session_lock(user_id, session_id)
    async with lock:
        session = {"messages": [], "expire_at": (datetime.utcnow() + timedelta(seconds=SESSION_EXPIRE)).isoformat()}
        await _set_session(user_id, session_id, session)
        logger.info("Sesión creada", extra={"user_id": user_id, "session_id": session_id})

async def get_session_history(user_id: int, session_id: str) -> List[dict]:
    lock = get_session_lock(user_id, session_id)
    async with lock:
        session = await _get_session(user_id, session_id)
        return list(session.get("messages", []))

async def add_message_to_session(user_id: int, session_id: str, role: str, content: str, file_name: Optional[str] = None):
    if role not in {"user", "assistant", "system"} or not content:
        raise ValueError("Role o content inválido")
    lock = get_session_lock(user_id, session_id)
    limiter = get_session_limiter(user_id, session_id)
    async with limiter, lock:
        session = await _get_session(user_id, session_id)
        message = {"role": role, "content": content, "timestamp": datetime.utcnow().isoformat()}
        if file_name:
            message["file_name"] = file_name
        session["messages"].append(message)
        session["expire_at"] = (datetime.utcnow() + timedelta(seconds=SESSION_EXPIRE)).isoformat()
        memory_sessions[_session_key(user_id, session_id)] = session  # actualizar memoria
        logger.info("Mensaje agregado", extra={"user_id": user_id, "session_id": session_id, "total_messages": len(session['messages'])})

async def delete_session(user_id: int, session_id: str):
    lock = get_session_lock(user_id, session_id)
    async with lock:
        key = _session_key(user_id, session_id)
        memory_sessions.pop(key, None)
        redis = await get_redis()
        if redis:
            await redis.delete(key)
        logger.info("Sesión eliminada", extra={"user_id": user_id, "session_id": session_id})

async def refresh_session(user_id: int, session_id: str):
    lock = get_session_lock(user_id, session_id)
    async with lock:
        session = await _get_session(user_id, session_id)
        session["expire_at"] = (datetime.utcnow() + timedelta(seconds=SESSION_EXPIRE)).isoformat()
        memory_sessions[_session_key(user_id, session_id)] = session
        redis = await get_redis()
        if redis:
            await redis.set(_session_key(user_id, session_id), json.dumps(session), ex=SESSION_EXPIRE)

# ---------------- Limpieza periódica ----------------
async def get_all_user_sessions() -> List[dict]:
    out = []
    redis = await get_redis()
    keys = await redis.keys("user:*:session:*") if redis else list(memory_sessions.keys())
    for key in keys:
        parts = key.split(":")
        try:
            uid = int(parts[1])
            sid = parts[3]
        except Exception:
            continue
        session = await _get_session(uid, sid)
        updated_at = datetime.fromisoformat(session.get("expire_at", datetime.utcnow().isoformat()))
        out.append({"user_id": uid, "conversation_id": sid, "updated_at": updated_at})
    return out

async def clean_old_conversations(months_old: int = 3):
    cutoff = datetime.utcnow() - timedelta(days=months_old * 30)
    sessions = await get_all_user_sessions()
    for s in sessions:
        if s["updated_at"] < cutoff:
            await delete_session(s["user_id"], s["conversation_id"])
            logger.info("Sesión antigua eliminada", extra={"user_id": s["user_id"], "session_id": s["conversation_id"]})

# ---------------- Flush de memoria a Redis ----------------
async def flush_memory_to_redis():
    redis = await get_redis()
    if not redis:
        return
    for key, session in memory_sessions.items():
        await redis.set(key, json.dumps(session), ex=SESSION_EXPIRE)
    logger.info("Memoria sincronizada con Redis")

# ---------------- Tareas periódicas ----------------
async def periodic_tasks():
    while True:
        try:
            # Limpieza de sesiones expiradas
            redis = await get_redis()
            lock_acquired = True
            if redis:
                lock_acquired = await redis.set(
                    REDIS_CLEAN_LOCK_KEY,
                    "1",
                    nx=True,
                    ex=LOCK_EXPIRE
                )
            if lock_acquired:
                logger.info({"event": "cleanup_start"})
                await clean_old_conversations()
                logger.info({"event": "cleanup_complete"})
                if redis:
                    await redis.delete(REDIS_CLEAN_LOCK_KEY)

            # Flush de memoria a Redis
            await flush_memory_to_redis()

        except Exception as e:
            logger.error({"event": "periodic_task_error", "error": str(e)}, exc_info=True)

        await asyncio.sleep(CLEAN_INTERVAL)

# Alias para compatibilidad con versiones anteriores
periodic_clean_task = periodic_tasks
