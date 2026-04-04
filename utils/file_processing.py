"""
File processing utilities for Groq AI Vision API.

Convierte imágenes y documentos a formatos compatibles con el chat multimodal
sin persistir blobs gigantes innecesarios en la base de datos.
"""
import base64
import binascii
import io
import logging
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse

import anyio
from fastapi import UploadFile

logger = logging.getLogger("file_processing")

# Supported image MIME types for Groq
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}

# Supported document types that can be processed
SUPPORTED_DOCUMENT_TYPES = {
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/html": "html",
    "application/json": "json",
    "text/csv": "csv",
    "application/xml": "xml",
    "text/xml": "xml",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
}

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB max per file
MAX_IMAGES_PER_REQUEST = 10
MAX_TEXT_CHARS_PER_DOCUMENT = 12000
MAX_TEXT_PREVIEW_CHARS = 600


def _empty_attachment_metadata() -> Dict[str, Any]:
    return {
        "counts": {"images": 0, "documents": 0},
        "images": [],
        "documents": [],
    }


def _finalize_attachment_metadata(meta: Dict[str, Any]) -> Dict[str, Any]:
    meta["counts"] = {
        "images": len(meta.get("images") or []),
        "documents": len(meta.get("documents") or []),
    }
    return meta


def _text_excerpt(text: str, max_chars: int = MAX_TEXT_PREVIEW_CHARS) -> str:
    raw = str(text or "").strip()
    if len(raw) <= max_chars:
        return raw
    return raw[: max_chars - 1].rstrip() + "…"


def _is_public_http_url(value: str) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except Exception:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _parse_data_uri(value: str) -> Tuple[Optional[str], str]:
    raw = str(value or "").strip()
    if raw.startswith("data:") and "," in raw:
        header, data = raw.split(",", 1)
        mime_type = header.split(":", 1)[1].split(";", 1)[0].strip().lower()
        return mime_type or None, data
    return None, raw


def _decode_base64_bytes(data: str) -> bytes:
    raw = "".join(str(data or "").strip().split())
    if not raw:
        return b""

    padding = (-len(raw)) % 4
    if padding:
        raw = raw + ("=" * padding)
    return base64.b64decode(raw, validate=True)


async def _extract_pdf_text(file_bytes: bytes) -> str:
    def _extract_with_pdfplumber() -> str:
        import pdfplumber

        text_parts: List[str] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages[:20]:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n\n".join(text_parts)

    def _extract_with_pypdf() -> str:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(file_bytes))
        text_parts: List[str] = []
        for page in reader.pages[:20]:
            page_text = page.extract_text() or ""
            if page_text.strip():
                text_parts.append(page_text)
        return "\n\n".join(text_parts)

    for extractor in (_extract_with_pdfplumber, _extract_with_pypdf):
        try:
            text = await anyio.to_thread.run_sync(extractor)
            if text.strip():
                return text[:MAX_TEXT_CHARS_PER_DOCUMENT]
        except ImportError:
            continue
        except Exception as exc:
            logger.warning(f"PDF extraction failed: {exc}")
    return ""


async def _extract_docx_text(file_bytes: bytes) -> str:
    def _extract() -> str:
        from docx import Document

        document = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text.strip() for p in document.paragraphs if str(p.text or "").strip()]
        return "\n".join(paragraphs)

    try:
        text = await anyio.to_thread.run_sync(_extract)
        return text[:MAX_TEXT_CHARS_PER_DOCUMENT]
    except ImportError:
        return ""
    except Exception as exc:
        logger.warning(f"DOCX extraction failed: {exc}")
        return ""


def _decode_text_bytes(file_bytes: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="ignore")


async def _extract_document_text(
    *,
    file_bytes: bytes,
    content_type: str,
    file_name: str,
) -> str:
    normalized_type = str(content_type or "").strip().lower()

    if normalized_type == "application/pdf":
        text = await _extract_pdf_text(file_bytes)
        if text:
            return text
        return f"[PDF Document: {file_name}]"

    if normalized_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        text = await _extract_docx_text(file_bytes)
        if text:
            return text
        return f"[DOCX Document: {file_name}]"

    if normalized_type in {
        "text/plain",
        "text/markdown",
        "text/html",
        "application/json",
        "text/csv",
        "application/xml",
        "text/xml",
        "application/msword",
    }:
        return _decode_text_bytes(file_bytes)[:MAX_TEXT_CHARS_PER_DOCUMENT]

    decoded = _decode_text_bytes(file_bytes).strip()
    if decoded:
        return decoded[:MAX_TEXT_CHARS_PER_DOCUMENT]
    return f"[File: {file_name}]"


