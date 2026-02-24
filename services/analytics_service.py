"""
📊 ANALYTICS SERVICE
================================

Servicio de analytics avanzado usando PostHog para tracking de eventos,
comportamiento de usuarios, funnels y métricas de producto.

Features:
- ✅ Event tracking
- ✅ User identification
- ✅ Feature flags
- ✅ Funnels
- ✅ A/B testing results
- ✅ Session recording
- ✅ Heatmaps

Author: Backend Team
Version: 1.0.0
"""

import os
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

try:
    import posthog
    POSTHOG_AVAILABLE = True
except ImportError:
    POSTHOG_AVAILABLE = False
    logging.warning("⚠️ posthog no instalado. Analytics deshabilitados.")

logger = logging.getLogger(__name__)


# ============================================================================
# EVENTOS PREDEFINIDOS
# ============================================================================

class AnalyticsEvent(str, Enum):
    """Eventos de analytics predefinidos"""
    
    # User lifecycle
    USER_SIGNED_UP = "user_signed_up"
    USER_LOGGED_IN = "user_logged_in"
    USER_LOGGED_OUT = "user_logged_out"
    USER_DELETED_ACCOUNT = "user_deleted_account"
    
    # Onboarding
    ONBOARDING_STARTED = "onboarding_started"
    ONBOARDING_COMPLETED = "onboarding_completed"
    ONBOARDING_SKIPPED = "onboarding_skipped"
    
    # Subscription
    PLAN_VIEWED = "plan_viewed"
    PLAN_SELECTED = "plan_selected"
    CHECKOUT_STARTED = "checkout_started"
    CHECKOUT_COMPLETED = "checkout_completed"
    SUBSCRIPTION_UPGRADED = "subscription_upgraded"
    SUBSCRIPTION_DOWNGRADED = "subscription_downgraded"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled"
    SUBSCRIPTION_RENEWED = "subscription_renewed"
    PAYMENT_FAILED = "payment_failed"
    
    # Features usage
    CHAT_MESSAGE_SENT = "chat_message_sent"
    VOICE_CONVERSATION_STARTED = "voice_conversation_started"
    IMAGE_GENERATED = "image_generated"
    DOCUMENT_GENERATED = "document_generated"
    AGENT_USED = "agent_used"
    SEARCH_PERFORMED = "search_performed"
    LIVESEARCH_USED = "livesearch_used"
    
    # Engagement
    REFERRAL_CODE_SHARED = "referral_code_shared"
    REFERRAL_SIGNUP = "referral_signup"
    INVITE_SENT = "invite_sent"
    TEAM_MEMBER_ADDED = "team_member_added"
    
    # Errors
    ERROR_OCCURRED = "error_occurred"
    RATE_LIMIT_HIT = "rate_limit_hit"
    QUOTA_EXCEEDED = "quota_exceeded"


# ============================================================================
# ANALYTICS SERVICE
# ============================================================================

