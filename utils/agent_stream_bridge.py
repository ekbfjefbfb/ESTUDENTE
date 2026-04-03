import sys
import io
import asyncio
import inspect
import time
from typing import Callable, Any, Optional

class AgentStreamBridge:
    """
    Ingeniería de Nivel Dios para capturar la salida de AutoGen.
    Funciona como un proxy para stdout que redirige el texto al WebSocket de forma asíncrona.
    """
    
    def __init__(self, on_new_token: Callable[[str], Any]):
        self.on_new_token = on_new_token
        self.old_stdout = sys.stdout
        self.string_io = io.StringIO()
        self._is_writing = False # Guardián de recursión
        
    def __enter__(self):
        sys.stdout = self
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.old_stdout
        
    def write(self, data: str):
        if self._is_writing:
            self.old_stdout.write(data)
            return

        self._is_writing = True
        try:
            if data and data.strip():
                # Limpiar códigos de escape de color ANSI
                import re
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                clean_data = ansi_escape.sub('', data)
                
                if self.on_new_token and clean_data.strip():
                    self.on_new_token(f"\n🤖 [Agente]: {clean_data}")
            
            self.old_stdout.write(data)
        finally:
            self._is_writing = False
        
    def flush(self):
        self.old_stdout.flush()

async def run_agent_with_streaming(agent_task_fn: Callable, on_token: Callable[[str], Any]):
    """
    Wrapper de Nivel Dios para ejecutar la tarea agéntica con latidos de corazón (Heartbeat).
    Evita timeouts en el frontend inyectando señales de vida periódicas.
    """
    bridge = AgentStreamBridge(on_token)
    loop = asyncio.get_event_loop()
    last_activity_time = [time.time()] # Usar lista para persistencia en clausura
    
    # Envolver on_token para registrar actividad
    def on_token_with_activity(token: str):
        last_activity_time[0] = time.time()
        on_token(token)
    
    bridge.on_new_token = on_token_with_activity
    
    # Tarea de latido para mantener el WebSocket vivo
    async def heartbeat_worker(stop_event: asyncio.Event):
        while not stop_event.is_set():
            await asyncio.sleep(8) # Latido cada 8 segundos
            if not stop_event.is_set():
                elapsed = time.time() - last_activity_time[0]
                if elapsed >= 8:
                    # Enviar señal de vida discreta al frontend
                    on_token(" . ") # Punto de carga o status
    
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_worker(stop_heartbeat))
    
    try:
        with bridge:
            def _run_sync():
                import time # Importar dentro para el thread
                out = agent_task_fn()
                if inspect.iscoroutine(out):
                    return asyncio.run(out)
                return out

            result = await loop.run_in_executor(None, _run_sync)
        return result
    finally:
        stop_heartbeat.set()
        await heartbeat_task # Limpieza de la tarea de latido
