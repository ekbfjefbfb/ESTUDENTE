"""
Configuración de planes de suscripción v4.0 - Psicología de Precios Agresiva
Estrategia de manipulación psicológica para forzar upgrades y competir con ChatGPT
Versión: 4.0 - Octubre 2025
"""

# =============================================
# CONFIGURACIÓN DE PLANES OPTIMIZADOS v4.0
# =============================================

PLANS = {
    # =========================================
    # DEMO (ULTRA RESTRICTIVO - Forzar upgrade)
    # =========================================
    "demo": {
        "name": "Demo",
        "display_name": "Demo Gratis",
        "price": 0.00,
        "price_annual": 0.00,
        "duration_days": 3,  # 🔥 REDUCIDO: 3 días (vs 7 anterior)
        "visible_in_pricing": True,
        "recommended": False,
        
        # Límites ULTRA RESTRICTIVOS para forzar upgrade
        "max_requests_total": 15,  # 🔥 REDUCIDO: 15 mensajes totales
        "max_tokens_total": 1500,
        "max_images_total": 5,  # ✅ 5 imágenes con SDXL local
        "max_voice_minutes_total": 15,  # ✅ ALINEADO 1:1 con mensajes
        "max_document_mb_total": 2,
        "max_livesearch_total": 2,
        
        # Límites diarios muy agresivos
        "max_requests_daily": 5,
        "max_tokens_daily": 500,
        "max_images_daily": 2,  # ✅ Aumentado (SDXL local = gratis)
        "max_voice_minutes_daily": 5,  # ✅ ALINEADO 1:1 (5 mensajes = 5 min)
        "max_document_mb_daily": 1,
        "max_livesearch_daily": 1,
        
        # Agentes y rate limits
        "max_personal_agents": 50,  # 🎯 TODOS visibles pero limitados en uso
        "max_users": 1,
        "cooldown_between_requests": 90,  # 🔥 90 segundos de cooldown (frustrante)
        "rate_limit_per_minute": 2,
        
        # 🎁 REFERRALS ELIMINADOS (no distraer del upgrade)
        "referral_bonus_days": 0,  # 🔥 Sin bonus por referidos
        "max_referral_bonus_days": 0,
        "can_share_referral_link": False,  # 🔥 Forzar upgrade primero
        
        # Features
        "features": {
            "basic_chat": True,
            "gpt4_access": True,  # Para enganchar con calidad
            "livesearch": True,
            "image_generation": True,
            "voice_synthesis": True,
            "document_analysis": True,
            "personal_agents": True,  # 50 agentes visibles
            "priority_support": False,
            "api_access": False,
            "voice_cloning": False,
            "bulk_operations": False,
            "webhooks": False,
            "integrations": False,
            "workspace_sharing": False,
            "sso": False,
            "sla": False,
            "dedicated_support": False,
            "white_label": False,
            "custom_integrations": False
        },
        
        # Mensajes de marketing (URGENCIA)
        "tagline": "💥 3 días para probar - 15 mensajes totales",
        "description": "Demo ultra limitado. Upgrade para desbloquear todo.",
        "target_audience": "Nuevos usuarios (forzar decisión rápida)",
        "urgency_message": "⏰ Solo 3 días - Upgrade ahora y ahorra 65% vs ChatGPT"
    },
    
    # =========================================
    # PRO - $7.99/mes (Precio psicológico < $10)
    # =========================================
    "pro": {
        "name": "Pro",
        "display_name": "Pro",
        "price": 7.99,  # 🎯 Precio psicológico debajo de $10
        "price_annual": 76.70,  # Ahorra $19/año (20% descuento)
        "duration_days": 30,
        "visible_in_pricing": True,
        "recommended": False,
        
        # Límites mensuales
        "max_requests_daily": 40,  # 1,200/mes
        "max_tokens_daily": 3400,  # ~100K/mes
        "max_images_daily": 2,  # 60/mes con SDXL local
        "max_voice_minutes_daily": 40,  # ✅ 1,200 min/mes = 20 horas (1:1 con chat)
        "max_document_mb_daily": 33,  # ~1GB/mes
        "max_livesearch_daily": 3,  # ~90/mes
        
        # Agentes y usuarios
        "max_personal_agents": 50,
        "max_users": 1,
        "cooldown_between_requests": 3,  # 3 segundos
        "rate_limit_per_minute": 20,
        
        # Features
        "features": {
            "basic_chat": True,
            "gpt4_access": True,
            "livesearch": True,
            "image_generation": True,
            "voice_synthesis": True,
            "document_analysis": True,
            "personal_agents": True,
            "priority_support": False,
            "api_access": False,
            "voice_cloning": False,
            "bulk_operations": False,
            "webhooks": False,
            "integrations": False,
            "workspace_sharing": False,
            "sso": False,
            "sla": False,
            "dedicated_support": False,
            "white_label": False,
            "custom_integrations": False
        },
        
        # Mensajes de marketing
        "tagline": "💎 Menos que 2 cafés al mes",
        "description": "1,200 mensajes IA/mes. Ideal para estudiantes y freelancers.",
        "target_audience": "Estudiantes, freelancers (60% usuarios)",
        "bullets": [
            "✅ 1,200 mensajes IA/mes (~40 diarios)",
            "✅ 50 agentes IA personalizados",
            "✅ 60 imágenes/mes con SDXL local",
            "✅ 1,200 minutos voz/mes = 20 horas (1:1 con chat)",
            "✅ 1GB documentos/mes",
            "✅ Qwen 2.5 Omni 57B incluido",
            "💰 Solo $7.99/mes (vs ChatGPT Plus $20)",
            "🔥 60% más barato que ChatGPT"
        ],
        "comparison": "ChatGPT Plus $20/mes - Nosotros $7.99/mes = Ahorra $144/año"
    },
    
    # =========================================
    # TEAM - $19/mes ⭐ MÁS POPULAR (Goldilocks)
    # =========================================
    "team": {
        "name": "Team",
        "display_name": "Team",
        "price": 19.00,  # 🎯 Precio Goldilocks (ni muy caro ni muy barato)
        "price_annual": 182.00,  # Ahorra $46/año (20% descuento)
        "duration_days": 30,
        "visible_in_pricing": True,
        "recommended": True,  # ⭐ PLAN MÁS POPULAR
        
        # Límites mensuales (compartidos entre 3 usuarios)
        "max_requests_daily": 200,  # 6,000/mes compartidos
        "max_tokens_daily": 16700,  # ~500K/mes compartidos
        "max_images_daily": 10,  # 300/mes compartidos con SDXL local
        "max_voice_minutes_daily": 200,  # ✅ 6,000 min/mes = 100 horas (1:1 con chat)
        "max_document_mb_daily": 167,  # ~5GB/mes compartidos
        "max_livesearch_daily": 17,  # ~500/mes compartidos
        
        # Agentes y usuarios
        "max_personal_agents": 50,
        "max_users": 3,  # 🎯 3 usuarios = $6.33/usuario
        "can_invite_users": True,
        "cooldown_between_requests": 1,
        "rate_limit_per_minute": 40,
        
        # Features
        "features": {
            "basic_chat": True,
            "gpt4_access": True,
            "livesearch": True,
            "image_generation": True,
            "voice_synthesis": True,
            "document_analysis": True,
            "personal_agents": True,
            "priority_support": True,  # Soporte 12h
            "api_access": True,
            "voice_cloning": True,
            "bulk_operations": True,
            "webhooks": True,
            "integrations": True,  # Zapier, Make, n8n
            "workspace_sharing": True,
            "sso": False,
            "sla": False,
            "dedicated_support": False,
            "white_label": False,
            "custom_integrations": False
        },
        
        # Mensajes de marketing
        "tagline": "⭐ MÁS POPULAR - Equipos pequeños",
        "description": "6,000 mensajes IA/mes compartidos. Perfecto para equipos de 3.",
        "target_audience": "Equipos pequeños 2-3 personas (30% usuarios)",
        "bullets": [
            "✅ 6,000 mensajes IA/mes compartidos",
            "✅ 3 usuarios = $6.33/usuario",
            "✅ 50 agentes IA compartidos",
            "✅ 300 imágenes/mes con SDXL local",
            "✅ 6,000 minutos voz/mes = 100 horas (1:1 con chat)",
            "✅ 5GB documentos/mes",
            "✅ API + Webhooks",
            "✅ Integraciones (Zapier, Make)",
            "✅ Soporte prioritario 12h",
            "💰 Solo $19/mes (vs ChatGPT Team $75)",
            "🔥 75% más barato que ChatGPT Team"
        ],
        "badge": "⭐ MÁS POPULAR",
        "comparison": "ChatGPT Team $75/mes - Nosotros $19/mes = Ahorra $672/año"
    },
    
    # =========================================
    # BUSINESS - $49/mes ⭐ MEJOR VALOR (Reducido de $69)
    # =========================================
    "business": {
        "name": "Business",
        "display_name": "Business Pro",
        "price": 49.00,  # 🔥 REDUCIDO de $69 a $49
        "price_annual": 470.00,  # Ahorra $118/año (20% descuento)
        "duration_days": 30,
        "visible_in_pricing": True,
        "recommended": False,
        
        # Límites mensuales MEJORADOS (compartidos entre 10 usuarios)
        "max_requests_daily": 1500,  # 🔥 AUMENTADO: 45,000/mes compartidos
        "max_tokens_daily": 125000,  # 🔥 AUMENTADO: ~3.75M/mes compartidos
        "max_images_daily": 100,  # 🔥 AUMENTADO: 3,000/mes compartidos
        "max_voice_minutes_daily": 1500,  # 🔥 AUMENTADO: 45,000 min/mes = 750 horas
        "max_document_mb_daily": 1000,  # 🔥 AUMENTADO: ~30GB/mes compartidos
        "max_livesearch_daily": 125,  # 🔥 AUMENTADO: ~3,750/mes compartidos
        
        # Agentes y usuarios
        "max_personal_agents": 50,
        "max_users": 10,  # 🎯 10 usuarios = $4.90/usuario
        "can_invite_users": True,
        "cooldown_between_requests": 0,  # Sin cooldown
        "rate_limit_per_minute": 150,  # AUMENTADO
        
        # Features COMPLETAS
        "features": {
            "basic_chat": True,
            "gpt4_access": True,
            "livesearch": True,
            "image_generation": True,
            "voice_synthesis": True,
            "document_analysis": True,
            "personal_agents": True,
            "priority_support": True,  # Soporte 2h
            "api_access": True,
            "voice_cloning": True,
            "bulk_operations": True,
            "webhooks": True,
            "integrations": True,
            "workspace_sharing": True,
            "sso": True,  # SSO/SAML incluido
            "sla": True,  # SLA 99.9% incluido
            "dedicated_support": True,  # Account manager incluido
            "white_label": True,  # 🔥 AHORA INCLUIDO (antes solo en Enterprise)
            "custom_integrations": True,
            "onboarding": True  # Onboarding personalizado incluido
        },
        
        # Mensajes de marketing MEJORADOS
        "tagline": "🚀 TODO INCLUIDO - Mejor valor total",
        "description": "45,000 mensajes IA/mes + White-label incluido. El plan más completo.",
        "target_audience": "Equipos medianos y empresas (10% usuarios)",
        "bullets": [
            "✅ 45,000 mensajes IA/mes compartidos (50% MÁS que antes)",
            "✅ 10 usuarios = $4.90/usuario (MÁS BARATO que cualquier plan)",
            "✅ 50 agentes IA compartidos",
            "✅ 3,000 imágenes/mes con SDXL local (DOBLE que antes)",
            "✅ 45,000 minutos voz/mes = 750 horas totales",
            "✅ 30GB documentos/mes (50% MÁS que antes)",
            "✅ SLA 99.9% garantizado",
            "✅ Soporte dedicado 2h + Account manager",
            "✅ SSO/SAML enterprise INCLUIDO",
            "✅ White-label COMPLETO INCLUIDO (antes solo en Enterprise $299)",
            "✅ Integraciones custom ilimitadas",
            "✅ Onboarding personalizado INCLUIDO",
            "✅ Infraestructura dedicada",
            "💰 Solo $49/mes (ANTES $69, AHORRAS $20)",
            "🔥 Precio especial permanente",
            "🎯 White-label incluido (valor $100/mes gratis)"
        ],
        "badge": "⭐ MEJOR VALOR TOTAL",
        "comparison": "ChatGPT Team $75/mes - Nosotros $49/mes = Ahorra $312/año + White-label gratis"
    }
}