class AnalyticsService:
    """
    Servicio de analytics con PostHog
    
    Usage:
        analytics = AnalyticsService()
        
        # Track event
        analytics.track(
            user_id="123",
            event=AnalyticsEvent.IMAGE_GENERATED,
            properties={
                "model": "sdxl",
                "resolution": "1024x1024",
                "generation_time_ms": 5000
            }
        )
        
        # Identify user
        analytics.identify(
            user_id="123",
            traits={
                "email": "user@example.com",
                "plan": "pro",
                "signup_date": "2025-10-01"
            }
        )
    """
    
    def __init__(self):
        """Inicializa PostHog"""
        self.enabled = POSTHOG_AVAILABLE
        
        if self.enabled:
            self._initialize_posthog()
        else:
            logger.warning("⚠️ Analytics DESHABILITADOS (posthog no instalado)")
    
    
    def _initialize_posthog(self):
        """Configura PostHog"""
        try:
            api_key = os.getenv("POSTHOG_API_KEY")
            host = os.getenv("POSTHOG_HOST", "https://app.posthog.com")
            
            if not api_key:
                logger.warning("⚠️ POSTHOG_API_KEY no configurada. Analytics en modo demo.")
                self.enabled = False
                return
            
            posthog.project_api_key = api_key
            posthog.host = host
            posthog.debug = os.getenv("DEBUG", "false").lower() in ("true", "1")
            
            # Configuración de batching
            posthog.max_queue_size = 100
            posthog.request_timeout = 3  # seconds
            
            logger.info(f"✅ PostHog inicializado: {host}")
        
        except Exception as e:
            logger.error(f"❌ Error inicializando PostHog: {e}")
            self.enabled = False
    
    
    def track(
        self,
        user_id: str,
        event: AnalyticsEvent,
        properties: Optional[Dict[str, Any]] = None
    ):
        """
        Trackea un evento
        
        Args:
            user_id: ID del usuario
            event: Tipo de evento (usar AnalyticsEvent enum)
            properties: Propiedades adicionales del evento
        
        Example:
            analytics.track(
                user_id="123",
                event=AnalyticsEvent.IMAGE_GENERATED,
                properties={
                    "model": "sdxl",
                    "prompt_length": 150,
                    "generation_time_ms": 5000
                }
            )
        """
        if not self.enabled:
            return
        
        try:
            event_properties = properties or {}
            event_properties["timestamp"] = datetime.utcnow().isoformat()
            
            posthog.capture(
                distinct_id=user_id,
                event=event.value if isinstance(event, AnalyticsEvent) else event,
                properties=event_properties
            )
            
            logger.debug(f"📊 Event tracked: {event} for user {user_id}")
        
        except Exception as e:
            logger.error(f"❌ Error tracking event: {e}")
    
    
    def identify(
        self,
        user_id: str,
        traits: Dict[str, Any]
    ):
        """
        Identifica usuario con sus características
        
        Args:
            user_id: ID del usuario
            traits: Características del usuario (email, plan, etc.)
        
        Example:
            analytics.identify(
                user_id="123",
                traits={
                    "email": "user@example.com",
                    "plan": "pro",
                    "signup_date": "2025-10-01",
                    "messages_count": 150,
                    "images_generated": 50
                }
            )
        """
        if not self.enabled:
            return
        
        try:
            posthog.identify(
                distinct_id=user_id,
                properties=traits
            )
            
            logger.debug(f"👤 User identified: {user_id}")
        
        except Exception as e:
            logger.error(f"❌ Error identifying user: {e}")
    
    
    def set_user_properties(
        self,
        user_id: str,
        properties: Dict[str, Any],
        set_once: bool = False
    ):
        """
        Actualiza propiedades de usuario
        
        Args:
            user_id: ID del usuario
            properties: Propiedades a actualizar
            set_once: Si True, solo setea si no existe (ej: signup_date)
        """
        if not self.enabled:
            return
        
        try:
            if set_once:
                posthog.set_once(user_id, properties)
            else:
                posthog.set(user_id, properties)
            
            logger.debug(f"📝 User properties updated: {user_id}")
        
        except Exception as e:
            logger.error(f"❌ Error updating user properties: {e}")
    
    
    def track_revenue(
        self,
        user_id: str,
        amount: float,
        currency: str = "USD",
        plan: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Trackea revenue (compras, subscripciones)
        
        Args:
            user_id: ID del usuario
            amount: Monto en la moneda especificada
            currency: Código de moneda (USD, EUR, etc.)
            plan: Nombre del plan comprado
            metadata: Datos adicionales
        """
        if not self.enabled:
            return
        
        try:
            properties = {
                "revenue": amount,
                "currency": currency,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if plan:
                properties["plan"] = plan
            
            if metadata:
                properties.update(metadata)
            
            self.track(
                user_id=user_id,
                event=AnalyticsEvent.CHECKOUT_COMPLETED,
                properties=properties
            )
            
            logger.info(f"💰 Revenue tracked: ${amount} {currency} from user {user_id}")
        
        except Exception as e:
            logger.error(f"❌ Error tracking revenue: {e}")
    
    
    def get_feature_flag(
        self,
        user_id: str,
        flag_key: str,
        default: bool = False
    ) -> bool:
        """
        Obtiene valor de feature flag para usuario
        
        Args:
            user_id: ID del usuario
            flag_key: Clave del feature flag
            default: Valor por defecto si no se puede obtener
        
        Returns:
            bool: Si el feature está habilitado
        
        Example:
            show_new_ui = analytics.get_feature_flag(
                user_id="123",
                flag_key="new_dashboard_ui"
            )
        """
        if not self.enabled:
            return default
        
        try:
            return posthog.feature_enabled(flag_key, user_id) or default
        except Exception as e:
            logger.error(f"❌ Error getting feature flag: {e}")
            return default
    
    
    def create_funnel_tracking(
        self,
        user_id: str,
        funnel_name: str,
        step: str,
        properties: Optional[Dict[str, Any]] = None
    ):
        """
        Trackea paso en funnel de conversión
        
        Args:
            user_id: ID del usuario
            funnel_name: Nombre del funnel (ej: "signup_flow")
            step: Paso actual (ej: "email_entered", "plan_selected")
            properties: Propiedades adicionales
        
        Example:
            # Signup funnel
            analytics.create_funnel_tracking(
                user_id="123",
                funnel_name="signup_flow",
                step="email_entered"
            )
            
            analytics.create_funnel_tracking(
                user_id="123",
                funnel_name="signup_flow",
                step="plan_selected",
                properties={"plan": "pro"}
            )
        """
        if not self.enabled:
            return
        
        event_properties = properties or {}
        event_properties["funnel_name"] = funnel_name
        event_properties["funnel_step"] = step
        
        self.track(
            user_id=user_id,
            event=f"funnel_{funnel_name}_{step}",
            properties=event_properties
        )
    
    
    def group(
        self,
        user_id: str,
        group_type: str,
        group_key: str,
        group_properties: Optional[Dict[str, Any]] = None
    ):
        """
        Asocia usuario a un grupo (ej: company, team)
        
        Args:
            user_id: ID del usuario
            group_type: Tipo de grupo ("company", "team", etc.)
            group_key: ID del grupo
            group_properties: Propiedades del grupo
        """
        if not self.enabled:
            return
        
        try:
            posthog.group_identify(
                group_type=group_type,
                group_key=group_key,
                properties=group_properties or {}
            )
            
            posthog.capture(
                distinct_id=user_id,
                event="$group",
                properties={
                    "$group_type": group_type,
                    "$group_key": group_key
                }
            )
            
            logger.debug(f"👥 User {user_id} grouped: {group_type}={group_key}")
        
        except Exception as e:
            logger.error(f"❌ Error grouping user: {e}")
    
    
    def alias(self, old_id: str, new_id: str):
        """
        Conecta identidad anónima con usuario registrado
        
        Args:
            old_id: ID anónimo (ej: session_id)
            new_id: ID de usuario registrado
        """
        if not self.enabled:
            return
        
        try:
            posthog.alias(old_id, new_id)
            logger.debug(f"🔗 Alias created: {old_id} -> {new_id}")
        except Exception as e:
            logger.error(f"❌ Error creating alias: {e}")
    
    
    def flush(self):
        """Fuerza envío de eventos en cola"""
        if not self.enabled:
            return
        
        try:
            posthog.flush()
        except Exception as e:
            logger.error(f"❌ Error flushing events: {e}")
    
    
    def shutdown(self):
        """Cierra conexión y envía eventos pendientes"""
        if not self.enabled:
            return
        
        try:
            posthog.shutdown()
            logger.info("✅ PostHog shut down")
        except Exception as e:
            logger.error(f"❌ Error shutting down PostHog: {e}")


# ============================================================================
# HELPERS PARA EVENTOS COMUNES
# ============================================================================

def track_user_signup(
    user_id: str,
    email: str,
    plan: str,
    referral_code: Optional[str] = None
):
    """Helper para trackear registro de usuario"""
    analytics = get_analytics_service()
    
    analytics.identify(
        user_id=user_id,
        traits={
            "email": email,
            "plan": plan,
            "signup_date": datetime.utcnow().isoformat(),
            "referred_by": referral_code
        }
    )
    
    analytics.track(
        user_id=user_id,
        event=AnalyticsEvent.USER_SIGNED_UP,
        properties={
            "plan": plan,
            "has_referral": bool(referral_code)
        }
    )


def track_subscription_event(
    user_id: str,
    event_type: str,  # "upgraded", "downgraded", "cancelled", "renewed"
    old_plan: Optional[str],
    new_plan: str,
    amount: Optional[float] = None
):
    """Helper para trackear eventos de suscripción"""
    analytics = get_analytics_service()
    
    event_map = {
        "upgraded": AnalyticsEvent.SUBSCRIPTION_UPGRADED,
        "downgraded": AnalyticsEvent.SUBSCRIPTION_DOWNGRADED,
        "cancelled": AnalyticsEvent.SUBSCRIPTION_CANCELLED,
        "renewed": AnalyticsEvent.SUBSCRIPTION_RENEWED
    }
    
    properties = {
        "old_plan": old_plan,
        "new_plan": new_plan
    }
    
    if amount:
        properties["amount"] = amount
        analytics.track_revenue(user_id, amount, plan=new_plan)
    
    analytics.track(
        user_id=user_id,
        event=event_map.get(event_type, AnalyticsEvent.SUBSCRIPTION_UPGRADED),
        properties=properties
    )
    
    # Actualizar propiedades de usuario
    analytics.set_user_properties(
        user_id=user_id,
        properties={"plan": new_plan}
    )


def track_feature_usage(
    user_id: str,
    feature: str,
    metadata: Optional[Dict[str, Any]] = None
):
    """Helper para trackear uso de features"""
    analytics = get_analytics_service()
    
    properties = {"feature": feature}
    if metadata:
        properties.update(metadata)
    
    analytics.track(
        user_id=user_id,
        event=f"{feature}_used",
        properties=properties
    )


# ============================================================================
# SINGLETON
# ============================================================================

_analytics_instance = None

def get_analytics_service() -> AnalyticsService:
    """Obtiene instancia singleton del servicio"""
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = AnalyticsService()
    return _analytics_instance


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "AnalyticsService",
    "AnalyticsEvent",
    "get_analytics_service",
    "track_user_signup",
    "track_subscription_event",
    "track_feature_usage"
]
