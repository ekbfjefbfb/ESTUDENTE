"""
OAuth Profile Service Enterprise v2.0 - Refactored
Auto-personalización de Agentes - Orquestador

Responsabilidades separadas:
- oauth_providers.py: Handlers para Google/Microsoft/GitHub/Apple
- oauth_profile_enrichment.py: Enriquecimiento de perfil
- oauth_db_persistence.py: Persistencia en DB
- oauth_agent_config.py: Auto-configuración de agentes

Este archivo es el ORQUESTADOR que coordina todo.
"""
import logging
import json
from typing import Dict, Any, List
from datetime import datetime

from services.redis_service import set_cache, get_cache
from services.oauth_providers import get_provider_profile
from services.oauth_profile_enrichment import profile_enrichment_service
from services.oauth_db_persistence import profile_persistence_service
from services.oauth_agent_config import agent_config_service
import json_log_formatter

# Logging
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("oauth_profile_service")
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(handler)


class OAuthProfileService:
    """Orquestador para obtener y procesar perfiles OAuth"""
    
    def __init__(self):
        self.cache_ttl = 3600  # 1 hora
    
    async def get_user_profile_from_oauth(
        self,
        user_id: int,
        provider: str,
        access_token: str
    ) -> Dict[str, Any]:
        """
        Obtiene perfil completo del usuario desde el proveedor OAuth
        Flujo: Cache → Provider → Enrichment → Persistencia
        """
        try:
            # 1. Verificar caché
            cache_key = f"oauth_profile:{user_id}:{provider}"
            cached = await get_cache(cache_key)
            if cached:
                logger.info({
                    "event": "oauth_profile_cache_hit",
                    "user_id": user_id,
                    "provider": provider
                })
                return json.loads(cached) if isinstance(cached, str) else cached
            
            # 2. Obtener perfil del proveedor
            profile = await get_provider_profile(provider, access_token)
            
            # 3. Enriquecer perfil
            profile = await profile_enrichment_service.enrich_profile(profile)
            
            # 4. Guardar en caché
            await set_cache(cache_key, json.dumps(profile), ttl=self.cache_ttl)
            
            # 5. Persistir en DB
            await profile_persistence_service.save_profile(user_id, profile)
            
            logger.info({
                "event": "oauth_profile_fetched",
                "user_id": user_id,
                "provider": provider,
                "fields_obtained": len(profile.keys())
            })
            
            return profile
            
        except Exception as e:
            logger.error({
                "event": "oauth_profile_error",
                "user_id": user_id,
                "provider": provider,
                "error": str(e)
            })
            return {}
    
    async def auto_configure_agents_for_user(
        self,
        user_id: str,
        provider: str,
        access_token: str
    ) -> List[Dict[str, Any]]:
        """
        Configura automáticamente agentes basado en perfil OAuth
        """
        # Obtener perfil (usará caché si existe)
        profile = await self.get_user_profile_from_oauth(user_id, provider, access_token)
        
        # Delegar a servicio de configuración
        return await agent_config_service.configure_agents(user_id, profile)


# Instancia global
oauth_profile_service = OAuthProfileService()