# NOTA: Plan Enterprise a $299 ELIMINADO - Business ahora incluye TODO
# =============================================
# MAPEO DE COMPATIBILIDAD (planes antiguos → nuevos v4.0)
# =============================================

PLAN_MIGRATION_MAP = {
    "trial": "demo",  # Trial → Demo (más restrictivo)
    "starter": "pro",  # Starter → Pro (mismo tier)
    "hobby": "pro",  # Hobby → Pro
    "basic": "pro",  # Basic → Pro
    "creator": "team",  # Creator → Team
    "professional": "team",  # Professional → Team
    "pro": "team",  # Pro (antiguo) → Team
    "business": "business",  # Mantener Business
    "enterprise": "enterprise"  # Mantener Enterprise
}

# Configuración adicional para compatibilidad
PLAN_CONFIGS = PLANS

# Modelo por defecto de DeepSeek
DEFAULT_DEEPSEEK_MODEL = "deepseek-vl-33b"

# Asegurar que todos los planes tengan configuración de modelos
for plan_name, plan_config in PLANS.items():
    if "models" not in plan_config:
        plan_config["models"] = {
            "deepseek_model": DEFAULT_DEEPSEEK_MODEL,
            "vision_model": "deepseek-vl-33b",
            "voice_stt_model": "whisper-large-v3",
            "voice_tts_model": "coqui-tts-enterprise"
        }

