import sys
import io
import asyncio
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
    Wrapper de Nivel Dios para ejecutar la tarea agéntica de forma segura 
    bajo el puente de streaming.
    """
    bridge = AgentStreamBridge(on_token)
    
    # AutoGen 0.2 es mayormente síncrono, lo ejecutamos en un thread para no bloquear el Event Loop
    loop = asyncio.get_event_loop()
    
    with bridge:
        # Ejecución en el pool de hilos del sistema
        result = await loop.run_in_executor(None, agent_task_fn)
        
    return result
