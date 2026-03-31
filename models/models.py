"""
Modelos de Base de Datos Enterprise - Mi Backend Super IA
Incluye modelos para agentes personalizados, perfiles dinámicos y integraciones
"""
from sqlalchemy import Column, String, Integer, DateTime, Float, Text, Boolean, ForeignKey, JSON, func, select, and_, delete, update, Date, Enum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Dict, Any, List, Optional
import enum
import uuid

Base = declarative_base()

class PlanType(str, enum.Enum):
    """Tipos de planes disponibles"""
    DEMO = "demo"
    NORMAL = "normal"
    PRO = "pro"
    ENTERPRISE = "enterprise"

class SubscriptionStatus(str, enum.Enum):
    """Estados de suscripción"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    PENDING = "pending"

class PaymentStatus(str, enum.Enum):
    """Estados de pago"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"
    CANCELLED = "cancelled"

# =============================================
# NUEVOS ENUMS PARA AGENTES PERSONALIZADOS
# =============================================

class AgentType(str, enum.Enum):
    """Tipos de agentes especializados"""
    TUTOR = "tutor"
    MENTOR = "mentor"
    ASSISTANT = "assistant"
    COACH = "coach"
    RESEARCHER = "researcher"
    CREATIVE = "creative"

class Specialization(str, enum.Enum):
    """Especializaciones por dominio"""
    TECHNOLOGY = "technology"
    BUSINESS = "business"
    ACADEMIC = "academic"
    CREATIVE = "creative"
    PERSONAL_DEV = "personal_development"
    LANGUAGE = "language"
    SCIENCE = "science"

class IntegrationStatus(str, enum.Enum):
    """Estados de integración externa"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    EXPIRED = "expired"

class ServiceType(str, enum.Enum):
    """Tipos de servicios integrados"""
    GOOGLE_CALENDAR = "google_calendar"
    GOOGLE_GMAIL = "google_gmail"
    GOOGLE_DRIVE = "google_drive"
    MICROSOFT_OUTLOOK = "microsoft_outlook"
    MICROSOFT_ONEDRIVE = "microsoft_onedrive"
    LINKEDIN = "linkedin"

class VisionProcessingType(str, enum.Enum):
    """Tipos de procesamiento de visión"""
    OCR_BASIC = "ocr_basic"
    OCR_ENHANCED = "ocr_enhanced"
    YOLO_DETECTION = "yolo_detection"
    YOLO_OCR_HYBRID = "yolo_ocr_hybrid"
    DOCUMENT_ANALYSIS = "document_analysis"
    TABLE_EXTRACTION = "table_extraction"

class ImageQuality(str, enum.Enum):
    """Niveles de calidad de imagen"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXCELLENT = "excellent"

# =============================================
# ENUMS PARA SISTEMA MULTI-USUARIO
# =============================================

class OrganizationMemberRole(str, enum.Enum):
    """Roles en una organización"""
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class InvitationStatus(str, enum.Enum):
    """Estados de invitación"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

class ReferralStatus(str, enum.Enum):
    """Estados de referido"""
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"

class Plan(Base):
    """
    Modelo de planes de suscripción
    """
    __tablename__ = "plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Float, nullable=False, default=0.0)
    currency = Column(String(3), default="USD")
    
    # Características del plan
    requests_per_month = Column(Integer, default=0)
    max_file_size_mb = Column(Integer, default=1)
    features = Column(JSON, default=list)
    
    # Configuración
    is_active = Column(Boolean, default=True)
    is_demo = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    users = relationship("User", back_populates="plan")
    subscriptions = relationship("Subscription", back_populates="plan")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte plan a diccionario"""
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "price": self.price,
            "currency": self.currency,
            "requests_per_month": self.requests_per_month,
            "max_file_size_mb": self.max_file_size_mb,
            "features": self.features or [],
            "is_active": self.is_active,
            "is_demo": self.is_demo
        }