# Multiplicadores de timeout por plan (v4.0)
TIMEOUT_MULTIPLIERS = {
    "demo": 0.5,
    "pro": 1.0,
    "team": 1.5,
    "business": 2.5,
    "enterprise": 3.5,
    # Compatibilidad planes antiguos
    "demo": 0.5,
    "starter": 0.8,
    "basic": 1.0,
    "pro": 2.0
}

# =============================================
# FUNCIONES DE UTILIDAD
# =============================================

def get_plan_config(plan_name: str) -> dict:
    """Obtiene la configuración de un plan (con mapeo de compatibilidad)"""
    plan_key = plan_name.lower()
    
    # Mapear planes antiguos a nuevos
    if plan_key in PLAN_MIGRATION_MAP:
        plan_key = PLAN_MIGRATION_MAP[plan_key]
    
    return PLANS.get(plan_key, PLANS["trial"])

def get_plan_limits(plan_name: str) -> dict:
    """Obtiene los límites de un plan"""
    plan = get_plan_config(plan_name)
    return {
        "max_requests_daily": plan.get("max_requests_daily", 5),
        "max_tokens_daily": plan.get("max_tokens_daily", 500),
        "max_images_daily": plan.get("max_images_daily", 0),
        "max_voice_minutes_daily": plan.get("max_voice_minutes_daily", 0),
        "max_document_mb_daily": plan.get("max_document_mb_daily", 0),
        "max_livesearch_daily": plan.get("max_livesearch_daily", 1),
        "cooldown_between_requests": plan.get("cooldown_between_requests", 60),
        "rate_limit_per_minute": plan.get("rate_limit_per_minute", 1)
    }

