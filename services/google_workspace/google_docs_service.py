"""
Google Docs Service - Creación y edición automática de documentos
Crea, edita y formatea documentos de Google Docs automáticamente
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json_log_formatter

from services.google_workspace.google_auth_service import google_auth_service
from services.google_workspace.google_drive_service import google_drive_service
from services.smart_cache_service import smart_cache

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("google_docs_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class GoogleDocsService:
    """
    Servicio completo de Google Docs
    Creación, edición y formateo automático de documentos
    """
    
    def __init__(self):
        self.document_templates = {
            "report": {
                "title": "📊 Reporte Ejecutivo",
                "sections": ["Resumen Ejecutivo", "Análisis", "Conclusiones", "Recomendaciones"]
            },
            "proposal": {
                "title": "💼 Propuesta Comercial",
                "sections": ["Objetivo", "Propuesta", "Cronograma", "Presupuesto"]
            },
            "meeting_notes": {
                "title": "📝 Notas de Reunión",
                "sections": ["Participantes", "Agenda", "Discusión", "Acciones"]
            },
            "project_plan": {
                "title": "🚀 Plan de Proyecto",
                "sections": ["Objetivos", "Alcance", "Cronograma", "Recursos", "Riesgos"]
            }
        }
    
    async def _get_docs_service(self, user_email: str):
        """Obtiene el servicio de Google Docs para un usuario."""
        credentials = await google_auth_service.get_valid_credentials(user_email)
        if not credentials:
            raise ValueError(f"No valid credentials for user: {user_email}")
        
        return build('docs', 'v1', credentials=credentials)
    
    async def create_document(self, user_email: str, title: str, 
                            template: Optional[str] = None,
                            folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Crea un nuevo documento de Google Docs
        
        Args:
            user_email: Email del usuario
            title: Título del documento
            template: Template a usar (opcional)
            folder_id: ID de carpeta donde guardar (opcional)
            
        Returns:
            Dict con información del documento creado
        """
        try:
            service = await self._get_docs_service(user_email)
            
            # Crear documento
            document = service.documents().create(body={'title': title}).execute()
            document_id = document['documentId']
            
            # Mover a carpeta específica si se especifica
            if folder_id:
                drive_service = await google_drive_service._get_drive_service(user_email)
                drive_service.files().update(
                    fileId=document_id,
                    addParents=folder_id,
                    removeParents='root'
                ).execute()
            
            # Aplicar template si se especifica
            if template and template in self.document_templates:
                await self._apply_template(service, document_id, template)
            
            # Obtener información completa del documento
            doc_info = service.documents().get(documentId=document_id).execute()
            
            logger.info({
                "event": "document_created",
                "user_email": user_email,
                "document_title": title,
                "document_id": document_id,
                "template": template,
                "folder_id": folder_id
            })
            
            return {
                "document_id": document_id,
                "title": doc_info['title'],
                "web_view_link": f"https://docs.google.com/document/d/{document_id}/edit",
                "created_time": datetime.utcnow().isoformat(),
                "template_applied": template is not None
            }
            
        except Exception as e:
            logger.error({
                "event": "create_document_error",
                "user_email": user_email,
                "title": title,
                "error": str(e)
            })
            raise
    
    async def _apply_template(self, service, document_id: str, template_name: str):
        """Aplica un template predefinido al documento."""
        template = self.document_templates[template_name]
        
        requests = []
        index = 1
        
        # Título principal
        requests.append({
            'insertText': {
                'location': {'index': index},
                'text': f"{template['title']}\n\n"
            }
        })
        index += len(template['title']) + 2
        
        # Formatear título
        requests.append({
            'updateTextStyle': {
                'range': {'startIndex': 1, 'endIndex': len(template['title']) + 1},
                'textStyle': {
                    'bold': True,
                    'fontSize': {'magnitude': 18, 'unit': 'PT'}
                },
                'fields': 'bold,fontSize'
            }
        })
        
        # Agregar fecha
        date_text = f"Fecha: {datetime.now().strftime('%d/%m/%Y')}\n\n"
        requests.append({
            'insertText': {
                'location': {'index': index},
                'text': date_text
            }
        })
        index += len(date_text)
        
        # Agregar secciones
        for section in template['sections']:
            section_text = f"{section}\n"
            requests.append({
                'insertText': {
                    'location': {'index': index},
                    'text': section_text
                }
            })
            
            # Formatear encabezado de sección
            requests.append({
                'updateTextStyle': {
                    'range': {'startIndex': index, 'endIndex': index + len(section)},
                    'textStyle': {
                        'bold': True,
                        'fontSize': {'magnitude': 14, 'unit': 'PT'}
                    },
                    'fields': 'bold,fontSize'
                }
            })
            
            index += len(section_text)
            
            # Agregar contenido placeholder
            content_text = "[Contenido de la sección]\n\n"
            requests.append({
                'insertText': {
                    'location': {'index': index},
                    'text': content_text
                }
            })
            index += len(content_text)
        
        # Ejecutar todas las requests
        service.documents().batchUpdate(
            documentId=document_id,
            body={'requests': requests}
        ).execute()
    
    async def add_content(self, user_email: str, document_id: str, 
                         content: str, position: str = "end",
                         formatting: Optional[Dict[str, Any]] = None) -> bool:
        """
        Agrega contenido a un documento existente
        
        Args:
            user_email: Email del usuario
            document_id: ID del documento
            content: Contenido a agregar
            position: Posición donde agregar ("end", "beginning", o índice específico)
            formatting: Opciones de formato (opcional)
            
        Returns:
            True si se agregó exitosamente
        """
        try:
            service = await self._get_docs_service(user_email)
            
            # Obtener documento para saber el índice final
            doc = service.documents().get(documentId=document_id).execute()
            
            if position == "end":
                index = len(doc['body']['content'][0]['paragraph']['elements'][0]['textRun']['content']) - 1
            elif position == "beginning":
                index = 1
            else:
                index = int(position)
            
            requests = []
            
            # Insertar contenido
            requests.append({
                'insertText': {
                    'location': {'index': index},
                    'text': content
                }
            })
            
            # Aplicar formato si se especifica
            if formatting:
                requests.append({
                    'updateTextStyle': {
                        'range': {
                            'startIndex': index,
                            'endIndex': index + len(content)
                        },
                        'textStyle': formatting,
                        'fields': ','.join(formatting.keys())
                    }
                })
            
            # Ejecutar requests
            service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            logger.info({
                "event": "content_added",
                "user_email": user_email,
                "document_id": document_id,
                "content_length": len(content),
                "position": position
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "add_content_error",
                "user_email": user_email,
                "document_id": document_id,
                "error": str(e)
            })
            return False
    
    async def replace_text(self, user_email: str, document_id: str,
                          find_text: str, replace_text: str) -> int:
        """
        Reemplaza texto en un documento
        
        Args:
            user_email: Email del usuario
            document_id: ID del documento
            find_text: Texto a buscar
            replace_text: Texto de reemplazo
            
        Returns:
            Número de reemplazos realizados
        """
        try:
            service = await self._get_docs_service(user_email)
            
            requests = [{
                'replaceAllText': {
                    'containsText': {
                        'text': find_text,
                        'matchCase': False
                    },
                    'replaceText': replace_text
                }
            }]
            
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            # Contar reemplazos
            replacements = 0
            for reply in result.get('replies', []):
                if 'replaceAllText' in reply:
                    replacements += reply['replaceAllText'].get('occurrencesChanged', 0)
            
            logger.info({
                "event": "text_replaced",
                "user_email": user_email,
                "document_id": document_id,
                "find_text": find_text,
                "replacements": replacements
            })
            
            return replacements
            
        except Exception as e:
            logger.error({
                "event": "replace_text_error",
                "user_email": user_email,
                "document_id": document_id,
                "error": str(e)
            })
            return 0
    
    async def insert_table(self, user_email: str, document_id: str,
                          rows: int, columns: int, position: str = "end",
                          data: Optional[List[List[str]]] = None) -> bool:
        """
        Inserta una tabla en el documento
        
        Args:
            user_email: Email del usuario
            document_id: ID del documento
            rows: Número de filas
            columns: Número de columnas
            position: Posición donde insertar
            data: Datos para llenar la tabla (opcional)
            
        Returns:
            True si se insertó exitosamente
        """
        try:
            service = await self._get_docs_service(user_email)
            
            # Determinar posición
            if position == "end":
                doc = service.documents().get(documentId=document_id).execute()
                index = len(doc['body']['content'][-1]['paragraph']['elements'][0]['textRun']['content'])
            else:
                index = int(position)
            
            requests = []
            
            # Insertar tabla
            requests.append({
                'insertTable': {
                    'location': {'index': index},
                    'rows': rows,
                    'columns': columns
                }
            })
            
            # Ejecutar inserción de tabla
            result = service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
            
            # Si hay datos, llenar la tabla
            if data:
                await self._fill_table_data(service, document_id, data, index)
            
            logger.info({
                "event": "table_inserted",
                "user_email": user_email,
                "document_id": document_id,
                "rows": rows,
                "columns": columns,
                "has_data": bool(data)
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "insert_table_error",
                "user_email": user_email,
                "document_id": document_id,
                "error": str(e)
            })
            return False
    
    async def _fill_table_data(self, service, document_id: str, data: List[List[str]], table_start_index: int):
        """Llena una tabla con datos."""
        requests = []
        
        for row_idx, row_data in enumerate(data):
            for col_idx, cell_data in enumerate(row_data):
                # Calcular índice de la celda (aproximado)
                cell_index = table_start_index + (row_idx * len(row_data)) + col_idx + 1
                
                requests.append({
                    'insertText': {
                        'location': {'index': cell_index},
                        'text': cell_data
                    }
                })
        
        if requests:
            service.documents().batchUpdate(
                documentId=document_id,
                body={'requests': requests}
            ).execute()
    
    async def get_document_content(self, user_email: str, document_id: str) -> Dict[str, Any]:
        """
        Obtiene el contenido completo de un documento
        
        Returns:
            Dict con el contenido del documento
        """
        try:
            service = await self._get_docs_service(user_email)
            
            doc = service.documents().get(documentId=document_id).execute()
            
            # Extraer texto plano
            content = ""
            for element in doc.get('body', {}).get('content', []):
                if 'paragraph' in element:
                    paragraph = element['paragraph']
                    for elem in paragraph.get('elements', []):
                        if 'textRun' in elem:
                            content += elem['textRun']['content']
            
            return {
                "document_id": document_id,
                "title": doc.get('title', ''),
                "content": content,
                "revision_id": doc.get('revisionId', ''),
                "document_style": doc.get('documentStyle', {}),
                "web_view_link": f"https://docs.google.com/document/d/{document_id}/edit"
            }
            
        except Exception as e:
            logger.error({
                "event": "get_document_content_error",
                "user_email": user_email,
                "document_id": document_id,
                "error": str(e)
            })
            raise
    
    async def create_from_template_and_data(self, user_email: str, template_name: str,
                                          data: Dict[str, Any], title: str,
                                          folder_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Crea un documento desde template y lo llena con datos automáticamente
        
        Args:
            user_email: Email del usuario
            template_name: Nombre del template
            data: Datos para llenar el documento
            title: Título del documento
            folder_id: Carpeta donde guardar
            
        Returns:
            Dict con información del documento creado
        """
        try:
            # Crear documento con template
            doc_info = await self.create_document(
                user_email, title, template_name, folder_id
            )
            
            document_id = doc_info['document_id']
            
            # Reemplazar placeholders con datos reales
            for key, value in data.items():
                placeholder = f"[{key}]"
                await self.replace_text(user_email, document_id, placeholder, str(value))
            
            # Agregar metadatos de generación
            metadata_text = f"\n\n---\nGenerado automáticamente el {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            await self.add_content(
                user_email, 
                document_id, 
                metadata_text,
                "end",
                {"italic": True, "fontSize": {"magnitude": 10, "unit": "PT"}}
            )
            
            logger.info({
                "event": "document_created_from_template",
                "user_email": user_email,
                "template": template_name,
                "document_id": document_id,
                "data_fields": len(data)
            })
            
            return doc_info
            
        except Exception as e:
            logger.error({
                "event": "create_from_template_error",
                "user_email": user_email,
                "template": template_name,
                "error": str(e)
            })
            raise

# Instancia global del servicio
google_docs_service = GoogleDocsService()