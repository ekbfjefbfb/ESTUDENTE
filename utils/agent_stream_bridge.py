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
            if data:
                # Limpiar códigos de escape de color ANSI
                import re
                ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
                clean_data = ansi_escape.sub('', data)
                
                # DETECCIÓN DE EVENTOS PRIORITARIOS (Flush inmediato)
                priority_markers = [
                    "Suggested tool Call", "suggested_assistant_action", 
                    "Execute tool Call", "executing_tool"
                ]
                is_priority = any(m in clean_data or m in clean_data.lower() for m in priority_markers)

                if is_priority:
                    self._flush_buffer() # Enviar lo que haya antes del estado
                    
                    if "Suggested tool Call" in clean_data or "suggested_assistant_action" in clean_data.lower():
                        tool_match = re.search(r"name='([^']+)'", clean_data) or re.search(r"action: ([^\s]+)", clean_data.lower())
                        tool_name = tool_match.group(1) if tool_match else "herramienta"
                        msg = "\n🔍 [Investigando]: Buscando fuentes..." if "search_web" in tool_name else f"\n⚙️ [Procesando]: Usando {tool_name}..."
                        if self.on_new_token: self.on_new_token(msg)
                    
                    elif "Execute tool Call" in clean_data or "executing_tool" in clean_data.lower():
                        if self.on_new_token: self.on_new_token(" ✨ [Finalizando]: Preparando explicación...")
                
                else:
                    # ACUMULAR EN BUFFER: Si no es prioridad, agrupamos tokens
                    self._buffer += clean_data
                    # Flush si hay salto de línea o buffer > 50 chars para mantener la fluidez
                    if "\n" in self._buffer or len(self._buffer) > 50:
                        self._flush_buffer()
            
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
            await asyncio.sleep(6) # Latido cada 6 segundos para máxima resiliencia
            if not stop_event.is_set():
                elapsed = time.time() - last_activity_time[0]
                if elapsed >= 6:
                    # Enviar señal de vida discreta al frontend (pulso de carga)
                    on_token(" .") 
    
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