def get_plan_features(plan_name: str) -> dict:
    """Obtiene las características de un plan"""
    plan = get_plan_config(plan_name)
    return plan.get("features", {})

def calculate_plan_value(plan_name: str) -> dict:
    """Calcula el valor y ahorros de un plan"""
    plan = get_plan_config(plan_name)
    price_monthly = plan.get("price", 0)
    price_annual = plan.get("price_annual", price_monthly * 12)
    
    # Costo aproximado si se pagara por uso
    usage_cost = {
        "trial": 0,
        "hobby": 65,  # Valor real si fuera pay-per-use
        "professional": 149,
        "business": 399,
        "enterprise": 1299,
        # Compatibilidad planes antiguos
        "demo": 0,
        "starter": 45,
        "basic": 89,
        "pro": 299
    }
    
    estimated_value = usage_cost.get(plan_name.lower(), 0)
    savings_monthly = max(0, estimated_value - price_monthly)
    savings_percent_monthly = (savings_monthly / estimated_value * 100) if estimated_value > 0 else 0
    
    # Calcular ahorro anual
    annual_discount = (price_monthly * 12) - price_annual
    
    return {
        "price_monthly": price_monthly,
        "price_annual": price_annual,
        "estimated_value": estimated_value,
        "savings_monthly": savings_monthly,
        "savings_percent_monthly": savings_percent_monthly,
        "annual_discount": annual_discount,
        "annual_discount_percent": (annual_discount / (price_monthly * 12) * 100) if price_monthly > 0 else 0
    }

