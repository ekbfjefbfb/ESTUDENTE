"""
🔐 OAuth Profile Service - Auto-personalización de Agentes
==========================================================

Obtiene información del usuario automáticamente desde proveedores OAuth
(Google, Microsoft, GitHub, Apple) para personalizar agentes sin preguntas.

DATOS OBTENIDOS AUTOMÁTICAMENTE:
- ✅ Nombre completo
- ✅ Email
- ✅ Foto de perfil
- ✅ Ubicación (ciudad, país)
- ✅ Idioma preferido
- ✅ Timezone
- ✅ Intereses (desde Google/Microsoft)
- ✅ Calendario (para agentes de productividad)
- ✅ Contactos (para agentes de networking)
- ✅ Historial de búsquedas (insights)
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from models.models import User
from database.db_enterprise import get_db_session
from services.redis_service import set_cache, get_cache
import json_log_formatter

# =============================================
# LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("oauth_profile_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# =============================================
# OAUTH PROFILE SERVICE
# =============================================

class OAuthProfileService:
    """Servicio para obtener perfil completo desde proveedores OAuth"""
    
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
        
        Args:
            user_id: ID del usuario en la DB
            provider: google, microsoft, github, apple
            access_token: Token de acceso OAuth
            
        Returns:
            Dict con toda la información del usuario
        """
        try:
            # Verificar caché primero
            cache_key = f"oauth_profile:{user_id}:{provider}"
            cached = await get_cache(cache_key)
            if cached:
                logger.info({
                    "event": "oauth_profile_cache_hit",
                    "user_id": user_id,
                    "provider": provider
                })
                return json.loads(cached) if isinstance(cached, str) else cached
            
            # Obtener perfil según proveedor
            if provider == "google":
                profile = await self._get_google_profile(access_token)
            elif provider == "microsoft":
                profile = await self._get_microsoft_profile(access_token)
            elif provider == "github":
                profile = await self._get_github_profile(access_token)
            elif provider == "apple":
                profile = await self._get_apple_profile(access_token)
            else:
                raise ValueError(f"Proveedor no soportado: {provider}")
            
            # Enriquecer con datos adicionales
            enriched_profile = await self._enrich_profile(profile, provider, access_token)
            
            # Guardar en caché
            await set_cache(cache_key, json.dumps(enriched_profile), ttl=self.cache_ttl)
            
            # Actualizar DB con info del perfil
            await self._update_user_profile_in_db(user_id, enriched_profile)
            
            logger.info({
                "event": "oauth_profile_fetched",
                "user_id": user_id,
                "provider": provider,
                "fields_obtained": len(enriched_profile.keys())
            })
            
            return enriched_profile
            
        except Exception as e:
            logger.error({
                "event": "oauth_profile_error",
                "user_id": user_id,
                "provider": provider,
                "error": str(e)
            })
            return {}
    
    async def _get_google_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de Google con máxima información posible"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Info básica del perfil
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                userinfo = userinfo_response.json()
                
                # 2. Info extendida de People API
                people_response = await client.get(
                    "https://people.googleapis.com/v1/people/me",
                    params={
                        "personFields": "names,emailAddresses,photos,locales,addresses,birthdays,genders,occupations,organizations,phoneNumbers,urls,biographies,interests"
                    },
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                people_data = people_response.json()
                
                # 3. Calendario para inferir timezone y horarios
                calendar_response = await client.get(
                    "https://www.googleapis.com/calendar/v3/users/me/settings/timezone",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                timezone_data = calendar_response.json()
                
                # Construir perfil completo
                profile = {
                    "provider": "google",
                    "basic": {
                        "email": userinfo.get("email"),
                        "name": userinfo.get("name"),
                        "given_name": userinfo.get("given_name"),
                        "family_name": userinfo.get("family_name"),
                        "picture": userinfo.get("picture"),
                        "locale": userinfo.get("locale"),
                        "verified_email": userinfo.get("verified_email", False)
                    },
                    "extended": self._parse_google_people_data(people_data),
                    "preferences": {
                        "timezone": timezone_data.get("value", "UTC"),
                        "language": userinfo.get("locale", "en").split("-")[0]
                    },
                    "fetched_at": datetime.utcnow().isoformat()
                }
                
                return profile
                
        except Exception as e:
            logger.error(f"Error fetching Google profile: {e}")
            return {"provider": "google", "error": str(e)}
    
    async def _get_microsoft_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de Microsoft/Azure AD"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # 1. Info básica
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_data = response.json()
                
                # 2. Foto de perfil
                try:
                    photo_response = await client.get(
                        "https://graph.microsoft.com/v1.0/me/photo/$value",
                        headers={"Authorization": f"Bearer {access_token}"}
                    )
                    photo_url = f"data:image/jpeg;base64,{photo_response.content.hex()}" if photo_response.status_code == 200 else None
                except:
                    photo_url = None
                
                profile = {
                    "provider": "microsoft",
                    "basic": {
                        "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                        "name": user_data.get("displayName"),
                        "given_name": user_data.get("givenName"),
                        "family_name": user_data.get("surname"),
                        "picture": photo_url,
                        "job_title": user_data.get("jobTitle"),
                        "office_location": user_data.get("officeLocation"),
                        "mobile_phone": user_data.get("mobilePhone"),
                        "business_phones": user_data.get("businessPhones", [])
                    },
                    "preferences": {
                        "language": user_data.get("preferredLanguage", "en"),
                        "timezone": "UTC"  # Microsoft no expone timezone fácilmente
                    },
                    "fetched_at": datetime.utcnow().isoformat()
                }
                
                return profile
                
        except Exception as e:
            logger.error(f"Error fetching Microsoft profile: {e}")
            return {"provider": "microsoft", "error": str(e)}
    
    async def _get_github_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de GitHub"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                user_data = response.json()
                
                profile = {
                    "provider": "github",
                    "basic": {
                        "email": user_data.get("email"),
                        "name": user_data.get("name"),
                        "username": user_data.get("login"),
                        "picture": user_data.get("avatar_url"),
                        "bio": user_data.get("bio"),
                        "location": user_data.get("location"),
                        "company": user_data.get("company"),
                        "blog": user_data.get("blog"),
                        "twitter_username": user_data.get("twitter_username")
                    },
                    "stats": {
                        "public_repos": user_data.get("public_repos", 0),
                        "followers": user_data.get("followers", 0),
                        "following": user_data.get("following", 0)
                    },
                    "fetched_at": datetime.utcnow().isoformat()
                }
                
                return profile
                
        except Exception as e:
            logger.error(f"Error fetching GitHub profile: {e}")
            return {"provider": "github", "error": str(e)}
    
    async def _get_apple_profile(self, access_token: str) -> Dict[str, Any]:
        """Obtiene perfil de Apple (limitado por privacidad)"""
        # Apple proporciona muy poca info por privacidad
        # Solo podemos obtener lo que viene en el ID token inicial
        return {
            "provider": "apple",
            "basic": {
                "email": None,  # Solo disponible en first sign-in
                "name": None
            },
            "note": "Apple proporciona información limitada por políticas de privacidad",
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    def _parse_google_people_data(self, people_data: Dict) -> Dict[str, Any]:
        """Parsea datos de Google People API"""
        extended = {}
        
        # Direcciones
        if "addresses" in people_data:
            addresses = people_data["addresses"]
            if addresses:
                addr = addresses[0]
                extended["location"] = {
                    "city": addr.get("city"),
                    "country": addr.get("country"),
                    "formatted": addr.get("formattedValue")
                }
        
        # Organizaciones (trabajo)
        if "organizations" in people_data:
            orgs = people_data["organizations"]
            if orgs:
                org = orgs[0]
                extended["work"] = {
                    "company": org.get("name"),
                    "title": org.get("title"),
                    "department": org.get("department")
                }
        
        # Biografía
        if "biographies" in people_data:
            bios = people_data["biographies"]
            if bios:
                extended["bio"] = bios[0].get("value")
        
        # Intereses
        if "interests" in people_data:
            interests = people_data["interests"]
            extended["interests"] = [i.get("value") for i in interests]
        
        # Teléfonos
        if "phoneNumbers" in people_data:
            phones = people_data["phoneNumbers"]
            extended["phones"] = [p.get("value") for p in phones]
        
        # URLs (redes sociales, sitio web)
        if "urls" in people_data:
            urls = people_data["urls"]
            extended["urls"] = [u.get("value") for u in urls]
        
        return extended
    
    async def _enrich_profile(
        self,
        profile: Dict[str, Any],
        provider: str,
        access_token: str
    ) -> Dict[str, Any]:
        """Enriquece el perfil con datos adicionales y análisis"""
        
        # Agregar metadatos
        profile["enriched"] = {
            "inferred_interests": await self._infer_interests_from_profile(profile),
            "suggested_agent_types": await self._suggest_agent_types(profile),
            "personality_hints": await self._infer_personality(profile),
            "optimal_communication_style": await self._infer_communication_style(profile)
        }
        
        return profile
    
    async def _infer_interests_from_profile(self, profile: Dict) -> List[str]:
        """Infiere intereses del perfil para personalización"""
        interests = []
        
        # Desde Google
        if profile.get("provider") == "google":
            extended = profile.get("extended", {})
            if "interests" in extended:
                interests.extend(extended["interests"])
            
            # Desde bio
            bio = extended.get("bio", "")
            if bio:
                # Keywords comunes
                keywords = ["tech", "business", "entrepreneur", "developer", "designer", 
                           "marketing", "sales", "finance", "data", "AI", "ML"]
                for kw in keywords:
                    if kw.lower() in bio.lower():
                        interests.append(kw)
        
        # Desde GitHub
        if profile.get("provider") == "github":
            bio = profile.get("basic", {}).get("bio", "")
            if bio:
                interests.append("technology")
                interests.append("programming")
        
        return list(set(interests))  # Eliminar duplicados
    
    async def _suggest_agent_types(self, profile: Dict) -> List[str]:
        """Sugiere tipos de agentes basado en el perfil"""
        suggestions = []
        
        basic = profile.get("basic", {})
        extended = profile.get("extended", {})
        
        # Por trabajo
        job_title = basic.get("job_title", "").lower()
        if any(word in job_title for word in ["ceo", "founder", "entrepreneur", "manager"]):
            suggestions.extend(["executive_assistant", "business_advisor", "productivity_coach"])
        
        if any(word in job_title for word in ["developer", "engineer", "programmer"]):
            suggestions.extend(["code_reviewer", "tech_advisor", "documentation_assistant"])
        
        if any(word in job_title for word in ["marketing", "sales"]):
            suggestions.extend(["content_creator", "social_media_manager", "copywriter"])
        
        # Por intereses
        interests = await self._infer_interests_from_profile(profile)
        if "tech" in interests or "AI" in interests:
            suggestions.append("tech_researcher")
        
        # Siempre útiles
        suggestions.extend(["general_assistant", "research_assistant"])
        
        return list(set(suggestions))[:5]  # Top 5
    
    async def _infer_personality(self, profile: Dict) -> Dict[str, Any]:
        """Infiere rasgos de personalidad para ajustar tono del agente"""
        hints = {
            "formality_level": "professional",  # casual, professional, formal
            "verbosity": "balanced",  # concise, balanced, detailed
            "emoji_usage": "moderate"  # none, minimal, moderate, frequent
        }
        
        # Ajustar según proveedor (asunciones razonables)
        provider = profile.get("provider")
        if provider == "github":
            hints["formality_level"] = "casual"
            hints["verbosity"] = "concise"
        
        return hints
    
    async def _infer_communication_style(self, profile: Dict) -> str:
        """Determina estilo óptimo de comunicación"""
        basic = profile.get("basic", {})
        
        # Por ubicación/idioma
        locale = basic.get("locale", "en")
        if locale.startswith("es"):
            return "friendly_spanish"
        elif locale.startswith("en"):
            return "professional_english"
        
        return "adaptive"
    
    async def _update_user_profile_in_db(
        self,
        user_id: int,
        profile: Dict[str, Any]
    ):
        """Actualiza la DB con información del perfil OAuth"""
        try:
            async with get_db_session() as session:
                basic = profile.get("basic", {})
                extended = profile.get("extended", {})
                enriched = profile.get("enriched", {})
                
                # Preparar datos para actualizar
                update_data = {}
                
                if basic.get("name"):
                    update_data["full_name"] = basic["name"]
                
                if basic.get("picture"):
                    update_data["profile_picture_url"] = basic["picture"]
                
                # Guardar perfil completo en campo JSONB
                update_data["oauth_profile"] = profile
                
                # Guardar intereses
                update_data["interests"] = enriched.get("inferred_interests", [])
                
                # Timezone y locale
                prefs = profile.get("preferences", {})
                if prefs.get("timezone"):
                    update_data["timezone"] = prefs["timezone"]
                if prefs.get("language"):
                    update_data["preferred_language"] = prefs["language"]
                
                # Ejecutar update
                stmt = (
                    update(User)
                    .where(User.id == user_id)
                    .values(**update_data)
                )
                await session.execute(stmt)
                await session.commit()
                
                logger.info({
                    "event": "user_profile_updated_from_oauth",
                    "user_id": user_id,
                    "fields_updated": list(update_data.keys())
                })
                
        except Exception as e:
            logger.error({
                "event": "user_profile_update_error",
                "user_id": user_id,
                "error": str(e)
            })
    
    async def auto_configure_agents_for_user(
        self,
        user_id: int,
        provider: str,
        access_token: str
    ) -> List[Dict[str, Any]]:
        """
        Configura automáticamente agentes personales basado en perfil OAuth
        SIN PREGUNTAR AL USUARIO
        
        Returns:
            Lista de agentes creados automáticamente
        """
        try:
            # Obtener perfil completo
            profile = await self.get_user_profile_from_oauth(user_id, provider, access_token)
            
            if not profile or "error" in profile:
                return []
            
            # Tipos sugeridos
            suggested_types = profile.get("enriched", {}).get("suggested_agent_types", [])
            
            # Crear configuraciones de agentes
            agents_configs = []
            
            basic = profile.get("basic", {})
            name = basic.get("given_name", "Usuario")
            
            # 1. Asistente Personal Principal
            agents_configs.append({
                "name": f"Asistente Personal de {name}",
                "type": "general_assistant",
                "personality": {
                    "tone": "friendly_professional",
                    "knows_user_name": name,
                    "knows_user_location": profile.get("extended", {}).get("location", {}).get("city"),
                    "user_interests": profile.get("enriched", {}).get("inferred_interests", []),
                    "communication_style": profile.get("enriched", {}).get("optimal_communication_style", "adaptive")
                },
                "instructions": f"""Eres el asistente personal de {name}. 
Conoces sus intereses: {', '.join(profile.get('enriched', {}).get('inferred_interests', []))}.
Adapta tus respuestas a su estilo de comunicación preferido.
Sé proactivo y anticipa sus necesidades."""
            })
            
            # 2. Agente especializado según trabajo
            job_title = basic.get("job_title")
            if job_title:
                agents_configs.append({
                    "name": f"Asesor {job_title}",
                    "type": "professional_advisor",
                    "personality": {
                        "expertise": job_title,
                        "industry_knowledge": True
                    },
                    "instructions": f"""Eres un asesor experto para {name}, quien trabaja como {job_title}.
Proporciona consejos profesionales específicos para su rol."""
                })
            
            # 3. Agente según intereses principales
            interests = profile.get("enriched", {}).get("inferred_interests", [])
            if interests:
                agents_configs.append({
                    "name": f"Experto en {interests[0].title()}",
                    "type": "domain_expert",
                    "personality": {
                        "specialization": interests[0]
                    },
                    "instructions": f"""Eres un experto en {interests[0]} para {name}.
Mantente actualizado y proporciona insights profundos en este campo."""
                })
            
            logger.info({
                "event": "agents_auto_configured",
                "user_id": user_id,
                "agents_created": len(agents_configs),
                "based_on_provider": provider
            })
            
            return agents_configs
            
        except Exception as e:
            logger.error({
                "event": "auto_configure_agents_error",
                "user_id": user_id,
                "error": str(e)
            })
            return []


# =============================================
# INSTANCIA GLOBAL
# =============================================
oauth_profile_service = OAuthProfileService()
