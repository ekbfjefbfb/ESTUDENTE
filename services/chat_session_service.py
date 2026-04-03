import asyncio
import logging
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc
from models.models import ChatSession, ChatMessage, User

logger = logging.getLogger("chat_session_service")

class ChatSessionService:
    """
    Servicio Maestro para la gestión de hilos de chat multi-sesión.
    Maneja persistencia en SQL para historial completo e inteligente.
    """
    
    def create_session(self, db: Session, user_id: str, title: str = "Nueva Conversación") -> ChatSession:
        """Crea una nueva sesión de chat persistente."""
        session_id = str(uuid.uuid4())
        db_session = ChatSession(
            id=session_id,
            user_id=user_id,
            title=title
        )
        db.add(db_session)
        db.commit()
        db.refresh(db_session)
        logger.info(f"Creada nueva sesión de chat: {session_id} para user_id={user_id}")
        return db_session

    def get_user_sessions(self, db: Session, user_id: str, limit: int = 50) -> List[ChatSession]:
        """Obtiene la lista de hilos de chat del usuario."""
        return db.query(ChatSession).filter(
            ChatSession.user_id == user_id,
            ChatSession.is_active == True
        ).order_by(desc(ChatSession.updated_at)).limit(limit).all()

    def get_session(self, db: Session, session_id: str, user_id: str) -> Optional[ChatSession]:
        """Obtiene una sesión validando ownership."""
        return db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
            ChatSession.is_active == True,
        ).first()

    def get_session_history(self, db: Session, session_id: str, user_id: str) -> List[ChatMessage]:
        """Recupera el historial COMPLETO de una sesión para el frontend."""
        session = self.get_session(db, session_id=session_id, user_id=user_id)
        if session is None:
            return []
        return db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.created_at).all()

    def add_message(
        self, 
        db: Session, 
        session_id: str, 
        user_id: str, 
        role: str, 
        content: str, 
        media_metadata: Dict[str, Any] = None,
        request_id: str = None
    ) -> ChatMessage:
        """Guarda un mensaje en la sesión persistente (Multipart support)."""
        session = self.get_session(db, session_id=session_id, user_id=user_id)
        if session is None:
            raise ValueError("session_not_found")

        db_message = ChatMessage(
            id=str(uuid.uuid4()),
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            media_metadata=media_metadata or {},
            request_id=request_id
        )
        db.add(db_message)
        
        # Actualizar el timestamp de la sesión
        db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).update({
            "updated_at": datetime.utcnow()
        })
        
        db.commit()
        db.refresh(db_message)
        return db_message

    def delete_session(self, db: Session, session_id: str, user_id: str) -> bool:
        """Elimina (desactiva) una sesión de chat."""
        updated = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.user_id == user_id,
        ).update({
            "is_active": False
        })
        db.commit()
        if updated:
            logger.info(f"Sesión desactivada: {session_id}")
        return bool(updated)

    async def auto_rename_session(self, session_id: str, first_messages_text: str):
        """
        Lógica de Bautismo Inteligente [Iris Naming Agent].
        Renombra la sesión basándose en el contenido de los primeros mensajes.
        """
        from services.groq_ai_service import chat_with_ai
        
        prompt = f"""Analiza estos primeros mensajes de un chat académico y genera un título 
        CORTO (máximo 5 palabras) y profesional que resuma el tema. Solo responde con el título.
        
        MENSAJES:
        {first_messages_text}"""
        
        try:
            # Llamada rápida a Groq para el nombre
            messages = [{"role": "system", "content": "Eres un bautizador de hilos de chat profesional."},
                        {"role": "user", "content": prompt}]
            
            ai_title = ""
            async for token in await chat_with_ai(messages=messages, user="system_namer", fast_reasoning=True, stream=True):
                if token: ai_title += token
            
            cleaned_title = ai_title.strip().replace('"', '').replace("'", "")
            if cleaned_title and len(cleaned_title) < 100:
                def _rename_sync():
                    from database import SessionLocal

                    db = SessionLocal()
                    try:
                        db.query(ChatSession).filter(ChatSession.id == session_id).update({
                            "title": cleaned_title
                        })
                        db.commit()
                    finally:
                        db.close()

                await asyncio.to_thread(_rename_sync)
                logger.info(f"Sesión {session_id} renombrada automáticamente a: {cleaned_title}")
        except Exception as e:
            logger.error(f"Error al renombrar sesión automáticamente: {e}")

# Singleton para acceso global
chat_session_service = ChatSessionService()