def get_upgrade_recommendations(current_plan: str) -> list:
    """Obtiene recomendaciones de upgrade basadas en el plan actual"""
    # Orden de planes (nuevos)
    plan_order = ["trial", "hobby", "professional", "business", "enterprise"]
    
    # Mapear plan actual si es antiguo
    current_plan_key = current_plan.lower()
    if current_plan_key in PLAN_MIGRATION_MAP:
        current_plan_key = PLAN_MIGRATION_MAP[current_plan_key]
    
    try:
        current_idx = plan_order.index(current_plan_key)
    except ValueError:
        current_idx = 0
    
    recommendations = []
    for i, plan_id in enumerate(plan_order):
        if i > current_idx and plan_id in PLANS:
            plan_config = PLANS[plan_id]
            
            # Saltar si no es visible (Enterprise)
            if not plan_config.get("visible_in_pricing", True):
                continue
            
            current_limits = get_plan_limits(current_plan)
            upgrade_limits = get_plan_limits(plan_id)
            
            benefits = []
            if upgrade_limits["max_requests_daily"] > current_limits["max_requests_daily"]:
                increase = upgrade_limits['max_requests_daily'] - current_limits['max_requests_daily']
                benefits.append(f"+{increase} mensajes/día ({upgrade_limits['max_requests_daily']} total)")
            
            if upgrade_limits["max_tokens_daily"] > current_limits["max_tokens_daily"]:
                benefits.append(f"{upgrade_limits['max_tokens_daily']:,} tokens/día")
            
            if upgrade_limits.get("max_images_daily", 0) > current_limits.get("max_images_daily", 0):
                benefits.append(f"+{upgrade_limits['max_images_daily'] - current_limits['max_images_daily']} imágenes/día")
            
            # Añadir features exclusivas
            current_features = get_plan_features(current_plan)
            upgrade_features = get_plan_features(plan_id)
            
            exclusive_features = []
            for feature, enabled in upgrade_features.items():
                if enabled and not current_features.get(feature, False):
                    feature_names = {
                        "api_access": "API Access",
                        "webhooks": "Webhooks",
                        "integrations": "Integraciones",
                        "sso": "SSO/SAML",
                        "sla": "SLA 99.9%",
                        "dedicated_support": "Soporte dedicado"
                    }
                    if feature in feature_names:
                        exclusive_features.append(feature_names[feature])
            
            if exclusive_features:
                benefits.extend(exclusive_features)
            
            current_price = PLANS[current_plan_key]["price"]
            upgrade_price = plan_config["price"]
            
            recommendations.append({
                "plan": plan_config.get("display_name", plan_config["name"]),
                "plan_id": plan_id,
                "price_monthly": upgrade_price,
                "price_annual": plan_config.get("price_annual", upgrade_price * 12),
                "benefits": benefits[:5],  # Top 5 beneficios
                "price_increase": upgrade_price - current_price,
                "value_multiplier": upgrade_limits["max_requests_daily"] / max(current_limits["max_requests_daily"], 1),
                "recommended": plan_config.get("recommended", False)
            })
    
    return recommendations

