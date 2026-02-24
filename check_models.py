#!/usr/bin/env python3
"""
Script de Verificación de Modelos de IA
Verifica qué modelos están instalados y disponibles
"""

import asyncio
import os
import sys
from pathlib import Path

# Colores para terminal
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

def print_header():
    print(f"{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}🤖 VERIFICACIÓN DE MODELOS DE IA{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")

def print_ok(msg):
    print(f"{GREEN}✅ {msg}{RESET}")

def print_error(msg):
    print(f"{RED}❌ {msg}{RESET}")

def print_warning(msg):
    print(f"{YELLOW}⚠️  {msg}{RESET}")

def print_info(msg):
    print(f"{BLUE}ℹ️  {msg}{RESET}")

async def check_ollama():
    """Verifica Ollama + Qwen"""
    print(f"\n{BLUE}[1/5] Verificando Ollama + Qwen 2.5 Omni...{RESET}")
    
    try:
        import httpx
        
        # Check si Ollama está corriendo
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                response = await client.get("http://localhost:11434/api/tags")
                
                if response.status_code == 200:
                    print_ok("Ollama está corriendo")
                    
                    # Check modelos instalados
                    data = response.json()
                    models = data.get("models", [])
                    
                    if models:
                        print_info(f"Modelos instalados: {len(models)}")
                        
                        # Buscar Qwen
                        qwen_models = [m for m in models if "qwen" in m["name"].lower()]
                        
                        if qwen_models:
                            for model in qwen_models:
                                size_bytes = model.get("size", 0)
                                size_gb = size_bytes / (1024 ** 3)
                                print_ok(f"Qwen encontrado: {model['name']} ({size_gb:.1f} GB)")
                            return True
                        else:
                            print_error("Qwen no encontrado")
                            print_info("Ejecuta: ollama pull qwen2.5-omni:57b")
                            return False
                    else:
                        print_warning("No hay modelos instalados en Ollama")
                        print_info("Ejecuta: ollama pull qwen2.5-omni:57b")
                        return False
                    
                    return True
                else:
                    print_error(f"Ollama responde con error: {response.status_code}")
                    return False
                    
            except httpx.ConnectError:
                print_error("Ollama no está corriendo")
                print_info("Inicia Ollama o instala desde: https://ollama.com")
                return False
                
    except ImportError:
        print_error("httpx no instalado")
        print_info("Ejecuta: pip install httpx")
        return False
    except Exception as e:
        print_error(f"Error al verificar Ollama: {e}")
        return False

def check_whisper():
    """Verifica Whisper"""
    print(f"\n{BLUE}[2/5] Verificando Whisper (Speech-to-Text)...{RESET}")
    
    try:
        import whisper
        print_ok("Whisper instalado")
        
        # Intentar cargar modelo
        try:
            # Verificar si el modelo está descargado
            import os
            from pathlib import Path
            
            cache_dir = Path.home() / ".cache" / "whisper"
            model_file = cache_dir / "large-v3.pt"
            
            if model_file.exists():
                size_mb = model_file.stat().st_size / (1024**2)
                print_ok(f"Whisper Large descargado ({size_mb:.0f} MB)")
            else:
                print_warning("Whisper Large no descargado (se descargará en primera ejecución)")
                print_info("Tamaño: ~2.9GB")
            
            return True
        except Exception as e:
            print_warning("No se pudo verificar modelo Whisper")
            return True
            
    except ImportError:
        print_error("Whisper no instalado")
        print_info("Ejecuta: pip install openai-whisper")
        return False
    except Exception as e:
        print_error(f"Error al verificar Whisper: {e}")
        return False

def check_coqui_tts():
    """Verifica Coqui TTS"""
    print(f"\n{BLUE}[3/5] Verificando Coqui TTS (Text-to-Speech)...{RESET}")
    
    try:
        from TTS.api import TTS
        print_ok("Coqui TTS instalado")
        
        # Verificar si el modelo está descargado
        try:
            from pathlib import Path
            
            tts_cache = Path.home() / ".local" / "share" / "tts"
            model_dir = tts_cache / "tts_models--multilingual--multi-dataset--xtts_v2"
            
            if model_dir.exists():
                print_ok("Coqui XTTS-v2 descargado")
            else:
                print_warning("Coqui XTTS-v2 no descargado (se descargará en primera ejecución)")
                print_info("Tamaño: ~1.8GB")
            
            return True
        except Exception as e:
            print_warning("No se pudo verificar modelo Coqui")
            return True
            
    except ImportError:
        print_error("Coqui TTS no instalado")
        print_info("Ejecuta: pip install TTS")
        return False
    except Exception as e:
        print_error(f"Error al verificar Coqui TTS: {e}")
        return False

