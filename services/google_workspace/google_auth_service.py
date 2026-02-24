"""
Google Auth Service - Autenticación completa con Google OAuth2
Obtiene información del usuario y mantiene acceso permanente
"""

import logging
import json
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import httpx
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import json_log_formatter

from services.smart_cache_service import smart_cache
from services.redis_service import get_redis_client
from models.models import User
from database.db_enterprise import get_primary_session as get_db_session

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("google_auth_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# =============================================
# CONFIGURACIÓN GOOGLE OAUTH2
# =============================================
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback")

# Scopes completos para Google Workspace
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.compose',
    'https://www.googleapis.com/auth/gmail.modify'
]

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
        
    def create_authorization_url(self, state: Optional[str] = None) -> Tuple[str, str]:
        """
        Crea URL de autorización para Google OAuth2
        
        Returns:
            Tuple[str, str]: (authorization_url, state)
        """
        try:
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
            flow.fetch_token(code=code)
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
            # Usar Google People API para información detallada
            service = build('people', 'v1', credentials=credentials)
            
            # Obtener perfil del usuario
            profile = service.people().get(
                resourceName='people/me',
                personFields='names,emailAddresses,photos,organizations,phoneNumbers,addresses'
            ).execute()
            
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
                user_info["email"] = primary_email.get('value')
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
            
            return user_info
            
        except Exception as e:
            logger.error({
                "event": "get_user_info_error",
                "error": str(e)
            })
            # Fallback a info básica
            return {
                "email": "unknown@gmail.com",
                "name": "Unknown User",
                "verified_email": False
            }
    
    async def _save_user_credentials(self, user_info: Dict[str, Any], credentials: Credentials) -> Dict[str, Any]:
        """
        Guarda las credenciales del usuario en BD y caché
        
        Returns:
            Dict con información completa del usuario
        """
        try:
            user_email = user_info["email"]
            
            # Serializar credentials para almacenamiento
            credentials_data = {
                "token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "token_uri": credentials.token_uri,
                "client_id": credentials.client_id,
                "client_secret": credentials.client_secret,
                "scopes": credentials.scopes,
                "expiry": credentials.expiry.isoformat() if credentials.expiry else None
            }
            
            # Guardar en caché (TTL de 1 hora)
            await smart_cache.set(
                "google_credentials",
                user_email,
                credentials_data,
                ttl=3600
            )
            
            # Guardar información del usuario en caché
            await smart_cache.set(
                "google_user_info",
                user_email,
                user_info,
                ttl=86400  # 24 horas
            )
            
            # TODO: Actualizar o crear usuario en BD con información de Google
            
            user_data = {
                "user_info": user_info,
                "credentials_saved": True,
                "scopes": credentials.scopes,
                "access_expires": credentials.expiry.isoformat() if credentials.expiry else None,
                "has_refresh_token": bool(credentials.refresh_token)
            }
            
            logger.info({
                "event": "user_credentials_saved",
                "user_email": user_email,
                "scopes_count": len(credentials.scopes or []),
                "has_refresh": bool(credentials.refresh_token)
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
            # Obtener credentials del caché
            credentials_data = await smart_cache.get("google_credentials", user_email)
            
            if not credentials_data:
                logger.warning({
                    "event": "credentials_not_found",
                    "user_email": user_email
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
                logger.info({
                    "event": "refreshing_expired_token",
                    "user_email": user_email
                })
                
                credentials.refresh(Request())
                
                # Actualizar en caché
                updated_credentials_data = credentials_data.copy()
                updated_credentials_data.update({
                    "token": credentials.token,
                    "expiry": credentials.expiry.isoformat() if credentials.expiry else None
                })
                
                await smart_cache.set(
                    "google_credentials",
                    user_email,
                    updated_credentials_data,
                    ttl=3600
                )
                
                logger.info({
                    "event": "token_refreshed",
                    "user_email": user_email
                })
            
            return credentials
            
        except Exception as e:
            logger.error({
                "event": "get_valid_credentials_error",
                "user_email": user_email,
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
            user_info = await smart_cache.get("google_user_info", user_email)
            return user_info
            
        except Exception as e:
            logger.error({
                "event": "get_user_info_cache_error",
                "user_email": user_email,
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
            credentials = await self.get_valid_credentials(user_email)
            
            if not credentials:
                return False
            
            # Revocar token en Google
            revoke_url = f"https://oauth2.googleapis.com/revoke?token={credentials.token}"
            
            async with httpx.AsyncClient() as client:
                response = await client.post(revoke_url)
            
            # Limpiar caché
            await smart_cache.delete("google_credentials", user_email)
            await smart_cache.delete("google_user_info", user_email)
            
            logger.info({
                "event": "user_access_revoked",
                "user_email": user_email,
                "revoke_status": response.status_code
            })
            
            return response.status_code == 200
            
        except Exception as e:
            logger.error({
                "event": "revoke_access_error",
                "user_email": user_email,
                "error": str(e)
            })
            return False

# Instancia global del servicio
google_auth_service = GoogleAuthService()