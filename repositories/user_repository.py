"""
User Repository — Fuente única de verdad para acceso a datos de usuario.

Centraliza las queries SQL que estaban duplicadas en:
- auth_service.py (5 veces)
- rate_limit_middleware.py
- timeout_middleware.py  
- groq_ai_service.py
- utils/auth.py
- prevalidation_middleware.py

Uso:
    from repositories.user_repository import user_repo
    
    user = await user_repo.get_by_id("user-123")
    user = await user_repo.get_by_email("user@example.com")
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from sqlalchemy import text

from models.dto import UserDTO

logger = logging.getLogger("user_repository")


# Queries SQL reutilizables
_FULL_USER_SELECT = """
    SELECT id, username, email, full_name,
           is_active,
           profile_picture_url, oauth_provider, hashed_password,
           created_at
    FROM users
"""


class UserRepository:
    """Acceso centralizado a datos de usuario."""

    async def _get_session(self):
        """Obtiene sesión de la DB enterprise."""
        from database.db_enterprise import get_primary_session
        return await get_primary_session()

    async def get_by_id(self, user_id: str) -> Optional[UserDTO]:
        """
        Busca un usuario por ID.
        
        Returns:
            UserDTO o None si no existe
        """
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text(f"{_FULL_USER_SELECT} WHERE id = :uid"),
                    {"uid": user_id}
                )
                row = result.first()
                if row:
                    return UserDTO.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Error fetching user by id={user_id}: {e}")
            return None

    async def get_by_email(self, email: str) -> Optional[UserDTO]:
        """Busca un usuario por email."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text(f"{_FULL_USER_SELECT} WHERE LOWER(email) = LOWER(:email)"),
                    {"email": email}
                )
                row = result.first()
                if row:
                    return UserDTO.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Error fetching user by email: {e}")
            return None

    async def get_by_username(self, username: str) -> Optional[UserDTO]:
        """Busca un usuario por username."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text(f"{_FULL_USER_SELECT} WHERE LOWER(username) = LOWER(:username)"),
                    {"username": username}
                )
                row = result.first()
                if row:
                    return UserDTO.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Error fetching user by username: {e}")
            return None



    async def get_hashed_password(self, user_id: str) -> Optional[str]:
        """Obtiene SOLO el hash de password (no se incluye en UserDTO por seguridad)."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text("SELECT hashed_password FROM users WHERE id = :uid"),
                    {"uid": user_id}
                )
                row = result.first()
                return row.hashed_password if row else None
        except Exception as e:
            logger.error(f"Error fetching password hash: {e}")
            return None

    async def exists(self, user_id: str) -> bool:
        """Verifica si un usuario existe (query ligera)."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text("SELECT 1 FROM users WHERE id = :uid LIMIT 1"),
                    {"uid": user_id}
                )
                return result.first() is not None
        except Exception as e:
            logger.error(f"Error checking user existence: {e}")
            return False

    async def email_exists(self, email: str) -> bool:
        """Verifica si un email ya está registrado."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text("SELECT 1 FROM users WHERE LOWER(email) = LOWER(:email) LIMIT 1"),
                    {"email": email}
                )
                return result.first() is not None
        except Exception as e:
            logger.error(f"Error checking email existence: {e}")
            return False

    async def username_exists(self, username: str) -> bool:
        """Verifica si un username ya está registrado."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text("SELECT 1 FROM users WHERE LOWER(username) = LOWER(:username) LIMIT 1"),
                    {"username": username}
                )
                return result.first() is not None
        except Exception as e:
            logger.error(f"Error checking username existence: {e}")
            return False

    async def update_last_activity(self, user_id: str) -> None:
        """Actualiza la última actividad del usuario."""
        try:
            session = await self._get_session()
            async with session:
                await session.execute(
                    text("UPDATE users SET last_activity = :now WHERE id = :uid"),
                    {"uid": user_id, "now": datetime.utcnow()}
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"Error updating last_activity for {user_id}: {e}")

    async def increment_request_count(self, user_id: str) -> None:
        """Incrementa el contador mensual de requests."""
        try:
            session = await self._get_session()
            async with session:
                await session.execute(
                    text("""
                        UPDATE users 
                        SET requests_used_this_month = requests_used_this_month + 1,
                            last_activity = :now
                        WHERE id = :uid
                    """),
                    {"uid": user_id, "now": datetime.utcnow()}
                )
                await session.commit()
        except Exception as e:
            logger.warning(f"Error incrementing request count for {user_id}: {e}")

    async def get_user_plan_name(self, user_id: str) -> str:
        """Obtiene el nombre del plan del usuario (para rate limiting, timeouts, etc)."""
        try:
            session = await self._get_session()
            async with session:
                result = await session.execute(
                    text("""
                        SELECT COALESCE(p.name, 'demo') as plan_name
                        FROM users u
                        LEFT JOIN plans p ON u.plan_id = p.id
                        WHERE u.id = :uid
                    """),
                    {"uid": user_id}
                )
                row = result.first()
                return row.plan_name if row else "demo"
        except Exception as e:
            logger.warning(f"Error fetching plan for {user_id}: {e}")
            return "demo"


# Singleton — importar así: from repositories.user_repository import user_repo
user_repo = UserRepository()
