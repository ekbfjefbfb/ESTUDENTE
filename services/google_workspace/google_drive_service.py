"""
Google Drive Service - Gestión completa de archivos en Google Drive
Crear, subir, descargar, organizar archivos y carpetas automáticamente
"""

import logging
import io
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload
from googleapiclient.errors import HttpError
import json_log_formatter

from services.google_workspace.google_auth_service import google_auth_service
from services.smart_cache_service import smart_cache

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("google_drive_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class GoogleDriveService:
    """
    Servicio completo de Google Drive
    Maneja archivos, carpetas, permisos y organización automática
    """
    
    def __init__(self):
        self.mime_types = {
            'folder': 'application/vnd.google-apps.folder',
            'document': 'application/vnd.google-apps.document',
            'spreadsheet': 'application/vnd.google-apps.spreadsheet',
            'presentation': 'application/vnd.google-apps.presentation',
            'pdf': 'application/pdf',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'txt': 'text/plain',
            'json': 'application/json',
            'png': 'image/png',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg'
        }
    
    async def _get_drive_service(self, user_email: str):
        """Obtiene el servicio de Google Drive para un usuario."""
        credentials = await google_auth_service.get_valid_credentials(user_email)
        if not credentials:
            raise ValueError(f"No valid credentials for user: {user_email}")
        
        return build('drive', 'v3', credentials=credentials)
    
    async def create_folder(self, user_email: str, folder_name: str, parent_folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Crea una carpeta en Google Drive
        
        Args:
            user_email: Email del usuario
            folder_name: Nombre de la carpeta
            parent_folder_id: ID de la carpeta padre (opcional)
            
        Returns:
            Dict con información de la carpeta creada
        """
        try:
            service = await self._get_drive_service(user_email)
            
            folder_metadata = {
                'name': folder_name,
                'mimeType': self.mime_types['folder']
            }
            
            if parent_folder_id:
                folder_metadata['parents'] = [parent_folder_id]
            
            folder = service.files().create(
                body=folder_metadata,
                fields='id, name, parents, createdTime, webViewLink'
            ).execute()
            
            logger.info({
                "event": "folder_created",
                "user_email": user_email,
                "folder_name": folder_name,
                "folder_id": folder['id'],
                "parent_id": parent_folder_id
            })
            
            return {
                "id": folder['id'],
                "name": folder['name'],
                "parents": folder.get('parents', []),
                "created_time": folder['createdTime'],
                "web_view_link": folder['webViewLink'],
                "type": "folder"
            }
            
        except Exception as e:
            logger.error({
                "event": "create_folder_error",
                "user_email": user_email,
                "folder_name": folder_name,
                "error": str(e)
            })
            raise
    
    async def upload_file(self, user_email: str, file_content: Union[str, bytes], 
                         file_name: str, mime_type: str, 
                         folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Sube un archivo a Google Drive
        
        Args:
            user_email: Email del usuario
            file_content: Contenido del archivo (string o bytes)
            file_name: Nombre del archivo
            mime_type: Tipo MIME del archivo
            folder_id: ID de la carpeta destino (opcional)
            
        Returns:
            Dict con información del archivo subido
        """
        try:
            service = await self._get_drive_service(user_email)
            
            # Preparar metadata del archivo
            file_metadata = {'name': file_name}
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Preparar contenido para upload
            if isinstance(file_content, str):
                file_content = file_content.encode('utf-8')
            
            media = MediaIoBaseUpload(
                io.BytesIO(file_content),
                mimetype=mime_type,
                resumable=True
            )
            
            # Subir archivo
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, name, parents, size, createdTime, webViewLink, webContentLink'
            ).execute()
            
            logger.info({
                "event": "file_uploaded",
                "user_email": user_email,
                "file_name": file_name,
                "file_id": file['id'],
                "size": file.get('size', 0),
                "folder_id": folder_id
            })
            
            return {
                "id": file['id'],
                "name": file['name'],
                "parents": file.get('parents', []),
                "size": int(file.get('size', 0)),
                "created_time": file['createdTime'],
                "web_view_link": file['webViewLink'],
                "download_link": file.get('webContentLink'),
                "type": "file"
            }
            
        except Exception as e:
            logger.error({
                "event": "upload_file_error",
                "user_email": user_email,
                "file_name": file_name,
                "error": str(e)
            })
            raise
    
    async def download_file(self, user_email: str, file_id: str) -> bytes:
        """
        Descarga un archivo de Google Drive
        
        Args:
            user_email: Email del usuario
            file_id: ID del archivo en Drive
            
        Returns:
            Contenido del archivo en bytes
        """
        try:
            service = await self._get_drive_service(user_email)
            
            request = service.files().get_media(fileId=file_id)
            file_content = io.BytesIO()
            downloader = MediaIoBaseDownload(file_content, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            file_content.seek(0)
            content = file_content.read()
            
            logger.info({
                "event": "file_downloaded",
                "user_email": user_email,
                "file_id": file_id,
                "size": len(content)
            })
            
            return content
            
        except Exception as e:
            logger.error({
                "event": "download_file_error",
                "user_email": user_email,
                "file_id": file_id,
                "error": str(e)
            })
            raise
    
    async def list_files(self, user_email: str, folder_id: Optional[str] = None, 
                        query: Optional[str] = None, max_results: int = 100) -> List[Dict[str, Any]]:
        """
        Lista archivos en Google Drive
        
        Args:
            user_email: Email del usuario
            folder_id: ID de carpeta específica (opcional)
            query: Query de búsqueda (opcional)
            max_results: Máximo número de resultados
            
        Returns:
            Lista de archivos
        """
        try:
            service = await self._get_drive_service(user_email)
            
            # Construir query
            search_query = "trashed=false"
            
            if folder_id:
                search_query += f" and '{folder_id}' in parents"
            
            if query:
                search_query += f" and name contains '{query}'"
            
            results = service.files().list(
                q=search_query,
                pageSize=max_results,
                fields="files(id, name, mimeType, size, createdTime, modifiedTime, webViewLink, parents)"
            ).execute()
            
            files = results.get('files', [])
            
            # Procesar archivos
            processed_files = []
            for file in files:
                processed_file = {
                    "id": file['id'],
                    "name": file['name'],
                    "mime_type": file['mimeType'],
                    "size": int(file.get('size', 0)),
                    "created_time": file['createdTime'],
                    "modified_time": file['modifiedTime'],
                    "web_view_link": file['webViewLink'],
                    "parents": file.get('parents', []),
                    "is_folder": file['mimeType'] == self.mime_types['folder']
                }
                processed_files.append(processed_file)
            
            logger.info({
                "event": "files_listed",
                "user_email": user_email,
                "folder_id": folder_id,
                "files_count": len(processed_files)
            })
            
            return processed_files
            
        except Exception as e:
            logger.error({
                "event": "list_files_error",
                "user_email": user_email,
                "folder_id": folder_id,
                "error": str(e)
            })
            raise
    
    async def share_file(self, user_email: str, file_id: str, 
                        share_with: Optional[str] = None, 
                        permission_type: str = "reader") -> Dict[str, Any]:
        """
        Comparte un archivo o carpeta
        
        Args:
            user_email: Email del usuario propietario
            file_id: ID del archivo/carpeta
            share_with: Email con quien compartir (opcional, si no se especifica será público)
            permission_type: Tipo de permiso ("reader", "writer", "commenter")
            
        Returns:
            Dict con información del permiso creado
        """
        try:
            service = await self._get_drive_service(user_email)
            
            if share_with:
                # Compartir con usuario específico
                permission = {
                    'type': 'user',
                    'role': permission_type,
                    'emailAddress': share_with
                }
            else:
                # Compartir públicamente
                permission = {
                    'type': 'anyone',
                    'role': permission_type
                }
            
            result = service.permissions().create(
                fileId=file_id,
                body=permission,
                fields='id, type, role, emailAddress'
            ).execute()
            
            # Obtener link compartido
            file_info = service.files().get(
                fileId=file_id,
                fields='webViewLink, webContentLink'
            ).execute()
            
            logger.info({
                "event": "file_shared",
                "user_email": user_email,
                "file_id": file_id,
                "shared_with": share_with or "public",
                "permission_type": permission_type
            })
            
            return {
                "permission_id": result['id'],
                "type": result['type'],
                "role": result['role'],
                "shared_with": result.get('emailAddress', 'public'),
                "web_view_link": file_info['webViewLink'],
                "download_link": file_info.get('webContentLink')
            }
            
        except Exception as e:
            logger.error({
                "event": "share_file_error",
                "user_email": user_email,
                "file_id": file_id,
                "error": str(e)
            })
            raise
    
    async def delete_file(self, user_email: str, file_id: str) -> bool:
        """
        Elimina un archivo o carpeta
        
        Args:
            user_email: Email del usuario
            file_id: ID del archivo/carpeta
            
        Returns:
            True si se eliminó exitosamente
        """
        try:
            service = await self._get_drive_service(user_email)
            
            service.files().delete(fileId=file_id).execute()
            
            logger.info({
                "event": "file_deleted",
                "user_email": user_email,
                "file_id": file_id
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "delete_file_error",
                "user_email": user_email,
                "file_id": file_id,
                "error": str(e)
            })
            return False
    
    async def create_project_structure(self, user_email: str, project_name: str) -> Dict[str, Any]:
        """
        Crea una estructura de carpetas para un proyecto
        
        Args:
            user_email: Email del usuario
            project_name: Nombre del proyecto
            
        Returns:
            Dict con la estructura creada
        """
        try:
            # Crear carpeta principal del proyecto
            main_folder = await self.create_folder(user_email, project_name)
            main_folder_id = main_folder['id']
            
            # Crear subcarpetas
            subfolders = [
                "📄 Documentos",
                "📊 Hojas de Cálculo", 
                "📁 Archivos",
                "📧 Emails Enviados",
                "🔄 Borradores"
            ]
            
            created_folders = {"main": main_folder}
            
            for subfolder_name in subfolders:
                subfolder = await self.create_folder(
                    user_email, 
                    subfolder_name, 
                    main_folder_id
                )
                # Usar key sin emojis para referencia
                key = subfolder_name.split(" ", 1)[1].lower().replace(" ", "_")
                created_folders[key] = subfolder
            
            logger.info({
                "event": "project_structure_created",
                "user_email": user_email,
                "project_name": project_name,
                "folders_created": len(created_folders)
            })
            
            return {
                "project_name": project_name,
                "main_folder": main_folder,
                "subfolders": created_folders,
                "web_link": main_folder['web_view_link']
            }
            
        except Exception as e:
            logger.error({
                "event": "create_project_structure_error",
                "user_email": user_email,
                "project_name": project_name,
                "error": str(e)
            })
            raise
    
    async def get_storage_info(self, user_email: str) -> Dict[str, Any]:
        """
        Obtiene información del almacenamiento de Google Drive
        
        Returns:
            Dict con información de almacenamiento
        """
        try:
            service = await self._get_drive_service(user_email)
            
            about = service.about().get(fields='storageQuota, user').execute()
            
            storage_quota = about.get('storageQuota', {})
            user_info = about.get('user', {})
            
            return {
                "user": {
                    "display_name": user_info.get('displayName'),
                    "email": user_info.get('emailAddress'),
                    "photo_link": user_info.get('photoLink')
                },
                "storage": {
                    "limit": int(storage_quota.get('limit', 0)),
                    "usage": int(storage_quota.get('usage', 0)),
                    "usage_in_drive": int(storage_quota.get('usageInDrive', 0)),
                    "usage_in_drive_trash": int(storage_quota.get('usageInDriveTrash', 0))
                }
            }
            
        except Exception as e:
            logger.error({
                "event": "get_storage_info_error",
                "user_email": user_email,
                "error": str(e)
            })
            raise

# Instancia global del servicio
google_drive_service = GoogleDriveService()