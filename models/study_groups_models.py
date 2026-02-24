"""
Study Groups Models - Grupos de Estudio Colaborativos
Modelos para grupos de estudio con efecto de red viral
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float, JSON, Enum as SQLEnum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import enum
import uuid

from models.models import Base

# =============================================
# ENUMS
# =============================================

class GroupRole(str, enum.Enum):
    """Roles en grupos de estudio"""
    ADMIN = "admin"          # Creador, todos los permisos
    MODERATOR = "moderator"  # Puede invitar y moderar
    MEMBER = "member"        # Miembro regular

class InvitationStatus(str, enum.Enum):
    """Estado de invitaciones"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"

class MessageType(str, enum.Enum):
    """Tipos de mensajes en chat grupal"""
    TEXT = "text"
    AI_RESPONSE = "ai_response"
    DOCUMENT_SHARE = "document_share"
    SYSTEM = "system"

class ActivityType(str, enum.Enum):
    """Tipos de actividad en grupo"""
    MEMBER_JOINED = "member_joined"
    MEMBER_LEFT = "member_left"
    DOCUMENT_SHARED = "document_shared"
    MESSAGE_SENT = "message_sent"
    EXAM_CREATED = "exam_created"
    STUDY_SESSION = "study_session"

# =============================================
# MODELOS
# =============================================

class StudyGroup(Base):
    """
    Grupo de estudio colaborativo
    
    Permite a estudiantes:
    - Compartir documentos/apuntes
    - Chat grupal con IA que conoce todos los docs
    - Colaborar en estudio
    - Efecto de red viral (1 usuario → 5 amigos)
    """
    __tablename__ = "study_groups"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"grp_{uuid.uuid4().hex[:12]}")
    name = Column(String(200), nullable=False, index=True)
    subject = Column(String(100), index=True)  # "Matemáticas", "Física", etc.
    description = Column(Text)
    
    # Metadata
    created_by = Column(String(50), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Configuración
    is_private = Column(Boolean, default=True)  # Requiere invitación vs abierto
    max_members = Column(Integer, default=50)
    university = Column(String(200))
    course_code = Column(String(50))  # "MATH201", "CS101", etc.
    
    # Status
    is_active = Column(Boolean, default=True, index=True)
    archived_at = Column(DateTime, nullable=True)
    
    # IA en Grupo
    ai_enabled = Column(Boolean, default=False)  # IA activada en grupo
    ai_personality = Column(String(50), default="Mentor")  # Personalidad de IA
    
    # Estadísticas
    members_count = Column(Integer, default=1)  # Denormalizado para performance
    documents_count = Column(Integer, default=0)
    messages_count = Column(Integer, default=0)
    
    # Configuración de notificaciones
    notification_settings = Column(JSON, default={
        "new_member": True,
        "new_document": True,
        "new_message": True,
        "mentions": True
    })
    
    # Relaciones
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    shared_documents = relationship("SharedDocument", back_populates="group", cascade="all, delete-orphan")
    messages = relationship("GroupMessage", back_populates="group", cascade="all, delete-orphan")
    invitations = relationship("GroupInvitation", back_populates="group", cascade="all, delete-orphan")
    activities = relationship("GroupActivity", back_populates="group", cascade="all, delete-orphan")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "name": self.name,
            "subject": self.subject,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_private": self.is_private,
            "members_count": self.members_count,
            "documents_count": self.documents_count,
            "messages_count": self.messages_count,
            "university": self.university,
            "course_code": self.course_code,
            "is_active": self.is_active,
            "ai_enabled": self.ai_enabled,
            "ai_personality": self.ai_personality
        }


class GroupMember(Base):
    """
    Miembro de un grupo de estudio
    
    Tracking de:
    - Rol y permisos
    - Actividad en el grupo
    - Contribuciones
    """
    __tablename__ = "group_members"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"mem_{uuid.uuid4().hex[:12]}")
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(50), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Rol y permisos
    role = Column(SQLEnum(GroupRole), default=GroupRole.MEMBER, nullable=False)
    
    # Metadata
    joined_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    invited_by = Column(String(50), ForeignKey("users.id"), nullable=True)
    
    # 🆕 V2: Perfil personalizado en el grupo (estilo WhatsApp)
    avatar_url = Column(String(500), nullable=True)  # Avatar custom para este grupo
    display_name = Column(String(100), nullable=True)  # Nombre custom en el grupo
    status_message = Column(String(200), nullable=True)  # "Estudiando para el parcial..."
    
    # Actividad
    last_seen_at = Column(DateTime, default=datetime.utcnow)
    messages_count = Column(Integer, default=0)
    documents_shared = Column(Integer, default=0)
    
    # Status
    is_active = Column(Boolean, default=True)
    muted_until = Column(DateTime, nullable=True)  # Silenciar notificaciones
    
    # Relaciones
    group = relationship("StudyGroup", back_populates="members")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "role": self.role.value if self.role else None,
            "avatar_url": self.avatar_url,  # 🆕 V2
            "display_name": self.display_name,  # 🆕 V2
            "status_message": self.status_message,  # 🆕 V2
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "messages_count": self.messages_count,
            "documents_shared": self.documents_shared,
            "is_active": self.is_active
        }


