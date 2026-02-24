# services/image_edit_service.py
import os
import io
import base64
import logging
from typing import Optional, Dict, Any, Callable
from PIL import Image, ImageEnhance, ImageOps, ImageFilter, ImageDraw, ImageFont, UnidentifiedImageError
import replicate
import asyncio
import json_log_formatter
from utils.resilience import resilient

# ---------------- Logging JSON ----------------
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("image_edit_service")
logger.addHandler(handler)
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

# ---------------- Configuración ----------------
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", 10 * 1024 * 1024))  # 10MB
MAX_IMG_PIXELS = int(os.getenv("MAX_IMG_PIXELS", 6_000_000))
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN")
if REPLICATE_API_TOKEN:
    os.environ["REPLICATE_API_TOKEN"] = REPLICATE_API_TOKEN

MODEL_SDXL = os.getenv("MODEL_SDXL", "stability-ai/stable-diffusion-xl")
MODEL_SDXL_INPAINT = os.getenv("MODEL_SDXL_INPAINT", "stability-ai/stable-diffusion-inpainting")
MODEL_CONTROLNET = os.getenv("MODEL_CONTROLNET", "lllyasviel/ControlNet")

# ---------------- Rate limiter simple ----------------
user_limiters: Dict[str, asyncio.Semaphore] = {}

def get_user_limiter(user_id: str, max_concurrent: int = 3) -> asyncio.Semaphore:
    if user_id not in user_limiters:
        user_limiters[user_id] = asyncio.Semaphore(max_concurrent)
    return user_limiters[user_id]

# ---------------- Helpers ----------------
def pil_from_bytes(data: bytes) -> Image.Image:
    try:
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except UnidentifiedImageError as e:
        logger.error({"event": "invalid_image_bytes", "error": str(e)})
        raise ValueError("Bytes proporcionados no son una imagen válida")

def bytes_from_pil(img: Image.Image, fmt: str = "PNG", quality: int = 95) -> bytes:
    bio = io.BytesIO()
    save_kwargs = {"format": fmt}
    if fmt.upper() in ["JPEG", "JPG"]:
        save_kwargs["quality"] = quality
    img.save(bio, **save_kwargs)
    return bio.getvalue()

def ensure_size_allowable(img: Image.Image) -> Image.Image:
    w, h = img.size
    if w * h > MAX_IMG_PIXELS:
        factor = (MAX_IMG_PIXELS / (w * h)) ** 0.5
        new_w = max(64, int(w * factor))
        new_h = max(64, int(h * factor))
        logger.info({"event": "resize_down", "from": f"{w}x{h}", "to": f"{new_w}x{new_h}"})
        return img.resize((new_w, new_h), Image.LANCZOS)
    return img

