from __future__ import annotations

from datetime import date
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from pydantic import BaseModel, Field

from utils.auth import get_current_user


router = APIRouter(prefix="/api/documents", tags=["Documents"])


class Apa7PdfRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    author: str = Field(..., min_length=1, max_length=200)
    institution: Optional[str] = Field(None, max_length=200)
    course: Optional[str] = Field(None, max_length=200)
    instructor: Optional[str] = Field(None, max_length=200)
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD (opcional)")

    paragraphs: List[str] = Field(..., min_length=1, description="Contenido del trabajo en párrafos")
    references: List[str] = Field(default_factory=list, description="Referencias en texto (una por item)")

    filename: str = Field(default="apa7.pdf", max_length=120)


@router.post("/apa7/pdf")
async def generate_apa7_pdf(
    payload: Apa7PdfRequest,
    _user=Depends(get_current_user),
):
    # Import local para evitar errores si reportlab no está instalado
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=1 * inch,
        rightMargin=1 * inch,
        topMargin=1 * inch,
        bottomMargin=1 * inch,
        title=payload.title,
        author=payload.author,
    )

    styles = getSampleStyleSheet()

    base = ParagraphStyle(
        name="APA7Base",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=12,
        leading=24,  # doble espacio
        spaceAfter=0,
        spaceBefore=0,
    )

    title_style = ParagraphStyle(
        name="APA7Title",
        parent=base,
        alignment=1,  # center
    )

    heading_style = ParagraphStyle(
        name="APA7Heading",
        parent=base,
        alignment=1,  # center
        spaceBefore=12,
    )

    body_style = ParagraphStyle(
        name="APA7Body",
        parent=base,
        firstLineIndent=0.5 * inch,
    )

    refs_style = ParagraphStyle(
        name="APA7Refs",
        parent=base,
        leftIndent=0.5 * inch,
        firstLineIndent=-0.5 * inch,  # sangría francesa
    )

    story = []

    # -----------------
    # Portada (simplificada APA 7: datos centrados)
    # -----------------
    story.append(Spacer(1, 2 * inch))
    story.append(Paragraph(payload.title, title_style))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Paragraph(payload.author, title_style))

    if payload.institution:
        story.append(Paragraph(payload.institution, title_style))
    if payload.course:
        story.append(Paragraph(payload.course, title_style))
    if payload.instructor:
        story.append(Paragraph(payload.instructor, title_style))

    dd = payload.due_date or date.today().isoformat()
    story.append(Paragraph(dd, title_style))

    story.append(PageBreak())

    # -----------------
    # Cuerpo
    # -----------------
    story.append(Paragraph(payload.title, heading_style))
    story.append(Spacer(1, 0.2 * inch))

    for p in payload.paragraphs:
        p = (p or "").strip()
        if not p:
            continue
        story.append(Paragraph(p.replace("\n", "<br/>") , body_style))
        story.append(Spacer(1, 0.2 * inch))

    # -----------------
    # Referencias
    # -----------------
    if payload.references:
        story.append(PageBreak())
        story.append(Paragraph("References", heading_style))
        story.append(Spacer(1, 0.2 * inch))
        for r in payload.references:
            r = (r or "").strip()
            if not r:
                continue
            story.append(Paragraph(r.replace("\n", "<br/>") , refs_style))
            story.append(Spacer(1, 0.1 * inch))

    doc.build(story)

    pdf_bytes = buffer.getvalue()
    buffer.close()

    filename = (payload.filename or "apa7.pdf").strip() or "apa7.pdf"
    if not filename.lower().endswith(".pdf"):
        filename = f"{filename}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
    )
