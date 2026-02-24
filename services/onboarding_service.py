"""
onboarding_service.py - Stub temporal para evitar errores de importación
NOTA: Este es un archivo temporal simplificado
"""

import logging
from typing import Any, Dict, Optional
from utils.safe_metrics import Counter, Histogram, Gauge

logger = logging.getLogger(__name__)

# Métricas seguras
SERVICE_OPERATIONS = Counter("onboarding_service_operations_total", "Operations", ["operation", "status"])

class OnboardingMode:
    """Stub temporal de OnboardingMode"""
    
    def __init__(self):
        self.initialized = True
        logger.info({"event": "onboarding_service_stub_initialized"})
    
    async def health_check(self):
        """Health check básico"""
        return {"status": "ok", "service": "onboarding_service", "mode": "stub"}

# Instancia global
onboardingmode = OnboardingMode()

# Funciones de compatibilidad comunes
async def init_onboarding_service():
    """Inicialización stub"""
    logger.info({"event": "onboarding_service_stub_init"})

async def get_service_status():
    """Estado del servicio"""
    return {"status": "stub", "service": "onboarding_service"}
