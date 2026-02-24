"""
📱 WhatsApp Models - Sistema Completo de Mensajería

Modelos para:
- Chats 1-a-1
- Grupos de estudio
- Proyectos colaborativos
- Mensajes
- Llamadas
- E2EE
"""

from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, ForeignKey, Text,
    JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from datetime import datetime
from enum import Enum
import enum

from models.models import Base


# ============================================================================
# ENUMS
# ============================================================================

class ChatType(str, Enum):
    """Tipos de chat"""
    DIRECT = "direct"        # Chat 1-a-1
    GROUP = "group"          # Grupo de estudio
    PROJECT = "project"      # Proyecto colaborativo


class MessageType(str, Enum):
    """Tipos de mensaje"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"         # Nota de voz
    DOCUMENT = "document"
    LOCATION = "location"
    CONTACT = "contact"
    STICKER = "sticker"


class MessageStatus(str, Enum):
    """Estados de mensaje (como WhatsApp)"""
    SENDING = "sending"      # Enviando (reloj)
    SENT = "sent"           # Enviado (1 check)
    DELIVERED = "delivered"  # Entregado (2 checks grises)
    READ = "read"           # Leído (2 checks azules)
    FAILED = "failed"       # Falló


class CallType(str, Enum):
    """Tipos de llamada"""
    VOICE = "voice"
    VIDEO = "video"


class CallStatus(str, Enum):
    """Estados de llamada"""
    RINGING = "ringing"
    ANSWERED = "answered"
    ENDED = "ended"
    MISSED = "missed"
    REJECTED = "rejected"


class StoryPrivacy(str, Enum):
    """Privacidad de historias"""
    PUBLIC = "public"          # Todos los contactos
    CONTACTS = "contacts"      # Solo contactos
    CLOSE_FRIENDS = "close_friends"  # Amigos cercanos
    CUSTOM = "custom"          # Lista personalizada


# ============================================================================
# MODELOS
# ============================================================================

class Chat(Base):
    """
    Chat principal.
    
    Puede ser:
    - DIRECT: Chat 1-a-1 entre dos personas
    - GROUP: Grupo de estudio (como WhatsApp group)
    - PROJECT: Proyecto colaborativo (con deadline y tareas)
    """
    __tablename__ = "whatsapp_chats"
    
    id = Column(String(100), primary_key=True)
    chat_type = Column(SQLEnum(ChatType), nullable=False)
    
    # Info del chat
    name = Column(String(200))              # Solo para grupos/proyectos
    description = Column(Text)              # Descripción
    avatar_url = Column(String(500))        # Foto del grupo
    
    # Configuración
    is_active = Column(Boolean, default=True)
    is_archived = Column(Boolean, default=False)
    is_muted = Column(Boolean, default=False)
    
    # IA
    ai_enabled = Column(Boolean, default=False)
    ai_personality = Column(String(50), default="Mentor")
    
    # Metadata
    created_by = Column(String(100))        # ID del creador
    created_at = Column(DateTime, default=datetime.utcnow)
    last_message_at = Column(DateTime)
    messages_count = Column(Integer, default=0)
    
    # Metadata adicional (JSON)
    extra_metadata = Column(JSON)           # deadline, status, etc
    
    # Relaciones
    members = relationship("ChatMember", back_populates="chat")
    messages = relationship("ChatMessage", back_populates="chat")
    calls = relationship("Call", back_populates="chat")
    
    def to_dict(self):
        return {
            "id": self.id,
            "chat_type": self.chat_type.value,
            "name": self.name,
            "description": self.description,
            "avatar_url": self.avatar_url,
            "is_active": self.is_active,
            "is_archived": self.is_archived,
            "is_muted": self.is_muted,
            "ai_enabled": self.ai_enabled,
            "ai_personality": self.ai_personality,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "messages_count": self.messages_count,
            "metadata": self.extra_metadata
        }


class ChatMember(Base):
    """
    Miembros de un chat.
    
    Roles:
    - admin: Puede modificar grupo, añadir/eliminar miembros
    - member: Miembro normal
    - collaborator: Colaborador de proyecto
    """
    __tablename__ = "chat_members"
    
    id = Column(String(100), primary_key=True)
    chat_id = Column(String(100), ForeignKey("chats.id"), nullable=False)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False)  # ✅ FIXED: ForeignKey
    
    # Rol
    role = Column(String(20), default="member")  # admin, member, collaborator
    
    # Estado
    is_active = Column(Boolean, default=True)
    joined_at = Column(DateTime, default=datetime.utcnow)
    left_at = Column(DateTime)
    
    # Configuración personal
    is_muted = Column(Boolean, default=False)
    is_pinned = Column(Boolean, default=False)
    custom_notifications = Column(JSON)
    
    # Último mensaje leído
    last_read_message_id = Column(String(100))
    last_read_at = Column(DateTime)
    
    # Relaciones
    chat = relationship("Chat", back_populates="members")
    
    def to_dict(self):
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "role": self.role,
            "is_active": self.is_active,
            "joined_at": self.joined_at.isoformat() if self.joined_at else None,
            "left_at": self.left_at.isoformat() if self.left_at else None,
            "is_muted": self.is_muted,
            "is_pinned": self.is_pinned,
            "last_read_at": self.last_read_at.isoformat() if self.last_read_at else None
        }


class ChatMessage(Base):
    """
    Mensaje de chat.
    Soporta texto, imágenes, videos, audios, documentos, etc.
    """
    __tablename__ = "whatsapp_chat_messages"
    
    id = Column(String(100), primary_key=True)
    chat_id = Column(String(100), ForeignKey("chats.id"), nullable=False)
    sender_id = Column(String(100), ForeignKey("users.id"), nullable=False)  # ✅ FIXED: ForeignKey
    
    # Contenido
    content = Column(Text)                  # Texto del mensaje
    message_type = Column(SQLEnum(MessageType), default=MessageType.TEXT)
    
    # Respuestas
    reply_to_id = Column(String(100))       # ID mensaje al que responde
    
    # Menciones
    mentioned_users = Column(JSON)          # Lista de user_ids mencionados
    
    # Adjuntos
    attachments = Column(JSON)              # Lista de archivos adjuntos
    
    # Estado (como WhatsApp)
    status = Column(SQLEnum(MessageStatus), default=MessageStatus.SENDING)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    edited_at = Column(DateTime)
    deleted_at = Column(DateTime)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    
    # E2EE
    is_encrypted = Column(Boolean, default=True)
    encryption_key_id = Column(String(100))
    
    # Metadata
    extra_metadata = Column(JSON)           # Ubicación, contacto, etc
    
    # Relaciones
    chat = relationship("Chat", back_populates="messages")
    
    def to_dict(self):
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "sender_id": self.sender_id,
            "content": self.content,
            "message_type": self.message_type.value,
            "reply_to_id": self.reply_to_id,
            "mentioned_users": self.mentioned_users,
            "attachments": self.attachments,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "edited_at": self.edited_at.isoformat() if self.edited_at else None,
            "deleted_at": self.deleted_at.isoformat() if self.deleted_at else None,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "read_at": self.read_at.isoformat() if self.read_at else None,
            "is_encrypted": self.is_encrypted,
            "metadata": self.extra_metadata
        }


class Call(Base):
    """
    Llamadas de voz/video.
    
    Como WhatsApp: historial de llamadas.
    """
    __tablename__ = "calls"
    
    id = Column(String(100), primary_key=True)
    chat_id = Column(String(100), ForeignKey("chats.id"), nullable=False)
    
    # Participantes
    caller_id = Column(String(100), ForeignKey("users.id"), nullable=False)     # ✅ FIXED: FK
    receiver_id = Column(String(100), ForeignKey("users.id"))                   # ✅ FIXED: FK
    participants = Column(JSON)                         # Para llamadas grupales
    
    # Tipo y estado
    call_type = Column(SQLEnum(CallType), nullable=False)
    status = Column(SQLEnum(CallStatus), default=CallStatus.RINGING)
    
    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    answered_at = Column(DateTime)
    ended_at = Column(DateTime)
    duration = Column(Integer, default=0)               # Segundos
    
    # WebRTC
    room_id = Column(String(200))                       # ID de sala WebRTC
    is_video = Column(Boolean, default=False)
    
    # Metadata
    extra_metadata = Column(JSON)
    
    # Relaciones
    chat = relationship("Chat", back_populates="calls")
    
    def to_dict(self):
        return {
            "id": self.id,
            "chat_id": self.chat_id,
            "caller_id": self.caller_id,
            "receiver_id": self.receiver_id,
            "participants": self.participants,
            "call_type": self.call_type.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "answered_at": self.answered_at.isoformat() if self.answered_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration": self.duration,
            "room_id": self.room_id,
            "is_video": self.is_video,
            "metadata": self.extra_metadata
        }


class EncryptionKey(Base):
    """
    Claves de cifrado E2EE (Signal Protocol).
    
    Cada usuario tiene:
    - Identity key (larga duración)
    - Prekeys (efímeras)
    """
    __tablename__ = "encryption_keys"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False)  # ✅ FIXED: FK
    
    # Tipo de clave
    key_type = Column(String(20), nullable=False)   # identity, prekey, signed_prekey
    
    # Clave pública (se comparte)
    public_key = Column(Text, nullable=False)
    
    # Metadata
    key_id = Column(Integer)                        # ID de prekey
    signature = Column(Text)                        # Firma de signed prekey
    
    # Estado
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "key_type": self.key_type,
            "public_key": self.public_key,
            "key_id": self.key_id,
            "signature": self.signature,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }


class Contact(Base):
    """
    Contactos del usuario.
    
    Como WhatsApp: agenda de contactos.
    """
    __tablename__ = "contacts"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False)       # ✅ FIXED: FK
    contact_user_id = Column(String(100), ForeignKey("users.id"), nullable=False)   # ✅ FIXED: FK
    
    # Info personalizada
    custom_name = Column(String(200))                   # Nombre personalizado
    is_favorite = Column(Boolean, default=False)
    is_blocked = Column(Boolean, default=False)
    
    # Timestamps
    added_at = Column(DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "contact_user_id": self.contact_user_id,
            "custom_name": self.custom_name,
            "is_favorite": self.is_favorite,
            "is_blocked": self.is_blocked,
            "added_at": self.added_at.isoformat() if self.added_at else None
        }


# ============================================================================
# WHATSAPP STORIES (ESTADOS)
# ============================================================================

class WhatsAppStory(Base):
    """
    Historia/Estado de WhatsApp (24 horas)
    
    Como WhatsApp:
    - Publicar imagen/video/texto
    - Expira automáticamente en 24h
    - Ver quién vio tu historia
    - Privacidad configurable
    """
    __tablename__ = "whatsapp_stories"
    
    id = Column(String(100), primary_key=True)
    user_id = Column(String(100), ForeignKey("users.id"), nullable=False)
    
    # Contenido
    content_type = Column(SQLEnum(MessageType), nullable=False)  # IMAGE, VIDEO, TEXT
    content_url = Column(Text)                    # URL del archivo en B2
    text_content = Column(Text)                   # Texto de la historia
    caption = Column(Text)                        # Caption/leyenda
    
    # Multimedia info
    filename = Column(String(500))
    file_size = Column(Integer)
    mime_type = Column(String(100))
    
    # Privacidad
    privacy = Column(SQLEnum(StoryPrivacy), default=StoryPrivacy.CONTACTS)
    allowed_users = Column(JSON, default=list)    # IDs de usuarios permitidos (si privacy=CUSTOM)
    
    # Metadata
    view_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)  # created_at + 24h
    
    # Relaciones
    views = relationship("StoryView", back_populates="story", cascade="all, delete-orphan")
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "content_type": self.content_type.value,
            "content_url": self.content_url,
            "text_content": self.text_content,
            "caption": self.caption,
            "filename": self.filename,
            "file_size": self.file_size,
            "mime_type": self.mime_type,
            "privacy": self.privacy.value,
            "view_count": self.view_count,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_expired": datetime.utcnow() > self.expires_at if self.expires_at else False
        }


class StoryView(Base):
    """
    Vista de una historia
    
    Registra quién vio cada historia y cuándo
    """
    __tablename__ = "story_views"
    
    id = Column(String(100), primary_key=True)
    story_id = Column(String(100), ForeignKey("whatsapp_stories.id"), nullable=False)
    viewer_user_id = Column(String(100), ForeignKey("users.id"), nullable=False)
    
    # Metadata
    viewed_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    story = relationship("WhatsAppStory", back_populates="views")
    
    def to_dict(self):
        return {
            "id": self.id,
            "story_id": self.story_id,
            "viewer_user_id": self.viewer_user_id,
            "viewed_at": self.viewed_at.isoformat() if self.viewed_at else None
        }


# Export
__all__ = [
    "ChatType", "MessageType", "MessageStatus", "CallType", "CallStatus", "StoryPrivacy",
    "Chat", "ChatMember", "ChatMessage", "Call", "EncryptionKey", "Contact",
    "WhatsAppStory", "StoryView"
]