class User(Base):
    """
    Modelo de usuario enterprise
    """
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=True, index=True)  # Nullable para registro con teléfono
    full_name = Column(String(100))
    bio = Column(Text)
    hashed_password = Column(String(255), nullable=True)  # Nullable para OAuth/Phone
    
    
    # Estado del usuario
    is_active = Column(Boolean, default=True)
    
    # Plan y suscripción
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    subscription_expires_at = Column(DateTime(timezone=True))
    
    # Tracking de uso
    requests_used_this_month = Column(Integer, default=0)
    last_request_reset = Column(DateTime(timezone=True), default=func.now())
    last_activity = Column(DateTime(timezone=True), default=func.now())
    
    # Metadatos
    profile_data = Column(JSON, default=dict)
    preferences = Column(JSON, default=dict)
    
    # 🔐 OAuth Profile Data (Auto-personalización)
    oauth_profile = Column(JSON, default=dict)  # Perfil completo desde OAuth provider
    profile_picture_url = Column(String(500))
    timezone = Column(String(50), default="UTC")
    preferred_language = Column(String(10), default="en")
    interests = Column(JSON, default=list)  # Lista de intereses del usuario
    oauth_provider = Column(String(20))  # google, microsoft, github, apple
    oauth_access_token = Column(String(500))  # Token para obtener datos fresh
    oauth_refresh_token = Column(String(500))
    oauth_token_expires_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    plan = relationship("Plan", back_populates="users")
    subscriptions = relationship("Subscription", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    documents = relationship("Document", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")
    
    # NUEVAS RELACIONES PARA AGENTES PERSONALIZADOS
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    integrations = relationship("ExternalIntegration", back_populates="user")
    chat_messages = relationship("ChatMessage", back_populates="user")
    
    # 🔥 NUEVAS RELACIONES PARA SISTEMA DE PERMISOS
    permissions = relationship("UserPermissions", back_populates="user", uselist=False)
    storage_strategy = relationship("StorageStrategy", back_populates="user", uselist=False)
    
    # 🎯 NUEVAS RELACIONES PARA SISTEMA MULTI-USUARIO
    referral_code = Column(String(8), unique=True, index=True, nullable=True)  # Código de referido
    referred_by_id = Column(String, ForeignKey("users.id"), nullable=True)  # Referido por
    referrals_made = relationship("Referral", foreign_keys="[Referral.referrer_id]", back_populates="referrer")
    referred_by_relation = relationship("Referral", foreign_keys="[Referral.referred_id]", back_populates="referred", uselist=False)
    
    organization_memberships = relationship("OrganizationMember", back_populates="user")
    sent_invitations = relationship("OrganizationInvitation", back_populates="invited_by")
    vision_jobs = relationship("VisionProcessingJob", back_populates="user")
    vision_analytics = relationship("VisionAnalytics", back_populates="user", uselist=False)
    cost_savings = relationship("CostSavings", back_populates="user", uselist=False)
    local_chat_metadata = relationship("LocalChatMetadata", back_populates="user")
    chat_sync_status = relationship("ChatSyncStatus", back_populates="user", uselist=False)
    
    # 📱 PUSH NOTIFICATIONS
    device_tokens = relationship("DeviceToken", back_populates="user")
    
    def get_plan_limits(self) -> Dict[str, Any]:
        """
        Obtiene los límites del plan del usuario
        """
        if not self.plan:
            return {
                "requests_per_month": 50,  # Plan demo por defecto
                "max_file_size_mb": 1,
                "features": ["basic_chat"]
            }
        
        return {
            "requests_per_month": self.plan.requests_per_month,
            "max_file_size_mb": self.plan.max_file_size_mb,
            "features": self.plan.features or []
        }
    
    def get_user_type(self) -> str:
        """
        Obtiene el tipo de usuario basado en su plan
        """
        if not self.plan:
            return "free"
        
        plan_name = self.plan.name.lower()
        
        type_mapping = {
            "demo": "trial",
            "normal": "basic", 
            "pro": "premium",
            "enterprise": "enterprise"
        }
        
        return type_mapping.get(plan_name, "free")
    
    def is_premium_user(self) -> bool:
        """
        Verifica si es usuario premium
        """
        if not self.plan:
            return False
        return self.plan.name.lower() in ["pro", "enterprise"]
    
    def can_access_feature(self, feature: str) -> bool:
        """
        Verifica si puede acceder a una característica específica
        """
        limits = self.get_plan_limits()
        features = limits.get("features", [])
        
        # Features universales para todos los planes premium
        if self.is_premium_user() and feature in [
            "unlimited_features", "all_features", "priority_support"
        ]:
            return True
        
        return feature in features
    
    def can_make_request(self) -> bool:
        """
        Verifica si el usuario puede hacer más requests este mes
        """
        limits = self.get_plan_limits()
        max_requests = limits.get("requests_per_month", 0)
        
        # Plan enterprise tiene requests ilimitados
        if self.plan and self.plan.name.lower() == "enterprise":
            return True
        
        return self.requests_used_this_month < max_requests
    
    def increment_request_count(self):
        """
        Incrementa el contador de requests del usuario
        """
        # Resetear contador si es un nuevo mes
        now = datetime.utcnow()
        if (not self.last_request_reset or 
            now.month != self.last_request_reset.month or 
            now.year != self.last_request_reset.year):
            self.requests_used_this_month = 0
            self.last_request_reset = now
        
        self.requests_used_this_month += 1
        self.last_activity = now
    
    def get_remaining_requests(self) -> int:
        """
        Obtiene requests restantes este mes
        """
        limits = self.get_plan_limits()
        max_requests = limits.get("requests_per_month", 0)
        
        if self.plan and self.plan.name.lower() == "enterprise":
            return float('inf')
        
        return max(0, max_requests - self.requests_used_this_month)
    
    def has_active_subscription(self) -> bool:
        """
        Verifica si tiene suscripción activa
        """
        if not self.subscription_expires_at:
            return False
        
        return self.subscription_expires_at > datetime.utcnow()
    
    def to_dict(self, include_sensitive: bool = False) -> Dict[str, Any]:
        """
        Convierte usuario a diccionario
        """
        data = {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "user_type": self.get_user_type(),
            "is_premium": self.is_premium_user(),
            "plan": self.plan.to_dict() if self.plan else None,
            "requests_used": self.requests_used_this_month,
            "requests_remaining": self.get_remaining_requests(),
            "has_active_subscription": self.has_active_subscription(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity": self.last_activity.isoformat() if self.last_activity else None
        }
        
        if include_sensitive:
            data.update({
                "profile_data": self.profile_data or {},
                "preferences": self.preferences or {}
            })
        
        return data

class Subscription(Base):
    """
    Modelo de suscripciones
    """
    __tablename__ = "subscriptions"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=False)
    
    # Estado y fechas
    status = Column(Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    cancelled_at = Column(DateTime(timezone=True))
    
    # Configuración de pago
    auto_renew = Column(Boolean, default=True)
    payment_method = Column(String(50))
    gateway = Column(String(50))
    gateway_subscription_id = Column(String(100))
    
    # Metadatos
    payment_metadata = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="subscriptions")
    plan = relationship("Plan", back_populates="subscriptions")
    payments = relationship("Payment", back_populates="subscription")

class Payment(Base):
    """
    Modelo de pagos
    """
    __tablename__ = "payments"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    subscription_id = Column(String, ForeignKey("subscriptions.id"), nullable=True)
    
    # Información del pago
    amount = Column(Float, nullable=False)
    currency = Column(String(3), default="USD")
    description = Column(Text)
    
    # Estado y gateway
    status = Column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    gateway = Column(String(50), nullable=False)
    gateway_transaction_id = Column(String(100))
    gateway_response = Column(JSON)
    
    # Timestamps
    processed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="payments")
    subscription = relationship("Subscription", back_populates="payments")

class Document(Base):
    """
    Modelo de documentos generados
    """
    __tablename__ = "documents"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Información del documento
    title = Column(String(200), nullable=False)
    content = Column(Text)
    document_type = Column(String(50))  # "pdf", "docx", "txt"
    file_path = Column(String(500))
    file_size = Column(Integer)
    
    # Metadatos
    document_metadata = Column(JSON, default=dict)
    is_public = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="documents")

