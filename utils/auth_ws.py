# utils/auth_ws.py
import jwt
import logging
from fastapi import WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState
from typing import Optional, Dict

from config import SECRET_KEY, ALGORITHM
from services.redis_service import get_redis  # Servicio centralizado de Redis

# ---------------- Logger JSON ----------------
logger = logging.getLogger("auth_ws")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        '{"time": "%(asctime)s", "level": "%(levelname)s", "message": "%(message)s"}'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel("INFO")

# ---------------- Helper ----------------
def extract_token(raw_token: Optional[str]) -> Optional[str]:
    """Normaliza token tipo 'Bearer ...'."""
    if not raw_token:
        return None
    if raw_token.startswith("Bearer "):
        return raw_token[7:]
    return raw_token

# ---------------- WebSocket Auth ----------------
async def authenticate_websocket(websocket: WebSocket) -> Dict:
    """
    Autenticación para WebSocket usando JWT.
    Retorna un dict con info de usuario, ej: {"user_id": "..."}.
    """
    try:
        # Extraer token
        token = extract_token(websocket.query_params.get("token") or websocket.headers.get("Authorization"))
        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise WebSocketDisconnect("Token requerido para WebSocket")

        # Decodificar JWT
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Token sin 'sub'")

        # Verificación de sesión en Redis
        redis = await get_redis()
        if redis:
            session_key = f"ws_session:{user_id}"
            is_blocked = await redis.get(session_key)
            if is_blocked == "blocked":
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                raise WebSocketDisconnect(f"Usuario {user_id} bloqueado")

        # Log de éxito
        client_host = websocket.client.host if websocket.client else "unknown"
        logger.info(
            f"WebSocket autenticado correctamente",
            extra={"user_id": user_id, "client": client_host}
        )

        # Retornar info usuario
        return {"user_id": user_id}

    except WebSocketDisconnect:
        raise  # dejar que FastAPI maneje la desconexión

    except Exception as e:
        # Cerrar WebSocket si aún está conectado
        if websocket.client_state == WebSocketState.CONNECTED:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        client_host = websocket.client.host if websocket.client else "unknown"
        logger.warning(
            f"WebSocket token inválido: {e}",
            extra={"client": client_host}
        )
        raise WebSocketDisconnect("Autenticación fallida")
