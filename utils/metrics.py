"""
Sistema de métricas con Prometheus
Versión: Production v1.0
Fecha: 2024-10-08
"""

import logging
import asyncio
import time
from typing import Dict, Any, Optional
from threading import Thread
import os

from prometheus_client import (
    Counter, Histogram, Gauge, Info, Enum,
    start_http_server, generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, REGISTRY
)
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.values import ValueClass

import json_log_formatter

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("metrics")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# =============================================
# CONFIGURACIÓN
# =============================================
METRICS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))
METRICS_ENABLED = os.getenv("METRICS_ENABLED", "true").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# =============================================
# MÉTRICAS GLOBALES DE LA APLICACIÓN
# =============================================

# Información de la aplicación
app_info = Info(
    "backend_saas_ultra_info", 
    "Información del Backend SaaS Ultra"
)

# Estado de la aplicación
app_status = Enum(
    "backend_saas_ultra_status",
    "Estado actual de la aplicación",
    states=["starting", "healthy", "degraded", "unhealthy"]
)

# Métricas de requests HTTP
http_requests_total = Counter(
    "http_requests_total",
    "Total de requests HTTP",
    ["method", "endpoint", "status_code", "user_type"]
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "Duración de requests HTTP en segundos",
    ["method", "endpoint", "user_type"],
    buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 25.0, 50.0, 100.0]
)

# Métricas de base de datos
db_connections_active = Gauge(
    "db_connections_active",
    "Conexiones activas a la base de datos"
)

