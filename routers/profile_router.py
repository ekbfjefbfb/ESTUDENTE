from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from database.db_enterprise import get_async_db
from models.models import User
from utils.auth import get_current_user


router = APIRouter(prefix="/api", tags=["Profile"])


class MeResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    profile_picture_url: Optional[str] = None


class AvatarUploadResponse(BaseModel):
    profile_picture_url: str


def _normalize_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _current_user_value(current_user: Any, key: str) -> Optional[str]:
    if isinstance(current_user, dict):
        return _normalize_str(current_user.get(key))
    return _normalize_str(getattr(current_user, key, None))


def _current_user_id(current_user: Any) -> str:
    user_id = _current_user_value(current_user, "user_id") or _current_user_value(current_user, "id")
    if not user_id:
        raise HTTPException(status_code=500, detail="invalid_user_context")
    return user_id


def _get_supabase_storage_keys() -> tuple[str, str]:
    url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    if not url:
        raise HTTPException(status_code=500, detail="supabase_url_not_configured")

    key = (
        os.getenv("SUPABASE_SERVICE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()

    if not key:
        raise HTTPException(status_code=500, detail="supabase_key_not_configured")

    return url, key


@router.get("/me", response_model=MeResponse)
async def get_me(current_user: Any = Depends(get_current_user)):
    user_id = _current_user_id(current_user)
    username = _current_user_value(current_user, "username")
    if not username:
        raise HTTPException(status_code=500, detail="invalid_user_context")
    email = _current_user_value(current_user, "email")
    full_name = _current_user_value(current_user, "full_name")
    phone_number = _current_user_value(current_user, "phone_number")
    profile_picture_url = _current_user_value(current_user, "profile_picture_url")
    return MeResponse(
        id=user_id,
        username=username,
        email=email,
        full_name=full_name,
        phone_number=phone_number,
        profile_picture_url=profile_picture_url,
    )


class UpdateProfileRequest(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None


class UpdateProfileResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    full_name: Optional[str] = None
    phone_number: Optional[str] = None
    profile_picture_url: Optional[str] = None
    updated_at: str


@router.put("/me", response_model=UpdateProfileResponse)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Actualizar datos del perfil del usuario"""
    user_id = _current_user_id(current_user)
    
    # Validar username único si se está actualizando
    if payload.username is not None:
        from sqlalchemy import select as sa_select
        existing = await db.execute(
            sa_select(User).where(
                and_(User.username == payload.username, User.id != user_id)
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="username_already_taken")
    
    # Construir valores a actualizar
    values: Dict[str, Any] = {}
    if payload.username is not None:
        values["username"] = payload.username
    if payload.full_name is not None:
        values["full_name"] = payload.full_name
    if payload.phone_number is not None:
        values["phone_number"] = payload.phone_number
    
    if values:
        values["updated_at"] = datetime.now(timezone.utc)
        await db.execute(update(User).where(User.id == user_id).values(**values))
        await db.commit()
        if not isinstance(current_user, dict):
            await db.refresh(current_user)
    
    return UpdateProfileResponse(
        id=user_id,
        username=(payload.username if payload.username is not None else (_current_user_value(current_user, "username") or "")),
        email=_current_user_value(current_user, "email"),
        full_name=(payload.full_name if payload.full_name is not None else _current_user_value(current_user, "full_name")),
        phone_number=(payload.phone_number if payload.phone_number is not None else _current_user_value(current_user, "phone_number")),
        profile_picture_url=_current_user_value(current_user, "profile_picture_url"),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@router.post("/me/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    content_type = (file.content_type or "").lower()
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=400, detail="invalid_avatar_mime")

    max_bytes = int(os.getenv("AVATAR_MAX_BYTES", str(5 * 1024 * 1024)))
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty_file")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="avatar_too_large")

    supabase_url, supabase_key = _get_supabase_storage_keys()
    bucket = (os.getenv("SUPABASE_AVATAR_BUCKET") or "avatars").strip() or "avatars"

    ext = "jpg" if content_type == "image/jpeg" else "png" if content_type == "image/png" else "webp"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    user_id = _current_user_id(current_user)
    object_path = f"{user_id}/{ts}.{ext}"

    upload_url = f"{supabase_url}/storage/v1/object/{bucket}/{object_path}"

    headers = {
        "Authorization": f"Bearer {supabase_key}",
        "apikey": supabase_key,
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(upload_url, content=data, headers=headers)
            if resp.status_code >= 400:
                raise HTTPException(status_code=502, detail="supabase_upload_failed")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="supabase_upload_failed")

    # Public URL (requires bucket to be public)
    public_url = f"{supabase_url}/storage/v1/object/public/{bucket}/{object_path}"

    await db.execute(
        update(User)
        .where(User.id == user_id)
        .values(profile_picture_url=public_url)
    )
    await db.commit()

    return AvatarUploadResponse(profile_picture_url=public_url)
