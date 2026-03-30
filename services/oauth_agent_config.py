"""
OAuth Agent Config - Auto-configuración de agentes basada en perfil OAuth
Separado de oauth_profile_service.py
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger("oauth_agent_config")


class AgentAutoConfigurationService:
    """Servicio para configurar automáticamente agentes basado en perfil OAuth"""
    
    async def configure_agents(self, user_id: str, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Configura agentes automáticamente basado en el perfil"""
        try:
            if not profile or "error" in profile:
                return []
            
            suggested_types = profile.get("enriched", {}).get("suggested_agent_types", [])
            basic = profile.get("basic", {})
            name = basic.get("given_name", "Usuario")
            
            agents_configs = []
            
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
                "based_on_provider": profile.get("provider")
            })
            
            return agents_configs
            
        except Exception as e:
            logger.error({
                "event": "auto_configure_agents_error",
                "user_id": user_id,
                "error": str(e)
            })
            return []


# Instancia global
agent_config_service = AgentAutoConfigurationService()
