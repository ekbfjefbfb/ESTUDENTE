from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from google.oauth2 import id_token
from google.auth.transport import requests
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
import uuid
import logging
from datetime import datetime

from config import GOOGLE_CLIENT_ID, JWT_SECRET_KEY, JWT_ALGORITHM
from utils.auth import create_access_token, create_refresh_token, get_password_hash
from database.db_enterprise import get_primary_session

logger = logging.getLogger("auth_google")
router = APIRouter(prefix="/api/auth/google", tags=["Auth"])

class GoogleTokenRequest(BaseModel):
    id_token: str

@router.post("/verify")
async def verify_google_token(
    request: GoogleTokenRequest,
    db: AsyncSession = Depends(get_primary_session)
):
    """
    Verifica el id_token de Google y autentica o registra al usuario con Plan Enterprise.
    IRIS ONE-TAP LOGIN.
    """
    try:
        # 1. Validar Token con Google
        idinfo = id_token.verify_oauth2_token(
            request.id_token, 
            requests.Request(), 
            GOOGLE_CLIENT_ID
        )

        # 2. Extraer datos del perfil
        email = idinfo.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="google_token_no_email")
        
        name = idinfo.get("name", "")
        picture = idinfo.get("picture", "")
        google_id = idinfo.get("sub") # ID único de Google

        # 3. Buscar usuario existente por email o google_id (oauth_profile->sub)
        # Usamos SQL directo para máxima performance y evitar circular imports
        result = await db.execute(
            text("SELECT id, is_active FROM users WHERE email = :email"),
            {"email": email}
        )
        user_row = result.first()

        if user_row:
            user_id, is_active = user_row
            if not is_active:
                raise HTTPException(status_code=403, detail="user_deactivated")
            
            # Actualizar perfil si es necesario (Opcional)
            await db.execute(
                text("UPDATE users SET profile_picture_url = :pic WHERE id = :uid"),
                {"pic": picture, "uid": user_id}
            )
            await db.commit()
        else:
            # 🚀 REGISTRO VIP: Crear nuevo usuario con Plan Enterprise
            user_id = str(uuid.uuid4())
            username = email.split("@")[0] + "_" + str(uuid.uuid4())[:4]
            
            # Buscar el ID del plan 'enterprise'
            plan_result = await db.execute(
                text("SELECT id FROM plans WHERE name = 'enterprise' LIMIT 1")
            )
            plan_row = plan_result.first()
            enterprise_plan_id = plan_row[0] if plan_row else None

            # Insertar nuevo usuario
            await db.execute(
                text("""
                    INSERT INTO users 
                    (id, username, email, full_name, profile_picture_url, oauth_provider, is_active, plan_id, created_at)
                    VALUES 
                    (:id, :username, :email, :name, :pic, 'google', true, :plan_id, :now)
                """),
                {
                    "id": user_id,
                    "username": username,
                    "email": email,
                    "name": name,
                    "pic": picture,
                    "plan_id": enterprise_plan_id,
                    "now": datetime.utcnow()
                }
            )
            await db.commit()
            logger.info(f"✅ Nuevo usuario VIP registrado vía Google: {email} (Plan Enterprise)")

        # 4. Generar Tókens de Iris
        access_token = await create_access_token(data={"sub": user_id})
        refresh_token = await create_refresh_token(data={"sub": user_id})

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user_id,
                "email": email,
                "name": name,
                "picture": picture,
                "plan": "enterprise"
            }
        }

    except ValueError as ve:
        logger.warning(f"Invalid Google Token: {ve}")
        raise HTTPException(status_code=401, detail="invalid_google_token")
    except Exception as e:
        logger.error(f"Error in Google Auth: {e}")
        raise HTTPException(status_code=500, detail="internal_auth_error")
