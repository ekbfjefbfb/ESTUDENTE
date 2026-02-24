"""
Smart Search Router - Reemplaza search_router.py con IA automática
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from services.search_service import SearchService
from services.gpt_service import chat_with_ai
from utils.auth import get_current_user_id

router = APIRouter(prefix="/api/search", tags=["smart-search"])

class SmartSearchRequest(BaseModel):
    query: str
    limit: int = 5
    language: str = "es"
    ai_analysis: bool = True

@router.post("/web")
async def smart_web_search(
    request: SmartSearchRequest,
    user_id: str = Depends(get_current_user_id)
):
    """Búsqueda web con IA local automática"""
    try:
        # 1. Búsqueda web
        search_service = SearchService()
        search_results = await search_service.search_web(
            query=request.query,
            limit=request.limit,
            language=request.language
        )
        
        # 2. IA automática
        ai_analysis = None
        if request.ai_analysis and search_results:
            # Crear contexto para IA
            results_context = "\n\n".join([
                f"**{result.get('title', '')}**\n{result.get('description', '')}"
                for result in search_results[:3]
            ])
            
            analysis_prompt = f"""
            Usuario buscó: "{request.query}"
            
            Resultados encontrados:
            {results_context}
            
            Analiza y resume la información más relevante para responder la búsqueda del usuario.
            """
            
            ai_analysis = await chat_with_ai(
                messages=[{"role": "user", "content": analysis_prompt}],
                user=user_id,
                friendly=True
            )
        
        return {
            "success": True,
            "query": request.query,
            "search_results": search_results,
            "ai_analysis": ai_analysis,
            "total_results": len(search_results)
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }