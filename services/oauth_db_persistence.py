"""
OAuth DB Persistence - Persistencia de perfiles OAuth en base de datos
Separado de oauth_profile_service.py
"""
import logging
from typing import Dict, Any
from sqlalchemy import update

from models.models import User
from database.db_enterprise import get_db_session

logger = logging.getLogger("oauth_db_persistence")


class ProfilePersistenceService:
    """Servicio para persistir perfiles OAuth en la base de datos"""
    
    async def save_profile(self, user_id: str, profile: Dict[str, Any]) -> bool:
        """Guarda el perfil OAuth en la base de datos del usuario"""
        session = None
        try:
            session = await get_db_session()
            basic = profile.get("basic", {})
            enriched = profile.get("enriched", {})
            
            update_data = {}
            
            if basic.get("name"):
                update_data["full_name"] = basic["name"]
            
            if basic.get("picture"):
                update_data["profile_picture_url"] = basic["picture"]
            
            # Guardar perfil completo en JSONB
            update_data["oauth_profile"] = profile
            
            # Guardar intereses
            update_data["interests"] = enriched.get("inferred_interests", [])
            
            # Timezone y locale
            prefs = profile.get("preferences", {})
            if prefs.get("timezone"):
                update_data["timezone"] = prefs["timezone"]
            if prefs.get("language"):
                update_data["preferred_language"] = prefs["language"]
            
            stmt = (
                update(User)
                .where(User.id == str(user_id))
                .values(**update_data)
            )
            await session.execute(stmt)
            await session.commit()
            
            logger.info({
                "event": "user_profile_updated_from_oauth",
                "user_id": user_id,
                "fields_updated": list(update_data.keys())
            })
            
            return True
                
        except Exception as e:
            if session is not None:
                try:
                    await session.rollback()
                except Exception:
                    pass
            logger.error({
                "event": "user_profile_update_error",
                "user_id": user_id,
                "error": str(e)
            })
            return False
        finally:
            if session is not None:
                await session.close()


# Instancia global
profile_persistence_service = ProfilePersistenceService()