# =============================================
# MODELOS PARA AGENTES PERSONALIZADOS
# =============================================

class UserProfile(Base):
    """
    Perfil dinámico del usuario construido automáticamente
    """
    __tablename__ = "user_profiles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), unique=True, nullable=False)
    
    # Información básica del usuario
    basic_info = Column(JSON, default=dict)  # edad, rol, objetivos iniciales
    
    # Intereses detectados automáticamente
    topic_interests = Column(JSON, default=dict)  # tema -> score de interés
    skill_levels = Column(JSON, default=dict)     # habilidad -> nivel
    
    # Preferencias de comunicación
    communication_preferences = Column(JSON, default=dict)
    preferred_explanation_style = Column(String(50), default="balanced")
    
    # Patrones de actividad
    activity_patterns = Column(JSON, default=dict)
    
    # Progreso de aprendizaje
    learning_progress = Column(JSON, default=dict)
    learning_velocity = Column(Float, default=0.5)
    
    # Estadísticas del perfil
    profile_completeness = Column(Float, default=0.0)
    total_interactions = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="profile")
    learning_patterns = relationship("LearningPattern", back_populates="user_profile")
    personal_agents = relationship("PersonalAgent", back_populates="user_profile")

class LearningPattern(Base):
    """
    Patrones de aprendizaje detectados automáticamente
    """
    __tablename__ = "learning_patterns"
    
    id = Column(Integer, primary_key=True, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    
    # Tipo de patrón detectado
    pattern_type = Column(String(100), nullable=False)  # topic_interest, learning_style, schedule
    pattern_data = Column(JSON, nullable=False)
    
    # Métricas del patrón
    confidence = Column(Float, default=0.0)  # 0.0 - 1.0
    frequency = Column(Integer, default=1)
    
    # Timestamps
    detected_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relaciones
    user_profile = relationship("UserProfile", back_populates="learning_patterns")

class PersonalAgent(Base):
    """
    Agentes personalizados por usuario
    """
    __tablename__ = "personal_agents"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(100), unique=True, nullable=False, index=True)
    user_profile_id = Column(Integer, ForeignKey("user_profiles.id"), nullable=False)
    
    # Configuración del agente
    agent_type = Column(Enum(AgentType), nullable=False)
    specialization = Column(Enum(Specialization), nullable=False)
    
    # Personalidad del agente
    personality_config = Column(JSON, default=dict)
    
    # Configuración adaptativa
    response_templates = Column(JSON, default=dict)
    specialized_prompts = Column(JSON, default=dict)
    learned_preferences = Column(JSON, default=dict)
    
    # Estado del agente
    user_context = Column(Text)
    conversation_memory = Column(JSON, default=list)  # Últimas 20 interacciones
    
    # Métricas del agente
    interaction_count = Column(Integer, default=0)
    effectiveness_score = Column(Float, default=0.5)
    adaptation_level = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_interaction = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user_profile = relationship("UserProfile", back_populates="personal_agents")
    interactions = relationship("AgentInteraction", back_populates="agent")

