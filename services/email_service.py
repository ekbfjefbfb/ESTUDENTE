"""
Email Service - Sistema de envío de emails
Versión: Production v1.0
Proveedor: SendGrid / Amazon SES / SMTP
"""
import logging
import os
from typing import List, Optional, Dict, Any
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# =============================================
# CONFIGURACIÓN
# =============================================

EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "sendgrid")  # sendgrid, ses, smtp
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@mibackendsuper.com")
FROM_NAME = os.getenv("FROM_NAME", "Mi Backend Super IA")

# Templates Jinja2
template_env = Environment(
    loader=FileSystemLoader("templates/emails"),
    autoescape=select_autoescape(['html', 'xml'])
)


# =============================================
# EMAIL SERVICE
# =============================================

class EmailService:
    """Servicio para envío de emails con múltiples proveedores"""
    
    def __init__(self):
        self.provider = EMAIL_PROVIDER
        self.from_email = FROM_EMAIL
        self.from_name = FROM_NAME
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """
        Enviar email genérico
        
        Args:
            to_email: Email destinatario
            subject: Asunto del email
            html_content: Contenido HTML
            text_content: Contenido texto plano (opcional)
            attachments: Lista de archivos adjuntos
        
        Returns:
            True si se envió correctamente
        """
        try:
            if self.provider == "sendgrid":
                return await self._send_sendgrid(
                    to_email, subject, html_content, text_content, attachments
                )
            elif self.provider == "ses":
                return await self._send_ses(
                    to_email, subject, html_content, text_content, attachments
                )
            elif self.provider == "smtp":
                return await self._send_smtp(
                    to_email, subject, html_content, text_content, attachments
                )
            else:
                logger.error(f"❌ Proveedor de email no soportado: {self.provider}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Error enviando email a {to_email}: {e}")
            return False
    
    # =============================================
    # SENDGRID
    # =============================================
    
    async def _send_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """Enviar email usando SendGrid"""
        try:
            from sendgrid import SendGridAPIClient
            from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
            
            message = Mail(
                from_email=(self.from_email, self.from_name),
                to_emails=to_email,
                subject=subject,
                html_content=html_content,
                plain_text_content=text_content or ""
            )
            
            # Agregar archivos adjuntos
            if attachments:
                for att in attachments:
                    attachment = Attachment(
                        FileContent(att.get("content")),
                        FileName(att.get("filename")),
                        FileType(att.get("type", "application/octet-stream")),
                        Disposition("attachment")
                    )
                    message.add_attachment(attachment)
            
            sg = SendGridAPIClient(SENDGRID_API_KEY)
            response = sg.send(message)
            
            logger.info(f"✅ Email enviado a {to_email} via SendGrid (status: {response.status_code})")
            return response.status_code in [200, 202]
        
        except Exception as e:
            logger.error(f"❌ Error SendGrid: {e}")
            return False
    
    # =============================================
    # AMAZON SES
    # =============================================
    
    async def _send_ses(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """Enviar email usando Amazon SES"""
        try:
            import boto3
            from botocore.exceptions import ClientError
            
            ses = boto3.client('ses', region_name=os.getenv("AWS_REGION", "us-east-1"))
            
            response = ses.send_email(
                Source=f"{self.from_name} <{self.from_email}>",
                Destination={'ToAddresses': [to_email]},
                Message={
                    'Subject': {'Data': subject, 'Charset': 'UTF-8'},
                    'Body': {
                        'Html': {'Data': html_content, 'Charset': 'UTF-8'},
                        'Text': {'Data': text_content or "", 'Charset': 'UTF-8'}
                    }
                }
            )
            
            logger.info(f"✅ Email enviado a {to_email} via SES (MessageId: {response['MessageId']})")
            return True
        
        except ClientError as e:
            logger.error(f"❌ Error SES: {e.response['Error']['Message']}")
            return False
        except Exception as e:
            logger.error(f"❌ Error SES: {e}")
            return False
    
    # =============================================
    # SMTP
    # =============================================
    
    async def _send_smtp(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """Enviar email usando SMTP"""
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders
            
            msg = MIMEMultipart('alternative')
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Agregar contenido
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Agregar archivos adjuntos
            if attachments:
                for att in attachments:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(att.get("content"))
                    encoders.encode_base64(part)
                    part.add_header('Content-Disposition', f"attachment; filename= {att.get('filename')}")
                    msg.attach(part)
            
            # Enviar
            smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
            smtp_port = int(os.getenv("SMTP_PORT", "587"))
            smtp_user = os.getenv("SMTP_USER")
            smtp_password = os.getenv("SMTP_PASSWORD")
            
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
            server.quit()
            
            logger.info(f"✅ Email enviado a {to_email} via SMTP")
            return True
        
        except Exception as e:
            logger.error(f"❌ Error SMTP: {e}")
            return False


# =============================================
# EMAILS PREDEFINIDOS
# =============================================

email_service = EmailService()


async def send_welcome_email(user_email: str, user_name: str) -> bool:
    """Email de bienvenida a nuevo usuario"""
    try:
        template = template_env.get_template("welcome.html")
        html_content = template.render(
            user_name=user_name,
            app_name="Mi Backend Super IA",
            login_url="https://app.mibackendsuper.com/login",
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=user_email,
            subject="🎉 ¡Bienvenido a Mi Backend Super IA!",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando email de bienvenida: {e}")
        return False


async def send_payment_success_email(
    user_email: str,
    user_name: str,
    plan_name: str,
    amount: float,
    currency: str = "USD"
) -> bool:
    """Email de confirmación de pago exitoso"""
    try:
        template = template_env.get_template("payment_success.html")
        html_content = template.render(
            user_name=user_name,
            plan_name=plan_name,
            amount=amount,
            currency=currency,
            date=datetime.now().strftime("%d/%m/%Y"),
            dashboard_url="https://app.mibackendsuper.com/dashboard",
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=user_email,
            subject=f"✅ Pago confirmado - Plan {plan_name}",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando email de pago: {e}")
        return False


async def send_payment_failed_email(
    user_email: str,
    user_name: str,
    plan_name: str,
    error_message: str
) -> bool:
    """Email de pago fallido"""
    try:
        template = template_env.get_template("payment_failed.html")
        html_content = template.render(
            user_name=user_name,
            plan_name=plan_name,
            error_message=error_message,
            retry_url="https://app.mibackendsuper.com/billing",
            support_email="support@mibackendsuper.com",
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=user_email,
            subject=f"❌ Error en el pago - Plan {plan_name}",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando email de pago fallido: {e}")
        return False


async def send_subscription_renewal_email(
    user_email: str,
    user_name: str,
    plan_name: str,
    renewal_date: str,
    amount: float
) -> bool:
    """Email de renovación de suscripción"""
    try:
        template = template_env.get_template("subscription_renewal.html")
        html_content = template.render(
            user_name=user_name,
            plan_name=plan_name,
            renewal_date=renewal_date,
            amount=amount,
            manage_url="https://app.mibackendsuper.com/subscription",
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=user_email,
            subject=f"🔄 Renovación de suscripción - Plan {plan_name}",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando email de renovación: {e}")
        return False


async def send_referral_invitation_email(
    inviter_name: str,
    invitee_email: str,
    referral_code: str
) -> bool:
    """Email de invitación por referido"""
    try:
        template = template_env.get_template("referral_invitation.html")
        signup_url = f"https://app.mibackendsuper.com/signup?ref={referral_code}"
        
        html_content = template.render(
            inviter_name=inviter_name,
            signup_url=signup_url,
            referral_code=referral_code,
            bonus_description="1 mes gratis en Plan Pro",
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=invitee_email,
            subject=f"🎁 {inviter_name} te invita a Mi Backend Super IA",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando invitación: {e}")
        return False


async def send_password_reset_email(
    user_email: str,
    user_name: str,
    reset_token: str
) -> bool:
    """Email de recuperación de contraseña"""
    try:
        template = template_env.get_template("password_reset.html")
        reset_url = f"https://app.mibackendsuper.com/reset-password?token={reset_token}"
        
        html_content = template.render(
            user_name=user_name,
            reset_url=reset_url,
            expiration_hours=24,
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=user_email,
            subject="🔑 Recuperación de contraseña",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando email de recuperación: {e}")
        return False


async def send_subscription_cancelled_email(
    user_email: str,
    user_name: str,
    plan_name: str,
    end_date: str
) -> bool:
    """Email de suscripción cancelada"""
    try:
        template = template_env.get_template("subscription_cancelled.html")
        html_content = template.render(
            user_name=user_name,
            plan_name=plan_name,
            end_date=end_date,
            reactivate_url="https://app.mibackendsuper.com/billing",
            year=datetime.now().year
        )
        
        return await email_service.send_email(
            to_email=user_email,
            subject=f"😢 Suscripción cancelada - Plan {plan_name}",
            html_content=html_content
        )
    except Exception as e:
        logger.error(f"❌ Error enviando email de cancelación: {e}")
        return False
