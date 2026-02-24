"""
user_profile_service.py - Servicio de perfiles de usuario
Gestiona perfiles y preferencias de usuarios
"""

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime
from utils.safe_metrics import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Métricas seguras
SERVICE_OPERATIONS = Counter("user_profile_service_operations_total", "Operations", ["operation", "status"])


class UserProfile:
    """Clase de perfil de usuario"""
    
    def __init__(self, user_id: str, preferences: Dict[str, Any] = None):
        self.user_id = user_id
        self.preferences = preferences or {}
        self.created_at = datetime.utcnow()
        self.updated_at = datetime.utcnow()
        self.metadata = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte el perfil a diccionario"""
        return {
            "user_id": self.user_id,
            "preferences": self.preferences,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata
        }


class LearningPattern:
    """Patrones de aprendizaje del usuario"""
    
    def __init__(self):
        self.profiles: Dict[str, UserProfile] = {}
        self.initialized = True
        logger.info({"event": "user_profile_service_initialized"})
    
    async def get_profile(self, user_id: str) -> Optional[UserProfile]:
        """Obtiene el perfil del usuario"""
        return self.profiles.get(user_id)
    
    async def create_profile(self, user_id: str, preferences: Dict[str, Any] = None) -> UserProfile:
        """Crea un nuevo perfil"""
        profile = UserProfile(user_id, preferences)
        self.profiles[user_id] = profile
        return profile
    
    async def health_check(self):
        """Health check básico"""
        return {
            "status": "ok",
            "service": "user_profile_service",
            "profiles_count": len(self.profiles)
        }


# Instancia global
learningpattern = LearningPattern()


# Funciones de compatibilidad
async def init_user_profile_service():
    """Inicialización del servicio"""
    logger.info({"event": "user_profile_service_init"})


async def get_service_status():
    """Estado del servicio"""
    return {"status": "operational", "service": "user_profile_service"}


async def get_user_profile(user_id: str) -> Optional[UserProfile]:
    """Obtiene el perfil de un usuario"""
    profile = await learningpattern.get_profile(user_id)
    if not profile:
        profile = await learningpattern.create_profile(user_id)
    return profile


async def get_profile_insights(user_id: str) -> Dict[str, Any]:
    """Obtiene insights del perfil"""
    profile = await get_user_profile(user_id)
    if not profile:
        return {}
    
    return {
        "user_id": user_id,
        "preferences": profile.preferences,
        "insights": {
            "profile_completeness": 50,
            "activity_level": "medium",
            "recommendations": []
        }
    }


async def update_profile_from_interaction(
    user_id: str,
    interaction: Dict[str, Any]
) -> Dict[str, Any]:
    """Actualiza el perfil basado en una interacción"""
    profile = await get_user_profile(user_id)
    if not profile:
        profile = await learningpattern.create_profile(user_id)
    
    # Actualizar metadata
    profile.metadata["last_interaction"] = datetime.utcnow().isoformat()
    profile.metadata["interaction_count"] = profile.metadata.get("interaction_count", 0) + 1
    profile.updated_at = datetime.utcnow()
    
    return profile.to_dict()


async def get_personalized_context(user_id: str) -> Dict[str, Any]:
    """Obtiene contexto personalizado del usuario"""
    profile = await get_user_profile(user_id)
    if not profile:
        return {}
    
    return {
        "user_id": user_id,
        "preferences": profile.preferences,
        "context": {
            "learning_style": "visual",
            "expertise_level": "intermediate",
            "interests": []
        }
    }
