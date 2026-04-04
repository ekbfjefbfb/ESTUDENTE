"""
Google Auth Service - Autenticación completa con Google OAuth2
Obtiene información del usuario y mantiene acceso permanente
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple
import httpx
import json_log_formatter
from sqlalchemy import func, select, update
from utils.bounded_dict import BoundedDict
from config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, GOOGLE_REDIRECT_URI, OAUTH_ENABLED

try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import Flow
    from googleapiclient.discovery import build
    GOOGLE_WORKSPACE_LIBS_AVAILABLE = True
    GOOGLE_WORKSPACE_IMPORT_ERROR = None
except Exception as exc:
    Credentials = None
    Request = None
    Flow = None
    build = None
    GOOGLE_WORKSPACE_LIBS_AVAILABLE = False
    GOOGLE_WORKSPACE_IMPORT_ERROR = exc

from services.smart_cache_service import smart_cache

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("google_auth_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)
logger.propagate = False

# Scopes completos para Google Workspace
GOOGLE_SCOPES = [
    'openid',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]
_OAUTH_STATE_CACHE: BoundedDict = BoundedDict(max_size=5000, ttl_seconds=600)

class GoogleAuthService:
    """
    Servicio completo de autenticación Google con OAuth2
    Maneja tokens, refresh automático y información de usuario
    """
    
    def __init__(self):
        self.client_id = GOOGLE_CLIENT_ID
        self.client_secret = GOOGLE_CLIENT_SECRET
        self.redirect_uri = GOOGLE_REDIRECT_URI
        self.scopes = GOOGLE_SCOPES

    @staticmethod
    def _cache_key(namespace: str, key: str) -> str:
        return f"{namespace}:{key}"

    @staticmethod
    def _normalize_email(user_email: Optional[str]) -> str:
        return str(user_email or "").strip().lower()

    async def _get_user_info_fallback(self, access_token: Optional[str]) -> Optional[Dict[str, Any]]:
        normalized_token = str(access_token or "").strip()
        if not normalized_token:
            return None

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://www.googleapis.com/oauth2/v2/userinfo",
                headers={"Authorization": f"Bearer {normalized_token}"},
            )
            response.raise_for_status()
            data = response.json()

        email = self._normalize_email(data.get("email"))
        if not email:
            return None

        return {
            "google_id": str(data.get("id") or ""),
            "email": email,
            "name": data.get("name"),
            "first_name": data.get("given_name"),
            "last_name": data.get("family_name"),
            "picture": data.get("picture"),
            "organization": None,
            "phone": None,
            "verified_email": bool(data.get("verified_email", False)),
        }

    async def _persist_credentials_to_db(
        self,
        *,
        user_email: str,
        user_info: Dict[str, Any],
        access_token: Optional[str],
        refresh_token: Optional[str],
        expires_at: Optional[datetime],
    ) -> bool:
        from database.db_enterprise import get_db_session
        from models.models import User

        session = None
        try:
            session = await get_db_session()
            update_data: Dict[str, Any] = {
                "oauth_provider": "google",
                "oauth_access_token": access_token,
                "oauth_token_expires_at": expires_at,
                "oauth_profile": user_info,
            }
            if refresh_token:
                update_data["oauth_refresh_token"] = refresh_token

            if user_info.get("picture"):
                update_data["profile_picture_url"] = user_info["picture"]

            stmt = (
                update(User)
                .where(func.lower(User.email) == user_email)
                .values(**update_data)
            )
            result = await session.execute(stmt)
            await session.commit()

            rowcount = int(result.rowcount or 0)
            if rowcount == 0:
                logger.warning({
                    "event": "google_credentials_db_user_not_found",
                    "user_email": user_email,
                })
                return False

            return True
        except Exception as exc:
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass
            logger.warning({
                "event": "google_credentials_db_persist_failed",
                "user_email": user_email,
                "error": str(exc),
            })
            return False
        finally:
            if session is not None:
                await session.close()

    async def _load_credentials_from_db(self, user_email: str) -> Optional[Dict[str, Any]]:
        from database.db_enterprise import get_db_session
        from models.models import User

        session = None
        try:
            session = await get_db_session()
            stmt = select(User).where(
                func.lower(User.email) == user_email,
                User.oauth_provider == "google",
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user is None or not user.oauth_access_token:
                return None

            return {
                "token": user.oauth_access_token,
                "refresh_token": user.oauth_refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scopes": list(self.scopes),
                "expiry": user.oauth_token_expires_at.isoformat() if user.oauth_token_expires_at else None,
            }
        except Exception as exc:
            logger.warning({
                "event": "google_credentials_db_load_failed",
                "user_email": user_email,
                "error": str(exc),
            })
            return None
        finally:
            if session is not None:
                await session.close()

    async def _load_user_info_from_db(self, user_email: str) -> Optional[Dict[str, Any]]:
        from database.db_enterprise import get_db_session
        from models.models import User

        session = None
        try:
            session = await get_db_session()
            stmt = select(User).where(
                func.lower(User.email) == user_email,
                User.oauth_provider == "google",
            )
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            if user is None:
                return None

            oauth_profile = user.oauth_profile if isinstance(user.oauth_profile, dict) else {}
            merged_profile = {
                "google_id": str(oauth_profile.get("google_id") or ""),
                "email": self._normalize_email(user.email or oauth_profile.get("email")),
                "name": oauth_profile.get("name") or user.full_name or user.username,
                "first_name": oauth_profile.get("first_name"),
                "last_name": oauth_profile.get("last_name"),
                "picture": oauth_profile.get("picture") or user.profile_picture_url,
                "organization": oauth_profile.get("organization"),
                "phone": oauth_profile.get("phone"),
                "verified_email": bool(oauth_profile.get("verified_email", False)),
            }
            if not merged_profile["email"]:
                return None
            return merged_profile
        except Exception as exc:
            logger.warning({
                "event": "google_user_info_db_load_failed",
                "user_email": user_email,
                "error": str(exc),
            })
            return None
        finally:
            if session is not None:
                await session.close()

    async def _clear_credentials_from_db(self, user_email: str) -> bool:
        from database.db_enterprise import get_db_session
        from models.models import User

        session = None
        try:
            session = await get_db_session()
            stmt = (
                update(User)
                .where(
                    func.lower(User.email) == user_email,
                    User.oauth_provider == "google",
                )
                .values(
                    oauth_access_token=None,
                    oauth_refresh_token=None,
                    oauth_token_expires_at=None,
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return bool(int(result.rowcount or 0))
        except Exception as exc:
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass
            logger.warning({
                "event": "google_credentials_db_clear_failed",
                "user_email": user_email,
                "error": str(exc),
            })
            return False
        finally:
            if session is not None:
                await session.close()

    async def sync_cached_credentials_to_db(self, user_email: str) -> bool:
        normalized_email = self._normalize_email(user_email)
        if not normalized_email:
            return False

        credentials_data = await smart_cache.get(
            self._cache_key("google_credentials", normalized_email)
        )
        user_info = await smart_cache.get(
            self._cache_key("google_user_info", normalized_email)
        ) or {"email": normalized_email}

        if not isinstance(credentials_data, dict) or not credentials_data.get("token"):
            return False

        expires_at = None
        raw_expiry = credentials_data.get("expiry")
        if raw_expiry:
            try:
                expires_at = datetime.fromisoformat(raw_expiry)
            except Exception:
                expires_at = None

        return await self._persist_credentials_to_db(
            user_email=normalized_email,
            user_info=user_info,
            access_token=credentials_data.get("token"),
            refresh_token=credentials_data.get("refresh_token"),
            expires_at=expires_at,
        )

    def _ensure_available(self):
        if not GOOGLE_WORKSPACE_LIBS_AVAILABLE:
            raise RuntimeError(f"google_workspace_unavailable: {GOOGLE_WORKSPACE_IMPORT_ERROR}")

    def _ensure_configured(self):
        if not OAUTH_ENABLED:
            raise RuntimeError("google_oauth_disabled")
        if not self.client_id or not self.client_secret or not self.redirect_uri:
            raise RuntimeError("google_oauth_not_configured")

    def get_public_config(self) -> Dict[str, Any]:
        return {
            "enabled": bool(
                OAUTH_ENABLED
                and self.client_id
                and self.client_secret
                and self.redirect_uri
                and GOOGLE_WORKSPACE_LIBS_AVAILABLE
            ),
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "scopes": list(self.scopes),
            "workspace_libs_available": GOOGLE_WORKSPACE_LIBS_AVAILABLE,
            "workspace_import_error": str(GOOGLE_WORKSPACE_IMPORT_ERROR) if GOOGLE_WORKSPACE_IMPORT_ERROR else None,
        }

    async def _build_service(self, service_name: str, version: str, credentials):
        self._ensure_available()
        return await asyncio.to_thread(build, service_name, version, credentials=credentials)

    async def _execute(self, request):
        return await asyncio.to_thread(request.execute)
        
    def create_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Crea URL de autorización para Google OAuth2
        
        Returns:
            Tuple[str, str]: (authorization_url, state)
        """
        try:
            self._ensure_available()
            self._ensure_configured()
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri]
                    }
                },
                scopes=self.scopes
            )
            flow.redirect_uri = self.redirect_uri
            
            authorization_url, flow_state = flow.authorization_url(
                access_type='offline',  # Para refresh tokens
                include_granted_scopes='true',
                state=state,
                prompt='consent'  # Fuerza reauthorization para refresh token
            )
            _OAUTH_STATE_CACHE[flow_state] = {"created_at": datetime.utcnow().isoformat()}
            
            logger.info({
                "event": "authorization_url_created",
                "state": flow_state,
                "scopes": len(self.scopes)
            })
            
            return authorization_url, flow_state
            
        except Exception as e:
            logger.error({
                "event": "authorization_url_creation_error",
                "error": str(e)
            })
            raise
    
    async def handle_oauth_callback(self, code: str, state: str) -> Dict[str, Any]:
        """
        Maneja el callback de OAuth2 y obtiene tokens + información del usuario
        
        Args:
            code: Authorization code de Google
            state: State parameter para validación
            
        Returns:
            Dict con información completa del usuario y tokens
        """
        try:
            self._ensure_available()
            self._ensure_configured()
            cached_state = _OAUTH_STATE_CACHE.pop(state, None)
            if not state or cached_state is None:
                raise RuntimeError("invalid_oauth_state")
            # Intercambiar code por tokens
            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": [self.redirect_uri]
                    }
                },
                scopes=self.scopes,
                state=state
            )
            flow.redirect_uri = self.redirect_uri
            
            # Obtener tokens
            await asyncio.to_thread(flow.fetch_token, code=code)
            credentials = flow.credentials
            
            # Obtener información del usuario
            user_info = await self._get_user_info(credentials)
            
            # Guardar credentials en caché y BD
            user_data = await self._save_user_credentials(user_info, credentials)
            
            logger.info({
                "event": "oauth_callback_success",
                "user_email": user_info.get("email"),
                "scopes_granted": len(credentials.scopes or [])
            })
            
            return user_data
            
        except Exception as e:
            logger.error({
                "event": "oauth_callback_error",
                "error": str(e)
            })
            raise
    
    async def _get_user_info(self, credentials: Credentials) -> Dict[str, Any]:
        """Obtiene información completa del usuario desde Google APIs."""
        try:
            self._ensure_available()
            # Usar Google People API para información detallada
            service = await self._build_service('people', 'v1', credentials)
            
            # Obtener perfil del usuario
            profile = await self._execute(
                service.people().get(
                    resourceName='people/me',
                    personFields='names,emailAddresses,photos,organizations,phoneNumbers,addresses'
                )
            )
            
            # Extraer información relevante
            user_info = {
                "google_id": profile.get("resourceName", "").replace("people/", ""),
                "email": None,
                "name": None,
                "first_name": None,
                "last_name": None,
                "picture": None,
                "organization": None,
                "phone": None,
                "verified_email": False
            }
            
            # Email
            emails = profile.get('emailAddresses', [])
            if emails:
                primary_email = next((e for e in emails if e.get('metadata', {}).get('primary')), emails[0])
                user_info["email"] = self._normalize_email(primary_email.get('value'))
                user_info["verified_email"] = primary_email.get('metadata', {}).get('verified', False)
            
            # Nombre
            names = profile.get('names', [])
            if names:
                primary_name = next((n for n in names if n.get('metadata', {}).get('primary')), names[0])
                user_info["name"] = primary_name.get('displayName')
                user_info["first_name"] = primary_name.get('givenName')
                user_info["last_name"] = primary_name.get('familyName')
            
            # Foto
            photos = profile.get('photos', [])
            if photos:
                primary_photo = next((p for p in photos if p.get('metadata', {}).get('primary')), photos[0])
                user_info["picture"] = primary_photo.get('url')
            
            # Organización
            organizations = profile.get('organizations', [])
            if organizations:
                current_org = next((o for o in organizations if o.get('current')), organizations[0])
                user_info["organization"] = current_org.get('name')
            
            # Teléfono
            phones = profile.get('phoneNumbers', [])
            if phones:
                primary_phone = next((p for p in phones if p.get('metadata', {}).get('primary')), phones[0])
                user_info["phone"] = primary_phone.get('value')
            
            if not user_info["email"]:
                fallback_info = await self._get_user_info_fallback(getattr(credentials, "token", None))
                if fallback_info:
                    return fallback_info
                raise RuntimeError("google_user_info_missing_email")

            return user_info
            
        except Exception as e:
            logger.error({
                "event": "get_user_info_error",
                "error": str(e)
            })
            fallback_info = await self._get_user_info_fallback(getattr(credentials, "token", None))
            if fallback_info:
                return fallback_info
            raise RuntimeError("google_user_info_unavailable") from e
    
    async def _save_user_credentials(self, user_info: Dict[str, Any], credentials: Credentials) -> Dict[str, Any]:
        """
        Guarda las credenciales del usuario en BD y caché
        
        Returns:
            Dict con información completa del usuario
        """
        try:
            user_email = self._normalize_email(user_info.get("email"))
            if not user_email:
                raise ValueError("google_user_email_missing")
            existing_credentials = await smart_cache.get(
                self._cache_key("google_credentials", user_email)
            )
            if not existing_credentials:
                existing_credentials = await self._load_credentials_from_db(user_email)
            resolved_refresh_token = credentials.refresh_token or (
                existing_credentials.get("refresh_token") if isinstance(existing_credentials, dict) else None
            )
            
            # Serializar credentials para almacenamiento
            credentials_data = {
                "token": credentials.token,
                "refresh_token": resolved_refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None
            }
            
            # Guardar en caché (TTL de 1 hora)
            await smart_cache.set(
                self._cache_key("google_credentials", user_email),
                credentials_data,
                ttl=3600
            )
            
            # Guardar información del usuario en caché
            await smart_cache.set(
                self._cache_key("google_user_info", user_email),
                user_info,
                ttl=86400  # 24 horas
            )
            
            db_persisted = await self._persist_credentials_to_db(
                user_email=user_email,
                user_info=user_info,
                access_token=credentials.token,
                refresh_token=resolved_refresh_token,
                expires_at=credentials.expiry,
            )
            
            user_data = {
                "user_info": user_info,
                "credentials_saved": True,
                "credentials_persisted_db": db_persisted,
                "scopes": credentials.scopes,
                "access_expires": credentials.expiry.isoformat() if credentials.expiry else None,
                "has_refresh_token": bool(resolved_refresh_token)
            }
            
            logger.info({
                "event": "user_credentials_saved",
                "user_email": user_email,
                "scopes_count": len(credentials.scopes or []),
                "has_refresh": bool(resolved_refresh_token)
            })
            
            return user_data
            
        except Exception as e:
            logger.error({
                "event": "save_credentials_error",
                "error": str(e)
            })
            raise
    
    async def get_valid_credentials(self, user_email: str) -> Optional[Credentials]:
        """
        Obtiene credenciales válidas para un usuario, refrescando si es necesario
        
        Args:
            user_email: Email del usuario
            
        Returns:
            Credentials válidas o None si no existen
        """
        try:
            self._ensure_available()
            normalized_email = self._normalize_email(user_email)
            if not normalized_email:
                return None
            # Obtener credentials del caché
            credentials_data = await smart_cache.get(
                self._cache_key("google_credentials", normalized_email)
            )
            
            if not credentials_data:
                credentials_data = await self._load_credentials_from_db(normalized_email)
                if credentials_data:
                    await smart_cache.set(
                        self._cache_key("google_credentials", normalized_email),
                        credentials_data,
                        ttl=3600,
                    )
                else:
                    logger.warning({
                        "event": "credentials_not_found",
                        "user_email": normalized_email
                    })
                    return None
            
            # Reconstruir credentials object
            credentials = Credentials(
                token=credentials_data["token"],
                refresh_token=credentials_data["refresh_token"],
                token_uri=credentials_data["token_uri"],
                client_id=credentials_data["client_id"],
                client_secret=credentials_data["client_secret"],
                scopes=credentials_data["scopes"]
            )
            
            if credentials_data["expiry"]:
                credentials.expiry = datetime.fromisoformat(credentials_data["expiry"])
            
            # Verificar si necesita refresh
            if credentials.expired:
                if not credentials.refresh_token:
                    logger.warning({
                        "event": "refresh_token_missing",
                        "user_email": normalized_email
                    })
                    return None
                logger.info({
                    "event": "refreshing_expired_token",
                    "user_email": normalized_email
                })
                
                await asyncio.to_thread(credentials.refresh, Request())
                
                # Actualizar en caché
                updated_credentials_data = credentials_data.copy()
                updated_credentials_data.update({
                    "token": credentials.token,
                    "expiry": credentials.expiry.isoformat() if credentials.expiry else None
                })
                
                await smart_cache.set(
                    self._cache_key("google_credentials", normalized_email),
                    updated_credentials_data,
                    ttl=3600
                )
                user_info = await self.get_user_info(normalized_email) or {"email": normalized_email}
                await self._persist_credentials_to_db(
                    user_email=normalized_email,
                    user_info=user_info,
                    access_token=credentials.token,
                    refresh_token=credentials.refresh_token,
                    expires_at=credentials.expiry,
                )
                
                logger.info({
                    "event": "token_refreshed",
                    "user_email": normalized_email
                })
            
            return credentials
            
        except Exception as e:
            logger.error({
                "event": "get_valid_credentials_error",
                "user_email": self._normalize_email(user_email),
                "error": str(e)
            })
            return None
    
    async def get_user_info(self, user_email: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información del usuario desde caché
        
        Args:
            user_email: Email del usuario
            
        Returns:
            Dict con información del usuario o None
        """
        try:
            normalized_email = self._normalize_email(user_email)
            if not normalized_email:
                return None
            user_info = await smart_cache.get(
                self._cache_key("google_user_info", normalized_email)
            )
            if user_info:
                return user_info

            user_info = await self._load_user_info_from_db(normalized_email)
            if user_info:
                await smart_cache.set(
                    self._cache_key("google_user_info", normalized_email),
                    user_info,
                    ttl=86400,
                )
            return user_info
            
        except Exception as e:
            logger.error({
                "event": "get_user_info_cache_error",
                "user_email": self._normalize_email(user_email),
                "error": str(e)
            })
            return None
    
    async def revoke_user_access(self, user_email: str) -> bool:
        """
        Revoca el acceso de Google para un usuario
        
        Args:
            user_email: Email del usuario
            
        Returns:
            True si se revocó exitosamente
        """
        try:
            normalized_email = self._normalize_email(user_email)
            credentials = await self.get_valid_credentials(normalized_email)
            
            if not credentials:
                return False
            
            # Revocar token en Google
            revoke_url = f"https://oauth2.googleapis.com/revoke?token={credentials.token}"
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(revoke_url)
            
            # Limpiar caché
            await smart_cache.delete(self._cache_key("google_credentials", normalized_email))
            await smart_cache.delete(self._cache_key("google_user_info", normalized_email))
            await self._clear_credentials_from_db(normalized_email)
            
            logger.info({
                "event": "user_access_revoked",
                "user_email": normalized_email,
                "revoke_status": response.status_code
            })
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error({
                "event": "revoke_access_error",
                "user_email": self._normalize_email(user_email),
                "error": str(e)
            })
            return False

# Instancia global del servicio
google_auth_service = GoogleAuthService()
