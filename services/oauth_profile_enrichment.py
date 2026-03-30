"""
OAuth Profile Enrichment - Enriquecimiento de datos de perfil
Separado de oauth_profile_service.py
"""
import logging
from typing import Dict, Any, List

logger = logging.getLogger("oauth_profile_enrichment")


class ProfileEnrichmentService:
    """Servicio para enriquecer perfiles OAuth con análisis adicional"""
    
    async def enrich_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Enriquece el perfil con datos adicionales y análisis"""
        profile["enriched"] = {
            "inferred_interests": await self._infer_interests(profile),
            "suggested_agent_types": await self._suggest_agent_types(profile),
            "personality_hints": await self._infer_personality(profile),
            "optimal_communication_style": await self._infer_communication_style(profile)
        }
        return profile
    
    async def _infer_interests(self, profile: Dict) -> List[str]:
        """Infiere intereses del perfil para personalización"""
        interests = []
        provider = profile.get("provider")
        
        if provider == "google":
            extended = profile.get("extended", {})
            if "interests" in extended:
                interests.extend(extended["interests"])
            
            bio = extended.get("bio", "")
            if bio:
                keywords = ["tech", "business", "entrepreneur", "developer", "designer",
                           "marketing", "sales", "finance", "data", "AI", "ML"]
                for kw in keywords:
                    if kw.lower() in bio.lower():
                        interests.append(kw)
        
        if provider == "github":
            bio = profile.get("basic", {}).get("bio", "")
            if bio:
                interests.extend(["technology", "programming"])
        
        return list(set(interests))
    
    async def _suggest_agent_types(self, profile: Dict) -> List[str]:
        """Sugiere tipos de agentes basado en el perfil"""
        suggestions = []
        basic = profile.get("basic", {})
        
        job_title = basic.get("job_title", "").lower()
        if any(word in job_title for word in ["ceo", "founder", "entrepreneur", "manager"]):
            suggestions.extend(["executive_assistant", "business_advisor", "productivity_coach"])
        
        if any(word in job_title for word in ["developer", "engineer", "programmer"]):
            suggestions.extend(["code_reviewer", "tech_advisor", "documentation_assistant"])
        
        if any(word in job_title for word in ["marketing", "sales"]):
            suggestions.extend(["content_creator", "social_media_manager", "copywriter"])
        
        interests = await self._infer_interests(profile)
        if "tech" in interests or "AI" in interests:
            suggestions.append("tech_researcher")
        
        suggestions.extend(["general_assistant", "research_assistant"])
        
        return list(set(suggestions))[:5]
    
    async def _infer_personality(self, profile: Dict) -> Dict[str, Any]:
        """Infiere rasgos de personalidad para ajustar tono del agente"""
        hints = {
            "formality_level": "professional",
            "verbosity": "balanced",
            "emoji_usage": "moderate"
        }
        
        provider = profile.get("provider")
        if provider == "github":
            hints["formality_level"] = "casual"
            hints["verbosity"] = "concise"
        
        return hints
    
    async def _infer_communication_style(self, profile: Dict) -> str:
        """Determina estilo óptimo de comunicación"""
        basic = profile.get("basic", {})
        locale = basic.get("locale", "en")
        
        if locale.startswith("es"):
            return "friendly_spanish"
        elif locale.startswith("en"):
            return "professional_english"
        
        return "adaptive"


# Instancia global
profile_enrichment_service = ProfileEnrichmentService()
