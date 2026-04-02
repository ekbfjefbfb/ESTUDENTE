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
    
    plan_id = Column(Integer, ForeignKey("plans.id"), nullable=True)
    plan_started_at = Column(DateTime(timezone=True))
    plan_ends_at = Column(DateTime(timezone=True))
    
    # Tracking de uso (Demo)
    demo_until = Column(DateTime(timezone=True))
    demo_requests_today = Column(Integer, default=0)
    demo_last_reset = Column(DateTime(timezone=True))
    demo_count = Column(Integer, default=0)
    last_demo_date = Column(DateTime)
    
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
    
    # Relaciones
    plan = relationship("Plan", back_populates="users")
    subscriptions = relationship("Subscription", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    sessions = relationship("UserSession", back_populates="user")
    
    # NUEVAS RELACIONES PARA AGENTES PERSONALIZADOS
    profile = relationship("UserProfile", back_populates="user", uselist=False)
    integrations = relationship("ExternalIntegration", back_populates="user")
    
    # 🔥 NUEVAS RELACIONES PARA SISTEMA DE PERMISOS
    
    # 🎯 REFERIDOS
    referrals_made = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    referred_by_relation = relationship("Referral", foreign_keys="Referral.referred_id", back_populates="referred")
    
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
        Verifica si el usuario puede hacer más requests hoy (Demo)
        """
        limits = self.get_plan_limits()
        max_requests = limits.get("requests_per_month", 50)
        
        # Plan enterprise
        if self.plan and self.plan.name.lower() == "enterprise":
            return True
        
        return (self.demo_requests_today or 0) < max_requests
    
    def increment_request_count(self):
        """
        Incrementa el contador de requests del usuario
        """
        now = datetime.utcnow()
        last_reset = self.demo_last_reset or now
        
        if now.date() != last_reset.date():
            self.demo_requests_today = 0
            self.demo_last_reset = now
            
        self.demo_requests_today = (self.demo_requests_today or 0) + 1
    
    def get_remaining_requests(self) -> int:
        """
        Obtiene requests restantes hoy
        """
        limits = self.get_plan_limits()
        max_requests = limits.get("requests_per_month", 50)
        
        if self.plan and self.plan.name.lower() == "enterprise":
            return 9999
        
        return max(0, max_requests - (self.demo_requests_today or 0))
    
    def has_active_subscription(self) -> bool:
        """
        Verifica si tiene suscripción activa
        """
        if not self.plan_ends_at:
            return False
        
        return self.plan_ends_at > datetime.utcnow()
    
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
            "requests_used": self.demo_requests_today or 0,
            "requests_remaining": self.get_remaining_requests(),
            "has_active_subscription": self.has_active_subscription(),
            "created_at": self.created_at.isoformat() if self.created_at else None
        }
        
        if include_sensitive:
            data.update({})
        
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
    "User",
    "Plan",
    "Subscription",
    "Payment",
    "UserSession",
    "UserProfile",
    "OnboardingSession",
    # Integraciones
    "ExternalIntegration",
    "SyncedExternalData",
    # Permisos y Enums de Sistema
    "PlanType",
    "SubscriptionStatus",
    "PaymentStatus",
    "IntegrationStatus",
    "ServiceType",
    "Specialization",
    # Usuario y Referidos
    "Referral",
    "ReferralStatus",
    "DeviceToken",
    "UserContext",
    "UserDocumentIndex",
    # Sesiones de Grabación (NUEVO v5.0)
    "RecordingSession",
    "RecordingSessionStatus",
    "RecordingSessionType",
    "TranscriptChunk",
    "SessionItem",
    "SessionItemStatus",
    "SessionItemType",
    "ScheduledRecording",
    # Enums de Visión
    "VisionProcessingType",
    "ImageQuality"
]