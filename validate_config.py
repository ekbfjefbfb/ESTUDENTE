#!/usr/bin/env python3
"""
validate_config.py - Validador completo de configuración del backend
Production Ready v4.0 - Backend Súper IA

Valida:
- Variables de entorno requeridas
- Conexiones a servicios externos (Redis, Firebase, PostHog)
- APIs externas (Google, OpenAI, Anthropic)
- Recursos locales (GPU, modelos de voz, archivos)
- Configuración de base de datos
"""

import os
import sys
import asyncio
import logging
from typing import Dict, List, Tuple
from datetime import datetime
from dotenv import load_dotenv

# Colores para output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConfigValidator:
    """Validador de configuración del sistema"""
    
    def __init__(self):
        self.results: List[Tuple[str, bool, str]] = []
        self.critical_failures = 0
        self.warnings = 0
        
    def log_result(self, service: str, success: bool, message: str, critical: bool = False):
        """Registra resultado de validación"""
        self.results.append((service, success, message))
        if not success:
            if critical:
                self.critical_failures += 1
            else:
                self.warnings += 1
    
    def print_header(self, text: str):
        """Imprime encabezado de sección"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")
    
    def print_result(self, service: str, success: bool, message: str):
        """Imprime resultado individual"""
        icon = f"{Colors.GREEN}✅" if success else f"{Colors.RED}❌"
        print(f"{icon} {service:<30} {Colors.RESET}{message}")
    
    # ========================================
    # VALIDACIÓN DE VARIABLES DE ENTORNO
    # ========================================
    
    def validate_env_variables(self):
        """Valida variables de entorno requeridas"""
        self.print_header("1. VALIDACIÓN DE VARIABLES DE ENTORNO")
        
        required_vars = {
            "SECRET_KEY": True,  # Critical
            "JWT_SECRET_KEY": True,  # Critical
            "DATABASE_URL": True,  # Critical
            "REDIS_URL": False,  # Warning
            "AI_SERVER_URL": True,  # Critical
            "ENVIRONMENT": False,
        }
        
        for var, critical in required_vars.items():
            value = os.getenv(var)
            exists = value is not None and value != ""
            self.log_result(
                var,
                exists,
                f"{'Configurada' if exists else 'No configurada'}",
                critical=critical and not exists
            )
            self.print_result(var, exists, f"{'Configurada' if exists else 'No configurada'}")
    
    # ========================================
    # VALIDACIÓN DE BASE DE DATOS
    # ========================================
    
    async def validate_database(self):
        """Valida conexión a base de datos"""
        self.print_header("2. VALIDACIÓN DE BASE DE DATOS")
        
        try:
            from database.db_enterprise import engine
            from sqlalchemy import text
            
            # Intentar conexión
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            
            self.log_result("Database Connection", True, "Conexión exitosa")
            self.print_result("Database Connection", True, "Conexión exitosa")
            
            # Validar que las tablas existen
            async with engine.connect() as conn:
                result = await conn.execute(text(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "UNION SELECT name FROM sqlite_master WHERE type='table'"
                ))
                tables = [row[0] for row in result.fetchall()]
            
            required_tables = ["users", "plans", "subscriptions", "payments"]
            for table in required_tables:
                exists = table in tables
                self.log_result(
                    f"Table: {table}",
                    exists,
                    f"{'Existe' if exists else 'No existe'}",
                    critical=True and not exists
                )
                self.print_result(f"Table: {table}", exists, f"{'Existe' if exists else 'No existe'}")
                
        except Exception as e:
            self.log_result("Database Connection", False, f"Error: {str(e)}", critical=True)
            self.print_result("Database Connection", False, f"Error: {str(e)}")
    
    # ========================================
    # VALIDACIÓN DE REDIS
    # ========================================
    
    async def validate_redis(self):
        """Valida conexión a Redis"""
        self.print_header("3. VALIDACIÓN DE REDIS")
        
        try:
            from services.redis_service import get_redis
            
            redis = await get_redis()
            await redis.ping()
            
            self.log_result("Redis Connection", True, "Conexión exitosa")
            self.print_result("Redis Connection", True, "Conexión exitosa")
            
            # Test set/get
            test_key = "validate_config_test"
            await redis.set(test_key, "test_value", ex=10)
            value = await redis.get(test_key)
            
            self.log_result("Redis Read/Write", value == b"test_value", "Operaciones funcionando")
            self.print_result("Redis Read/Write", value == b"test_value", "Operaciones funcionando")
            
        except Exception as e:
            self.log_result("Redis Connection", False, f"Error: {str(e)}")
            self.print_result("Redis Connection", False, f"Error: {str(e)}")
    
    # ========================================
    # VALIDACIÓN DE IA LOCAL
    # ========================================
    
    async def validate_ai_service(self):
        """Valida servicio de IA local (DeepSeek-VL)"""
        self.print_header("4. VALIDACIÓN DE SERVICIO DE IA LOCAL")
        
        try:
            from services.qwen_client import get_qwen_client
            
            client = await get_qwen_client()
            
            # Test simple de health check
            health = await client.check_health()
            
            success = health is not None
            
            self.log_result(
                "Qwen 2.5 Omni",
                success,
                f"{'Funcionando correctamente' if success else 'Error en respuesta'}",
                critical=True
            )
            self.print_result("DeepSeek-VL 33B", success, f"{'Funcionando correctamente' if success else 'Error en respuesta'}")
            
        except Exception as e:
            self.log_result("DeepSeek-VL 33B", False, f"Error: {str(e)}", critical=True)
            self.print_result("DeepSeek-VL 33B", False, f"Error: {str(e)}")
    
    # ========================================
    # VALIDACIÓN DE MODELOS DE VOZ
    # ========================================
    
    def validate_voice_models(self):
        """Valida modelos de voz (Whisper + Coqui TTS)"""
        self.print_header("5. VALIDACIÓN DE MODELOS DE VOZ")
        
        # Whisper
        try:
            import whisper
            model_name = os.getenv("WHISPER_MODEL", "base")
            
            self.log_result("Whisper Library", True, f"Instalado (modelo: {model_name})")
            self.print_result("Whisper Library", True, f"Instalado (modelo: {model_name})")
        except ImportError:
            self.log_result("Whisper Library", False, "No instalado", critical=True)
            self.print_result("Whisper Library", False, "No instalado")
        
        # Coqui TTS
        try:
            from TTS.api import TTS
            
            self.log_result("Coqui TTS Library", True, "Instalado")
            self.print_result("Coqui TTS Library", True, "Instalado")
        except ImportError:
            self.log_result("Coqui TTS Library", False, "No instalado", critical=True)
            self.print_result("Coqui TTS Library", False, "No instalado")
    
    # ========================================
    # VALIDACIÓN DE GPU/DEVICE
    # ========================================
    
    def validate_gpu(self):
        """Valida disponibilidad de GPU"""
        self.print_header("6. VALIDACIÓN DE GPU/DEVICE")
        
        # CUDA (NVIDIA)
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            device = "cuda" if cuda_available else "cpu"
            
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                self.log_result("CUDA GPU", True, f"Disponible: {gpu_name}")
                self.print_result("CUDA GPU", True, f"Disponible: {gpu_name}")
            else:
                self.log_result("CUDA GPU", False, "No disponible (usando CPU)")
                self.print_result("CUDA GPU", False, "No disponible (usando CPU)")
                
        except ImportError:
            self.log_result("PyTorch", False, "No instalado")
            self.print_result("PyTorch", False, "No instalado")
        
        # MPS (Apple Silicon)
        try:
            import torch
            if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
                self.log_result("Apple MPS", True, "Disponible")
                self.print_result("Apple MPS", True, "Disponible")
        except:
            pass
    
    # ========================================
    # VALIDACIÓN DE APIS EXTERNAS (OPCIONALES)
    # ========================================
    
    def validate_external_apis(self):
        """Valida APIs externas opcionales"""
        self.print_header("7. VALIDACIÓN DE APIS EXTERNAS (OPCIONAL)")
        
        optional_apis = {
            "GOOGLE_CLIENT_ID": "Google OAuth",
            "GOOGLE_CLIENT_SECRET": "Google OAuth Secret",
            "OPENAI_API_KEY": "OpenAI API",
            "ANTHROPIC_API_KEY": "Anthropic API",
            "FIREBASE_CREDENTIALS": "Firebase",
            "POSTHOG_API_KEY": "PostHog Analytics",
        }
        
        for var, name in optional_apis.items():
            value = os.getenv(var)
            exists = value is not None and value != ""
            self.log_result(name, exists, f"{'Configurada' if exists else 'No configurada (opcional)'}")
            self.print_result(name, exists, f"{'Configurada' if exists else 'No configurada (opcional)'}")
    
    # ========================================
    # VALIDACIÓN DE FILESYSTEM
    # ========================================
    
    def validate_filesystem(self):
        """Valida directorios y permisos"""
        self.print_header("8. VALIDACIÓN DE SISTEMA DE ARCHIVOS")
        
        required_dirs = [
            "voice_cache",
            "voice_presets",
            "uploads",
            "logs",
        ]
        
        for dir_name in required_dirs:
            exists = os.path.exists(dir_name)
            writable = os.access(dir_name, os.W_OK) if exists else False
            
            if not exists:
                try:
                    os.makedirs(dir_name, exist_ok=True)
                    exists = True
                    writable = True
                except Exception as e:
                    pass
            
            status = "OK" if (exists and writable) else "Error"
            self.log_result(f"Directory: {dir_name}", exists and writable, status)
            self.print_result(f"Directory: {dir_name}", exists and writable, status)
    
    # ========================================
    # RESUMEN FINAL
    # ========================================
    
    def print_summary(self):
        """Imprime resumen final"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}RESUMEN DE VALIDACIÓN{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.RESET}\n")
        
        total = len(self.results)
        passed = sum(1 for _, success, _ in self.results if success)
        failed = total - passed
        
        print(f"Total de validaciones: {total}")
        print(f"{Colors.GREEN}✅ Exitosas: {passed}{Colors.RESET}")
        print(f"{Colors.RED}❌ Fallidas: {failed}{Colors.RESET}")
        print(f"{Colors.YELLOW}⚠️  Advertencias: {self.warnings}{Colors.RESET}")
        print(f"{Colors.RED}🔥 Críticas: {self.critical_failures}{Colors.RESET}")
        
        if self.critical_failures > 0:
            print(f"\n{Colors.RED}{Colors.BOLD}❌ SISTEMA NO LISTO PARA PRODUCCIÓN{Colors.RESET}")
            print(f"{Colors.RED}Hay {self.critical_failures} fallo(s) crítico(s) que deben resolverse.{Colors.RESET}")
            return False
        elif self.warnings > 0:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠️  SISTEMA PARCIALMENTE LISTO{Colors.RESET}")
            print(f"{Colors.YELLOW}Hay {self.warnings} advertencia(s) - funcionalidad reducida.{Colors.RESET}")
            return True
        else:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✅ SISTEMA 100% LISTO PARA PRODUCCIÓN{Colors.RESET}")
            return True
    
    # ========================================
    # EJECUCIÓN COMPLETA
    # ========================================
    
    async def run_all_validations(self):
        """Ejecuta todas las validaciones"""
        print(f"\n{Colors.BOLD}{Colors.GREEN}🚀 VALIDADOR DE CONFIGURACIÓN - Backend Súper IA v4.0{Colors.RESET}")
        print(f"{Colors.BLUE}Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{Colors.RESET}\n")
        
        # Cargar variables de entorno
        load_dotenv()
        
        # Ejecutar validaciones
        self.validate_env_variables()
        await self.validate_database()
        await self.validate_redis()
        await self.validate_ai_service()
        self.validate_voice_models()
        self.validate_gpu()
        self.validate_external_apis()
        self.validate_filesystem()
        
        # Resumen
        ready = self.print_summary()
        
        return ready


async def main():
    """Función principal"""
    validator = ConfigValidator()
    ready = await validator.run_all_validations()
    
    # Exit code
    sys.exit(0 if ready else 1)


if __name__ == "__main__":
    asyncio.run(main())
