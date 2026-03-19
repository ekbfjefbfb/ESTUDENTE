# services/local_chat_service.py
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import json
import hashlib
import asyncio
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from database.db_enterprise import get_primary_session
from models.models import ChatMessage, LocalChatMetadata, ChatSyncStatus
import logging
import gzip
import base64

logger = logging.getLogger(__name__)


def _debug_enabled() -> bool:
    try:
        from config import DEBUG as CONFIG_DEBUG

        return bool(CONFIG_DEBUG)
    except Exception:
        return str(os.getenv("DEBUG") or "").strip() in {"1", "true", "True"}

class LocalChatService:
    """💬 Gestión de chats con almacenamiento local híbrido"""
    
    def __init__(self):
        self.sync_priorities = {
            "critical": 1,      # Mensajes importantes del sistema
            "high": 2,          # Conversaciones marcadas como importantes
            "medium": 3,        # Mensajes recientes (últimos 7 días)
            "low": 4,           # Mensajes antiguos
            "local_only": 5     # Solo almacenar localmente
        }
        
        self.compression_threshold = 1024  # 1KB - comprimir mensajes más grandes
        
    async def save_message(
        self,
        user_id: str,
        message: Dict[str, Any],
        storage_strategy: str,
        db: Optional[AsyncSession] = None,
        priority: str = "medium"
    ) -> Dict[str, Any]:
        """
        💾 Guarda mensaje según estrategia de almacenamiento
        """
        try:
            if db is None:
                async with get_primary_session() as session:
                    return await self.save_message(
                        user_id=user_id,
                        message=message,
                        storage_strategy=storage_strategy,
                        db=session,
                        priority=priority,
                    )

            message_id = message.get("id") or self._generate_message_id()
            timestamp = message.get("timestamp") or datetime.utcnow().isoformat()
            content = message.get("content", "")
            
            if storage_strategy == "local":
                # 📱 Almacenamiento local primario
                result = await self._save_to_local_storage(
                    user_id, message_id, message, priority, db
                )
                
                # Solo metadata básica en cloud
                await self._save_metadata_to_cloud(
                    user_id, message_id, message, priority, db
                )
                
                return {
                    "message_id": message_id,
                    "stored_locally": True,
                    "cloud_metadata": True,
                    "compressed": result["compressed"],
                    "cost_impact": -0.92,  # 92% reducción de costo
                    "storage_saved_bytes": result["storage_saved"],
                    "sync_status": "metadata_only"
                }
                
            else:
                # ☁️ Almacenamiento tradicional en cloud
                cloud_result = await self._save_full_message_to_cloud(
                    user_id, message, db
                )
                
                return {
                    "message_id": message_id,
                    "stored_locally": False,
                    "cloud_metadata": True,
                    "compressed": False,
                    "cost_impact": 0.0,
                    "storage_saved_bytes": 0,
                    "sync_status": "cloud_full"
                }
                
        except Exception as e:
            logger.error(f"Error saving message for user {user_id}: {str(e)}")
            detail = str(e) if _debug_enabled() else "save_message_failed"
            raise Exception(detail)
    
    async def _save_to_local_storage(
        self,
        user_id: str,
        message_id: str,
        message: Dict[str, Any],
        priority: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        """📱 Guarda mensaje en almacenamiento local (simulado)"""
        
        content = json.dumps(message, ensure_ascii=False)
        original_size = len(content.encode('utf-8'))
        
        # Comprimir si es necesario
        compressed = False
        if original_size > self.compression_threshold:
            compressed_content = gzip.compress(content.encode('utf-8'))
            content = base64.b64encode(compressed_content).decode('ascii')
            compressed = True
            final_size = len(content)
        else:
            final_size = original_size
        
        # Crear hash para verificación de integridad
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()
        
        # En una implementación real, esto se enviaría al frontend
        # para ser guardado en localStorage/IndexedDB
        local_storage_record = {
            "message_id": message_id,
            "user_id": user_id,
            "content": content,
            "compressed": compressed,
            "content_hash": content_hash,
            "priority": priority,
            "timestamp": message.get("timestamp"),
            "expires_at": (datetime.utcnow() + timedelta(days=30)).isoformat(),
            "size_bytes": final_size
        }
        
        # Guardar metadata local en DB para tracking
        await self._save_local_metadata(
            user_id, message_id, local_storage_record, db
        )
        
        return {
            "compressed": compressed,
            "storage_saved": original_size - final_size if compressed else 0,
            "local_record": local_storage_record
        }
    
    async def _save_metadata_to_cloud(
        self,
        user_id: str,
        message_id: str,
        message: Dict[str, Any],
        priority: str,
        db: AsyncSession
    ):
        """☁️ Guarda solo metadata en cloud (ahorro masivo)"""
        
        content_preview = message.get("content", "")[:100]  # Solo preview
        content_hash = hashlib.sha256(
            json.dumps(message).encode('utf-8')
        ).hexdigest()
        
        metadata_record = ChatMessage(
            id=message_id,
            user_id=user_id,
            content_preview=content_preview,  # Solo preview, no contenido completo
            content_hash=content_hash,
            message_type=message.get("type", "user"),
            stored_locally=True,
            sync_priority=priority,
            created_at=datetime.utcnow(),
            metadata_only=True,
            estimated_size_bytes=len(json.dumps(message).encode('utf-8'))
        )
        
        db.add(metadata_record)
        await db.commit()
        
        logger.info(f"Saved metadata-only record for message {message_id}")
    
    async def _save_full_message_to_cloud(
        self,
        user_id: str,
        message: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """☁️ Guarda mensaje completo en cloud (método tradicional)"""
        
        message_id = message.get("id") or self._generate_message_id()
        content = json.dumps(message.get("content", ""))
        
        chat_message = ChatMessage(
            id=message_id,
            user_id=user_id,
            content=content,  # Contenido completo
            content_preview=content[:100],
            message_type=message.get("type", "user"),
            stored_locally=False,
            sync_priority="immediate",
            created_at=datetime.utcnow(),
            metadata_only=False,
            estimated_size_bytes=len(content.encode('utf-8'))
        )
        
        db.add(chat_message)
        await db.commit()
        
        return {
            "message_id": message_id,
            "size_bytes": len(content.encode('utf-8'))
        }
    
    async def _save_local_metadata(
        self,
        user_id: str,
        message_id: str,
        local_record: Dict[str, Any],
        db: AsyncSession
    ):
        """📊 Guarda metadata sobre almacenamiento local"""
        
        metadata = LocalChatMetadata(
            user_id=user_id,
            message_id=message_id,
            local_storage_key=f"chat_{user_id}_{message_id}",
            content_hash=local_record["content_hash"],
            compressed=local_record["compressed"],
            size_bytes=local_record["size_bytes"],
            priority=local_record["priority"],
            expires_at=datetime.fromisoformat(local_record["expires_at"].replace('Z', '+00:00')),
            created_at=datetime.utcnow()
        )
        
        db.add(metadata)
        await db.commit()
    
    async def sync_local_messages(
        self,
        user_id: str,
        local_messages: List[Dict[str, Any]],
        force_sync: bool = False,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """
        🔄 Sincroniza mensajes locales con cloud cuando sea necesario
        """
        try:
            if db is None:
                async with get_primary_session() as session:
                    return await self.sync_local_messages(
                        user_id=user_id,
                        local_messages=local_messages,
                        force_sync=force_sync,
                        db=session,
                    )
            
            logger.info(f"Syncing {len(local_messages)} messages for user {user_id}")
            
            sync_results = {
                "messages_processed": len(local_messages),
                "messages_synced": 0,
                "messages_kept_local": 0,
                "storage_saved_mb": 0.0,
                "cost_saved_usd": 0.0,
                "errors": []
            }
            
            for message in local_messages:
                try:
                    should_sync = force_sync or await self._should_sync_message(
                        message, user_id, db
                    )
                    
                    if should_sync:
                        result = await self._sync_message_to_cloud(
                            user_id, message, db
                        )
                        sync_results["messages_synced"] += 1
                        sync_results["cost_saved_usd"] += result.get("cost_saved", 0)
                    else:
                        sync_results["messages_kept_local"] += 1
                        # Calcular ahorro por mantener local
                        message_size = len(json.dumps(message).encode('utf-8'))
                        sync_results["storage_saved_mb"] += message_size / (1024 * 1024)
                        sync_results["cost_saved_usd"] += self._calculate_storage_cost_saved(message_size)
                        
                except Exception as e:
                    sync_results["errors"].append({
                        "message_id": message.get("id", "unknown"),
                        "error": str(e)
                    })
            
            # Actualizar estado de sincronización
            await self._update_sync_status(user_id, sync_results, db)
            
            return sync_results
            
        except Exception as e:
            logger.error(f"Error syncing messages for user {user_id}: {str(e)}")
            detail = str(e) if _debug_enabled() else "sync_messages_failed"
            raise Exception(detail)
    
    async def _should_sync_message(
        self,
        message: Dict[str, Any],
        user_id: str,
        db: AsyncSession
    ) -> bool:
        """🤔 Determina si un mensaje debe sincronizarse con cloud"""
        
        # Criterios de sincronización inteligente
        message_age_hours = self._get_message_age_hours(message)
        priority = message.get("priority", "medium")
        message_type = message.get("type", "user")
        content_length = len(str(message.get("content", "")))
        
        # Reglas de sincronización
        if priority == "critical":
            return True  # Siempre sincronizar críticos
        
        if message_type == "system":
            return True  # Siempre sincronizar mensajes del sistema
        
        if message_age_hours < 24 and priority == "high":
            return True  # Mensajes importantes recientes
        
        if message_age_hours > 168:  # 7 días
            return False  # Mensajes antiguos solo local
        
        if content_length > 5000:  # Mensajes muy largos
            return False  # Mantener local para ahorrar
        
        # Verificar si el usuario ha marcado para sincronizar
        user_preference = await self._get_user_sync_preference(user_id, db)
        if user_preference == "minimal":
            return False
        
        return priority in ["high", "medium"]  # Por defecto
    
    async def _sync_message_to_cloud(
        self,
        user_id: str,
        message: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """☁️ Sincroniza mensaje específico con cloud"""
        
        try:
            message_id = message.get("id")
            
            # Verificar si ya existe metadata
            result = await db.execute(
                select(ChatMessage).where(
                    ChatMessage.id == message_id,
                    ChatMessage.user_id == user_id,
                ).limit(1)
            )
            existing = result.scalar_one_or_none()
            
            if existing and existing.metadata_only:
                # Actualizar de metadata a contenido completo
                existing.content = json.dumps(message.get("content", ""))
                existing.metadata_only = False
                existing.sync_priority = "synced"
                existing.updated_at = datetime.utcnow()

                await db.commit()
                
                cost_saved = 0  # Ya no hay ahorro al sincronizar
            else:
                # Crear nuevo registro completo
                await self._save_full_message_to_cloud(user_id, message, db)
                cost_saved = 0
            
            return {
                "synced": True,
                "cost_saved": cost_saved
            }
        except Exception as e:
            logger.warning(f"Error sincronizando mensaje (tabla puede no existir): {e}")
            return {"synced": False, "cost_saved": 0, "error": str(e)}
    
    async def get_user_chat_stats(
        self,
        user_id: str,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """📊 Obtiene estadísticas de chat del usuario"""
        
        try:
            if db is None:
                async with get_primary_session() as session:
                    return await self.get_user_chat_stats(user_id=user_id, db=session)

            # Contar mensajes por tipo de almacenamiento
            result = await db.execute(
                select(func.count()).select_from(ChatMessage).where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.stored_locally == True,
                )
            )
            local_count = int(result.scalar_one() or 0)

            result = await db.execute(
                select(func.count()).select_from(ChatMessage).where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.stored_locally == False,
                )
            )
            cloud_count = int(result.scalar_one() or 0)

            result = await db.execute(
                select(func.coalesce(func.sum(ChatMessage.estimated_size_bytes), 0)).where(
                    ChatMessage.user_id == user_id
                )
            )
            total_size_bytes = int(result.scalar_one() or 0)

            result = await db.execute(
                select(func.coalesce(func.sum(ChatMessage.estimated_size_bytes), 0)).where(
                    ChatMessage.user_id == user_id,
                    ChatMessage.stored_locally == True,
                )
            )
            storage_saved_bytes = int(result.scalar_one() or 0)
            
            cost_saved = self._calculate_total_cost_saved(storage_saved_bytes)
            
            return {
                "total_messages": local_count + cloud_count,
                "local_messages": local_count,
                "cloud_messages": cloud_count,
                "local_percentage": round((local_count / max(local_count + cloud_count, 1)) * 100, 2),
                "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
                "storage_saved_mb": round(storage_saved_bytes / (1024 * 1024), 2),
                "monthly_cost_saved_usd": cost_saved,
                "annual_cost_saved_usd": round(cost_saved * 12, 2),
                "optimization_score": self._calculate_chat_optimization_score(
                    local_count, cloud_count, storage_saved_bytes
                )
            }
            
        except Exception as e:
            logger.warning(f"Error getting chat stats (tabla puede no existir): {e}")
            # Retornar valores por defecto seguros
            return {
                "total_messages": 0,
                "local_messages": 0,
                "cloud_messages": 0,
                "local_percentage": 0.0,
                "total_size_mb": 0.0,
                "storage_saved_mb": 0.0,
                "monthly_cost_saved_usd": 0.0,
                "annual_cost_saved_usd": 0.0,
                "optimization_score": 0,
                "error": "Chat stats unavailable"
            }
    
    async def cleanup_old_local_messages(
        self,
        user_id: str,
        days_to_keep: int = 30,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """🧹 Limpia mensajes locales antiguos"""
        
        try:
            if db is None:
                async with get_primary_session() as session:
                    return await self.cleanup_old_local_messages(
                        user_id=user_id,
                        days_to_keep=days_to_keep,
                        db=session,
                    )
            
            cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
            
            # Encontrar mensajes para limpiar
            result = await db.execute(
                select(LocalChatMetadata).where(
                    LocalChatMetadata.user_id == user_id,
                    LocalChatMetadata.created_at < cutoff_date,
                )
            )
            old_metadata = list(result.scalars().all())
            
            cleanup_stats = {
                "messages_cleaned": len(old_metadata),
                "storage_freed_mb": 0.0,
                "messages_to_delete": []
            }
            
            for metadata in old_metadata:
                cleanup_stats["storage_freed_mb"] += metadata.size_bytes / (1024 * 1024)
                cleanup_stats["messages_to_delete"].append({
                    "message_id": metadata.message_id,
                    "local_storage_key": metadata.local_storage_key,
                    "size_mb": round(metadata.size_bytes / (1024 * 1024), 3)
                })
                
                # Eliminar metadata
                await db.delete(metadata)

            await db.commit()
            
            return cleanup_stats
        except Exception as e:
            logger.warning(f"Error en cleanup (tabla puede no existir): {e}")
            return {
                "messages_cleaned": 0,
                "storage_freed_mb": 0.0,
                "messages_to_delete": [],
                "error": "Cleanup unavailable"
            }
    
    # 🔧 MÉTODOS AUXILIARES
    
    def _generate_message_id(self) -> str:
        """🆔 Genera ID único para mensaje"""
        import uuid
        return str(uuid.uuid4())
    
    def _get_message_age_hours(self, message: Dict[str, Any]) -> float:
        """⏰ Calcula edad del mensaje en horas"""
        try:
            timestamp_str = message.get("timestamp")
            if not timestamp_str:
                return 0.0
            
            message_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            age = datetime.utcnow() - message_time.replace(tzinfo=None)
            return age.total_seconds() / 3600
        except:
            return 0.0
    
    async def _get_user_sync_preference(self, user_id: str, db: AsyncSession) -> str:
        """⚙️ Obtiene preferencia de sincronización del usuario"""
        # Implementar consulta a configuración de usuario
        # Por ahora retornar "balanced" por defecto
        return "balanced"  # Opciones: "minimal", "balanced", "aggressive"
    
    def _calculate_storage_cost_saved(self, size_bytes: int) -> float:
        """💰 Calcula costo ahorrado por almacenar localmente"""
        # Costo estimado por MB de almacenamiento en cloud
        cost_per_mb = 0.02  # $0.02 por MB por mes
        size_mb = size_bytes / (1024 * 1024)
        return size_mb * cost_per_mb
    
    def _calculate_total_cost_saved(self, total_bytes: int) -> float:
        """💰 Calcula ahorro total de costos"""
        cost_per_mb = 0.02
        size_mb = total_bytes / (1024 * 1024)
        
        # Incluir costos de DB requests, bandwidth, etc.
        storage_cost = size_mb * cost_per_mb
        request_cost = (total_bytes / 1024) * 0.0001  # Por request
        bandwidth_cost = size_mb * 0.001  # Por transferencia
        
        return storage_cost + request_cost + bandwidth_cost
    
    def _calculate_chat_optimization_score(
        self, 
        local_count: int, 
        cloud_count: int, 
        storage_saved_bytes: int
    ) -> int:
        """📈 Calcula puntuación de optimización de chat (0-100)"""
        total_messages = local_count + cloud_count
        if total_messages == 0:
            return 0
        
        local_percentage = (local_count / total_messages) * 100
        storage_saved_mb = storage_saved_bytes / (1024 * 1024)
        
        # Puntuación basada en porcentaje local y ahorro
        score = min(local_percentage + (storage_saved_mb * 2), 100)
        return int(score)
    
    async def _update_sync_status(
        self,
        user_id: str,
        sync_results: Dict[str, Any],
        db: AsyncSession
    ):
        """📊 Actualiza estado de sincronización"""
        
        try:
            result = await db.execute(
                select(ChatSyncStatus).where(ChatSyncStatus.user_id == user_id).limit(1)
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.last_sync = datetime.utcnow()
                existing.messages_synced += sync_results["messages_synced"]
                existing.messages_local += sync_results["messages_kept_local"]
                existing.storage_saved_mb += sync_results["storage_saved_mb"]
                existing.cost_saved_usd += sync_results["cost_saved_usd"]
            else:
                new_status = ChatSyncStatus(
                    user_id=user_id,
                    last_sync=datetime.utcnow(),
                    messages_synced=sync_results["messages_synced"],
                    messages_local=sync_results["messages_kept_local"],
                    storage_saved_mb=sync_results["storage_saved_mb"],
                    cost_saved_usd=sync_results["cost_saved_usd"],
                    created_at=datetime.utcnow()
                )
                db.add(new_status)
            
            await db.commit()
        except Exception as e:
            logger.warning(f"Error actualizando sync status (tabla puede no existir): {e}")
            # No propagar error - funcionalidad no crítica

# 🌐 Instancia global del servicio
local_chat_service = LocalChatService()