async def process_uploaded_files(
    files: Optional[List[UploadFile]],
    max_images: int = MAX_IMAGES_PER_REQUEST
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """
    Process uploaded files for Groq AI consumption.
    
    Returns:
        Tuple of (image_content_list, text_content_list)
        - image_content_list: List of dicts with type and image_url for Groq
        - text_content_list: List of extracted text from documents
    """
    if not files:
        return [], [], _empty_attachment_metadata()
    
    image_contents = []
    text_contents = []
    attachment_meta = _empty_attachment_metadata()
    image_count = 0
    
    for file in files:
        try:
            content_type = file.content_type or ""
            file_name = file.filename or ""
            
            # Read file content
            file_bytes = await file.read()
            file_size = len(file_bytes)
            
            if file_size > MAX_FILE_SIZE_BYTES:
                logger.warning(f"File {file_name} too large ({file_size} bytes), skipping")
                continue
            
            # Reset file pointer for potential future reads
            await file.seek(0)
            
            # Process based on content type
            if content_type in SUPPORTED_IMAGE_TYPES:
                if image_count >= max_images:
                    logger.warning(f"Max images ({max_images}) reached, skipping image {file_name}")
                    attachment_meta["images"].append({
                        "name": file_name,
                        "content_type": content_type,
                        "size_bytes": file_size,
                        "source": "multipart",
                        "skipped_reason": "max_images_reached",
                    })
                    continue

                # Convert image to base64 for Groq vision
                base64_data = base64.b64encode(file_bytes).decode('utf-8')
                image_url = f"data:{content_type};base64,{base64_data}"
                
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
                attachment_meta["images"].append({
                    "name": file_name,
                    "content_type": content_type,
                    "size_bytes": file_size,
                    "source": "multipart",
                })
                image_count += 1
                logger.info(f"Processed image: {file_name} ({content_type}, {file_size} bytes)")
                
            elif content_type in SUPPORTED_DOCUMENT_TYPES:
                text = await _extract_document_text(
                    file_bytes=file_bytes,
                    content_type=content_type,
                    file_name=file_name,
                )
                text_contents.append(f"[Document: {file_name}]\n{text}")
                attachment_meta["documents"].append({
                    "name": file_name,
                    "content_type": content_type,
                    "size_bytes": file_size,
                    "source": "multipart",
                    "text_excerpt": _text_excerpt(text),
                })
                    
            else:
                # Try to decode as text for unknown types
                try:
                    text = _decode_text_bytes(file_bytes)
                    if len(text) > 0:
                        text_contents.append(f"[File: {file_name}]\n{text[:5000]}")
                        attachment_meta["documents"].append({
                            "name": file_name,
                            "content_type": content_type or "application/octet-stream",
                            "size_bytes": file_size,
                            "source": "multipart",
                            "text_excerpt": _text_excerpt(text),
                        })
                    else:
                        logger.warning(f"Unknown file type {content_type}: {file_name}, skipping")
                except Exception:
                    logger.warning(f"Could not process file {file_name} with type {content_type}")
                    
        except Exception as e:
            logger.error(f"Error processing file {file.filename if file else 'unknown'}: {e}")
            continue
    
    return image_contents, text_contents, _finalize_attachment_metadata(attachment_meta)


async def process_base64_files(
    images_base64: Optional[List[str]] = None,
    docs_base64: Optional[List[str]] = None,
    max_images: int = MAX_IMAGES_PER_REQUEST
) -> Tuple[List[Dict[str, Any]], List[str], Dict[str, Any]]:
    """
    Process base64 encoded images and documents for Groq AI.
    Used for JSON-based chat requests.
    """
    image_contents: List[Dict[str, Any]] = []
    text_contents: List[str] = []
    attachment_meta = _empty_attachment_metadata()
    image_count = 0

    if isinstance(images_base64, str):
        images_base64 = [images_base64]
    if isinstance(docs_base64, str):
        docs_base64 = [docs_base64]
    
    if images_base64:
        for b64_str in images_base64:
            if not b64_str:
                continue
            
            try:
                raw_value = str(b64_str).strip()
                if _is_public_http_url(raw_value):
                    if image_count >= max_images:
                        continue
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {"url": raw_value}
                    })
                    attachment_meta["images"].append({
                        "name": None,
                        "content_type": "image/url",
                        "size_bytes": None,
                        "source": "url",
                        "url": raw_value,
                    })
                    image_count += 1
                    continue

                mime_type, data = _parse_data_uri(raw_value)
                if not mime_type:
                    mime_type = "image/jpeg"

                decoded = _decode_base64_bytes(data)
                if len(decoded) > MAX_FILE_SIZE_BYTES:
                    logger.warning("Base64 image too large, skipping")
                    continue

                if image_count >= max_images:
                    continue

                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{base64.b64encode(decoded).decode('utf-8')}"}
                })
                attachment_meta["images"].append({
                    "name": None,
                    "content_type": mime_type,
                    "size_bytes": len(decoded),
                    "source": "inline_base64",
                })
                image_count += 1
                logger.info(f"Processed base64 image ({mime_type})")
            except (binascii.Error, ValueError) as e:
                logger.error(f"Error processing base64 image: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing base64 image: {e}")

    if docs_base64:
        for idx, b64_str in enumerate(docs_base64):
            if not b64_str:
                continue
            try:
                raw_value = str(b64_str).strip()
                if _is_public_http_url(raw_value):
                    text = f"[Remote Document URL]\n{raw_value}"
                    text_contents.append(text)
                    attachment_meta["documents"].append({
                        "name": None,
                        "content_type": "application/url",
                        "size_bytes": None,
                        "source": "url",
                        "url": raw_value,
                        "text_excerpt": _text_excerpt(text),
                    })
                    continue

                mime_type, data = _parse_data_uri(raw_value)
                decoded = _decode_base64_bytes(data)
                if len(decoded) > MAX_FILE_SIZE_BYTES:
                    logger.warning("Base64 document too large, skipping")
                    continue

                normalized_mime = str(mime_type or "application/octet-stream").lower()
                file_name = f"document_{idx + 1}"

                if normalized_mime in SUPPORTED_IMAGE_TYPES:
                    if image_count >= max_images:
                        continue
                    image_contents.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{normalized_mime};base64,{base64.b64encode(decoded).decode('utf-8')}"}
                    })
                    attachment_meta["images"].append({
                        "name": file_name,
                        "content_type": normalized_mime,
                        "size_bytes": len(decoded),
                        "source": "inline_base64",
                    })
                    image_count += 1
                    continue

                text = await _extract_document_text(
                    file_bytes=decoded,
                    content_type=normalized_mime,
                    file_name=file_name,
                )
                text_contents.append(f"[Documento JSON {idx+1}]\n{text}")
                attachment_meta["documents"].append({
                    "name": file_name,
                    "content_type": normalized_mime,
                    "size_bytes": len(decoded),
                    "source": "inline_base64",
                    "text_excerpt": _text_excerpt(text),
                })
            except (binascii.Error, ValueError) as e:
                logger.error(f"Error processing base64 doc: {e}")
            except Exception as e:
                logger.error(f"Unexpected error processing base64 doc: {e}")

    return image_contents, text_contents, _finalize_attachment_metadata(attachment_meta)


