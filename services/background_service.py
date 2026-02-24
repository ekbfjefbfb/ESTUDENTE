"""
Servicio de Procesamiento Asíncrono
Maneja tareas en background para respuestas más rápidas
"""

import logging
import asyncio
import json
from datetime import datetime
from typing import Callable, Dict, Any, Optional, List
from concurrent.futures import ThreadPoolExecutor
import threading
from queue import Queue

from services.smart_cache_service import smart_cache
from services.redis_service import get_redis_client
import json_log_formatter

# =============================================
# CONFIGURACIÓN DE LOGGING
# =============================================
formatter = json_log_formatter.JSONFormatter()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger = logging.getLogger("async_processor")
logger.setLevel(logging.INFO)
logger.addHandler(handler)

class AsyncTaskProcessor:
    """
    Procesador de tareas asíncronas para optimizar respuestas
    Maneja operaciones no críticas en background
    """
    
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.task_queue = asyncio.Queue()
        self.is_running = False
        self.worker_tasks = []
        
        # Tipos de tareas y sus prioridades
        self.task_priorities = {
            "audit_log": 1,           # Menor prioridad
            "usage_analytics": 2,
            "cache_cleanup": 3,
            "metrics_update": 4,
            "notification": 5,        # Mayor prioridad
        }
        
    async def start(self):
        """Inicia el procesador de tareas."""
        if self.is_running:
            return
            
        self.is_running = True
        
        # Crear workers
        for i in range(3):  # 3 workers concurrentes
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self.worker_tasks.append(task)
        
        logger.info({
            "event": "async_processor_started",
            "workers": len(self.worker_tasks)
        })
    
    async def stop(self):
        """Detiene el procesador de tareas."""
        self.is_running = False
        
        # Cancelar workers
        for task in self.worker_tasks:
            task.cancel()
        
        # Esperar a que terminen
        await asyncio.gather(*self.worker_tasks, return_exceptions=True)
        
        # Cerrar executor
        self.executor.shutdown(wait=True)
        
        logger.info({
            "event": "async_processor_stopped"
        })
    
    async def add_task(self, task_type: str, func: Callable, *args, **kwargs):
        """
        Agrega una tarea al procesador
        
        Args:
            task_type: Tipo de tarea (para priorización)
            func: Función a ejecutar
            *args, **kwargs: Argumentos para la función
        """
        if not self.is_running:
            await self.start()
        
        priority = self.task_priorities.get(task_type, 1)
        task_data = {
            "type": task_type,
            "func": func,
            "args": args,
            "kwargs": kwargs,
            "priority": priority,
            "created_at": datetime.utcnow().isoformat(),
            "id": f"{task_type}_{int(datetime.utcnow().timestamp() * 1000)}"
        }
        
        await self.task_queue.put(task_data)
        
        logger.debug({
            "event": "task_added",
            "task_type": task_type,
            "task_id": task_data["id"],
            "queue_size": self.task_queue.qsize()
        })
    
    async def _worker(self, worker_name: str):
        """Worker que procesa tareas del queue."""
        logger.info({
            "event": "worker_started",
            "worker": worker_name
        })
        
        while self.is_running:
            try:
                # Obtener tarea del queue
                task_data = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0
                )
                
                await self._execute_task(worker_name, task_data)
                
            except asyncio.TimeoutError:
                # Timeout normal, continuar
                continue
            except Exception as e:
                logger.error({
                    "event": "worker_error",
                    "worker": worker_name,
                    "error": str(e)
                })
                await asyncio.sleep(1)
        
        logger.info({
            "event": "worker_stopped",
            "worker": worker_name
        })
    
    async def _execute_task(self, worker_name: str, task_data: Dict[str, Any]):
        """Ejecuta una tarea específica."""
        start_time = datetime.utcnow()
        
        try:
            func = task_data["func"]
            args = task_data.get("args", ())
            kwargs = task_data.get("kwargs", {})
            
            # Ejecutar función
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # Ejecutar función sincrónica en executor
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    self.executor, 
                    lambda: func(*args, **kwargs)
                )
            
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.info({
                "event": "task_completed",
                "worker": worker_name,
                "task_type": task_data["type"],
                "task_id": task_data["id"],
                "execution_time": execution_time,
                "result_type": type(result).__name__
            })
            
        except Exception as e:
            execution_time = (datetime.utcnow() - start_time).total_seconds()
            
            logger.error({
                "event": "task_execution_error",
                "worker": worker_name,
                "task_type": task_data["type"],
                "task_id": task_data["id"],
                "execution_time": execution_time,
                "error": str(e)
            })