class AgentInteraction(Base):
    """
    Registro de interacciones con agentes personalizados
    """
    __tablename__ = "agent_interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(100), ForeignKey("personal_agents.agent_id"), nullable=False)
    interaction_id = Column(String(100), unique=True, nullable=False)
    
    # Contenido de la interacción
    user_message = Column(Text, nullable=False)
    agent_response = Column(Text, nullable=False)
    
    # Contexto de la interacción
    context_used = Column(JSON, default=dict)
    personalization_applied = Column(JSON, default=dict)
    
    # Métricas de la interacción
    response_time_ms = Column(Integer)
    user_satisfaction = Column(Float)  # Rating opcional del usuario
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relaciones
    agent = relationship("PersonalAgent", back_populates="interactions")

class OnboardingSession(Base):
    """
    Sesiones de onboarding inteligente
    """
    __tablename__ = "onboarding_sessions"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), nullable=False)
    
    # Estado del onboarding
    current_step = Column(String(50), nullable=False)
    estimated_completion = Column(Float, default=0.0)
    personalization_score = Column(Float, default=0.0)
    
    # Datos recopilados
    collected_data = Column(JSON, default=dict)
    detected_preferences = Column(JSON, default=dict)
    conversation_history = Column(JSON, default=list)
    
    # Estado de finalización
    is_completed = Column(Boolean, default=False)
    completion_duration_seconds = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True))
    
    # Relaciones
    user = relationship("User")

class ExternalIntegration(Base):
    """
    Integraciones con servicios externos
    """
    __tablename__ = "external_integrations"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), nullable=False)
    
    # Configuración de la integración
    service_type = Column(Enum(ServiceType), nullable=False)
    status = Column(Enum(IntegrationStatus), default=IntegrationStatus.DISCONNECTED)
    
    # Configuración OAuth
    access_token_hash = Column(String(255))  # Token encriptado
    refresh_token_hash = Column(String(255))  # Refresh token encriptado
    token_expires_at = Column(DateTime(timezone=True))
    
    # Permisos y configuración
    permissions = Column(JSON, default=list)
    integration_metadata = Column(JSON, default=dict)
    
    # Sincronización
    last_sync_at = Column(DateTime(timezone=True))
    sync_frequency_minutes = Column(Integer, default=60)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="integrations")
    synced_data = relationship("SyncedExternalData", back_populates="integration")

class SyncedExternalData(Base):
    """
    Datos sincronizados desde servicios externos
    """
    __tablename__ = "synced_external_data"
    
    id = Column(Integer, primary_key=True, index=True)
    integration_id = Column(Integer, ForeignKey("external_integrations.id"), nullable=False)
    
    # Tipo de datos
    data_type = Column(String(100), nullable=False)  # calendar_events, emails, files, etc.
    external_id = Column(String(255))  # ID del objeto en el servicio externo
    
    # Contenido sincronizado
    data_content = Column(JSON, nullable=False)
    
    # Metadatos de sincronización
    sync_version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    synced_at = Column(DateTime(timezone=True), server_default=func.now())
    external_updated_at = Column(DateTime(timezone=True))
    
    # Relaciones
    integration = relationship("ExternalIntegration", back_populates="synced_data")

class UserSession(Base):
    """
    Modelo de sesiones de usuario
    """
    __tablename__ = "user_sessions"
    
    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Información de la sesión
    token_hash = Column(String(255), nullable=False)
    device_info = Column(JSON)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    
    # Estado
    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_activity = Column(DateTime(timezone=True), default=func.now())
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relaciones
    user = relationship("User", back_populates="sessions")

# Export de modelos - VERSIÓN COMPLETA
# =============================================
# MODELOS PARA SISTEMA DE PERMISOS INTELIGENTES
# =============================================

class UserPermissions(Base):
    """📱 Permisos otorgados por el usuario"""
    __tablename__ = "user_permissions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    permissions_data = Column(JSON, nullable=False)  # JSON con todos los permisos
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="permissions")

