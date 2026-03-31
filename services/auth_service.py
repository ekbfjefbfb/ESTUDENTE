"""
Auth Service - Servicio de autenticación empresarial
Versión: Production v3.0 - Simplificada para resolución de problemas
"""

import asyncio
import logging
import re
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager

import json_log_formatter
from utils.safe_metrics import Counter, Histogram  # Métricas seguras
from passlib.context import CryptContext

from database.db_enterprise import get_primary_session as get_db_session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, text
from sqlalchemy.exc import IntegrityError

from models.models import User
from utils.auth import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from services.redis_service import init_redis, redis
from config import GOOGLE_CLIENT_ID, APPLE_CLIENT_ID

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("auth_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)

# =============================================
# MÉTRICAS PROMETHEUS (Seguras)
# =============================================
AUTH_REQUESTS = Counter(
    "auth_requests_total",
    "Total authentication requests",
    ["method", "status"]
)

AUTH_PROCESSING_TIME = Histogram(
    "auth_processing_seconds",
    "Authentication processing time"
)

pwd_context = CryptContext(schemes=["bcrypt", "pbkdf2_sha256"], deprecated="auto")

class AuthService:
    """Servicio de autenticación empresarial con OAuth múltiple"""

    def __init__(self):
        self.redis = None
        self.session_timeout = 3600  # 1 hora

    async def _hash_password(self, password: str) -> str:
        """Hash password - ejecutado en thread separado para no bloquear event loop"""
        pwd = str(password or "")
        
        def _do_hash():
            try:
                if len(pwd.encode("utf-8")) > 72:
                    return pwd_context.hash(pwd, scheme="pbkdf2_sha256")
            except Exception:
                return pwd_context.hash(pwd, scheme="pbkdf2_sha256")

            try:
                return pwd_context.hash(pwd, scheme="bcrypt")
            except Exception:
                return pwd_context.hash(pwd, scheme="pbkdf2_sha256")
        
        return await asyncio.to_thread(_do_hash)

    async def _verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify password - ejecutado en thread separado para no bloquear event loop"""
        def _do_verify():
            try:
                return pwd_context.verify(plain_password, hashed_password)
            except Exception:
                return False
        
        return await asyncio.to_thread(_do_verify)

    async def _generate_unique_username(self, session: AsyncSession, email: str) -> str:
        base = (email.split("@")[0] if email and "@" in email else "user").strip().lower()
        base = re.sub(r"[^a-z0-9_\-]", "_", base)[:30] or "user"

        candidate = base
        for _ in range(8):
            try:
                result = await session.execute(
                    select(User.id).where(User.username == candidate)
                )
                if result.scalar_one_or_none() is None:
                    return candidate
            except Exception:
                # Si la tabla no existe, generar username único
                return f"{base}_{uuid.uuid4().hex[:6]}"[:50]

        # Si no se pudo verificar, generar username con UUID único
        return f"user_{uuid.uuid4().hex[:12]}"[:50]

    async def register_email_password_v2(self, email: str, password: str, full_name: Optional[str] = None, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """Registro con email/password - usa sesión inyectada o crea una"""
        start_time = time.time()
        own_session = session is None
        try:
            AUTH_REQUESTS.labels(method="email_register", status="started").inc()

            if own_session:
                session = await get_db_session()
            
            async with session:
                email = (email or "").strip().lower()
                if not email:
                    raise Exception("Email inválido")
                if not password or len(str(password)) < 8:
                    raise Exception("Password inválido")

                # Verificar con SQLAlchemy ORM
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                if user is not None:
                    raise Exception("El email ya está registrado")

                username = await self._generate_unique_username(session, email=email)

                hashed_password = await self._hash_password(str(password))
                
                # Crear nuevo usuario con ORM
                user_id = str(uuid.uuid4())
                try:
                    new_user = User(
                        id=user_id,
                        username=username,
                        email=email,
                        hashed_password=hashed_password,
                        is_active=True
                    )
                    session.add(new_user)
                except Exception as e:
                    logger.error(f"Error creando usuario ORM: {e}")
                    raise
                await session.commit()

            access_token = await create_access_token({"sub": user_id})
            refresh_token = await create_refresh_token({"sub": user_id})

            processing_time = time.time() - start_time
            AUTH_PROCESSING_TIME.observe(processing_time)
            AUTH_REQUESTS.labels(method="email_register", status="success").inc()

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {
                    "id": user_id,
                    "email": email,
                    "name": full_name or username,
                },
            }
        except Exception as e:
            processing_time = time.time() - start_time
            AUTH_REQUESTS.labels(method="email_register", status="failed").inc()
            logger.error({"event": "email_register_failed", "error": str(e), "processing_time": processing_time})
            raise

    async def login_email_password(self, email: str, password: str, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """Login con email/password - usa sesión inyectada o crea una"""
        start_time = time.time()
        own_session = session is None
        try:
            AUTH_REQUESTS.labels(method="email_login", status="started").inc()

            if own_session:
                session = await get_db_session()
            
            async with session:
                email = (email or "").strip().lower()
                if not email:
                    raise Exception("Credenciales inválidas")
                if not password:
                    raise Exception("Credenciales inválidas")

                # Verificar con SQLAlchemy ORM
                result = await session.execute(
                    select(User).where(User.email == email)
                )
                user = result.scalar_one_or_none()
                
                if user is None:
                    raise Exception("Credenciales inválidas")
                
                user_id = user.id
                user_email = user.email
                username = user.username
                is_active = user.is_active
                hashed_password = user.hashed_password
                
                if not is_active:
                    raise Exception("Credenciales inválidas")

                if not hashed_password:
                    raise Exception("user_has_no_password")

                if not await self._verify_password(str(password), str(hashed_password)):
                    raise Exception("Credenciales inválidas")

            access_token = await create_access_token({"sub": str(user_id)})
            refresh_token = await create_refresh_token({"sub": str(user_id)})

            processing_time = time.time() - start_time
            AUTH_PROCESSING_TIME.observe(processing_time)
            AUTH_REQUESTS.labels(method="email_login", status="success").inc()

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {
                    "id": user_id,
                    "email": user_email,
                    "name": username,
                },
            }
        except Exception as e:
            processing_time = time.time() - start_time
            AUTH_REQUESTS.labels(method="email_login", status="failed").inc()
            logger.error({"event": "email_login_failed", "error": str(e), "processing_time": processing_time})
            raise

    async def authenticate_google_user(self, google_token: str) -> Dict[str, Any]:
        """Autentica usuario validando criptográficamente el token de Google"""
        start_time = time.time()
        
        try:
            AUTH_REQUESTS.labels(method="google", status="started").inc()
            
            import httpx
            
            # 1. Validar el token directamente de forma segura con Google
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"https://oauth2.googleapis.com/tokeninfo?id_token={google_token}")
                if resp.status_code != 200:
                    raise Exception(f"Token de Google inválido o expirado: {resp.text}")
                
                payload = resp.json()
            
            # 2. Verificar Audience contra el backend
            from config import GOOGLE_CLIENT_ID
            if GOOGLE_CLIENT_ID and payload.get("aud") != GOOGLE_CLIENT_ID:
                raise Exception(f"Audience (aud) no coincide con GOOGLE_CLIENT_ID")
            
            email = payload.get("email")
            if not email:
                raise Exception("El token no proporcionó un email válido")
            
            user_data = {
                "email": email,
                "name": payload.get("name") or payload.get("given_name") or email.split("@")[0],
                "google_id": payload.get("sub")
            }
            
            # Crear o actualizar usuario
            session = await get_db_session()
            async with session:
                user = await self._get_or_create_user(session, user_data)
                
                # Crear tokens
                from utils.auth import create_access_token, create_refresh_token
                access_token = await create_access_token({"sub": str(user.id)})
                refresh_token = await create_refresh_token({"sub": str(user.id)})
                
                result = {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.full_name
                    }
                }
            
            processing_time = time.time() - start_time
            AUTH_PROCESSING_TIME.observe(processing_time)
            AUTH_REQUESTS.labels(method="google", status="success").inc()
            
            logger.info({
                "event": "google_auth_success",
                "user_id": user.id,
                "processing_time": processing_time
            })
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            AUTH_REQUESTS.labels(method="google", status="failed").inc()
            
            logger.error({
                "event": "google_auth_failed",
                "error": str(e),
                "processing_time": processing_time
            })
            
            raise Exception(f"Error en autenticación con Google: {str(e)}")

    async def authenticate_apple_user(self, apple_token: str) -> Dict[str, Any]:
        """Autentica usuario validando criptográficamente la firma RS256 de Apple"""
        start_time = time.time()
        
        try:
            AUTH_REQUESTS.labels(method="apple", status="started").inc()
            
            import httpx
            from jose import jwt
            from config import APPLE_CLIENT_ID
            
            # 1. Traer llaves públicas (JWKs) de Apple
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get("https://appleid.apple.com/auth/keys")
                if resp.status_code != 200:
                    raise Exception("No se pudieron obtener las llaves de seguridad de Apple")
                apple_keys = resp.json().get("keys", [])
            
            # 2. Encontrar qué llave firmó el token
            unverified_header = jwt.get_unverified_header(apple_token)
            kid = unverified_header.get("kid")
            if not kid:
                raise Exception("El token no tiene un identificador de llave ('kid') válido")
            
            rsa_key = next((key for key in apple_keys if key.get("kid") == kid), None)
            if not rsa_key:
                raise Exception("No se encontró una llave pública coincidente en Apple para la firma del token")
            
            # 3. Validar matemáticamente el payload y el vencimiento
            payload = jwt.decode(
                apple_token,
                rsa_key,
                algorithms=["RS256"],
                audience=APPLE_CLIENT_ID,        # Valida que sea para nuestro bundle id
                issuer="https://appleid.apple.com" # Exige que Apple lo haya emitido
            )
            
            email = payload.get("email")
            if not email:
                raise Exception("El token de Apple no proporcionó un email")
            
            user_data = {
                "email": email,
                "name": "Apple User", # Las identidades ocultas de Apple no mandan name en el JWT (sólo en callback de OAuth)
                "apple_id": payload.get("sub")
            }
            
            session = await get_db_session()
            async with session:
                user = await self._get_or_create_user(session, user_data)
                
                from utils.auth import create_access_token, create_refresh_token
                access_token = await create_access_token({"sub": str(user.id)})
                refresh_token = await create_refresh_token({"sub": str(user.id)})
                
                result = {
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "token_type": "bearer",
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.full_name
                    }
                }
            
            processing_time = time.time() - start_time
            AUTH_PROCESSING_TIME.observe(processing_time)
            AUTH_REQUESTS.labels(method="apple", status="success").inc()
            
            logger.info({
                "event": "apple_auth_success",
                "user_id": user.id,
                "processing_time": processing_time
            })
            
            return result
            
        except Exception as e:
            processing_time = time.time() - start_time
            AUTH_REQUESTS.labels(method="apple", status="failed").inc()
            
            logger.error({
                "event": "apple_auth_failed",
                "error": str(e),
                "processing_time": processing_time
            })
            
            raise Exception(f"Error en autenticación con Apple: {str(e)}")

    async def _get_or_create_user(self, session: AsyncSession, user_data: Dict[str, Any]) -> User:
        """Obtiene o crea un usuario en la base de datos"""
        try:
            email = user_data.get("email")
            result = await session.execute(
                select(User).where(User.email == email)
            )
            user = result.scalar_one_or_none()

            if not user:
                # Crear nuevo usuario con ORM
                user_id = str(uuid.uuid4())
                username = email.split("@")[0][:30] if email and "@" in email else f"user_{uuid.uuid4().hex[:8]}"
                
                # Verificar si username existe
                result2 = await session.execute(
                    select(User.id).where(User.username == username)
                )
                if result2.scalar_one_or_none():
                    username = f"{username}_{uuid.uuid4().hex[:6]}"
                
                user = User(
                    id=user_id,
                    username=username,
                    email=email,
                    is_active=True
                )
                session.add(user)
                await session.commit()
                
                logger.info({
                    "event": "user_created",
                    "user_id": user_id,
                    "email": email
                })
            else:
                # Actualizar usuario existente con ORM
                from sqlalchemy.sql import func
                user.last_activity = func.now()
                session.add(user)
                await session.commit()
                
                logger.info({
                    "event": "user_updated",
                    "user_id": user.id,
                    "email": user.email
                })
            
            return user
        except Exception as e:
            logger.error(f"❌ Error en _get_or_create_user: {e}")
            await session.rollback()
            raise

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Renueva el access token usando el refresh token"""
        try:
            # Decodificar refresh token (async)
            payload = await decode_refresh_token(refresh_token)
            user_id = payload.get("sub")

            if not user_id:
                raise Exception("Token de refresh inválido")

            # Verificar que el usuario existe
            session = await get_db_session()
            async with session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()

                if not user or not user.is_active:
                    raise Exception("Usuario no encontrado o inactivo")

            # Crear nuevo access token (async) - consistente con utils/auth
            new_access_token = await create_access_token({"sub": str(user_id)})

            logger.info({
                "event": "token_refreshed",
                "user_id": user_id
            })

            return {
                "access_token": new_access_token,
                "token_type": "bearer",
                "expires_in": 3600
            }

        except Exception as e:
            logger.error({
                "event": "refresh_token_failed",
                "error": str(e)
            })
            raise Exception(f"Error renovando token: {str(e)}")

    async def logout_user(self, user_id: str) -> bool:
        """Cierra sesión del usuario"""
        try:
            # Invalidar sesiones en Redis si está disponible
            if self.redis:
                await self.redis.delete(f"user_session:{user_id}")
            
            logger.info({
                "event": "user_logout",
                "user_id": user_id
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "logout_failed",
                "user_id": user_id,
                "error": str(e)
            })
            return False

    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene el perfil del usuario"""
        try:
            session = await get_db_session()
            async with session:
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    return None
                
                return {
                    "id": user.id,
                    "email": user.email,
                    "username": user.username,
                    "is_active": user.is_active
                }
                
        except Exception as e:
            logger.error({
                "event": "get_profile_failed",
                "user_id": user_id,
                "error": str(e)
            })
            return None

# Instancia global del servicio
auth_service = AuthService()

# =============================================
# FUNCIONES ADICIONALES PARA COMPATIBILIDAD
# =============================================
async def oauth_login_or_register(db_session, provider: str, id_token: str, name: str = None) -> Dict[str, Any]:
    """Función de compatibilidad para login/registro OAuth"""
    try:
        if provider == "google":
            return await auth_service.authenticate_google_user(id_token)
        elif provider == "apple":
            return await auth_service.authenticate_apple_user(id_token)
        else:
            raise Exception(f"Proveedor OAuth no soportado: {provider}")
            
    except Exception as e:
        logger.error({
            "event": "oauth_login_register_failed",
            "provider": provider,
            "error": str(e)
        })
        raise

async def refresh_access_token_service(refresh_token: str) -> Dict[str, Any]:
    """Función de compatibilidad para renovar token"""
    return await auth_service.refresh_access_token(refresh_token)

async def register_email_password_service(email: str, password: str, full_name: Optional[str] = None, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Función de compatibilidad para registrar usuario con email/password"""
    return await auth_service.register_email_password_v2(email=email, password=password, full_name=full_name, session=session)

async def login_email_password_service(email: str, password: str, session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Función de compatibilidad para login con email/password"""
    return await auth_service.login_email_password(email=email, password=password, session=session)

# =============================================
# FUNCIONES DE INICIALIZACIÓN
# =============================================
async def init_auth_service():
    """Inicializa el servicio de autenticación"""
    try:
        # Inicializar Redis si está disponible
        auth_service.redis = await init_redis()
        
        logger.info({
            "event": "auth_service_initialized",
            "redis_available": auth_service.redis is not None
        })
        
    except Exception as e:
        logger.warning({
            "event": "auth_service_init_partial",
            "error": str(e),
            "message": "Servicio funcionará sin algunas características"
        })