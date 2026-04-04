"""
File processing utilities for Groq AI Vision API
Converts images and documents to formats compatible with Groq's vision capabilities
"""
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple
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
}

MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20MB max per file
MAX_IMAGES_PER_REQUEST = 10


async def process_uploaded_files(
    files: Optional[List[UploadFile]],
    max_images: int = MAX_IMAGES_PER_REQUEST
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Process uploaded files for Groq AI consumption.
    
    Returns:
        Tuple of (image_content_list, text_content_list)
        - image_content_list: List of dicts with type and image_url for Groq
        - text_content_list: List of extracted text from documents
    """
    if not files:
        return [], []
    
    image_contents = []
    text_contents = []
    
    for idx, file in enumerate(files):
        if idx >= max_images:
            logger.warning(f"Max images ({max_images}) reached, skipping remaining files")
            break
        
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
                # Convert image to base64 for Groq vision
                base64_data = base64.b64encode(file_bytes).decode('utf-8')
                image_url = f"data:{content_type};base64,{base64_data}"
                
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
                logger.info(f"Processed image: {file_name} ({content_type}, {file_size} bytes)")
                
            elif content_type in SUPPORTED_DOCUMENT_TYPES:
                # Extract text from document
                if content_type == "text/plain":
                    try:
                        text = file_bytes.decode('utf-8')
                        text_contents.append(f"[Document: {file_name}]\n{text[:10000]}")
                    except UnicodeDecodeError:
                        text_contents.append(f"[Document: {file_name}]\n[Binary content, could not decode as text]")
                        
                elif content_type == "application/json":
                    try:
                        text = file_bytes.decode('utf-8')
                        text_contents.append(f"[JSON: {file_name}]\n{text[:5000]}")
                    except UnicodeDecodeError:
                        text_contents.append(f"[JSON: {file_name}]\n[Binary content]")
                        
                elif content_type == "application/pdf":
                    # For PDFs, we note them but can't extract text without additional libraries
                    text_contents.append(f"[PDF Document: {file_name}]\n[PDF content - {file_size} bytes. The user has uploaded a PDF that may contain important information.]")
                    
                else:
                    text_contents.append(f"[File: {file_name}]\n[Content type: {content_type}, size: {file_size} bytes]")
                    
            else:
                # Try to decode as text for unknown types
                try:
                    text = file_bytes.decode('utf-8', errors='ignore')
                    if len(text) > 0:
                        text_contents.append(f"[File: {file_name}]\n{text[:5000]}")
                    else:
                        logger.warning(f"Unknown file type {content_type}: {file_name}, skipping")
                except Exception:
                    logger.warning(f"Could not process file {file_name} with type {content_type}")
                    
        except Exception as e:
            logger.error(f"Error processing file {file.filename if file else 'unknown'}: {e}")
            continue
    
    return image_contents, text_contents


async def process_base64_files(
    images_base64: Optional[List[str]] = None,
    docs_base64: Optional[List[str]] = None,
    max_images: int = MAX_IMAGES_PER_REQUEST
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Process base64 encoded images and documents for Groq AI.
    Used for JSON-based chat requests.
    """
    image_contents = []
    text_contents = []
    
    if images_base64:
        for idx, b64_str in enumerate(images_base64):
            if idx >= max_images:
                break
            if not b64_str:
                continue
            
            try:
                # Basic check for data URI vs raw base64
                if "," in b64_str:
                    header, data = b64_str.split(",", 1)
                    mime_type = header.split(":", 1)[1].split(";", 1)[0]
                else:
                    mime_type = "image/jpeg" # Default fallback
                    data = b64_str
                
                image_contents.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{data}"}
                })
                logger.info(f"Processed base64 image ({mime_type})")
            except Exception as e:
                logger.error(f"Error processing base64 image: {e}")

    if docs_base64:
        for idx, b64_str in enumerate(docs_base64):
            if not b64_str:
                continue
            try:
                if "," in b64_str:
                    _, data = b64_str.split(",", 1)
                else:
                    data = b64_str
                
                decoded = base64.b64decode(data).decode('utf-8', errors='ignore')
                text_contents.append(f"[Documento JSON {idx+1}]\n{decoded[:5000]}")
            except Exception as e:
                logger.error(f"Error processing base64 doc: {e}")
                
    return image_contents, text_contents


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