class StorageStrategy(Base):
    """💾 Estrategia de almacenamiento del usuario"""
    __tablename__ = "storage_strategies"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    strategy_config = Column(JSON, nullable=False)  # Configuración de almacenamiento
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="storage_strategy")

class CostSavings(Base):
    """💰 Métricas de ahorro de costos"""
    __tablename__ = "cost_savings"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    monthly_savings_usd = Column(Float, default=0.0)
    annual_savings_usd = Column(Float, default=0.0)
    requests_saved = Column(Integer, default=0)
    storage_saved_mb = Column(Float, default=0.0)
    carbon_saved_kg = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_calculated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="cost_savings")

# =============================================
# MODELOS PARA CHAT LOCAL HÍBRIDO
# =============================================

class LocalChatMetadata(Base):
    """📊 Metadata de mensajes almacenados localmente"""
    __tablename__ = "local_chat_metadata"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    message_id = Column(String(255), nullable=False, unique=True)
    local_storage_key = Column(String(500), nullable=False)  # Clave para localStorage
    content_hash = Column(String(255), nullable=False)  # SHA256 del contenido
    compressed = Column(Boolean, default=False)
    size_bytes = Column(Integer, default=0)
    priority = Column(String(50), default="medium")  # critical, high, medium, low
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="local_chat_metadata")

class ChatSyncStatus(Base):
    """🔄 Estado de sincronización de chat"""
    __tablename__ = "chat_sync_status"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    last_sync = Column(DateTime(timezone=True), nullable=True)
    messages_synced = Column(Integer, default=0)
    messages_local = Column(Integer, default=0)
    storage_saved_mb = Column(Float, default=0.0)
    cost_saved_usd = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="chat_sync_status")

# =============================================
# MODELO DE MENSAJES DE CHAT MEJORADO
# =============================================

class ChatMessage(Base):
    """💬 Modelo mejorado para mensajes de chat híbrido"""
    __tablename__ = "chat_messages"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=True)  # Puede ser null si está solo local
    content_preview = Column(String(500), nullable=True)  # Preview del contenido
    content_hash = Column(String(255), nullable=True)  # Hash para verificación
    message_type = Column(String(50), default="user")  # user, assistant, system
    stored_locally = Column(Boolean, default=False)
    metadata_only = Column(Boolean, default=False)  # Solo metadata, contenido en local
    sync_priority = Column(String(50), default="medium")
    estimated_size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="chat_messages")

# =============================================
# MODELOS PARA VISION PIPELINE - YOLO8 + OCR
# =============================================

class VisionProcessingJob(Base):
    """🎯 Trabajos de procesamiento de visión con YOLO8 + OCR"""
    __tablename__ = "vision_processing_jobs"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    filename = Column(String(500), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    content_type = Column(String(100), nullable=False)
    
    # Configuración de procesamiento
    processing_type = Column(Enum(VisionProcessingType), default=VisionProcessingType.YOLO_OCR_HYBRID)
    enhance_quality = Column(Boolean, default=True)
    detect_tables = Column(Boolean, default=True)
    extract_metadata = Column(Boolean, default=True)
    
    # Resultados
    success = Column(Boolean, default=False)
    extracted_text = Column(Text, nullable=True)
    text_length = Column(Integer, default=0)
    objects_detected = Column(Integer, default=0)
    text_regions_found = Column(Integer, default=0)
    tables_found = Column(Integer, default=0)
    image_quality_score = Column(Float, default=0.0)
    image_quality = Column(Enum(ImageQuality), nullable=True)
    
    # Métricas de procesamiento
    processing_time_seconds = Column(Float, default=0.0)
    device_used = Column(String(50), nullable=True)  # cuda, mps, cpu
    yolo_model_version = Column(String(50), default="YOLOv8n")
    ocr_languages_used = Column(JSON, default=list)
    
    # Metadatos adicionales
    detected_objects_json = Column(JSON, default=list)  # Lista de objetos detectados
    ocr_regions_json = Column(JSON, default=list)  # Regiones de texto extraídas
    error_message = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relación con usuario
    user = relationship("User", back_populates="vision_jobs")

class VisionAnalytics(Base):
    """📊 Analytics agregadas de procesamiento de visión por usuario"""
    __tablename__ = "vision_analytics"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, unique=True)
    
    # Contadores totales
    total_images_processed = Column(Integer, default=0)
    total_text_extracted_chars = Column(Integer, default=0)
    total_objects_detected = Column(Integer, default=0)
    total_tables_extracted = Column(Integer, default=0)
    
    # Métricas de calidad promedio
    avg_image_quality_score = Column(Float, default=0.0)
    avg_processing_time_seconds = Column(Float, default=0.0)
    success_rate_percentage = Column(Float, default=0.0)
    
    # Tipos de procesamiento más usados
    most_used_processing_type = Column(Enum(VisionProcessingType), nullable=True)
    preferred_languages = Column(JSON, default=list)
    
    # Dispositivos utilizados
    cuda_usage_count = Column(Integer, default=0)
    cpu_usage_count = Column(Integer, default=0)
    mps_usage_count = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relación con usuario
    user = relationship("User", back_populates="vision_analytics")