class BackgroundTaskService:
    """
    Servicio de tareas en background específicas del negocio
    """
    
    def __init__(self):
        self.processor = AsyncTaskProcessor()
    
    async def start(self):
        """Inicia el servicio."""
        await self.processor.start()
    
    async def stop(self):
        """Detiene el servicio."""
        await self.processor.stop()
    
    async def log_request_audit(self, user_id: str, endpoint: str, request_data: Dict[str, Any]):
        """Registra auditoría de request en background."""
        await self.processor.add_task(
            "audit_log",
            self._save_audit_log,
            user_id,
            endpoint,
            request_data
        )
    
    async def update_usage_analytics(self, user_id: str, action: str, metadata: Dict[str, Any]):
        """Actualiza analytics de uso en background."""
        await self.processor.add_task(
            "usage_analytics",
            self._update_analytics,
            user_id,
            action,
            metadata
        )
    
    async def cleanup_expired_cache(self, pattern: str):
        """Limpia caché expirado en background."""
        await self.processor.add_task(
            "cache_cleanup",
            self._cleanup_cache,
            pattern
        )
    
    async def update_metrics(self, metric_name: str, value: float, tags: Dict[str, str] = None):
        """Actualiza métricas en background."""
        await self.processor.add_task(
            "metrics_update",
            self._update_prometheus_metrics,
            metric_name,
            value,
            tags or {}
        )
    
    async def send_notification(self, user_id: str, notification_type: str, data: Dict[str, Any]):
        """Envía notificación en background."""
        await self.processor.add_task(
            "notification",
            self._send_user_notification,
            user_id,
            notification_type,
            data
        )
    
    # =============================================
    # IMPLEMENTACIONES DE TAREAS ESPECÍFICAS
    # =============================================
    
    async def _save_audit_log(self, user_id: str, endpoint: str, request_data: Dict[str, Any]):
        """Guarda log de auditoría."""
        try:
            redis_client = await get_redis_client()
            
            audit_entry = {
                "user_id": user_id,
                "endpoint": endpoint,
                "timestamp": datetime.utcnow().isoformat(),
                "request_data": request_data,
                "ip": request_data.get("ip", "unknown"),
                "user_agent": request_data.get("user_agent", "unknown")
            }
            
            # Guardar en Redis con TTL de 30 días
            audit_key = f"audit:{user_id}:{int(datetime.utcnow().timestamp())}"
            await redis_client.setex(
                audit_key,
                30 * 24 * 3600,  # 30 días
                json.dumps(audit_entry)
            )
            
        except Exception as e:
            logger.error({
                "event": "audit_log_save_error",
                "user_id": user_id,
                "error": str(e)
            })
    
    async def _update_analytics(self, user_id: str, action: str, metadata: Dict[str, Any]):
        """Actualiza analytics de uso."""
        try:
            redis_client = await get_redis_client()
            
            # Contadores diarios por acción
            today = datetime.utcnow().strftime("%Y-%m-%d")
            analytics_key = f"analytics:{action}:{today}"
            
            await redis_client.incr(analytics_key)
            await redis_client.expire(analytics_key, 90 * 24 * 3600)  # 90 días
            
            # Analytics por usuario
            user_analytics_key = f"user_analytics:{user_id}:{action}:{today}"
            await redis_client.incr(user_analytics_key)
            await redis_client.expire(user_analytics_key, 90 * 24 * 3600)
            
        except Exception as e:
            logger.error({
                "event": "analytics_update_error",
                "user_id": user_id,
                "action": action,
                "error": str(e)
            })
    
    async def _cleanup_cache(self, pattern: str):
        """Limpia caché por patrón."""
        try:
            deleted_count = await smart_cache.invalidate_pattern(pattern)
            logger.info({
                "event": "cache_cleanup_completed",
                "pattern": pattern,
                "deleted_keys": deleted_count
            })
        except Exception as e:
            logger.error({
                "event": "cache_cleanup_error",
                "pattern": pattern,
                "error": str(e)
            })
    
    async def _update_prometheus_metrics(self, metric_name: str, value: float, tags: Dict[str, str]):
        """Actualiza métricas de Prometheus."""
        try:
            # Aquí se implementaría la actualización de métricas
            # Por ejemplo, usando prometheus_client
            logger.debug({
                "event": "metrics_updated",
                "metric": metric_name,
                "value": value,
                "tags": tags
            })
        except Exception as e:
            logger.error({
                "event": "metrics_update_error",
                "metric": metric_name,
                "error": str(e)
            })
    
    async def _send_user_notification(self, user_id: str, notification_type: str, data: Dict[str, Any]):
        """Envía notificación a usuario."""
        try:
            # Aquí se implementaría el envío de notificaciones
            # Por ejemplo, email, push, webhook, etc.
            logger.info({
                "event": "notification_sent",
                "user_id": user_id,
                "type": notification_type,
                "data": data
            })
        except Exception as e:
            logger.error({
                "event": "notification_send_error",
                "user_id": user_id,
                "type": notification_type,
                "error": str(e)
            })

# Instancia global del servicio
background_service = BackgroundTaskService()