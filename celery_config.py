"""
⚙️ Celery Task Queue Configuration
==================================

Sistema de colas de tareas para procesamiento asíncrono:
- ✅ OCR de documentos largos
- ✅ Generación de imágenes batch
- ✅ Análisis de documentos pesados
- ✅ Procesamiento de videos
- ✅ Envío de emails masivos
- ✅ Generación de reportes
- ✅ Background jobs

Celery con Redis como broker y backend.
"""

import os
from celery import Celery
from celery.schedules import crontab
from kombu import Exchange, Queue
from datetime import timedelta

# =============================================
# CONFIGURACIÓN
# =============================================

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# =============================================
# CELERY APP
# =============================================

celery_app = Celery(
    "mi_backend_super",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
    include=[
        'tasks.document_tasks',
        'tasks.image_tasks',
        'tasks.notification_tasks',
        'tasks.analytics_tasks',
        'tasks.cleanup_tasks',
        'tasks.auto_reports',  # 🔥 v6.0: Reportes automáticos agencias
        'tasks.construction_reports',  # 🏗️ v6.0: Reportes construcción
        'tasks.auto_reports_marketing',  # 📊 v6.1: Reportes marketing (Google Ads + Meta + TikTok)
    ]
)

# =============================================
# CONFIGURACIÓN AVANZADA
# =============================================

celery_app.conf.update(
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Result Backend
    result_expires=3600,  # 1 hora
    result_extended=True,
    
    # Task Settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hora max por tarea
    task_soft_time_limit=3000,  # 50 minutos soft limit
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    
    # Worker Settings
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,
    worker_disable_rate_limits=False,
    worker_concurrency=8,  # 🔥 OPTIMIZADO: 2→8 workers para +400% throughput
    
    # Retry Policy
    task_autoretry_for=(Exception,),
    task_retry_kwargs={'max_retries': 3},
    task_retry_backoff=True,
    task_retry_backoff_max=600,  # 10 minutos max
    task_retry_jitter=True,
    
    # Monitoring
    worker_send_task_events=True,
    task_send_sent_event=True,
    
    # Performance
    broker_pool_limit=10,
    broker_connection_retry=True,
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    
    # Redis Settings
    redis_max_connections=50,
    redis_socket_keepalive=True,
    redis_socket_timeout=30.0,
    
    # Beat Schedule (para tareas periódicas)
    beat_schedule={
        # 🔄 LIMPIEZA Y MANTENIMIENTO
        'cleanup-old-results': {
            'task': 'tasks.cleanup_tasks.cleanup_old_results',
            'schedule': timedelta(hours=6),
        },
        'cleanup-expired-sessions': {
            'task': 'tasks.cleanup_tasks.cleanup_expired_sessions',
            'schedule': timedelta(hours=1),
        },
        
        # 📊 ANALYTICS GENERAL
        'generate-analytics-reports': {
            'task': 'tasks.analytics_tasks.generate_daily_analytics',
            'schedule': timedelta(hours=24),
        },
        
        # 🔥 AGENCIAS MARKETING v6.0 - Auto Reportes
        'send-weekly-reports': {
            'task': 'tasks.auto_reports.send_weekly_reports',
            'schedule': crontab(day_of_week=5, hour=9, minute=0),  # Viernes 9:00 AM
            'options': {'queue': 'high_priority'}
        },
        'send-monthly-reports': {
            'task': 'tasks.auto_reports.send_monthly_reports',
            'schedule': crontab(day_of_month=1, hour=9, minute=0),  # Día 1 del mes 9:00 AM
            'options': {'queue': 'high_priority'}
        },
        
        # 🔥 AGENCIAS MARKETING v6.0 - Monitoreo Proactivo
        'monitor-campaigns-health': {
            'task': 'tasks.auto_reports.monitor_campaigns_health',
            'schedule': timedelta(hours=1),  # Cada hora
            'options': {'queue': 'analytics'}
        },
        'detect-anomalies': {
            'task': 'tasks.auto_reports.detect_campaign_anomalies',
            'schedule': timedelta(hours=6),  # Cada 6 horas
            'options': {'queue': 'analytics'}
        },
        
        # 🏗️ CONSTRUCCIÓN v6.0 - Reportes y Monitoreo
        'send-weekly-construction-reports': {
            'task': 'tasks.construction_reports.generate_weekly_construction_report',
            'schedule': crontab(day_of_week=6, hour=8, minute=0),  # Sábados 8:00 AM
            'options': {'queue': 'high_priority'}
        },
        
        # 📊 MARKETING MULTI-PLATAFORMA v6.1 - Reportes Automáticos
        'send-friday-marketing-reports': {
            'task': 'tasks.auto_reports_marketing.send_friday_reports',
            'schedule': crontab(day_of_week=5, hour=17, minute=0),  # Viernes 5:00 PM
            'options': {'queue': 'high_priority'}
        },
        'detect-marketing-campaign-anomalies': {
            'task': 'tasks.auto_reports_marketing.detect_campaign_anomalies',
            'schedule': timedelta(hours=6),  # Cada 6 horas
            'options': {'queue': 'analytics'}
        },
        'optimize-marketing-ad-spend': {
            'task': 'tasks.auto_reports_marketing.optimize_ad_spend',
            'schedule': crontab(hour=3, minute=0),  # Diario 3:00 AM
            'options': {'queue': 'analytics'}
        },
        'monitor-project-delays': {
            'task': 'tasks.construction_reports.monitor_project_delays',
            'schedule': timedelta(hours=6),  # Cada 6 horas
            'options': {'queue': 'analytics'}
        },
        'alert-budget-overruns': {
            'task': 'tasks.construction_reports.alert_budget_overruns',
            'schedule': crontab(hour=9, minute=0),  # Diario 9:00 AM
            'options': {'queue': 'analytics'}
        },
    },
)