# =============================================
# MODELOS PARA SISTEMA MULTI-USUARIO
# =============================================

class Organization(Base):
    """🏢 Organizaciones - Equipos multi-usuario"""
    __tablename__ = "organizations"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Plan de la organización
    plan_id = Column(String(50), nullable=False)  # starter, creator, business, enterprise
    
    # Configuración de límites compartidos
    shared_message_limit = Column(Integer, nullable=False)  # Mensajes compartidos por mes
    max_members = Column(Integer, nullable=False)  # Máximo de miembros
    
    # Uso actual
    messages_used_this_month = Column(Integer, default=0)
    current_members = Column(Integer, default=1)
    
    # Reseteo de uso
    last_usage_reset = Column(DateTime(timezone=True), default=func.now())
    
    # Metadata
    settings = Column(JSON, default=dict)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relaciones
    members = relationship("OrganizationMember", back_populates="organization")
    invitations = relationship("OrganizationInvitation", back_populates="organization")
    usage_tracking = relationship("UsageTracking", back_populates="organization")


class OrganizationMember(Base):
    """👥 Miembros de una organización"""
    __tablename__ = "organization_members"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    organization_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Rol en la organización
    role = Column(Enum(OrganizationMemberRole), default=OrganizationMemberRole.MEMBER)
    
    # Estado
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), default=func.now())
    
    # Relaciones
    organization = relationship("Organization", back_populates="members")
    user = relationship("User", back_populates="organization_memberships")


class OrganizationInvitation(Base):
    """📨 Invitaciones a organizaciones"""
    __tablename__ = "organization_invitations"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    organization_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    invited_by_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    
    # Información de la invitación
    email = Column(String(100), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)  # Token único para el link
    role = Column(Enum(OrganizationMemberRole), default=OrganizationMemberRole.MEMBER)
    
    # Estado
    status = Column(Enum(InvitationStatus), default=InvitationStatus.PENDING)
    
    # Expiración
    expires_at = Column(DateTime(timezone=True), nullable=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relaciones
    organization = relationship("Organization", back_populates="invitations")
    invited_by = relationship("User", back_populates="sent_invitations")


class UsageTracking(Base):
    """📊 Tracking de uso por organización"""
    __tablename__ = "usage_tracking"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    organization_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Período
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    
    # Uso total del período
    total_messages = Column(Integer, default=0)
    total_voice_minutes = Column(Float, default=0.0)
    total_vision_images = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relación
    organization = relationship("Organization", back_populates="usage_tracking")


class UsageEvent(Base):
    """📝 Eventos de uso individuales"""
    __tablename__ = "usage_events"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    organization_id = Column(String(255), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    
    # Tipo de evento
    event_type = Column(String(50), nullable=False)  # message, voice, vision, search
    
    # Metadata del evento (renamed from 'metadata' to avoid SQLAlchemy reserved word)
    event_metadata = Column(JSON, default=dict)
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Referral(Base):
    """🎁 Sistema de referidos - Marketing viral con validación anti-fraude"""
    __tablename__ = "referrals"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    
    # Referidor (quien compartió)
    referrer_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Referido (quien se registró)
    referred_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    referred_email = Column(String(100), nullable=True)  # Email del referido (antes de registrarse)
    
    # Estado
    status = Column(Enum(ReferralStatus), default=ReferralStatus.PENDING)
    
    # Bonus otorgado
    bonus_granted = Column(Boolean, default=False)
    bonus_days = Column(Integer, default=0)  # Días de trial otorgados (0 hasta validar)
    
    # 🔒 Metadata para detección de fraude (renamed from 'metadata' to avoid SQLAlchemy reserved word)
    referral_metadata = Column(JSON, default=dict)  # {ip, device, registered_at, validated_at}
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relaciones
    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_made")
    referred = relationship("User", foreign_keys=[referred_id], back_populates="referred_by_relation")


# =============================================
# MODELO PARA PUSH NOTIFICATIONS
# =============================================

class DeviceToken(Base):
    """📱 Device tokens para push notifications (Firebase FCM)"""
    __tablename__ = "device_tokens"
    
    id = Column(String(255), primary_key=True, index=True)  # UUID
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Token de dispositivo
    token = Column(Text, nullable=False, unique=True)  # Firebase device token (puede ser largo)
    
    # Información del dispositivo
    platform = Column(String(20), nullable=False)  # ios, android, web
    device_id = Column(String(255), nullable=True)  # ID único del dispositivo
    device_name = Column(String(200), nullable=True)  # Nombre del dispositivo (ej: "iPhone de Alberto")
    
    # Estado
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), default=func.now())
    
    # Relación
    user = relationship("User", back_populates="device_tokens")


