"""services/gpt_service.py

Slim wrapper for the student assistant build.

Exports `chat_with_ai` used by routers/services.
"""

from services.siliconflow_ai_service import chat_with_ai

__all__ = ["chat_with_ai"]
