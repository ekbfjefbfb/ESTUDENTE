"""
📱 SMS Service - Verificación con Twilio

Servicio para:
- Enviar códigos de verificación por SMS
- Verificar códigos
- 2FA
"""

import logging
import os
import random
from typing import Optional
from datetime import datetime, timedelta

from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from services.redis_service import get_redis

logger = logging.getLogger(__name__)


class SMSService:
    """Servicio de SMS con Twilio"""
    
    def __init__(self):
        # Configuración Twilio
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")
        
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("⚠️ Twilio credentials not configured - SMS disabled")
            self.client = None
        else:
            self.client = Client(self.account_sid, self.auth_token)
    
    
    def generate_verification_code(self) -> str:
        """Genera código de 6 dígitos"""
        return f"{random.randint(100000, 999999)}"
    
    
    async def send_verification_code(
        self,
        phone_number: str,
        code: Optional[str] = None
    ) -> dict:
        """
        Envía código de verificación por SMS.
        
        Args:
            phone_number: Número en formato E.164 (+521234567890)
            code: Código opcional (si no, genera uno)
        
        Returns:
            {"success": bool, "code": str (solo en dev), "expires_at": datetime}
        """
        try:
            # Generar código si no se provee
            if not code:
                code = self.generate_verification_code()
            
            # Guardar en Redis (expira en 5 minutos)
            redis = await get_redis()
            key = f"sms_code:{phone_number}"
            await redis.setex(key, 300, code)  # 5 minutos
            
            # En desarrollo, no enviar SMS real
            if os.getenv("ENVIRONMENT") == "development":
                logger.info(f"📱 [DEV] SMS Code for {phone_number}: {code}")
                return {
                    "success": True,
                    "code": code,  # Solo en dev
                    "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
                    "dev_mode": True
                }
            
            # Enviar SMS real con Twilio
            if not self.client:
                raise Exception("Twilio not configured")
            
            message = self.client.messages.create(
                body=f"Tu código de verificación es: {code}\n\nVálido por 5 minutos.",
                from_=self.phone_number,
                to=phone_number
            )
            
            logger.info(f"✅ SMS enviado a {phone_number}: {message.sid}")
            
            return {
                "success": True,
                "expires_at": (datetime.utcnow() + timedelta(minutes=5)).isoformat(),
                "message_sid": message.sid
            }
        
        except TwilioRestException as e:
            logger.error(f"❌ Twilio error: {e}")
            raise Exception(f"Error enviando SMS: {e.msg}")
        
        except Exception as e:
            logger.error(f"❌ Error enviando SMS: {e}")
            raise
    
    
    async def verify_code(
        self,
        phone_number: str,
        code: str
    ) -> bool:
        """
        Verifica código de SMS.
        
        Args:
            phone_number: Número de teléfono
            code: Código a verificar
        
        Returns:
            True si código es válido
        """
        try:
            redis = await get_redis()
            key = f"sms_code:{phone_number}"
            
            # Obtener código guardado
            saved_code = await redis.get(key)
            
            if not saved_code:
                logger.warning(f"⚠️ Código expirado o no existe: {phone_number}")
                return False
            
            # Verificar código
            if saved_code.decode('utf-8') == code:
                # Eliminar código usado
                await redis.delete(key)
                logger.info(f"✅ Código verificado: {phone_number}")
                return True
            else:
                logger.warning(f"⚠️ Código incorrecto: {phone_number}")
                return False
        
        except Exception as e:
            logger.error(f"❌ Error verificando código: {e}")
            return False
    
    
    async def send_2fa_code(
        self,
        phone_number: str
    ) -> dict:
        """Envía código 2FA"""
        return await self.send_verification_code(phone_number)
    
    
    async def verify_2fa_code(
        self,
        phone_number: str,
        code: str
    ) -> bool:
        """Verifica código 2FA"""
        return await self.verify_code(phone_number, code)


# Singleton
sms_service = SMSService()


# Export
__all__ = ["sms_service", "SMSService"]
