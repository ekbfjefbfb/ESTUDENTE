from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import update
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
async def get_me(current_user: User = Depends(get_current_user)):
    return MeResponse(
        id=str(current_user.id),
        username=current_user.username,
        email=current_user.email,
        full_name=current_user.full_name,
        phone_number=current_user.phone_number,
        profile_picture_url=current_user.profile_picture_url,
    )


@router.post("/me/avatar", response_model=AvatarUploadResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
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
    ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    object_path = f"{current_user.id}/{ts}.{ext}"

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
        .where(User.id == str(current_user.id))
        .values(profile_picture_url=public_url)
    )
    await db.commit()

    return AvatarUploadResponse(profile_picture_url=public_url)