def encode_b64(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")

# ---------------- Transformaciones Pillow ----------------
def apply_filters_pillow(img: Image.Image, filters: Dict[str, Any]) -> Image.Image:
    im = img.convert("RGBA")
    try:
        if filters.get("grayscale"):
            im = ImageOps.grayscale(im).convert("RGBA")
        if "brightness" in filters:
            im = ImageEnhance.Brightness(im).enhance(float(filters["brightness"]))
        if "contrast" in filters:
            im = ImageEnhance.Contrast(im).enhance(float(filters["contrast"]))
        if "saturation" in filters:
            im = ImageEnhance.Color(im).enhance(float(filters["saturation"]))
        if "blur" in filters:
            im = im.filter(ImageFilter.GaussianBlur(radius=float(filters["blur"])))
    except Exception as e:
        logger.warning({"event": "filter_apply_error", "error": str(e)})
    return im

def add_text_pillow(img: Image.Image, text: str, pos: tuple = (10, 10), font_size: int = 24, color: str = "#FFFFFF") -> Image.Image:
    im = img.convert("RGBA")
    draw = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    draw.text(pos, text, fill=color, font=font)
    return im

def resize_pillow(img: Image.Image, width: int, height: Optional[int] = None) -> Image.Image:
    if width and not height:
        w, h = img.size
        ratio = width / w
        height = int(h * ratio)
    return img.resize((width, height), Image.LANCZOS)

# ---------------- Replicate SDXL ----------------
@resilient(max_attempts=3, wait_min=1, wait_max=6)
def replicate_generate_sd(prompt: str, image_b64: Optional[str] = None, mask_b64: Optional[str] = None,
                          width: int = 1024, height: int = 1024, steps: int = 30, controlnet: Optional[dict] = None) -> bytes:
    try:
        inputs = {
            "prompt": prompt,
            "width": width,
            "height": height,
            "num_inference_steps": steps,
            "guidance_scale": 7.5,
        }
        if image_b64:
            inputs["init_image"] = image_b64
        if mask_b64:
            inputs["mask"] = mask_b64
        if controlnet:
            inputs["controlnet"] = controlnet
        model = replicate.models.get(MODEL_SDXL)
        version = model.versions.list()[0]
        output = replicate.run(version.id, input=inputs, timeout=300)
        if isinstance(output, list):
            out0 = output[0]
        else:
            out0 = output
        if isinstance(out0, str) and out0.startswith("data:"):
            b64 = out0.split(",", 1)[1]
            return base64.b64decode(b64)
        if isinstance(out0, str) and out0.startswith("http"):
            import httpx
            r = httpx.get(out0, timeout=60)
            r.raise_for_status()
            return r.content
        if isinstance(out0, (bytes, bytearray)):
            return bytes(out0)
        raise RuntimeError("Salida inesperada del modelo Replicate")
    except Exception as e:
        logger.exception({"event": "replicate_error", "error": str(e)})
        raise RuntimeError("Error generando imagen en Replicate") from e

# ---------------- Pipeline principal ----------------
async def edit_image_pipeline(
    user_id: str,
    image_bytes: bytes,
    operation: str,
    params: Dict[str, Any],
    mask_bytes: Optional[bytes] = None,
    progress_cb: Optional[Callable[[float], None]] = None
) -> bytes:
    limiter = get_user_limiter(user_id)
    async with limiter:
        if len(image_bytes) > MAX_FILE_SIZE:
            raise ValueError("Imagen demasiado grande")
        pil_img = pil_from_bytes(image_bytes)
        pil_img = ensure_size_allowable(pil_img)
        if progress_cb:
            progress_cb(0.05)

        op = operation.lower()
        result_bytes: bytes

        try:
            if op == "filter":
                filters = params.get("filters", {})
                out_img = apply_filters_pillow(pil_img, filters)
                if "text" in params:
                    out_img = add_text_pillow(out_img, params.get("text", ""), pos=tuple(params.get("text_pos", (10,10))))
                result_bytes = bytes_from_pil(out_img)
                if progress_cb: progress_cb(1.0)
                return result_bytes

            if op == "resize":
                width = params.get("width")
                height = params.get("height")
                out_img = resize_pillow(pil_img, width, height)
                result_bytes = bytes_from_pil(out_img)
                if progress_cb: progress_cb(1.0)
                return result_bytes

            if op == "sd_generate":
                prompt = params.get("prompt", "")
                if not prompt:
                    raise ValueError("Prompt requerido para sd_generate")
                image_b64 = encode_b64(image_bytes) if params.get("use_init_image") else None
                mask_b64 = encode_b64(mask_bytes) if mask_bytes else None
                controlnet = params.get("controlnet")
                result_bytes = await asyncio.to_thread(
                    replicate_generate_sd, prompt, image_b64, mask_b64,
                    params.get("width",1024), params.get("height",1024),
                    params.get("steps",30), controlnet
                )
                if progress_cb: progress_cb(1.0)
                return result_bytes

            raise ValueError(f"Operación desconocida: {operation}")
        except Exception as e:
            logger.exception({"event": "edit_pipeline_error", "operation": operation, "user_id": user_id, "error": str(e)})
            raise

# =============================================
# CLASE PRINCIPAL ImageEditService
# =============================================
class ImageEditService:
    """Servicio principal de edición de imágenes"""
    
    def __init__(self):
        self.initialized = True
        logger.info({"event": "image_edit_service_initialized"})
    
    async def health_check(self):
        """Health check del servicio"""
        return {
            "status": "ok", 
            "service": "image_edit_service",
            "replicate_available": bool(REPLICATE_API_TOKEN)
        }
    
    async def generate_image(self, prompt: str, **kwargs) -> bytes:
        """Genera una imagen desde un prompt"""
        return await edit_image_pipeline(
            b"", 
            "sd_generate", 
            {"prompt": prompt, **kwargs}
        )
    
    async def edit_image(self, image_bytes: bytes, operation: str, **params) -> bytes:
        """Edita una imagen usando el pipeline"""
        return await edit_image_pipeline(image_bytes, operation, params)

# Instancia global
image_edit_service = ImageEditService()
