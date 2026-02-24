"""
Utilidades de Autenticación Enterprise - Mi Backend Super IA
"""
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from jose import JWTError, jwt
import redis.asyncio as redis

# Usar get_async_db desde database.db_enterprise
# Nota: Importar de forma lazy dentro de las funciones para evitar circular imports
from models.models import User
from config import (
    JWT_SECRET_KEY, 
    JWT_ALGORITHM, 
    JWT_EXPIRATION_MINUTES, 
    JWT_REFRESH_EXPIRATION_DAYS,
    REDIS_URL
)

# Import lazy para evitar circular dependency
def get_db_session():
    """Import lazy de get_primary_session para evitar circular imports"""
    from database.db_enterprise import get_primary_session
    return get_primary_session

logger = logging.getLogger("auth_utils")
security = HTTPBearer(auto_error=False)

# Redis para blacklist de tokens
redis_client = None

async def get_redis_client():
    """
    Obtiene cliente Redis para manejo de tokens
    """
    global redis_client
    if redis_client is None:
        try:
            redis_client = redis.from_url(REDIS_URL)
            await redis_client.ping()
            logger.info("✅ Redis conectado para auth")
        except Exception as e:
            logger.warning(f"⚠️ Redis no disponible para auth: {e}")
            redis_client = None
    return redis_client

async def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Crea token de acceso JWT
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRATION_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Crea token de refresh JWT
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=JWT_REFRESH_EXPIRATION_DAYS)
    
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

async def verify_token(token: str) -> Dict[str, Any]:
    """
    Verifica y decodifica token JWT
    """
    try:
        # Verificar si el token está en blacklist
        redis_conn = await get_redis_client()
        if redis_conn:
            is_blacklisted = await redis_conn.get(f"blacklist:{token}")
            if is_blacklisted:
                raise JWTError("Token revocado")
        
        # Decodificar token
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        
        # Verificar tipo de token
        token_type = payload.get("type")
        if not token_type:
            raise JWTError("Tipo de token no especificado")
        
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def blacklist_token(token: str, expires_in: int = None):
    """
    Añade token a blacklist
    """
    try:
        redis_conn = await get_redis_client()
        if redis_conn:
            if expires_in is None:
                expires_in = JWT_EXPIRATION_MINUTES * 60  # en segundos
            
            await redis_conn.setex(
                f"blacklist:{token}", 
                expires_in, 
                "revoked"
            )
            logger.info("✅ Token añadido a blacklist")
        else:
            logger.warning("⚠️ No se pudo blacklist token - Redis no disponible")
    except Exception as e:
        logger.error(f"❌ Error blacklisting token: {e}")

# Wrapper para evitar circular import
async def _get_db_dependency():
    """Dependency lazy para evitar circular import"""
    from database.db_enterprise import get_primary_session
    async for session in get_primary_session():
        yield session

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(_get_db_dependency)
) -> User:
    """
    Obtiene el usuario actual desde el token JWT
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acceso requerido",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # Verificar token
        payload = await verify_token(credentials.credentials)
        
        # Verificar que es token de acceso
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tipo de token inválido"
            )
        
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido - usuario no especificado"
            )
        
        # Buscar usuario en DB
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no encontrado"
            )
        
        # Verificar que el usuario esté activo
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario desactivado"
            )
        
        # Actualizar última actividad
        try:
            await db.execute(
                update(User)
                .where(User.id == user_id)
                .values(last_activity=datetime.utcnow())
            )
            await db.commit()
        except Exception as e:
            logger.warning(f"No se pudo actualizar última actividad: {e}")
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error obteniendo usuario: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error de autenticación interno"
        )

async def get_current_user_id(
    current_user: User = Depends(get_current_user)
) -> str:
    """
    Obtiene solo el ID del usuario actual
    """
    return current_user.id

async def get_current_user_optional(
    authorization: Optional[str] = Header(None)
) -> Optional[User]:
    """
    Obtiene el usuario actual de forma opcional (sin requerir autenticación)
    Retorna None si no hay token o el token es inválido
    """
    if not authorization:
        return None
    
    try:
        scheme, token = authorization.split()
        if scheme.lower() != "bearer":
            return None
        
        payload = await verify_token(token)
        user_id = payload.get("sub")
        
        if not user_id:
            return None
        
        # Lazy load de la sesión DB
        db = _get_db_dependency()
        session = await anext(db)
        
        try:
            from models.models import User
            result = await session.execute(
                select(User).where(User.id == int(user_id))
            )
            user = result.scalar_one_or_none()
            return user
        finally:
            await session.close()
            
    except Exception as e:
        logger.debug(f"Token opcional inválido: {e}")
        return None

async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Obtiene usuario actual verificando que esté activo
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    return current_user

async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Obtiene usuario actual verificando que sea admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permisos de administrador requeridos"
        )
    return current_user

async def get_current_premium_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Obtiene usuario actual verificando que sea premium
    """
    if not current_user.is_premium_user():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Suscripción premium requerida"
        )
    return current_user

