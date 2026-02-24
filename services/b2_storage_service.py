"""
☁️ Backblaze B2 Storage Service
================================

Servicio para gestionar archivos en Backblaze B2:
- Upload de archivos (imágenes, videos, audio, documentos)
- Download de archivos
- Delete de archivos
- Generación de URLs públicas

Integración con WhatsApp para multimedia.
"""

import os
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import hashlib
from b2sdk.v2 import InMemoryAccountInfo, B2Api, UploadSourceBytes

logger = logging.getLogger(__name__)


class B2StorageService:
    """
    Servicio de almacenamiento en Backblaze B2
    """
    
    def __init__(self):
        # Credenciales de B2
        self.application_key_id = os.getenv("B2_APPLICATION_KEY_ID")
        self.application_key = os.getenv("B2_APPLICATION_KEY")
        self.bucket_name = os.getenv("B2_BUCKET_NAME", "mi-backend-super")
        
        # Inicializar API
        self.info = InMemoryAccountInfo()
        self.b2_api = B2Api(self.info)
        self.bucket = None
        self.initialized = False
        
        # Intentar inicializar
        self._initialize()
    
    def _initialize(self):
        """Inicializa la conexión con B2"""
        if not self.application_key_id or not self.application_key:
            logger.warning("⚠️ B2 credentials not configured, service disabled")
            return
        
        try:
            # Autenticar
            self.b2_api.authorize_account("production", self.application_key_id, self.application_key)
            
            # Obtener bucket
            self.bucket = self.b2_api.get_bucket_by_name(self.bucket_name)
            
            self.initialized = True
            logger.info(f"✅ B2StorageService initialized (bucket: {self.bucket_name})")
            
        except Exception as e:
            logger.error(f"❌ Error initializing B2: {e}")
            self.initialized = False
    
    def is_available(self) -> bool:
        """Verifica si el servicio está disponible"""
        return self.initialized
    
    async def upload_file(
        self,
        file_content: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
        folder: str = "uploads"
    ) -> Dict[str, Any]:
        """
        Sube un archivo a B2
        
        Args:
            file_content: Contenido del archivo en bytes
            filename: Nombre del archivo
            content_type: MIME type del archivo
            folder: Carpeta virtual en B2
            
        Returns:
            Dict con información del archivo subido:
            - url: URL pública del archivo
            - file_id: ID del archivo en B2
            - filename: Nombre del archivo
            - size: Tamaño en bytes
        """
        if not self.initialized:
            raise Exception("B2 Storage not available")
        
        try:
            # Generar nombre único
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            file_hash = hashlib.md5(file_content).hexdigest()[:8]
            unique_filename = f"{folder}/{timestamp}_{file_hash}_{filename}"
            
            # Subir archivo
            upload_source = UploadSourceBytes(file_content)
            file_info = self.bucket.upload(
                upload_source=upload_source,
                file_name=unique_filename,
                content_type=content_type
            )
            
            # Generar URL pública
            download_url = self.b2_api.get_download_url_for_file_name(
                bucket_name=self.bucket_name,
                file_name=unique_filename
            )
            
            result = {
                "url": download_url,
                "file_id": file_info.id_,
                "filename": filename,
                "unique_filename": unique_filename,
                "size": len(file_content),
                "content_type": content_type,
                "uploaded_at": datetime.utcnow().isoformat()
            }
            
            logger.info(f"✅ File uploaded to B2: {filename} ({len(file_content)} bytes)")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error uploading to B2: {e}")
            raise Exception(f"Failed to upload file: {str(e)}")
    
    async def delete_file(self, file_id: str, filename: str) -> bool:
        """
        Elimina un archivo de B2
        
        Args:
            file_id: ID del archivo en B2
            filename: Nombre del archivo
            
        Returns:
            True si se eliminó correctamente
        """
        if not self.initialized:
            logger.warning("B2 not initialized, cannot delete file")
            return False
        
        try:
            self.b2_api.delete_file_version(file_id, filename)
            logger.info(f"✅ File deleted from B2: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error deleting from B2: {e}")
            return False
    
    async def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene información de un archivo
        
        Args:
            file_id: ID del archivo en B2
            
        Returns:
            Dict con información del archivo o None
        """
        if not self.initialized:
            return None
        
        try:
            file_version = self.b2_api.get_file_info(file_id)
            return {
                "file_id": file_version.id_,
                "filename": file_version.file_name,
                "size": file_version.size,
                "content_type": file_version.content_type,
                "upload_timestamp": file_version.upload_timestamp
            }
        except Exception as e:
            logger.error(f"❌ Error getting file info: {e}")
            return None
    
    def generate_public_url(self, filename: str) -> str:
        """
        Genera URL pública para un archivo
        
        Args:
            filename: Nombre del archivo (con path)
            
        Returns:
            URL pública
        """
        if not self.initialized:
            return f"https://storage.example.com/{filename}"
        
        return self.b2_api.get_download_url_for_file_name(
            bucket_name=self.bucket_name,
            file_name=filename
        )
    
    async def upload_whatsapp_media(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        chat_id: str
    ) -> Dict[str, Any]:
        """
        Sube multimedia de WhatsApp con organización por chat
        
        Args:
            file_content: Contenido del archivo
            filename: Nombre original
            content_type: MIME type
            chat_id: ID del chat
            
        Returns:
            Dict con información del archivo
        """
        folder = f"whatsapp/{chat_id}"
        return await self.upload_file(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            folder=folder
        )
    
    async def upload_story_media(
        self,
        file_content: bytes,
        filename: str,
        content_type: str,
        user_id: str
    ) -> Dict[str, Any]:
        """
        Sube multimedia para historias de WhatsApp
        
        Args:
            file_content: Contenido del archivo
            filename: Nombre original
            content_type: MIME type
            user_id: ID del usuario
            
        Returns:
            Dict con información del archivo
        """
        folder = f"whatsapp/stories/{user_id}"
        return await self.upload_file(
            file_content=file_content,
            filename=filename,
            content_type=content_type,
            folder=folder
        )


# =============================================
# INSTANCIA GLOBAL (SINGLETON)
# =============================================

_b2_storage: Optional[B2StorageService] = None


def get_b2_storage() -> B2StorageService:
    """
    Obtiene la instancia global de B2StorageService
    
    Returns:
        B2StorageService instance
    """
    global _b2_storage
    if _b2_storage is None:
        _b2_storage = B2StorageService()
    return _b2_storage


# =============================================
# EXPORTS
# =============================================

__all__ = [
    "B2StorageService",
    "get_b2_storage"
]
