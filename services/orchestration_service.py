import logging
from groq import Groq
import config

logger = logging.getLogger(__name__)

class ScoutOrchestrator:
    """
    Orquestador Scout de Nivel Dios.
    Clasifica en milisegundos si una tarea requiere agentes o un simple chat.
    """
    
    def __init__(self):
        self.client = Groq(api_key=config.GROQ_API_KEY)
        self.model = config.GROQ_MODEL_FAST # Usamos Llama 3.1 8B para máxima velocidad
        
    def should_use_agents(self, user_message: str) -> bool:
        """
        Analiza el mensaje y decide la ruta óptima.
        Retorna True si requiere agentes (AutoGen).
        """
        try:
            prompt = f"""Analiza el mensaje del usuario y responde únicamente con 'AGENT' si requiere:
            - Escribir o ejecutar código.
            - Una investigación profunda o multi-paso.
            - Un razonamiento complejo que requiera varios expertos.
            
            De lo contrario, responde 'CHAT'. Solo una palabra.
            
            Mensaje: "{user_message}"
            """
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "system", "content": "Eres un clasificador de intención ultra-rápido."},
                         {"role": "user", "content": prompt}],
                max_tokens=5,
                temperature=0.0
            )
            
            decision = response.choices[0].message.content.strip().upper()
            logger.info(f"Scout Decision: {decision} para mensaje: {user_message[:30]}...")
            
            return "AGENT" in decision
            
        except Exception as e:
            logger.error(f"Error en Scout Orchestrator: {e}")
            return False # Fallback a chat normal por seguridad

# Singleton
scout = ScoutOrchestrator()
