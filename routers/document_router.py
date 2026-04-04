from fastapi import APIRouter, Depends, HTTPException, Body
from fastapi.responses import StreamingResponse
from typing import Optional, List
import logging

from services.document_service import create_document_from_user_message
from utils.auth import get_current_user
from models.models import User

logger = logging.getLogger("document_router")

router = APIRouter()

@router.post("/generate")
async def generate_document(
    content: str = Body(..., description="Message or content to base the document on"),
    doc_type: str = Body("pdf", description="Format: pdf, word, csv, excel"),
    title: Optional[str] = Body(None, description="Optional title"),
    extra_images_prompts: Optional[List[str]] = Body(None, description="Optional prompts to generate images in the document"),
    current_user: User = Depends(get_current_user)
):
    """
    Generates a document from the given content and format using the AI Document Service.
    Returns the file as a downloadable stream.
    """
    try:
        format_val = doc_type.lower().strip()
        if format_val not in ["pdf", "word", "csv", "excel", "text"]:
            raise HTTPException(status_code=400, detail="Invalid doc_type. Must be: pdf, word, csv, excel, text")
            
        file_buffer = await create_document_from_user_message(
            user_message=content,
            user_id=str(current_user.id),
            doc_type=format_val,
            extra_images_prompts=extra_images_prompts,
            provided_title=title
        )
        
        # Determine MIME type based on doc_type
        if format_val == "pdf":
            media_type = "application/pdf"
            ext = ".pdf"
        elif format_val == "word":
            media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ext = ".docx"
        elif format_val == "csv":
            media_type = "text/csv"
            ext = ".csv"
        elif format_val == "excel":
            media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ext = ".xlsx"
        else:
            media_type = "text/plain"
            ext = ".txt"
            
        # Create safe filename using title if exists
        safe_title = "".join(c for c in (title or "kiis_document") if c.isalnum() or c in " _-").replace(" ", "_")[:30]
        filename = f"{safe_title}{ext}"
        
        return StreamingResponse(
            file_buffer,
            media_type=media_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{filename}\"",
                "Access-Control-Expose-Headers": "Content-Disposition"  # Important for Flutter to read the filename
            }
        )
        
    except Exception as e:
        logger.error(f"Error generating document via API: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate document: {str(e)}")