def check_yolo():
    """Verifica YOLOv8"""
    print(f"\n{BLUE}[4/5] Verificando YOLOv8 (Computer Vision)...{RESET}")
    
    try:
        from ultralytics import YOLO
        print_ok("Ultralytics (YOLOv8) instalado")
        
        # Verificar si el modelo está descargado
        try:
            from pathlib import Path
            
            # YOLOv8 guarda modelos en ~/.cache/torch/hub
            cache_dir = Path.home() / ".cache" / "torch" / "hub"
            
            # Buscar archivo yolov8n.pt
            yolo_files = list(cache_dir.glob("**/yolov8n.pt")) if cache_dir.exists() else []
            
            if yolo_files:
                size_mb = yolo_files[0].stat().st_size / (1024**2)
                print_ok(f"YOLOv8n descargado ({size_mb:.1f} MB)")
            else:
                print_warning("YOLOv8n no descargado (se descargará en primera ejecución)")
                print_info("Tamaño: ~6MB")
            
            return True
        except Exception as e:
            print_warning("No se pudo verificar modelo YOLO")
            return True
            
    except ImportError:
        print_error("Ultralytics (YOLOv8) no instalado")
        print_info("Ejecuta: pip install ultralytics")
        return False
    except Exception as e:
        print_error(f"Error al verificar YOLOv8: {e}")
        return False

def check_api_keys():
    """Verifica API Keys opcionales"""
    print(f"\n{BLUE}[5/5] Verificando API Keys (Opcionales)...{RESET}")
    
    api_keys = {
        "OPENAI_API_KEY": "OpenAI GPT-4",
        "ANTHROPIC_API_KEY": "Anthropic Claude",
        "GROQ_API_KEY": "Groq",
        "ELEVENLABS_API_KEY": "ElevenLabs TTS"
    }
    
    found_keys = []
    
    for key_name, service_name in api_keys.items():
        if os.getenv(key_name):
            print_warning(f"{service_name} configurado (opcional)")
            found_keys.append(service_name)
        else:
            print_info(f"{service_name} no configurado (no necesario)")
    
    if not found_keys:
        print_ok("Backend configurado para funcionar 100% con modelos locales")
    
    return True

def print_summary(results):
    """Imprime resumen final"""
    print(f"\n{BLUE}{'='*60}{RESET}")
    print(f"{BLUE}📊 RESUMEN{RESET}")
    print(f"{BLUE}{'='*60}{RESET}\n")
    
    all_ok = all(results.values())
    
    if all_ok:
        print_ok("¡Todos los modelos están listos!")
        print_info("El backend puede funcionar 100% sin APIs externas")
        print_info("Costo: $0/mes 🎉")
    else:
        print_warning("Algunos modelos no están disponibles")
        print_info("El backend funcionará con las alternativas disponibles")
    
    print(f"\n{BLUE}Resultados:{RESET}")
    for check, result in results.items():
        status = f"{GREEN}✅{RESET}" if result else f"{RED}❌{RESET}"
        print(f"  {status} {check}")
    
    print(f"\n{BLUE}{'='*60}{RESET}\n")
    
    if not all_ok:
        print(f"{YELLOW}💡 Para instalar lo que falta:{RESET}")
        if not results.get("Ollama + Qwen"):
            print("   1. Instala Ollama: curl -fsSL https://ollama.com/install.sh | sh")
            print("   2. Descarga Qwen: ollama pull qwen2.5-omni:57b")
        if not results.get("Whisper"):
            print("   3. Instala Whisper: pip install openai-whisper")
        if not results.get("Coqui TTS"):
            print("   4. Instala Coqui: pip install TTS")
        if not results.get("YOLOv8"):
            print("   5. Instala YOLO: pip install ultralytics")
        print()

async def main():
    """Función principal"""
    print_header()
    
    results = {
        "Ollama + Qwen": await check_ollama(),
        "Whisper": check_whisper(),
        "Coqui TTS": check_coqui_tts(),
        "YOLOv8": check_yolo(),
        "API Keys": check_api_keys()
    }
    
    print_summary(results)
    
    # Return code para CI/CD
    return 0 if all(results.values()) else 1

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Verificación cancelada{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Error inesperado: {e}{RESET}")
        sys.exit(1)