# =============================================
# TASK ROUTES Y PRIORIDADES
# =============================================

# Definir exchanges y queues
default_exchange = Exchange('default', type='direct')
priority_exchange = Exchange('priority', type='direct')
slow_exchange = Exchange('slow', type='direct')

celery_app.conf.task_queues = (
    # Queue default
    Queue('default', default_exchange, routing_key='default', priority=5),
    
    # Queue de alta prioridad (usuarios premium, tareas críticas)
    Queue('high_priority', priority_exchange, routing_key='high_priority', priority=10),
    
    # Queue para tareas lentas (OCR, procesamiento pesado)
    Queue('slow_tasks', slow_exchange, routing_key='slow', priority=3),
    
    # Queue para notificaciones
    Queue('notifications', default_exchange, routing_key='notifications', priority=7),
    
    # Queue para analytics
    Queue('analytics', default_exchange, routing_key='analytics', priority=4),
)

# Routing de tareas
celery_app.conf.task_routes = {
    # Tareas de documentos (OCR, análisis)
    'tasks.document_tasks.*': {
        'queue': 'slow_tasks',
        'routing_key': 'slow'
    },
    
    # Tareas de imágenes
    'tasks.image_tasks.generate_image': {
        'queue': 'high_priority',
        'routing_key': 'high_priority'
    },
    'tasks.image_tasks.batch_generate': {
        'queue': 'slow_tasks',
        'routing_key': 'slow'
    },
    
    # Notificaciones
    'tasks.notification_tasks.*': {
        'queue': 'notifications',
        'routing_key': 'notifications'
    },
    
    # Analytics
    'tasks.analytics_tasks.*': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
    
    # 🔥 v6.0: Auto Reportes Agencias
    'tasks.auto_reports.send_weekly_reports': {
        'queue': 'high_priority',
        'routing_key': 'high_priority'
    },
    'tasks.auto_reports.send_monthly_reports': {
        'queue': 'high_priority',
        'routing_key': 'high_priority'
    },
    'tasks.auto_reports.monitor_campaigns_health': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
    'tasks.auto_reports.detect_campaign_anomalies': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
    
    # 🏗️ v6.0: Construcción
    'tasks.construction_reports.generate_weekly_construction_report': {
        'queue': 'high_priority',
        'routing_key': 'high_priority'
    },
    'tasks.construction_reports.monitor_project_delays': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
    'tasks.construction_reports.alert_budget_overruns': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
    'tasks.construction_reports.analyze_safety_photos': {
        'queue': 'slow_tasks',
        'routing_key': 'slow'
    },
    
    # 📊 v6.1: Marketing Multi-Plataforma (Google Ads + Meta + TikTok)
    'tasks.auto_reports_marketing.send_friday_reports': {
        'queue': 'high_priority',
        'routing_key': 'high_priority'
    },
    'tasks.auto_reports_marketing.generate_weekly_marketing_report': {
        'queue': 'high_priority',
        'routing_key': 'high_priority'
    },
    'tasks.auto_reports_marketing.detect_campaign_anomalies': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
    'tasks.auto_reports_marketing.optimize_ad_spend': {
        'queue': 'analytics',
        'routing_key': 'analytics'
    },
}

# =============================================
# RATE LIMITS
# =============================================

celery_app.conf.task_annotations = {
    # Limitar tareas de generación de imágenes
    'tasks.image_tasks.generate_image': {
        'rate_limit': '10/m',  # 10 por minuto
    },
    
    # Limitar emails
    'tasks.notification_tasks.send_email': {
        'rate_limit': '100/m',  # 100 por minuto
    },
    
    # Limitar OCR
    'tasks.document_tasks.ocr_document': {
        'rate_limit': '5/m',  # 5 por minuto
    },
}

# =============================================
# TASK BASE CLASS
# =============================================

from celery import Task
import logging

logger = logging.getLogger('celery_tasks')

class CallbackTask(Task):
    """Clase base para tareas con callbacks"""
    
    def on_success(self, retval, task_id, args, kwargs):
        """Callback cuando tarea termina exitosamente"""
        logger.info(f'✅ Task {self.name} [{task_id}] succeeded')
        return super().on_success(retval, task_id, args, kwargs)
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Callback cuando tarea falla"""
        logger.error(f'❌ Task {self.name} [{task_id}] failed: {exc}')
        return super().on_failure(exc, task_id, args, kwargs, einfo)
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Callback cuando tarea se reintenta"""
        logger.warning(f'🔄 Task {self.name} [{task_id}] retrying: {exc}')
        return super().on_retry(exc, task_id, args, kwargs, einfo)

# =============================================
# EXPORTS
# =============================================

__all__ = ['celery_app', 'CallbackTask']
