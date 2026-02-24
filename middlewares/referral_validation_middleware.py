"""
Middleware de validación automática de referidos

Este middleware intercepta las acciones del usuario y automáticamente
valida los referidos cuando realizan acciones reales en la app.

🔒 ANTI-FRAUDE: Solo se otorga bonus cuando el referido:
- Envía su primer mensaje
- Completa 3+ mensajes
- Pasa 24 horas activo
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from services.invitation_service import InvitationService
from models.models import User
import logging

logger = logging.getLogger(__name__)


class ReferralValidationMiddleware(BaseHTTPMiddleware):
    """
    Middleware que valida automáticamente referidos cuando usan la app
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Intercepta requests y valida referidos automáticamente
        """
        # Ejecutar el request primero
        response = await call_next(request)
        
        # Solo validar en requests exitosos (200)
        if response.status_code != 200:
            return response
        
        # Solo validar en endpoints de chat/mensajes
        if not self._is_message_endpoint(request.url.path):
            return response
        
        # Obtener usuario actual
        user = getattr(request.state, "user", None)
        if not user:
            return response
        
        # Verificar si este usuario tiene un referido pendiente
        try:
            db: AsyncSession = request.state.db
            await self._validate_referral_if_needed(db, user)
        except Exception as e:
            logger.error(f"Error validating referral: {e}")
            # No fallar el request por esto
        
        return response
    
    def _is_message_endpoint(self, path: str) -> bool:
        """
        Verifica si el endpoint es de mensajes
        """
        message_endpoints = [
            "/api/chat",
            "/api/unified-chat",
            "/api/personal-agent",
            "/api/voice"
        ]
        
        return any(path.startswith(endpoint) for endpoint in message_endpoints)
    
    async def _validate_referral_if_needed(self, db: AsyncSession, user: User):
        """
        Valida el referido si es necesario
        """
        from sqlalchemy import select
        from models.models import Referral
        
        # Verificar si tiene un referido pendiente
        referral_query = await db.execute(
            select(Referral).where(
                Referral.referred_id == str(user.id),
                Referral.status == "PENDING"
            )
        )
        referral = referral_query.scalar_one_or_none()
        
        if referral:
            # Tiene un referido pendiente, validarlo
            result = await InvitationService.validate_and_grant_referral_bonus(
                db=db,
                referred_user_id=str(user.id),
                action="first_message"
            )
            
            if result.get("bonus_granted"):
                logger.info(f"✅ Referral bonus granted automatically for user {user.id}")


# =============================================
# HOOK PARA VALIDACIÓN EN ENDPOINTS ESPECÍFICOS
# =============================================

async def validate_referral_on_action(
    db: AsyncSession,
    user_id: str,
    action: str = "first_message"
):
    """
    Función auxiliar para validar referidos desde cualquier endpoint
    
    **Uso en tus endpoints:**
    
    ```python
    # En tu endpoint de chat
    @router.post("/api/chat/message")
    async def send_message(
        message: str,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        # Procesar mensaje...
        
        # Validar referido automáticamente
        await validate_referral_on_action(
            db=db,
            user_id=str(current_user.id),
            action="first_message"
        )
        
        return {"message": "Sent"}
    ```
    """
    try:
        await InvitationService.validate_and_grant_referral_bonus(
            db=db,
            referred_user_id=user_id,
            action=action
        )
    except Exception as e:
        logger.error(f"Error validating referral: {e}")


# =============================================
# REGISTRO DEL MIDDLEWARE
# =============================================

"""
Para activar el middleware, agregar en main.py:

from middlewares.referral_validation_middleware import ReferralValidationMiddleware

app.add_middleware(ReferralValidationMiddleware)
"""
