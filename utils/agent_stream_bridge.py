import sys
import io
import asyncio
import inspect
import time
from typing import Callable, Any

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
        self._buffer = ""
        
    def __enter__(self):
        sys.stdout = self
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout = self.old_stdout

    def _flush_buffer(self):
        """Envía el contenido acumulado al frontend."""
        if not self._buffer:
            return
        # Limpieza Discreta: Regresamos a "Tutor" para los prefijos
        msg = self._buffer.replace("iris_", "").replace("expert_", "").strip()
        if msg and self.on_new_token:
            self.on_new_token(msg)
        self._buffer = ""
        
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
                
                # FILTRO DE IDENTIDADES (Limpieza Silenciosa)
                is_internal_noise = False
                noise_patterns = [
                    "(to ", "----------------", ">>>>", "TERMINATE", 
                    "proxy_", "iris_", "expert_", "exitcode:", "code_execution_config"
                ]
                if any(m in clean_data for m in noise_patterns):
                    is_internal_noise = True
                
                # DETECCIÓN DE EVENTOS PRIORITARIOS (Status Genéricos)
                priority_markers = ["Suggested tool Call", "Execute tool Call"]
                is_priority = any(m in clean_data for m in priority_markers)

                if is_priority:
                    self._flush_buffer() 
                    if "Suggested tool Call" in clean_data:
                        tool_match = re.search(r"name='([^']+)'", clean_data)
                        tool_name = tool_match.group(1) if tool_match else "herramienta"
                        msg = "\n[Tutor]: Investigando fuentes..." if "search_web" in tool_name else "\n[Tutor]: Resolviendo con mi equipo..."
                        if self.on_new_token:
                            self.on_new_token(msg)
                    elif "Execute tool Call" in clean_data:
                        if self.on_new_token:
                            self.on_new_token(" [Tutor]: Estructurando tu respuesta...")
                
                elif not is_internal_noise:
                    self._buffer += clean_data
                    if "\n" in self._buffer or len(self._buffer) > 60:
                        self._flush_buffer()
            
            self.old_stdout.write(data)
        finally:
            self._is_writing = False

    def flush(self):
        self.old_stdout.flush()

async def run_agent_with_streaming(agent_task_fn: Callable, on_token: Callable[[str], Any]):
    """
    Wrapper de Nivel Dios para ejecutar la tarea agéntica con latidos de corazón (Heartbeat).
    Iris inyecta señales de vida periódicas de forma discreta.
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
                if elapsed >= 10:
                    # Enviar señal de vida pedagógica discreta
                    on_token("\n✨ [Tutor]: Sigo aquí, conectando conceptos para ti...")
                    last_activity_time[0] = time.time() # Reset para no saturar
                elif elapsed >= 5:
                    on_token(" .") 
    
    stop_heartbeat = asyncio.Event()
    heartbeat_task = asyncio.create_task(heartbeat_worker(stop_heartbeat))
    
    try:
        with bridge:
            def _run_sync():
                out = agent_task_fn()
                if inspect.iscoroutine(out):
                    return asyncio.run(out)
                return out

            result = await loop.run_in_executor(None, _run_sync)
        return result
    finally:
        stop_heartbeat.set()
        await heartbeat_task # Limpieza de la tarea de latido