def is_plan_feature_enabled(plan_name: str, feature: str) -> bool:
    """Verifica si una característica está habilitada en un plan"""
    plan = get_plan_config(plan_name)
    features = plan.get("features", {})
    return features.get(feature, False)

def get_plan_timeout_multiplier(plan_name: str) -> float:
    """Obtiene el multiplicador de timeout para un plan"""
    return TIMEOUT_MULTIPLIERS.get(plan_name.lower(), 1.0)

# =============================================
# CONFIGURACIÓN ANTI-ABUSO MEJORADA
# =============================================

def get_demo_usage_limits():
    """Obtiene límites ultra restrictivos para usuarios demo"""
    return {
        "max_requests_total": 10,
        "max_requests_daily": 5,
        "max_tokens_total": 1000,
        "max_tokens_daily": 500,
        "max_images_total": 1,
        "max_voice_minutes_total": 1,
        "max_document_mb_total": 2,
        "max_livesearch_total": 2,
        "cooldown_seconds": 60,
        "duration_hours": 72  # 3 días
    }

def get_user_limits(user):
    """Obtiene límites específicos para un usuario"""
    if not hasattr(user, 'plan') or not user.plan:
        limits = get_demo_usage_limits()
    else:
        plan_config = PLANS.get(user.plan.name.lower())
        if not plan_config:
            limits = get_demo_usage_limits()
        else:
            limits = get_plan_limits(user.plan.name)
    
    return limits

# =============================================
# ANÁLISIS FINANCIERO
# =============================================

def calculate_break_even_metrics():
    """Calcula métricas de break-even del negocio (ACTUALIZADO)"""
    fixed_costs_monthly = 466.33  # Costos fijos reales
    cost_per_user = 10.60  # Costo promedio por usuario
    
    # Distribución objetivo de usuarios por plan (NUEVOS PLANES)
    target_distribution = {
        "trial": {"users": 1000, "conversion_rate": 0.20},  # 20% conversión objetivo
        "hobby": {"users": 150, "price": 19.00},
        "professional": {"users": 200, "price": 39.00},  # Plan ancla
        "business": {"users": 40, "price": 99.00},
        "enterprise": {"users": 10, "price": 499.00}
    }
    
    # Calcular ingresos proyectados
    monthly_revenue = 0
    for plan, data in target_distribution.items():
        if plan != "trial":
            monthly_revenue += data["users"] * data["price"]
    
    # Calcular usuarios de pago
    paying_users = sum(data["users"] for plan, data in target_distribution.items() if plan != "trial")
    
    # Calcular costos variables (con descuento por volumen)
    base_variable_costs = paying_users * cost_per_user
    
    # Descuento por volumen (más usuarios = mejor negociación)
    volume_discount = 0.0
    if paying_users > 500:
        volume_discount = 0.30  # 30% descuento
    elif paying_users > 200:
        volume_discount = 0.20  # 20% descuento
    elif paying_users > 100:
        volume_discount = 0.10  # 10% descuento
    
    variable_costs = base_variable_costs * (1 - volume_discount)
    
    # Break-even
    total_costs = fixed_costs_monthly + variable_costs
    profit = monthly_revenue - total_costs
    profit_margin = (profit / monthly_revenue * 100) if monthly_revenue > 0 else 0
    
    # Precio promedio ponderado
    avg_price = monthly_revenue / paying_users if paying_users > 0 else 39.00
    
    return {
        "monthly_revenue": monthly_revenue,
        "fixed_costs": fixed_costs_monthly,
        "variable_costs": variable_costs,
        "volume_discount": volume_discount,
        "total_costs": total_costs,
        "profit": profit,
        "profit_margin": profit_margin,
        "paying_users": paying_users,
        "avg_price_per_user": avg_price,
        "break_even_users": max(0, fixed_costs_monthly / (avg_price - cost_per_user * (1 - volume_discount))),
        "annual_revenue": monthly_revenue * 12,
        "annual_profit": profit * 12
    }

