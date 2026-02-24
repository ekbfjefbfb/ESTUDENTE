"""
Gmail Service - Envío automático de emails con documentos
Envía documentos, reportes y notificaciones automáticamente por Gmail
"""

import logging
import base64
import mimetypes
from datetime import datetime
from typing import Optional, Dict, Any, List, Union
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
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
logger = logging.getLogger("gmail_service")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class GmailService:
    """
    Servicio completo de Gmail
    Envío automático de emails con archivos adjuntos y templates
    """
    
    def __init__(self):
        self.email_templates = {
            "document_share": {
                "subject": "📄 Documento compartido: {document_title}",
                "body": """
Hola,

Te comparto el documento "{document_title}" que fue generado automáticamente.

🔗 Link directo: {document_link}

📂 También está disponible en tu Google Drive.

Este documento fue creado el {creation_date} usando IA.

Saludos,
Tu Asistente IA
                """
            },
            "report_delivery": {
                "subject": "📊 Reporte listo: {report_title}",
                "body": """
Estimado/a,

Tu reporte "{report_title}" ha sido generado exitosamente.

📈 Contiene:
- Análisis automático de datos
- Gráficos y visualizaciones
- Conclusiones y recomendaciones

🔗 Acceder al reporte: {report_link}

📎 También se encuentra adjunto a este email.

Generado automáticamente el {generation_date}.

Saludos,
Sistema Automatizado
                """
            },
            "project_update": {
                "subject": "🚀 Actualización de proyecto: {project_name}",
                "body": """
Equipo,

Actualización automática del proyecto "{project_name}":

📊 Estado actual: {project_status}
📅 Progreso: {progress_percentage}%
📋 Documentos actualizados: {documents_count}

🔗 Carpeta del proyecto: {project_folder_link}

Esta actualización fue generada automáticamente.

Saludos,
Gestor de Proyectos IA
                """
            }
        }
    
    async def _get_gmail_service(self, user_email: str):
        """Obtiene el servicio de Gmail para un usuario."""
        credentials = await google_auth_service.get_valid_credentials(user_email)
        if not credentials:
            raise ValueError(f"No valid credentials for user: {user_email}")
        
        return build('gmail', 'v1', credentials=credentials)
    
    async def send_email(self, user_email: str, to_emails: Union[str, List[str]],
                        subject: str, body: str, html_body: Optional[str] = None,
                        attachments: Optional[List[Dict[str, Any]]] = None,
                        cc: Optional[List[str]] = None,
                        bcc: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Envía un email
        
        Args:
            user_email: Email del remitente
            to_emails: Email(s) destinatario(s)
            subject: Asunto del email
            body: Contenido del email (texto plano)
            html_body: Contenido HTML (opcional)
            attachments: Lista de archivos adjuntos
            cc: Lista de emails en CC
            bcc: Lista de emails en BCC
            
        Returns:
            Dict con información del email enviado
        """
        try:
            service = await self._get_gmail_service(user_email)
            
            # Crear mensaje
            message = MIMEMultipart('alternative')
            message['From'] = user_email
            
            # Manejar destinatarios
            if isinstance(to_emails, str):
                to_emails = [to_emails]
            message['To'] = ', '.join(to_emails)
            
            if cc:
                message['Cc'] = ', '.join(cc)
            if bcc:
                message['Bcc'] = ', '.join(bcc)
            
            message['Subject'] = subject
            
            # Agregar contenido
            text_part = MIMEText(body, 'plain', 'utf-8')
            message.attach(text_part)
            
            if html_body:
                html_part = MIMEText(html_body, 'html', 'utf-8')
                message.attach(html_part)
            
            # Agregar archivos adjuntos
            if attachments:
                for attachment in attachments:
                    await self._add_attachment(message, attachment, user_email)
            
            # Codificar mensaje
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            
            # Enviar email
            sent_message = service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info({
                "event": "email_sent",
                "user_email": user_email,
                "to_emails": to_emails,
                "subject": subject,
                "message_id": sent_message['id'],
                "attachments_count": len(attachments) if attachments else 0
            })
            
            return {
                "message_id": sent_message['id'],
                "thread_id": sent_message['threadId'],
                "to_emails": to_emails,
                "subject": subject,
                "sent_time": datetime.utcnow().isoformat(),
                "status": "sent"
            }
            
        except Exception as e:
            logger.error({
                "event": "send_email_error",
                "user_email": user_email,
                "to_emails": to_emails,
                "subject": subject,
                "error": str(e)
            })
            raise
    
    async def _add_attachment(self, message: MIMEMultipart, attachment: Dict[str, Any], user_email: str):
        """Agrega un archivo adjunto al mensaje."""
        try:
            if 'drive_file_id' in attachment:
                # Archivo desde Google Drive
                file_content = await google_drive_service.download_file(
                    user_email, attachment['drive_file_id']
                )
                filename = attachment.get('filename', 'attachment')
                content_type = attachment.get('content_type', 'application/octet-stream')
            elif 'content' in attachment:
                # Contenido directo
                file_content = attachment['content']
                if isinstance(file_content, str):
                    file_content = file_content.encode('utf-8')
                filename = attachment.get('filename', 'attachment.txt')
                content_type = attachment.get('content_type', 'text/plain')
            else:
                logger.warning({"event": "invalid_attachment", "attachment": attachment})
                return
            
            # Crear adjunto
            part = MIMEBase(*content_type.split('/'))
            part.set_payload(file_content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            
            message.attach(part)
            
        except Exception as e:
            logger.error({
                "event": "add_attachment_error",
                "attachment": attachment,
                "error": str(e)
            })
    
    async def send_document_notification(self, user_email: str, to_emails: Union[str, List[str]],
                                       document_info: Dict[str, Any],
                                       custom_message: Optional[str] = None) -> Dict[str, Any]:
        """
        Envía notificación de documento compartido
        
        Args:
            user_email: Email del remitente
            to_emails: Email(s) destinatario(s)
            document_info: Información del documento
            custom_message: Mensaje personalizado (opcional)
            
        Returns:
            Dict con información del email enviado
        """
        try:
            template = self.email_templates["document_share"]
            
            # Personalizar contenido
            subject = template["subject"].format(
                document_title=document_info.get('title', 'Documento')
            )
            
            if custom_message:
                body = custom_message
            else:
                body = template["body"].format(
                    document_title=document_info.get('title', 'Documento'),
                    document_link=document_info.get('web_view_link', ''),
                    creation_date=datetime.now().strftime('%d/%m/%Y %H:%M')
                )
            
            # Enviar email
            result = await self.send_email(
                user_email=user_email,
                to_emails=to_emails,
                subject=subject,
                body=body
            )
            
            logger.info({
                "event": "document_notification_sent",
                "user_email": user_email,
                "document_id": document_info.get('id'),
                "recipients": len(to_emails) if isinstance(to_emails, list) else 1
            })
            
            return result
            
        except Exception as e:
            logger.error({
                "event": "send_document_notification_error",
                "user_email": user_email,
                "document_info": document_info,
                "error": str(e)
            })
            raise
    
    async def send_report_with_attachment(self, user_email: str, to_emails: Union[str, List[str]],
                                        report_info: Dict[str, Any],
                                        attachment_file_id: str) -> Dict[str, Any]:
        """
        Envía reporte con archivo adjunto
        
        Args:
            user_email: Email del remitente
            to_emails: Email(s) destinatario(s)
            report_info: Información del reporte
            attachment_file_id: ID del archivo en Drive para adjuntar
            
        Returns:
            Dict con información del email enviado
        """
        try:
            template = self.email_templates["report_delivery"]
            
            # Personalizar contenido
            subject = template["subject"].format(
                report_title=report_info.get('title', 'Reporte')
            )
            
            body = template["body"].format(
                report_title=report_info.get('title', 'Reporte'),
                report_link=report_info.get('web_view_link', ''),
                generation_date=datetime.now().strftime('%d/%m/%Y %H:%M')
            )
            
            # Preparar adjunto
            attachments = [{
                'drive_file_id': attachment_file_id,
                'filename': f"{report_info.get('title', 'Reporte')}.pdf"
            }]
            
            # Enviar email
            result = await self.send_email(
                user_email=user_email,
                to_emails=to_emails,
                subject=subject,
                body=body,
                attachments=attachments
            )
            
            logger.info({
                "event": "report_with_attachment_sent",
                "user_email": user_email,
                "report_title": report_info.get('title'),
                "attachment_id": attachment_file_id,
                "recipients": len(to_emails) if isinstance(to_emails, list) else 1
            })
            
            return result
            
        except Exception as e:
            logger.error({
                "event": "send_report_attachment_error",
                "user_email": user_email,
                "report_info": report_info,
                "error": str(e)
            })
            raise
    
    async def send_bulk_emails(self, user_email: str, email_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Envía múltiples emails en lote
        
        Args:
            user_email: Email del remitente
            email_list: Lista de emails a enviar
            
        Returns:
            Lista con resultados de cada envío
        """
        results = []
        
        for email_data in email_list:
            try:
                result = await self.send_email(
                    user_email=user_email,
                    to_emails=email_data['to'],
                    subject=email_data['subject'],
                    body=email_data['body'],
                    html_body=email_data.get('html_body'),
                    attachments=email_data.get('attachments'),
                    cc=email_data.get('cc'),
                    bcc=email_data.get('bcc')
                )
                results.append({"status": "sent", "result": result})
                
            except Exception as e:
                results.append({
                    "status": "failed",
                    "error": str(e),
                    "email_data": email_data
                })
                
                logger.error({
                    "event": "bulk_email_failed",
                    "user_email": user_email,
                    "to": email_data.get('to'),
                    "error": str(e)
                })
        
        logger.info({
            "event": "bulk_emails_completed",
            "user_email": user_email,
            "total_emails": len(email_list),
            "sent": len([r for r in results if r["status"] == "sent"]),
            "failed": len([r for r in results if r["status"] == "failed"])
        })
        
        return results
    
    async def get_sent_emails(self, user_email: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Obtiene lista de emails enviados
        
        Args:
            user_email: Email del usuario
            max_results: Máximo número de resultados
            
        Returns:
            Lista de emails enviados
        """
        try:
            service = await self._get_gmail_service(user_email)
            
            # Buscar emails enviados
            results = service.users().messages().list(
                userId='me',
                labelIds=['SENT'],
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            
            email_list = []
            for message in messages:
                # Obtener detalles del mensaje
                msg = service.users().messages().get(
                    userId='me',
                    id=message['id'],
                    format='metadata',
                    metadataHeaders=['To', 'Subject', 'Date']
                ).execute()
                
                headers = {h['name']: h['value'] for h in msg['payload']['headers']}
                
                email_info = {
                    "message_id": message['id'],
                    "thread_id": msg['threadId'],
                    "to": headers.get('To', ''),
                    "subject": headers.get('Subject', ''),
                    "date": headers.get('Date', ''),
                    "snippet": msg.get('snippet', '')
                }
                
                email_list.append(email_info)
            
            logger.info({
                "event": "sent_emails_retrieved",
                "user_email": user_email,
                "emails_count": len(email_list)
            })
            
            return email_list
            
        except Exception as e:
            logger.error({
                "event": "get_sent_emails_error",
                "user_email": user_email,
                "error": str(e)
            })
            return []
    
    async def create_email_template(self, template_name: str, subject: str, body: str) -> bool:
        """
        Crea un template de email personalizado
        
        Args:
            template_name: Nombre del template
            subject: Asunto del template
            body: Cuerpo del template
            
        Returns:
            True si se creó exitosamente
        """
        try:
            self.email_templates[template_name] = {
                "subject": subject,
                "body": body
            }
            
            # Guardar en caché para persistencia
            await smart_cache.set(
                "email_templates",
                template_name,
                {"subject": subject, "body": body},
                ttl=86400 * 30  # 30 días
            )
            
            logger.info({
                "event": "email_template_created",
                "template_name": template_name
            })
            
            return True
            
        except Exception as e:
            logger.error({
                "event": "create_email_template_error",
                "template_name": template_name,
                "error": str(e)
            })
            return False

# Instancia global del servicio
gmail_service = GmailService()