def build_message_with_files(
    message: str,
    image_contents: List[Dict[str, Any]],
    text_contents: List[str]
) -> Dict[str, Any]:
    """
    Build a message dict for Groq AI that includes images and text.
    
    Groq vision API format:
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "message"},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
        ]
    }
    """
    content_parts = []
    
    # Add user's text message
    if message:
        content_parts.append({"type": "text", "text": message})
    
    # Add extracted text from documents as context
    if text_contents:
        doc_text = "\n\n".join(text_contents)
        if content_parts:
            # Append document text to existing message
            existing_text = content_parts[0]["text"]
            content_parts[0]["text"] = f"{existing_text}\n\nDocuments:\n{doc_text}"
        else:
            content_parts.append({"type": "text", "text": f"Documents:\n{doc_text}"})
    
    # Add images (Groq expects these as separate content parts)
    for img in image_contents:
        content_parts.append(img)
    
    # Return in proper format for Groq API
    if len(content_parts) == 1 and content_parts[0]["type"] == "text":
        # Simple text-only message
        return {"role": "user", "content": content_parts[0]["text"]}
    else:
        # Multi-part message with images
        return {"role": "user", "content": content_parts}


def is_vision_request(image_contents: List[Dict[str, Any]]) -> bool:
    """Check if the request contains images for vision processing."""
    return len(image_contents) > 0