def validate_pricing_sustainability():
    """Valida que los precios sean sostenibles"""
    metrics = calculate_break_even_metrics()
    
    sustainability_check = {
        "is_profitable": metrics["profit"] > 0,
        "margin_healthy": metrics["profit_margin"] > 20,  # Margen mínimo 20%
        "break_even_realistic": metrics["break_even_users"] < 500,  # Meta realista
        "revenue_covers_fixed": metrics["monthly_revenue"] > metrics["fixed_costs"]
    }
    
    return {
        "metrics": metrics,
        "sustainability": sustainability_check,
        "recommendations": {
            "demo_conversion_critical": True,
            "focus_on_basic_pro": True,
            "enterprise_high_value": True,
            "cost_monitoring_essential": True
        }
    }

# =============================================
# CONFIGURACIÓN DE DISTRIBUCIÓN
# =============================================

DISTRIBUTION_STRATEGY = {
    "web_app": {
        "subscription_handling": True,
        "payment_processing": True,
        "full_features": True,
        "avoid_store_commission": True
    },
    "mobile_app": {
        "login_only": True,
        "basic_features": True,
        "redirect_to_web": True,
        "no_payments": True  # Evitar comisión 30%
    },
    "app_stores": {
        "apple_commission": 0.30,
        "google_commission": 0.30,
        "strategy": "freemium_web_redirect"
    }
}

def get_effective_price_after_commission(plan_name: str, platform: str = "web") -> float:
    """Calcula precio efectivo después de comisiones"""
    plan = get_plan_config(plan_name)
    base_price = plan.get("price", 0)
    
    if platform in ["ios", "android"]:
        commission = DISTRIBUTION_STRATEGY["app_stores"]["apple_commission"]
        return base_price * (1 - commission)
    
    return base_price  # Web no tiene comisión

# =============================================
# FUNCIONES HELPER PARA FRONTEND
# =============================================

def get_visible_plans() -> list:
    """Obtiene solo los planes visibles para la página de pricing"""
    visible = []
    for plan_id, plan_config in PLANS.items():
        if plan_config.get("visible_in_pricing", False):
            visible.append({
                "id": plan_id,
                "name": plan_config.get("display_name", plan_config["name"]),
                "price_monthly": plan_config["price"],
                "price_annual": plan_config.get("price_annual", plan_config["price"] * 12),
                "annual_savings": (plan_config["price"] * 12) - plan_config.get("price_annual", plan_config["price"] * 12),
                "tagline": plan_config.get("tagline", ""),
                "description": plan_config.get("description", ""),
                "bullets": plan_config.get("bullets", []),
                "recommended": plan_config.get("recommended", False),
                "badge": plan_config.get("badge", ""),
                "cta": "Comenzar" if plan_config["price"] > 0 else "Probar Gratis"
            })
    
    # Ordenar por precio
    visible.sort(key=lambda x: x["price_monthly"])
    return visible