class SharedDocument(Base):
    """
    Documento compartido en biblioteca del grupo
    
    Features:
    - Tracking de engagement (views, downloads)
    - Categorización y tags
    - Permisos de acceso
    """
    __tablename__ = "shared_documents"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"sdoc_{uuid.uuid4().hex[:12]}")
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id = Column(String(50), nullable=False)  # ID del documento original
    
    # Compartido por
    shared_by = Column(String(50), ForeignKey("users.id"), nullable=False)
    shared_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Metadata
    document_type = Column(String(50), default="pdf")  # pdf, notes, audio, image
    title = Column(String(500), nullable=False)
    description = Column(Text)
    file_url = Column(String(1000))  # URL del archivo si está en storage
    
    # Categorización
    tags = Column(JSON, default=[])  # ["examen", "capitulo-3", "importante"]
    category = Column(String(100))  # "Apuntes", "Papers", "Exámenes", etc.
    
    # Engagement metrics
    views_count = Column(Integer, default=0)
    downloads_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    
    # Permisos
    can_download = Column(Boolean, default=True)
    can_edit = Column(Boolean, default=False)
    
    # AI Analysis (opcional)
    ai_summary = Column(Text, nullable=True)  # Resumen generado por IA
    ai_key_concepts = Column(JSON, default=[])  # Conceptos clave extraídos
    
    # Relaciones
    group = relationship("StudyGroup", back_populates="shared_documents")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "group_id": self.group_id,
            "document_id": self.document_id,
            "title": self.title,
            "description": self.description,
            "document_type": self.document_type,
            "shared_by": self.shared_by,
            "shared_at": self.shared_at.isoformat() if self.shared_at else None,
            "tags": self.tags,
            "category": self.category,
            "views_count": self.views_count,
            "downloads_count": self.downloads_count,
            "ai_summary": self.ai_summary,
            "can_download": self.can_download
        }


class GroupMessage(Base):
    """
    Mensaje en chat grupal
    
    Features:
    - Chat entre miembros
    - Respuestas de IA con contexto del grupo
    - Menciones y reacciones
    - Threading (reply_to)
    """
    __tablename__ = "group_messages"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"msg_{uuid.uuid4().hex[:12]}")
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), nullable=True)  # NULL si es mensaje de IA
    
    # Contenido
    content = Column(Text, nullable=False)
    message_type = Column(SQLEnum(MessageType), default=MessageType.TEXT, nullable=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    edited_at = Column(DateTime, nullable=True)
    
    # Contexto (para respuestas IA)
    context = Column(JSON, nullable=True)  # Documentos usados, confidence, etc.
    ai_model = Column(String(50), nullable=True)  # "deepseek-vl:33b"
    
    # Referencias
    reply_to = Column(String(50), ForeignKey("group_messages.id"), nullable=True)
    mentioned_users = Column(JSON, default=[])  # ["user_id_1", "user_id_2"]
    
    # Engagement
    reactions = Column(JSON, default={})  # {"👍": ["user1", "user2"], "❤️": ["user3"]}
    
    # Relaciones
    group = relationship("StudyGroup", back_populates="messages")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "content": self.content,
            "message_type": self.message_type.value if self.message_type else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "reply_to": self.reply_to,
            "mentioned_users": self.mentioned_users,
            "reactions": self.reactions,
            "context": self.context
        }


class GroupInvitation(Base):
    """
    Invitación a grupo de estudio
    
    Features:
    - Invitaciones por email
    - Links de invitación con token
    - Expiración automática
    - Tracking de conversión
    """
    __tablename__ = "group_invitations"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"inv_{uuid.uuid4().hex[:12]}")
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Invitado
    invited_email = Column(String(255), nullable=False, index=True)
    invited_user_id = Column(String(50), ForeignKey("users.id"), nullable=True)
    
    # Invitador
    invited_by = Column(String(50), ForeignKey("users.id"), nullable=False)
    invited_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Token de invitación
    invitation_token = Column(String(100), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime, default=lambda: datetime.utcnow() + timedelta(days=7), nullable=False)
    
    # Status
    status = Column(SQLEnum(InvitationStatus), default=InvitationStatus.PENDING, nullable=False)
    accepted_at = Column(DateTime, nullable=True)
    
    # Relaciones
    group = relationship("StudyGroup", back_populates="invitations")
    
    @staticmethod
    def generate_token() -> str:
        """Genera token único de invitación"""
        return uuid.uuid4().hex
    
    def is_expired(self) -> bool:
        """Verifica si invitación expiró"""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "group_id": self.group_id,
            "invited_email": self.invited_email,
            "invited_by": self.invited_by,
            "invited_at": self.invited_at.isoformat() if self.invited_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "status": self.status.value if self.status else None,
            "invitation_token": self.invitation_token,
            "is_expired": self.is_expired()
        }