# =============================================
# AGENDA IA EN TIEMPO REAL (CLASES)
# =============================================


class RecordingSessionType(str, enum.Enum):
    MANUAL = "manual"
    SCHEDULED_AUTO = "scheduled_auto"
    AGENDA_LIVE = "agenda_live"

class RecordingSessionStatus(str, enum.Enum):
    RECORDING = "recording"
    PROCESSING = "processing"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"

class SessionItemType(str, enum.Enum):
    TASK = "task"
    EVENT = "event"
    KEY_POINT = "key_point"
    SUMMARY = "summary"
    REMINDER = "reminder"

class SessionItemStatus(str, enum.Enum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    DONE = "done"
    CANCELED = "canceled"

class RecordingSession(Base):
    """🎙️ Modelo Unificado de Sesión de Grabación"""
    __tablename__ = "recording_sessions"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    session_type = Column(String(32), default=RecordingSessionType.MANUAL, nullable=False)
    status = Column(String(32), default=RecordingSessionStatus.RECORDING, nullable=False, index=True)
    
    title = Column(String(200), nullable=False)
    teacher_name = Column(String(200), nullable=True)
    
    # Relación opcional con programación
    scheduled_id = Column(String(36), ForeignKey("scheduled_recordings.id", ondelete="SET NULL"), nullable=True)
    
    # Transcripción acumulada
    transcript = Column(Text, default="", nullable=False)
    language = Column(String(10), default="es", nullable=True)
    
    # Resumen y Estado de IA
    summary = Column(Text, nullable=True)
    extracted_state = Column(JSON, default=dict) # Para compatibilidad con AgendaSession
    
    # Timestamps y Duración
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    user = relationship("User")
    chunks = relationship("TranscriptChunk", back_populates="session", cascade="all, delete-orphan")
    items = relationship("SessionItem", back_populates="session", cascade="all, delete-orphan")
    scheduled = relationship("ScheduledRecording", foreign_keys=[scheduled_id])

class TranscriptChunk(Base):
    """📝 Modelo Unificado de Chunk de Transcripción"""
    __tablename__ = "transcript_chunks"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("recording_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    text = Column(Text, nullable=False)
    timestamp_seconds = Column(Integer, nullable=True)
    t_start_ms = Column(Integer, nullable=True) # Para compatibilidad con AgendaChunk
    t_end_ms = Column(Integer, nullable=True)   # Para compatibilidad con AgendaChunk
    
    # Análisis de relevancia
    relevance_label = Column(String(16), nullable=True)
    relevance_reason = Column(Text, nullable=True)
    relevance_signals = Column(JSON, default=list)
    relevance_score = Column(Float, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("RecordingSession", back_populates="chunks")

class SessionItem(Base):
    """🎯 Modelo Unificado de Item Extraído (Tarea, Resumen, etc)"""
    __tablename__ = "session_items"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String(36), ForeignKey("recording_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    item_type = Column(String(32), nullable=False, index=True)
    status = Column(String(32), default=SessionItemStatus.SUGGESTED, nullable=False)

    title = Column(String(400), nullable=True)
    content = Column(Text, nullable=False)

    datetime_start = Column(DateTime(timezone=True), nullable=True)
    datetime_end = Column(DateTime(timezone=True), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)

    priority = Column(String(20), nullable=True)
    order_index = Column(Integer, default=0, nullable=False)
    important = Column(Boolean, default=False)

    source = Column(String(16), default="ai", nullable=False)
    confidence = Column(Float, nullable=True)
    item_metadata = Column(JSON, default=dict)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    session = relationship("RecordingSession", back_populates="items")


# =============================================
# 🤖 AGENDA INTELIGENTE AUTOMATIZADA
# Programación automática de grabaciones vía chat
# =============================================

class ScheduledRecording(Base):
    """🗓️ Grabación programada por usuario vía chat, se ejecuta automáticamente"""
    __tablename__ = "scheduled_recordings"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    class_name = Column(String(200), nullable=False)
    teacher_name = Column(String(200), nullable=True)

    # Cuándo debe ejecutarse
    scheduled_at = Column(DateTime(timezone=True), nullable=False, index=True)
    timezone = Column(String(50), default="America/Mexico_City", nullable=False)

    # Estado del scheduling
    status = Column(String(32), default="pending", nullable=False, index=True)
    # pending → listo para ejecutar
    # recording → en progreso
    # completed → terminó OK
    # missed → no se pudo iniciar (usuario no disponible)
    # cancelled → usuario canceló

    # Ubicación (opcional, para verificar que usuario está en lugar correcto)
    location_lat = Column(Float, nullable=True)
    location_lng = Column(Float, nullable=True)
    location_radius_meters = Column(Integer, default=100)  # Radio permitido
    location_name = Column(String(200), nullable=True)  # "Edificio A", "Aula 302"

    # Relación con grabación real (se llena cuando se ejecuta)
    recording_session_id = Column(String(36), ForeignKey("recording_sessions.id", ondelete="SET NULL"), nullable=True)

    # Metadata de AI
    extracted_from_message = Column(Text, nullable=True)  # Mensaje original
    ai_confidence = Column(Float, default=0.0)  # 0.0-1.0
    ai_reasoning = Column(Text, nullable=True)  # Por qué AI decidió esto

    # Notificaciones
    notification_sent_5min = Column(Boolean, default=False)  # Notificación "en 5 min"
    notification_sent_1min = Column(Boolean, default=False)   # Notificación "ahora"

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    executed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Relaciones
    user = relationship("User")
    recording_session = relationship("RecordingSession", foreign_keys=[recording_session_id])


class UserContext(Base):
    """📍 Contexto en tiempo real del usuario para decisiones inteligentes"""
    __tablename__ = "user_context"

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)

    # Ubicación actual
    current_location_lat = Column(Float, nullable=True)
    current_location_lng = Column(Float, nullable=True)
    location_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Dispositivo
    device_id = Column(String(100), nullable=True)  # Identificador único del celular
    device_battery_level = Column(Integer, nullable=True)  # 0-100
    device_platform = Column(String(20), nullable=True)  # ios, android
    last_device_ping = Column(DateTime(timezone=True), nullable=True)

    # Estado
    timezone = Column(String(50), default="America/Mexico_City")
    is_recording = Column(Boolean, default=False)
    current_recording_id = Column(String(36), nullable=True)

    # Preferencias de automatización
    auto_recording_enabled = Column(Boolean, default=True)  # Puede desactivar
    preferred_notification_time = Column(Integer, default=5)  # Minutos antes

    # Límites para proteger al usuario
    daily_auto_recordings_count = Column(Integer, default=0)  # Reset diario
    daily_auto_recordings_date = Column(Date, nullable=True)  # Fecha del reset

    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User")


class UserDocumentIndex(Base):
    """📄 Índice de documentos del teléfono del usuario (metadatos solo)"""
    __tablename__ = "user_document_index"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    device_id = Column(String(100), nullable=False, index=True)

    # Metadatos del archivo
    filename = Column(String(500), nullable=False)
    file_path = Column(String(1000), nullable=False)  # Ruta local en teléfono
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    created_on_device = Column(DateTime(timezone=True), nullable=True)
    modified_on_device = Column(DateTime(timezone=True), nullable=True)

    # Contenido indexado (preview, no todo el archivo)
    content_preview = Column(Text, nullable=True)  # Primeros 2000 chars
    extracted_text = Column(Text, nullable=True)  # OCR si es imagen/PDF

    # Categorización AI
    document_type = Column(String(50), nullable=True)  # syllabus, notes, assignment, exam, other
    related_class = Column(String(200), nullable=True)  # "Cálculo I", "Física"
    keywords = Column(Text, nullable=True)  # JSON array de palabras clave

    # Si el documento sigue existiendo en el dispositivo
    is_deleted_on_device = Column(Boolean, default=False)

    last_sync = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")


# =============================================
# ACTUALIZAR MODELO USER PARA NUEVAS RELACIONES
# =============================================

# Exportar todos los modelos y enums
__all__ = [
    # Core
    "Base",
    "User",
    "Plan",
    "Subscription",
    "Payment",
    "Document",
    "UserSession",
    # Perfil y agentes
    "UserProfile",
    "LearningPattern",
    "PersonalAgent",
    "AgentInteraction",
    "OnboardingSession",
    # Integraciones
    "ExternalIntegration",
    "SyncedExternalData",
    # Chat
    "ChatMessage",
    "LocalChatMetadata",
    "ChatSyncStatus",
    # Permisos
    "UserPermissions",
    "StorageStrategy",
    "CostSavings",
    # Vision Pipeline
    "VisionProcessingJob",
    "VisionAnalytics",
    # Multi-Usuario
    "Organization",
    "OrganizationMember",
    "OrganizationInvitation",
    "UsageTracking",
    "UsageEvent",
    "Referral",
    # Push Notifications
    "DeviceToken",
    # Sesiones de Grabación
    "RecordingSession",
    "TranscriptChunk",
    "SessionItem",
    # Agenda Inteligente
    "ScheduledRecording",
    "UserContext",
    "UserDocumentIndex",
    # Enums
    "PlanType",
    "SubscriptionStatus",
    "PaymentStatus",
    "AgentType",
    "Specialization",
    "IntegrationStatus",
    "ServiceType",
    "VisionProcessingType",
    "ImageQuality",
    "OrganizationMemberRole",
    "InvitationStatus",
    "ReferralStatus"
]