db_query_duration_seconds = Histogram(
    "db_query_duration_seconds",
    "Duración de queries a la base de datos",
    ["operation", "table"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

# Métricas de Redis
redis_connections_active = Gauge(
    "redis_connections_active",
    "Conexiones activas a Redis"
)

redis_operations_total = Counter(
    "redis_operations_total",
    "Total de operaciones en Redis",
    ["operation", "status"]
)

# Métricas de cola de tareas
task_queue_size = Gauge(
    "task_queue_size",
    "Tamaño actual de la cola de tareas",
    ["queue_name"]
)

task_processing_duration_seconds = Histogram(
    "task_processing_duration_seconds",
    "Duración de procesamiento de tareas",
    ["task_type", "user_type", "status"],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

# Métricas de usuarios
active_users_total = Gauge(
    "active_users_total",
    "Total de usuarios activos",
    ["user_type", "plan"]
)

user_sessions_total = Gauge(
    "user_sessions_total",
    "Total de sesiones de usuario activas"
)

# Métricas de servicios AI
ai_requests_total = Counter(
    "ai_requests_total",
    "Total de requests a servicios de IA",
    ["service", "model", "user_type", "status"]
)

ai_response_time_seconds = Histogram(
    "ai_response_time_seconds",
    "Tiempo de respuesta de servicios de IA",
    ["service", "model"],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)

# Métricas de pagos
payment_transactions_total = Counter(
    "payment_transactions_total",
    "Total de transacciones de pago",
    ["gateway", "currency", "status"]
)

payment_amount_total = Counter(
    "payment_amount_total",
    "Monto total de pagos procesados",
    ["gateway", "currency", "status"]
)

# Métricas de archivos
file_operations_total = Counter(
    "file_operations_total",
    "Total de operaciones con archivos",
    ["operation", "file_type", "status"]
)

file_size_bytes = Histogram(
    "file_size_bytes",
    "Tamaño de archivos procesados",
    ["file_type"],
    buckets=[1024, 10240, 102400, 1048576, 10485760, 52428800, 104857600]
)

# Métricas de errores
error_total = Counter(
    "error_total",
    "Total de errores en la aplicación",
    ["error_type", "component", "severity"]
)

# =============================================
# FUNCIONES DE CONFIGURACIÓN
# =============================================

def setup_metrics(port: Optional[int] = None) -> bool:
    """
    Configura e inicia el servidor de métricas de Prometheus.
    
    Args:
        port: Puerto para el servidor de métricas (default: METRICS_PORT)
        
    Returns:
        bool: True si se configuró correctamente, False en caso contrario
    """
    if not METRICS_ENABLED:
        logger.info({"event": "metrics_disabled", "reason": "METRICS_ENABLED=false"})
        return False
    
    try:
        metrics_port = port or METRICS_PORT
        
        # Configurar información de la aplicación
        app_info.info({
            "version": "1.0.0",
            "environment": ENVIRONMENT,
            "service": "backend_saas_ultra",
            "build_date": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        })
        
        # Establecer estado inicial
        app_status.state("starting")
        
        # Iniciar servidor en thread separado para no bloquear
        def start_server():
            try:
                start_http_server(metrics_port)
                logger.info({
                    "event": "metrics_server_started",
                    "port": metrics_port,
                    "endpoint": f"http://localhost:{metrics_port}/metrics"
                })
            except Exception as e:
                logger.error({
                    "event": "metrics_server_start_failed",
                    "port": metrics_port,
                    "error": str(e)
                })
        
        # Solo iniciar servidor en el proceso principal
        if os.getenv("PROMETHEUS_MULTIPROC_DIR") is None:
            server_thread = Thread(target=start_server, daemon=True)
            server_thread.start()
        
        # Marcar como healthy después de la configuración
        app_status.state("healthy")
        
        logger.info({
            "event": "metrics_setup_completed",
            "port": metrics_port,
            "enabled": True
        })
        
        return True
        
    except Exception as e:
        logger.error({
            "event": "metrics_setup_failed",
            "error": str(e),
            "port": port or METRICS_PORT
        })
        return False

def get_metrics_summary() -> Dict[str, Any]:
    """Obtiene un resumen de las métricas actuales."""
    try:
        from prometheus_client.parser import text_string_to_metric_families
        
        metrics_text = generate_latest(REGISTRY).decode('utf-8')
        families = text_string_to_metric_families(metrics_text)
        
        summary = {
            "timestamp": time.time(),
            "environment": ENVIRONMENT,
            "metrics_count": 0,
            "categories": {}
        }
        
        for family in families:
            summary["metrics_count"] += 1
            category = family.name.split('_')[0]
            
            if category not in summary["categories"]:
                summary["categories"][category] = 0
            summary["categories"][category] += 1
        
        return summary
        
    except Exception as e:
        logger.error({
            "event": "get_metrics_summary_failed",
            "error": str(e)
        })
        return {"error": str(e)}

# =============================================
# DECORADORES PARA MÉTRICAS
# =============================================

def track_time(metric: Histogram, labels: Dict[str, str] = None):
    """Decorador para trackear tiempo de ejecución."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                error_total.labels(
                    error_type=type(e).__name__,
                    component=func.__name__,
                    severity="error"
                ).inc()
                raise
        return wrapper
    return decorator

def track_async_time(metric: Histogram, labels: Dict[str, str] = None):
    """Decorador para trackear tiempo de ejecución de funciones async."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start_time
                if labels:
                    metric.labels(**labels).observe(duration)
                else:
                    metric.observe(duration)
                return result
            except Exception as e:
                duration = time.time() - start_time
                error_total.labels(
                    error_type=type(e).__name__,
                    component=func.__name__,
                    severity="error"
                ).inc()
                raise
        return wrapper
    return decorator

# =============================================
# FUNCIONES HELPER
# =============================================

def increment_counter(counter: Counter, labels: Dict[str, str] = None, value: float = 1):
    """Helper para incrementar contadores de forma segura."""
    try:
        if labels:
            counter.labels(**labels).inc(value)
        else:
            counter.inc(value)
    except Exception as e:
        logger.error({
            "event": "counter_increment_failed",
            "counter": counter._name,
            "error": str(e)
        })

def set_gauge(gauge: Gauge, value: float, labels: Dict[str, str] = None):
    """Helper para establecer valores de gauge de forma segura."""
    try:
        if labels:
            gauge.labels(**labels).set(value)
        else:
            gauge.set(value)
    except Exception as e:
        logger.error({
            "event": "gauge_set_failed",
            "gauge": gauge._name,
            "error": str(e)
        })

def observe_histogram(histogram: Histogram, value: float, labels: Dict[str, str] = None):
    """Helper para observar valores en histogram de forma segura."""
    try:
        if labels:
            histogram.labels(**labels).observe(value)
        else:
            histogram.observe(value)
    except Exception as e:
        logger.error({
            "event": "histogram_observe_failed",
            "histogram": histogram._name,
            "error": str(e)
        })

# =============================================
# MÉTRICAS CUSTOMIZADAS POR COMPONENTE
# =============================================

class ComponentMetrics:
    """Clase para agrupar métricas por componente."""
    
    def __init__(self, component_name: str):
        self.component_name = component_name
        
        # Métricas específicas del componente
        self.requests = Counter(
            f"{component_name}_requests_total",
            f"Total requests para {component_name}",
            ["operation", "status"]
        )
        
        self.duration = Histogram(
            f"{component_name}_duration_seconds",
            f"Duración de operaciones en {component_name}",
            ["operation"]
        )
        
        self.errors = Counter(
            f"{component_name}_errors_total",
            f"Total errores en {component_name}",
            ["error_type"]
        )
    
    def track_request(self, operation: str, status: str = "success"):
        """Trackea un request del componente."""
        self.requests.labels(operation=operation, status=status).inc()
    
    def track_error(self, error_type: str):
        """Trackea un error del componente."""
        self.errors.labels(error_type=error_type).inc()

# =============================================
# INICIALIZACIÓN
# =============================================

# Crear métricas por componente principales
auth_metrics = ComponentMetrics("auth")
payment_metrics = ComponentMetrics("payment")
ai_metrics = ComponentMetrics("ai_service")
document_metrics = ComponentMetrics("document")
vision_metrics = ComponentMetrics("vision")

# Exportar métricas principales para uso en otros módulos
__all__ = [
    "setup_metrics",
    "get_metrics_summary",
    "track_time",
    "track_async_time",
    "increment_counter",
    "set_gauge",
    "observe_histogram",
    "ComponentMetrics",
    "http_requests_total",
    "http_request_duration_seconds",
    "db_connections_active",
    "redis_connections_active",
    "task_queue_size",
    "active_users_total",
    "ai_requests_total",
    "payment_transactions_total",
    "error_total",
    "auth_metrics",
    "payment_metrics",
    "ai_metrics",
    "document_metrics",
    "vision_metrics"
]

# Aliases para compatibilidad con código legacy
REQUESTS_TOTAL = http_requests_total
TIMEOUT_COUNT = Counter(
    "timeout_count_total",
    "Total de timeouts en requests",
    ["endpoint", "method"]
)
RATE_LIMIT_HITS = Counter(
    "rate_limit_hits_total",
    "Total de hits de rate limiting",
    ["endpoint", "user_type"]
)

logger.info({
    "event": "metrics_module_loaded",
    "metrics_enabled": METRICS_ENABLED,
    "port": METRICS_PORT
})
