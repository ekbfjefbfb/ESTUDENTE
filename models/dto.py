"""
DTOs (Data Transfer Objects) — Objetos ligeros para transportar datos entre capas.

Elimina los hacks type('User', (), {...})() que se usaban en auth_service.py.
Estos dataclasses son inmutables, tipados y fáciles de serializar.
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass(frozen=True)
class UserDTO:
    """
    Representación ligera de un usuario para transporte entre capas.
    
    No depende de SQLAlchemy — se puede usar en services, utils, routers
    sin importar el modelo ORM.
    """
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    is_active: bool = True
    plan_name: Optional[str] = None
    profile_picture_url: Optional[str] = None
    oauth_provider: Optional[str] = None
    created_at: Optional[datetime] = None

    @property
    def user_id(self) -> str:
        """Alias para compatibilidad con código que usa user['user_id']."""
        return self.id

    def to_dict(self) -> Dict[str, Any]:
        """Convierte a dict para respuestas JSON."""
        data = asdict(self)
        if data.get("created_at"):
            data["created_at"] = data["created_at"].isoformat()
        return data

    @classmethod
    def from_db_row(cls, row) -> "UserDTO":
        """
        Crea UserDTO desde un resultado de query SQL (Row o dict).
        
        Uso:
            result = await session.execute(text("SELECT ..."))
            row = result.first()
            user = UserDTO.from_db_row(row)
        """
        if hasattr(row, "_mapping"):
            # SQLAlchemy Row
            data = dict(row._mapping)
        elif isinstance(row, dict):
            data = row
        else:
            # Asume que es un objeto con atributos
            data = {
                "id": getattr(row, "id", ""),
                "username": getattr(row, "username", ""),
                "email": getattr(row, "email", None),
                "full_name": getattr(row, "full_name", None),
                "is_active": getattr(row, "is_active", True),
                "profile_picture_url": getattr(row, "profile_picture_url", None),
                "oauth_provider": getattr(row, "oauth_provider", None),
            }
        
        return cls(
            id=str(data.get("id", "")),
            username=str(data.get("username", "")),
            email=data.get("email"),
            full_name=data.get("full_name"),
            is_active=bool(data.get("is_active", True)),
            profile_picture_url=data.get("profile_picture_url"),
            oauth_provider=data.get("oauth_provider"),
            created_at=data.get("created_at"),
        )


@dataclass(frozen=True)
class TokenPair:
    """Par de tokens JWT (access + refresh)."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600  # segundos

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuthResult:
    """Resultado de una operación de autenticación."""
    success: bool
    user: Optional[UserDTO] = None
    tokens: Optional[TokenPair] = None
    error: Optional[str] = None
    is_new_user: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"success": self.success}
        if self.user:
            data["user"] = self.user.to_dict()
        if self.tokens:
            data["tokens"] = self.tokens.to_dict()
        if self.error:
            data["error"] = self.error
        if self.is_new_user:
            data["is_new_user"] = True
        return data
