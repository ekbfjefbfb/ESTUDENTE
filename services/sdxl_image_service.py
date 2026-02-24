"""
Servicio de generación de imágenes con Stable Diffusion XL (SDXL)
Generación local en GPU 2 (12 GB VRAM)
Sin dependencia de APIs externas
Versión: 1.0 - Octubre 2025
"""

import torch
from diffusers import StableDiffusionXLPipeline, EulerDiscreteScheduler
from typing import Optional, List, Dict, Any
import time
import logging
from pathlib import Path
import uuid
from PIL import Image
import io
import base64

logger = logging.getLogger(__name__)

class SDXLImageService:
    """
    Servicio de generación de imágenes con SDXL
    Optimizado para RTX A6000 (12 GB VRAM)
    """
    
    def __init__(
        self,
        model_id: str = "stabilityai/stable-diffusion-xl-base-1.0",
        refiner_id: str = "stabilityai/stable-diffusion-xl-refiner-1.0",
        device: str = "cuda:1",  # GPU 2
        use_refiner: bool = False,  # Refiner opcional (requiere +4GB VRAM)
        cache_dir: str = "./models/sdxl"
    ):
        """
        Inicializa el servicio SDXL
        
        Args:
            model_id: ID del modelo SDXL base en HuggingFace
            refiner_id: ID del modelo refiner (opcional)
            device: GPU a usar (cuda:1 = GPU 2)
            use_refiner: Si usar el refiner (mejor calidad, +4GB VRAM)
            cache_dir: Directorio para cachear modelos
        """
        self.model_id = model_id
        self.refiner_id = refiner_id
        self.device = device
        self.use_refiner = use_refiner
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.pipeline = None
        self.refiner = None
        self.is_loaded = False
        
        logger.info(f"🎨 Inicializando SDXL Image Service en {device}")
    
    def load_model(self):
        """
        Carga el modelo SDXL en memoria (12 GB VRAM)
        """
        if self.is_loaded:
            logger.info("✅ Modelo SDXL ya cargado")
            return
        
        try:
            logger.info(f"⏳ Cargando SDXL desde {self.model_id}...")
            start_time = time.time()
            
            # Cargar pipeline base con optimizaciones
            self.pipeline = StableDiffusionXLPipeline.from_pretrained(
                self.model_id,
                torch_dtype=torch.float16,  # FP16 para ahorrar VRAM
                use_safetensors=True,
                variant="fp16",
                cache_dir=str(self.cache_dir)
            ).to(self.device)
            
            # Optimizaciones de memoria
            self.pipeline.enable_attention_slicing()
            self.pipeline.enable_vae_slicing()
            
            # Scheduler optimizado (Euler es rápido y de calidad)
            self.pipeline.scheduler = EulerDiscreteScheduler.from_config(
                self.pipeline.scheduler.config
            )
            
            # Cargar refiner si está habilitado
            if self.use_refiner:
                logger.info(f"⏳ Cargando SDXL Refiner...")
                self.refiner = StableDiffusionXLPipeline.from_pretrained(
                    self.refiner_id,
                    torch_dtype=torch.float16,
                    use_safetensors=True,
                    variant="fp16",
                    cache_dir=str(self.cache_dir)
                ).to(self.device)
                
                self.refiner.enable_attention_slicing()
                self.refiner.enable_vae_slicing()
            
            load_time = time.time() - start_time
            self.is_loaded = True
            
            logger.info(f"✅ SDXL cargado en {load_time:.2f}s")
            logger.info(f"📊 VRAM usado: ~12 GB en {self.device}")
            
        except Exception as e:
            logger.error(f"❌ Error cargando SDXL: {str(e)}")
            raise
    
    def unload_model(self):
        """
        Descarga el modelo de memoria para liberar VRAM
        """
        if not self.is_loaded:
            return
        
        try:
            logger.info("🗑️ Descargando SDXL de memoria...")
            
            if self.pipeline:
                del self.pipeline
                self.pipeline = None
            
            if self.refiner:
                del self.refiner
                self.refiner = None
            
            # Limpiar caché de CUDA
            torch.cuda.empty_cache()
            
            self.is_loaded = False
            logger.info("✅ SDXL descargado, VRAM liberada")
            
        except Exception as e:
            logger.error(f"❌ Error descargando SDXL: {str(e)}")
    
    def generate_image(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
        width: int = 1024,
        height: int = 1024,
        num_inference_steps: int = 30,  # 30 steps = ~8 segundos
        guidance_scale: float = 7.5,
        num_images: int = 1,
        seed: Optional[int] = None,
        style_preset: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Genera imágenes con SDXL
        
        Args:
            prompt: Descripción de la imagen a generar
            negative_prompt: Cosas a evitar en la imagen
            width: Ancho en píxeles (múltiplo de 8)
            height: Alto en píxeles (múltiplo de 8)
            num_inference_steps: Pasos de difusión (más = mejor calidad, más lento)
            guidance_scale: Qué tan fuerte seguir el prompt (7-12 típico)
            num_images: Número de imágenes a generar
            seed: Seed para reproducibilidad (None = aleatorio)
            style_preset: Estilo predefinido (photographic, digital-art, etc)
        
        Returns:
            Lista de diccionarios con info de cada imagen generada
        """
        if not self.is_loaded:
            self.load_model()
        
        try:
            logger.info(f"🎨 Generando {num_images} imagen(es): '{prompt[:50]}...'")
            start_time = time.time()
            
            # Aplicar preset de estilo si se especifica
            if style_preset:
                prompt = self._apply_style_preset(prompt, style_preset)
            
            # Negative prompt por defecto
            if negative_prompt is None:
                negative_prompt = (
                    "ugly, blurry, low quality, distorted, deformed, "
                    "watermark, text, signature, bad anatomy"
                )
            
            # Seed para reproducibilidad
            generator = None
            if seed is not None:
                generator = torch.Generator(device=self.device).manual_seed(seed)
            
            # Generar imagen base
            output = self.pipeline(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=num_inference_steps,
                guidance_scale=guidance_scale,
                num_images_per_prompt=num_images,
                generator=generator
            )
            
            images = output.images
            
            # Refinar imágenes si el refiner está habilitado
            if self.use_refiner and self.refiner:
                logger.info("🎨 Refinando imágenes...")
                refined_images = []
                for img in images:
                    refined = self.refiner(
                        prompt=prompt,
                        image=img,
                        num_inference_steps=15,  # Menos pasos para refiner
                        generator=generator
                    ).images[0]
                    refined_images.append(refined)
                images = refined_images
            
            generation_time = time.time() - start_time
            time_per_image = generation_time / num_images
            
            logger.info(
                f"✅ {num_images} imagen(es) generada(s) en {generation_time:.2f}s "
                f"(~{time_per_image:.2f}s/imagen)"
            )
            
            # Preparar resultado
            results = []
            for i, image in enumerate(images):
                result = {
                    "image": image,
                    "prompt": prompt,
                    "negative_prompt": negative_prompt,
                    "width": width,
                    "height": height,
                    "steps": num_inference_steps,
                    "guidance_scale": guidance_scale,
                    "seed": seed,
                    "style_preset": style_preset,
                    "generation_time": time_per_image,
                    "index": i
                }
                results.append(result)
            
            return results
            
        except Exception as e:
            logger.error(f"❌ Error generando imagen: {str(e)}")
            raise
    
    def save_image(
        self,
        image: Image.Image,
        output_path: Optional[str] = None,
        format: str = "PNG",
        quality: int = 95
    ) -> str:
        """
        Guarda una imagen en disco
        
        Args:
            image: Imagen PIL a guardar
            output_path: Ruta donde guardar (None = auto-generar)
            format: Formato de imagen (PNG, JPEG, WEBP)
            quality: Calidad para formatos con pérdida (JPEG, WEBP)
        
        Returns:
            Ruta donde se guardó la imagen
        """
        if output_path is None:
            output_dir = Path("./generated_images")
            output_dir.mkdir(exist_ok=True)
            filename = f"sdxl_{uuid.uuid4().hex[:8]}.{format.lower()}"
            output_path = str(output_dir / filename)
        
        try:
            image.save(output_path, format=format, quality=quality)
            logger.info(f"💾 Imagen guardada en: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"❌ Error guardando imagen: {str(e)}")
            raise
    
    def image_to_base64(
        self,
        image: Image.Image,
        format: str = "PNG",
        quality: int = 95
    ) -> str:
        """
        Convierte una imagen PIL a base64 para enviar en API
        
        Args:
            image: Imagen PIL
            format: Formato de imagen
            quality: Calidad para formatos con pérdida
        
        Returns:
            String base64 de la imagen
        """
        buffer = io.BytesIO()
        image.save(buffer, format=format, quality=quality)
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        return f"data:image/{format.lower()};base64,{img_base64}"
    
    def _apply_style_preset(self, prompt: str, style: str) -> str:
        """
        Aplica un preset de estilo al prompt
        
        Args:
            prompt: Prompt original
            style: Nombre del preset
        
        Returns:
            Prompt modificado con el estilo
        """
        style_presets = {
            "photographic": f"{prompt}, photorealistic, 8k uhd, dslr, high quality, film grain",
            "digital-art": f"{prompt}, digital art, concept art, highly detailed, trending on artstation",
            "comic-book": f"{prompt}, comic book style, vibrant colors, bold lines, dynamic composition",
            "anime": f"{prompt}, anime style, manga, studio ghibli, detailed, vibrant colors",
            "3d-model": f"{prompt}, 3d render, octane render, highly detailed, professional lighting",
            "cinematic": f"{prompt}, cinematic lighting, movie scene, dramatic, epic composition",
            "fantasy-art": f"{prompt}, fantasy art, magical, ethereal, mystical, detailed",
            "isometric": f"{prompt}, isometric view, game asset, clean, detailed",
            "line-art": f"{prompt}, line art, black and white, clean lines, detailed sketch",
            "low-poly": f"{prompt}, low poly, 3d, geometric, minimalist, game asset",
            "neon-punk": f"{prompt}, neon, cyberpunk, vibrant colors, futuristic",
            "origami": f"{prompt}, origami style, paper art, folded paper, clean",
            "pixel-art": f"{prompt}, pixel art, retro, 8-bit, game sprite",
            "texture": f"{prompt}, seamless texture, tileable, high resolution"
        }
        
        return style_presets.get(style, prompt)
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        Obtiene información sobre el modelo cargado
        
        Returns:
            Diccionario con info del modelo
        """
        return {
            "model_id": self.model_id,
            "refiner_id": self.refiner_id if self.use_refiner else None,
            "device": self.device,
            "is_loaded": self.is_loaded,
            "use_refiner": self.use_refiner,
            "vram_usage_gb": 12 if self.is_loaded else 0,
            "vram_usage_with_refiner_gb": 16 if self.use_refiner else 12,
            "supported_resolutions": [
                {"width": 1024, "height": 1024, "aspect": "1:1"},
                {"width": 1152, "height": 896, "aspect": "4:3"},
                {"width": 896, "height": 1152, "aspect": "3:4"},
                {"width": 1216, "height": 832, "aspect": "3:2"},
                {"width": 832, "height": 1216, "aspect": "2:3"},
                {"width": 1344, "height": 768, "aspect": "16:9"},
                {"width": 768, "height": 1344, "aspect": "9:16"}
            ],
            "recommended_steps": {
                "fast": 20,
                "balanced": 30,
                "quality": 50
            },
            "estimated_time_per_image": {
                "fast": "5-6s",
                "balanced": "8-10s",
                "quality": "15-20s"
            },
            "style_presets": [
                "photographic", "digital-art", "comic-book", "anime",
                "3d-model", "cinematic", "fantasy-art", "isometric",
                "line-art", "low-poly", "neon-punk", "origami",
                "pixel-art", "texture"
            ]
        }


# =============================================
# INSTANCIA GLOBAL (Singleton)
# =============================================

_sdxl_service_instance = None

def get_sdxl_service() -> SDXLImageService:
    """
    Obtiene la instancia singleton del servicio SDXL
    
    Returns:
        Instancia de SDXLImageService
    """
    global _sdxl_service_instance
    
    if _sdxl_service_instance is None:
        _sdxl_service_instance = SDXLImageService(
            device="cuda:1",  # GPU 2
            use_refiner=False,  # Deshabilitado por defecto (ahorra 4GB)
            cache_dir="./models/sdxl"
        )
    
    return _sdxl_service_instance


# =============================================
# FUNCIONES DE UTILIDAD
# =============================================

async def generate_image_from_prompt(
    prompt: str,
    user_plan: str = "pro",
    **kwargs
) -> List[Dict[str, Any]]:
    """
    Función helper para generar imágenes según el plan del usuario
    
    Args:
        prompt: Descripción de la imagen
        user_plan: Plan del usuario (afecta calidad/velocidad)
        **kwargs: Parámetros adicionales para generate_image()
    
    Returns:
        Lista de diccionarios con imágenes generadas
    """
    service = get_sdxl_service()
    
    # Ajustar parámetros según el plan
    plan_settings = {
        "demo": {
            "num_inference_steps": 20,  # Rápido
            "width": 768,
            "height": 768
        },
        "pro": {
            "num_inference_steps": 30,  # Balanceado
            "width": 1024,
            "height": 1024
        },
        "team": {
            "num_inference_steps": 40,  # Calidad
            "width": 1024,
            "height": 1024
        },
        "business": {
            "num_inference_steps": 50,  # Alta calidad
            "width": 1152,
            "height": 1152
        },
        "enterprise": {
            "num_inference_steps": 50,  # Máxima calidad
            "width": 1344,
            "height": 1344
        }
    }
    
    # Aplicar configuración del plan
    plan_config = plan_settings.get(user_plan.lower(), plan_settings["pro"])
    
    # Merge con kwargs del usuario
    generation_params = {**plan_config, **kwargs}
    
    # Generar imagen
    return service.generate_image(prompt, **generation_params)


# =============================================
# EXPORTAR
# =============================================

__all__ = [
    "SDXLImageService",
    "get_sdxl_service",
    "generate_image_from_prompt"
]