async def refresh_access_token(refresh_token: str, db: AsyncSession) -> Dict[str, str]:
    """
    Refresca token de acceso usando refresh token
    """
    try:
        # Verificar refresh token
        payload = await verify_token(refresh_token)
        
        # Verificar que es refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de refresh inválido"
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de refresh inválido"
            )
        
        # Verificar que el usuario existe y está activo
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuario no válido"
            )
        
        # Crear nuevo access token
        access_token = await create_access_token(data={"sub": user_id})
        
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": JWT_EXPIRATION_MINUTES * 60
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refrescando token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error refrescando token"
        )

async def logout_user(token: str):
    """
    Cierra sesión del usuario añadiendo token a blacklist
    """
    try:
        # Decodificar token para obtener tiempo de expiración
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM], options={"verify_exp": False})
        
        # Calcular tiempo hasta expiración
        exp = payload.get("exp")
        if exp:
            expires_in = exp - datetime.utcnow().timestamp()
            if expires_in > 0:
                await blacklist_token(token, int(expires_in))
        
        logger.info("✅ Usuario deslogueado exitosamente")
        
    except Exception as e:
        logger.error(f"Error en logout: {e}")
        # No lanzar excepción para que logout siempre funcione

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verifica contraseña contra hash
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """
    Genera hash de contraseña
    """
    from passlib.context import CryptContext
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return pwd_context.hash(password)

# Rate limiting por usuario
user_request_counts = {}

async def check_user_rate_limit(user_id: str, max_requests: int = 100, window_minutes: int = 60) -> bool:
    """
    Verifica rate limit por usuario
    """
    try:
        redis_conn = await get_redis_client()
        if not redis_conn:
            return True  # Permitir si Redis no está disponible
        
        key = f"rate_limit:user:{user_id}"
        current_count = await redis_conn.get(key)
        
        if current_count is None:
            await redis_conn.setex(key, window_minutes * 60, 1)
            return True
        
        if int(current_count) >= max_requests:
            return False
        
        await redis_conn.incr(key)
        return True
        
    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        return True  # Permitir en caso de error

async def decode_refresh_token(refresh_token: str) -> Dict[str, Any]:
    """
    Decodifica y valida un refresh token
    """
    try:
        # Verificar token
        payload = await verify_token(refresh_token)
        
        # Verificar que es refresh token
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de refresh inválido"
            )
        
        return payload
        
    except Exception as e:
        logger.error(f"Error decodificando refresh token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de refresh inválido"
        )

# Alias para compatibilidad
decode_access_token = verify_token

# Export de funciones principales
__all__ = [
    "get_current_user",
    "get_current_user_id", 
    "get_current_active_user",
    "get_current_admin_user",
    "get_current_premium_user",
    "create_access_token",
    "create_refresh_token",
    "verify_token",
    "decode_access_token",  # Alias de verify_token
    "refresh_access_token",
    "decode_refresh_token",
    "logout_user",
    "blacklist_token",
    "verify_password",
    "get_password_hash",
    "check_user_rate_limit"
]