class GroupActivity(Base):
    """
    Log de actividad del grupo
    
    Para:
    - Analytics y métricas
    - Feed de actividad
    - Notificaciones
    """
    __tablename__ = "group_activities"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"act_{uuid.uuid4().hex[:12]}")
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(50), ForeignKey("users.id"), nullable=True)
    
    # Actividad
    activity_type = Column(SQLEnum(ActivityType), nullable=False, index=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    activity_metadata = Column(JSON, default={})  # Datos adicionales específicos de cada tipo (RENAMED from 'metadata' to avoid SQLAlchemy conflict)
    
    # Relaciones
    group = relationship("StudyGroup", back_populates="activities")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "group_id": self.group_id,
            "user_id": self.user_id,
            "activity_type": self.activity_type.value if self.activity_type else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "metadata": self.activity_metadata  # Keep 'metadata' in API response for consistency
        }


# =============================================
# CHAT SESSIONS (V2 - Switch Grupo/IA Personal)
# =============================================

class SessionType(str, enum.Enum):
    """Tipo de sesión de chat"""
    GROUP = "group"      # 👥 Chat grupal (todos ven)
    PERSONAL = "personal"  # 🤖 IA personal (privado)


class ChatSession(Base):
    """
    Sesión de chat: puede ser GRUPAL o PERSONAL
    
    Permite al usuario cambiar entre:
    - Modo Grupo: Mensajes visibles para todos
    - Modo IA Personal: Chat privado con IA usando contexto del grupo
    """
    __tablename__ = "chat_sessions"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"sess_{uuid.uuid4().hex[:12]}")
    user_id = Column(String(50), ForeignKey("users.id"), nullable=False, index=True)
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Tipo de sesión
    session_type = Column(SQLEnum(SessionType), nullable=False, default=SessionType.GROUP)
    
    # Estado
    is_active = Column(Boolean, default=True, index=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_message_at = Column(DateTime, nullable=True)
    messages_count = Column(Integer, default=0)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "session_type": self.session_type.value if self.session_type else None,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "messages_count": self.messages_count
        }


class PrivateAIMessage(Base):
    """
    Mensajes privados entre usuario y IA
    
    Cuando el usuario está en modo PERSONAL:
    - Sus mensajes NO van al chat grupal
    - La IA responde usando contexto del grupo (documentos compartidos)
    - Solo el usuario ve estos mensajes
    """
    __tablename__ = "private_ai_messages"
    
    # Identificación
    id = Column(String(50), primary_key=True, default=lambda: f"pvt_{uuid.uuid4().hex[:12]}")
    user_id = Column(String(50), ForeignKey("users.id"), nullable=False, index=True)
    session_id = Column(String(50), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    group_id = Column(String(50), ForeignKey("study_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Mensajes
    user_message = Column(Text, nullable=False)
    ai_response = Column(Text, nullable=False)
    
    # Contexto usado
    context_docs = Column(JSON, default=[])  # IDs de documentos usados por la IA
    context_messages = Column(JSON, default=[])  # IDs de mensajes del grupo usados como contexto
    
    # Attachments (usuario puede enviar docs en modo privado)
    attachments = Column(JSON, default=[])
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    tokens_used = Column(Integer, default=0)  # Para tracking de costos
    
    def to_dict(self) -> Dict[str, Any]:
        """Convierte a diccionario"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "group_id": self.group_id,
            "user_message": self.user_message,
            "ai_response": self.ai_response,
            "context_docs": self.context_docs,
            "context_messages": self.context_messages,
            "attachments": self.attachments,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "tokens_used": self.tokens_used
        }


# =============================================
# FUNCIONES HELPER
# =============================================

def create_default_group_settings() -> Dict[str, Any]:
    """Configuración por defecto de grupo"""
    return {
        "notification_settings": {
            "new_member": True,
            "new_document": True,
            "new_message": True,
            "mentions": True
        },
        "chat_settings": {
            "allow_ai": True,
            "allow_mentions": True,
            "allow_reactions": True
        },
        "privacy_settings": {
            "is_private": True,
            "require_approval": False,
            "allow_invite_links": True
        }
    }