def get_plan_comparison_table() -> dict:
    """Genera tabla comparativa de features para el frontend"""
    visible_plans = ["hobby", "professional", "business"]
    
    features_list = [
        {"id": "messages", "name": "Mensajes IA/mes", "type": "limit"},
        {"id": "agents", "name": "Agentes IA personalizados", "type": "limit"},
        {"id": "images", "name": "Imágenes/mes", "type": "limit"},
        {"id": "voice", "name": "Síntesis de voz/mes", "type": "limit"},
        {"id": "documents", "name": "Documentos/mes", "type": "limit"},
        {"id": "users", "name": "Usuarios incluidos", "type": "limit"},
        {"id": "ai_access", "name": "Acceso a IA Local", "type": "feature"},
        {"id": "api_access", "name": "API Access", "type": "feature"},
        {"id": "webhooks", "name": "Webhooks", "type": "feature"},
        {"id": "integrations", "name": "Integraciones", "type": "feature"},
        {"id": "priority_support", "name": "Soporte prioritario", "type": "feature"},
        {"id": "sso", "name": "SSO/SAML", "type": "feature"},
        {"id": "sla", "name": "SLA 99.9%", "type": "feature"},
    ]
    
    comparison = {
        "plans": [],
        "features": []
    }
    
    # Añadir planes
    for plan_id in visible_plans:
        plan = PLANS[plan_id]
        comparison["plans"].append({
            "id": plan_id,
            "name": plan.get("display_name", plan["name"]),
            "price": plan["price"],
            "recommended": plan.get("recommended", False)
        })
    
    # Añadir features
    for feature in features_list:
        feature_row = {
            "id": feature["id"],
            "name": feature["name"],
            "type": feature["type"],
            "values": []
        }
        
        for plan_id in visible_plans:
            plan = PLANS[plan_id]
            
            if feature["type"] == "limit":
                if feature["id"] == "messages":
                    value = f"~{plan['max_requests_daily'] * 30:,}"
                elif feature["id"] == "agents":
                    value = str(plan["max_personal_agents"])
                elif feature["id"] == "images":
                    value = f"~{plan['max_images_daily'] * 30:,}"
                elif feature["id"] == "voice":
                    value = f"~{plan['max_voice_minutes_daily'] * 30:,} min"
                elif feature["id"] == "documents":
                    value = f"~{int(plan['max_document_mb_daily'] * 30 / 1024)}GB"
                elif feature["id"] == "users":
                    value = str(plan.get("max_users", 1))
                else:
                    value = "-"
            else:
                # Feature booleana
                enabled = plan["features"].get(feature["id"], False)
                value = "✅" if enabled else "❌"
            
            feature_row["values"].append(value)
        
        comparison["features"].append(feature_row)
    
    return comparison

def get_plan_faq() -> list:
    """Obtiene FAQs para la página de pricing"""
    return [
        {
            "question": "¿Todos los planes tienen acceso a los 50 agentes IA?",
            "answer": "Sí, todos los planes incluyen acceso completo a los 50 agentes IA personalizados. La diferencia está en los límites de uso (mensajes, imágenes, voz, etc.)."
        },
        {
            "question": "¿Puedo cambiar de plan en cualquier momento?",
            "answer": "Sí, puedes hacer upgrade o downgrade en cualquier momento. Los cambios se aplican inmediatamente y se prorratea el pago."
        },
        {
            "question": "¿Qué pasa si supero los límites de mi plan?",
            "answer": "Recibirás una notificación cuando alcances el 80% de tu límite. Puedes hacer upgrade para obtener más capacidad o esperar al próximo ciclo de facturación."
        },
        {
            "question": "¿Hay descuento en planes anuales?",
            "answer": "Sí, los planes anuales tienen un 16.6% de descuento (equivalente a 2 meses gratis)."
        },
        {
            "question": "¿Los planes incluyen múltiples usuarios?",
            "answer": "Sí, Professional incluye 3 usuarios y Business incluye 10 usuarios. Puedes añadir usuarios adicionales por un costo extra."
        },
        {
            "question": "¿Qué es el plan Enterprise?",
            "answer": "El plan Enterprise es personalizado para organizaciones grandes con necesidades específicas. Contacta a ventas para una propuesta a medida."
        },
        {
            "question": "¿Puedo probar antes de pagar?",
            "answer": "Sí, ofrecemos un trial gratuito de 7 días con acceso a todas las funciones (con límites reducidos)."
        }
    ]

# Exportar todo para compatibilidad
__all__ = [
    "PLANS", "PLAN_CONFIGS", "PLAN_MIGRATION_MAP", "TIMEOUT_MULTIPLIERS",
    "get_plan_config", "get_plan_limits", "get_plan_features", 
    "calculate_plan_value", "get_upgrade_recommendations", 
    "is_plan_feature_enabled", "get_plan_timeout_multiplier",
    "get_demo_usage_limits", "get_user_limits",
    "calculate_break_even_metrics", "validate_pricing_sustainability",
    "DISTRIBUTION_STRATEGY", "get_effective_price_after_commission",
    "get_visible_plans", "get_plan_comparison_table", "get_plan_faq"
]