"""
Background Tasks con Logging Automático de Excepciones.

Reemplaza asyncio.create_task() desnudo que pierde excepciones silenciosamente.

Uso:
    from utils.background import safe_create_task
    
    # En vez de:  asyncio.create_task(save_progress(...))
    safe_create_task(save_progress(...), name="save_progress")
"""

import asyncio
import logging
from typing import Coroutine, Any, Optional

logger = logging.getLogger("background_tasks")


def safe_create_task(
    coro: Coroutine[Any, Any, Any],
    name: str = "unnamed_task",
) -> asyncio.Task:
    """
    Crea un asyncio.Task con logging automático de excepciones.
    
    Args:
        coro: Coroutine a ejecutar
        name: Nombre descriptivo para logs
    
    Returns:
        asyncio.Task configurada con callback de error
    """
    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(lambda t: _on_task_done(t, name))
    return task


def _on_task_done(task: asyncio.Task, name: str) -> None:
    """Callback que se ejecuta cuando la task termina."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        logger.debug(f"Background task '{name}' was cancelled")
        return
    
    if exc is not None:
        logger.error(
            f"Background task '{name}' failed with {type(exc).__name__}: {exc}",
            exc_info=exc,
        )
