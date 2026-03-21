"""
Configuration Validator - Production Security
Valida que todas las configuraciones críticas estén presentes en producción
Versión: 1.0 - Noviembre 2025
"""

import os
import logging
from typing import List, Dict, Any

logger = logging.getLogger("config_validator")

# Variables críticas que DEBEN estar en producción
REQUIRED_PRODUCTION_VARS = {
    # Core
    "SECRET_KEY": "Clave secreta para JWT y encriptación",
    "JWT_SECRET_KEY": "Clave secreta para firmar JWT (distinta a SECRET_KEY)",
    "DATABASE_URL": "URL de la base de datos PostgreSQL",
    
    # LLM
    "GROQ_API_KEY": "Groq API key",
    
    # Pagos (al menos uno) - ahora opcional
    # "payment_gateway": [
    #     ("STRIPE_SECRET_KEY", "Stripe payment gateway"),
    #     ("PAYPAL_CLIENT_ID", "PayPal payment gateway"),
    #     ("MERCADOPAGO_ACCESS_TOKEN", "MercadoPago payment gateway"),
    # ],
    
    # SMS/WhatsApp - ahora opcional
    # "TWILIO_ACCOUNT_SID": "Twilio para SMS y WhatsApp",
    # "TWILIO_AUTH_TOKEN": "Twilio authentication",
}

# Variables recomendadas (warnings si faltan)
RECOMMENDED_VARS = {
    "FIREBASE_CREDENTIALS_PATH": "Push notifications (Firebase FCM)",
    "SENTRY_DSN": "Error tracking (Sentry)",
    "SMTP_HOST": "Email transaccional",
    "B2_APPLICATION_KEY_ID": "File storage (Backblaze B2)",
}


def validate_production_config() -> Dict[str, Any]:
    """
    Valida la configuración de producción
    
    Returns:
        Dict con resultados de validación:
        - valid: bool - Si la config es válida
        - errors: List[str] - Errores críticos
        - warnings: List[str] - Warnings no críticos
    """
    
    environment = os.getenv("ENVIRONMENT", "development")
    
    # Solo validar en producción
    if environment != "production":
        logger.info(f"⏭️ Skipping config validation (environment: {environment})")
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "environment": environment
        }
    
    logger.info("🔍 Validating production configuration...")
    
    errors = []
    warnings = []
    
    # Validar variables requeridas
    for var_name, description in REQUIRED_PRODUCTION_VARS.items():
        
        # Caso especial: payment gateways (al menos uno)
        if var_name == "payment_gateway":
            gateway_found = False
            for gw_var, gw_desc in description:
                if os.getenv(gw_var):
                    gateway_found = True
                    logger.info(f"✅ Payment gateway found: {gw_desc}")
                    break
            
            if not gateway_found:
                errors.append(
                    f"❌ No payment gateway configured. Set at least one: "
                    f"STRIPE_SECRET_KEY, PAYPAL_CLIENT_ID, or MERCADOPAGO_ACCESS_TOKEN"
                )
            continue
        
        # Variables normales
        value = os.getenv(var_name)
        
        if not value:
            errors.append(f"❌ Missing required variable: {var_name} ({description})")
        elif value in ["", "changeme", "your-key-here", "dev-secret-key-change-in-production"]:
            errors.append(f"❌ {var_name} has invalid/default value. Must be set to real credentials.")
        else:
            logger.info(f"✅ {var_name}: configured")

    # CORS: en producción no permitir wildcard
    cors_origins_raw = str(os.getenv("CORS_ORIGINS", "")).strip()
    if not cors_origins_raw:
        errors.append("❌ Missing required variable: CORS_ORIGINS (Allowed origins for CORS)")
    else:
        origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
        if "*" in origins:
            errors.append("❌ CORS_ORIGINS cannot include '*' in production")

    # OAuth: si está habilitado, exigir credenciales del provider
    oauth_enabled = str(os.getenv("OAUTH_ENABLED") or "").strip().lower() in {"1", "true", "t", "yes"}
    if oauth_enabled:
        if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
            warnings.append("⚠️ OAUTH_ENABLED=true but GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET are not configured")
        if not os.getenv("APPLE_CLIENT_ID") or not os.getenv("APPLE_CLIENT_SECRET"):
            warnings.append("⚠️ OAUTH_ENABLED=true but APPLE_CLIENT_ID/APPLE_CLIENT_SECRET are not configured")

    # JWT secret no debe ser igual a SECRET_KEY (reduce blast radius)
    secret_key = os.getenv("SECRET_KEY")
    jwt_secret_key = os.getenv("JWT_SECRET_KEY")
    if secret_key and jwt_secret_key and secret_key == jwt_secret_key:
        warnings.append("⚠️ JWT_SECRET_KEY should be different from SECRET_KEY in production")
    
    # Validar variables recomendadas
    for var_name, description in RECOMMENDED_VARS.items():
        value = os.getenv(var_name)
        
        if not value:
            warnings.append(f"⚠️ Recommended variable missing: {var_name} ({description})")
        else:
            logger.info(f"✅ {var_name}: configured")
    
    # Resultado final
    is_valid = len(errors) == 0
    
    if is_valid:
        logger.info("✅ Production configuration is VALID")
    else:
        logger.error(f"❌ Production configuration has {len(errors)} critical errors")
    
    if warnings:
        logger.warning(f"⚠️ {len(warnings)} recommended variables missing")
    
    return {
        "valid": is_valid,
        "errors": errors,
        "warnings": warnings,
        "environment": environment
    }


def validate_or_exit():
    """
    Valida la configuración y termina el proceso si hay errores críticos
    
    Use esto en main.py al inicio para asegurar configuración válida
    """
    result = validate_production_config()
    
    if not result["valid"]:
        print("\n" + "="*80)
        print("❌ PRODUCTION CONFIGURATION ERRORS")
        print("="*80)
        
        for error in result["errors"]:
            print(error)
        
        print("\n" + "="*80)
        print("Please fix these errors before deploying to production.")
        print("="*80 + "\n")
        
        # En producción, terminar el proceso
        if result["environment"] == "production":
            import sys
            sys.exit(1)
    
    # Mostrar warnings (no críticos)
    if result["warnings"]:
        print("\n" + "="*80)
        print("⚠️ PRODUCTION CONFIGURATION WARNINGS")
        print("="*80)
        
        for warning in result["warnings"]:
            print(warning)
        
        print("\n" + "="*80)
        print("These are recommended but not required.")
        print("="*80 + "\n")


if __name__ == "__main__":
    # Test de validación
    validate_or_exit()
