"""
🚀 Servicio de LiveSearch SÚPER POTENTE - Búsqueda web en tiempo real

Integra 100+ motores de búsqueda y fuentes especializadas:
- SearXNG (meta-búsqueda con 100+ motores)
- DuckDuckGo (fallback general)
- ArXiv (papers científicos)
- PubMed (investigación médica)
- Google Scholar (académico)
- GitHub (código)
- Stack Overflow (programación)
- NewsAPI + Google News (noticias)
- Reddit (social)
- Yahoo Finance + CryptoCompare (finanzas)
- OpenWeatherMap (clima)
- Wikipedia (conocimiento)
"""

import os
import httpx
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
from urllib.parse import quote_plus

# Importaciones condicionales para fuentes especializadas
try:
    import arxiv
    ARXIV_AVAILABLE = True
except ImportError:
    ARXIV_AVAILABLE = False

try:
    from pymed import PubMed
    PUBMED_AVAILABLE = True
except ImportError:
    PUBMED_AVAILABLE = False

try:
    from scholarly import scholarly
    SCHOLAR_AVAILABLE = True
except ImportError:
    SCHOLAR_AVAILABLE = False

try:
    from stackapi import StackAPI
    STACKOVERFLOW_AVAILABLE = True
except ImportError:
    STACKOVERFLOW_AVAILABLE = False

try:
    from newsapi import NewsApiClient
    NEWSAPI_AVAILABLE = True
except ImportError:
    NEWSAPI_AVAILABLE = False

try:
    from gnews import GNews
    GNEWS_AVAILABLE = True
except ImportError:
    GNEWS_AVAILABLE = False

try:
    import praw
    REDDIT_AVAILABLE = True
except ImportError:
    REDDIT_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

try:
    import cryptocompare
    CRYPTOCOMPARE_AVAILABLE = True
except ImportError:
    CRYPTOCOMPARE_AVAILABLE = False

try:
    from pyowm import OWM
    OPENWEATHER_AVAILABLE = True
except ImportError:
    OPENWEATHER_AVAILABLE = False

try:
    import wikipediaapi
    WIKIPEDIA_AVAILABLE = True
except ImportError:
    WIKIPEDIA_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    BEAUTIFULSOUP_AVAILABLE = True
except ImportError:
    BEAUTIFULSOUP_AVAILABLE = False

try:
    import feedparser
    FEEDPARSER_AVAILABLE = True
except ImportError:
    FEEDPARSER_AVAILABLE = False

logger = logging.getLogger(__name__)


class LiveSearchError(Exception):
    """Error al realizar búsqueda web"""
    pass


class LiveSearchService:
    """
    Servicio de búsqueda web en tiempo real
    
    Características:
    - Búsqueda con SearXNG (meta-buscador, prioridad)
    - Fallback automático a DuckDuckGo
    - Detección inteligente de necesidad de búsqueda
    - Filtrado y ranking de resultados
    - Caché de resultados recientes
    """
    
    def __init__(
        self,
        searxng_url: Optional[str] = None,
        timeout: int = 15,
        max_results: int = 5
    ):
        """
        Inicializa el servicio de búsqueda
        
        Args:
            searxng_url: URL de instancia SearXNG (ej: http://localhost:8080)
            timeout: Timeout en segundos
            max_results: Máximo de resultados a retornar
        """
        self.searxng_url = searxng_url or os.getenv("SEARXNG_URL", "")
        self.timeout = timeout
        self.max_results = max_results
        
        # Validar URL
        if self.searxng_url:
            self.searxng_url = self.searxng_url.rstrip('/')
        
        logger.info(
            f"LiveSearchService inicializado - "
            f"SearXNG: {'✅' if self.searxng_url else '❌'}, "
            f"Max resultados: {max_results}"
        )
    
    def should_search(self, query: str) -> bool:
        """
        Determina si una consulta requiere búsqueda web
        
        Args:
            query: Consulta del usuario
            
        Returns:
            True si se recomienda búsqueda web
        """
        # Palabras clave que indican necesidad de búsqueda
        search_indicators = [
            # Español
            "busca", "búsqueda", "encuentra", "información sobre",
            "qué es", "quién es", "cuál es", "dónde está",
            "cuándo", "últimas noticias", "noticias", "precio",
            "clima", "tiempo", "actualidad", "hoy", "ahora",
            "2025", "2024", "reciente", "último", "nueva",
            
            # Inglés
            "search", "find", "look up", "what is", "who is",
            "where is", "when", "latest", "news", "price",
            "weather", "today", "now", "current", "recent"
        ]
        
        query_lower = query.lower()
        
        # Verificar indicadores
        for indicator in search_indicators:
            if indicator in query_lower:
                logger.info(f"🔍 Búsqueda web activada por indicador: '{indicator}'")
                return True
        
        # Verificar si pregunta por información actual/fechas
        if any(word in query_lower for word in ["202", "hoy", "ahora", "today", "now", "current"]):
            logger.info("🔍 Búsqueda web activada por referencia temporal")
            return True
        
        return False
    
    async def search_searxng(
        self,
        query: str,
        categories: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda usando SearXNG
        
        Args:
            query: Término de búsqueda
            categories: Categorías a buscar (general, news, images, etc.)
            
        Returns:
            Lista de resultados con formato:
            [
                {
                    "title": "Título del resultado",
                    "url": "https://...",
                    "content": "Descripción...",
                    "engine": "google",
                    "score": 0.95
                }
            ]
        """
        if not self.searxng_url:
            raise LiveSearchError("SearXNG no configurado (falta SEARXNG_URL)")
        
        # Preparar parámetros
        params = {
            "q": query,
            "format": "json",
            "safesearch": 1,  # Búsqueda moderada
        }
        
        if categories:
            params["categories"] = ",".join(categories)
        
        logger.info(f"🔍 Buscando en SearXNG: '{query}'")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.searxng_url}/search",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = data.get("results", [])
                    
                    # Procesar y filtrar resultados
                    processed_results = []
                    for result in results[:self.max_results * 2]:  # Obtener más para filtrar
                        processed = {
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "content": result.get("content", ""),
                            "engine": result.get("engine", "unknown"),
                            "score": result.get("score", 0.5),
                            "published": result.get("publishedDate", "")
                        }
                        
                        # Filtrar resultados sin contenido útil
                        if processed["title"] and processed["url"]:
                            processed_results.append(processed)
                    
                    # Ordenar por score y limitar
                    processed_results.sort(key=lambda x: x["score"], reverse=True)
                    final_results = processed_results[:self.max_results]
                    
                    logger.info(f"✅ SearXNG encontró {len(final_results)} resultados relevantes")
                    return final_results
                    
                else:
                    raise LiveSearchError(f"SearXNG status {response.status_code}")
                    
        except httpx.TimeoutException:
            logger.error("⏱️ Timeout en SearXNG")
            raise LiveSearchError("Timeout en búsqueda SearXNG")
            
        except Exception as e:
            logger.error(f"❌ Error en SearXNG: {str(e)}")
            raise LiveSearchError(f"Error en SearXNG: {str(e)}")
    
    async def search_duckduckgo(self, query: str) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda usando DuckDuckGo Instant Answer API
        
        Args:
            query: Término de búsqueda
            
        Returns:
            Lista de resultados
        """
        logger.info(f"🦆 Buscando en DuckDuckGo: '{query}'")
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.duckduckgo.com/",
                    params={
                        "q": query,
                        "format": "json",
                        "no_html": 1,
                        "skip_disambig": 1
                    }
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    
                    # Abstract (resumen principal)
                    if data.get("Abstract"):
                        results.append({
                            "title": data.get("Heading", query),
                            "url": data.get("AbstractURL", ""),
                            "content": data.get("Abstract", ""),
                            "engine": "duckduckgo",
                            "score": 1.0,
                            "published": ""
                        })
                    
                    # Related Topics
                    for topic in data.get("RelatedTopics", [])[:self.max_results]:
                        if isinstance(topic, dict) and "Text" in topic:
                            results.append({
                                "title": topic.get("Text", "")[:100],
                                "url": topic.get("FirstURL", ""),
                                "content": topic.get("Text", ""),
                                "engine": "duckduckgo",
                                "score": 0.8,
                                "published": ""
                            })
                    
                    logger.info(f"✅ DuckDuckGo encontró {len(results)} resultados")
                    return results[:self.max_results]
                    
                else:
                    raise LiveSearchError(f"DuckDuckGo status {response.status_code}")
                    
        except Exception as e:
            logger.error(f"❌ Error en DuckDuckGo: {str(e)}")
            raise LiveSearchError(f"Error en DuckDuckGo: {str(e)}")
    
    async def search(
        self,
        query: str,
        use_fallback: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Realiza búsqueda web con fallback automático
        
        Args:
            query: Término de búsqueda
            use_fallback: Si True, usa DuckDuckGo si SearXNG falla
            
        Returns:
            Lista de resultados ordenados por relevancia
        """
        logger.info(f"🌐 Iniciando búsqueda web: '{query}'")
        
        # Intentar SearXNG primero si está configurado
        if self.searxng_url:
            try:
                results = await self.search_searxng(query)
                if results:
                    return results
                else:
                    logger.warning("⚠️ SearXNG no retornó resultados, usando fallback")
            except LiveSearchError as e:
                logger.warning(f"⚠️ SearXNG falló: {str(e)}, usando fallback")
        
        # Fallback a DuckDuckGo
        if use_fallback:
            try:
                results = await self.search_duckduckgo(query)
                return results
            except LiveSearchError as e:
                logger.error(f"❌ Fallback DuckDuckGo también falló: {str(e)}")
                raise LiveSearchError("Todos los motores de búsqueda fallaron")
        else:
            raise LiveSearchError("SearXNG no disponible y fallback deshabilitado")
    
    def format_results_for_llm(self, results: List[Dict[str, Any]]) -> str:
        """
        Formatea resultados de búsqueda para inyección en prompt de LLM
        
        Args:
            results: Lista de resultados de búsqueda
            
        Returns:
            Texto formateado para contexto del LLM
        """
        if not results:
            return "No se encontraron resultados relevantes."
        
        formatted = "📚 **Información de búsqueda web:**\n\n"
        
        for i, result in enumerate(results, 1):
            formatted += f"**Resultado {i}:**\n"
            formatted += f"Título: {result['title']}\n"
            formatted += f"URL: {result['url']}\n"
            formatted += f"Contenido: {result['content'][:300]}...\n"
            
            if result.get('published'):
                formatted += f"Fecha: {result['published']}\n"
            
            formatted += "\n"
        
        formatted += "\n*Usa esta información para responder la consulta del usuario.*"
        
        return formatted
    
    async def search_and_format(self, query: str) -> str:
        """
        Realiza búsqueda y formatea resultados en un solo paso
        
        Args:
            query: Término de búsqueda
            
        Returns:
            Resultados formateados para LLM
        """
        try:
            results = await self.search(query)
            return self.format_results_for_llm(results)
        except LiveSearchError as e:
            return f"⚠️ No se pudo realizar la búsqueda web: {str(e)}"


# Instancia global
_livesearch_service: Optional[LiveSearchService] = None


def get_livesearch_service() -> LiveSearchService:
    """
    Obtiene la instancia global del servicio de búsqueda
    
    Returns:
        Instancia de LiveSearchService
    """
    global _livesearch_service
    
    if _livesearch_service is None:
        _livesearch_service = LiveSearchService()
    
    return _livesearch_service


async def search_web(query: str) -> str:
    """
    Función helper para búsqueda web rápida
    
    Args:
        query: Término de búsqueda
        
    Returns:
        Resultados formateados
    """
    service = get_livesearch_service()
    return await service.search_and_format(query)


# ========================================
# 🚀 SUPER LIVESEARCH - Búsqueda Multi-Fuente
# ========================================

class SuperLiveSearchService(LiveSearchService):
    """
    🚀 Servicio de búsqueda SÚPER POTENTE
    
    Extiende LiveSearchService con capacidades especializadas:
    - 🔬 Académico: ArXiv, PubMed, Google Scholar
    - 💻 Código: GitHub, Stack Overflow
    - 📰 Noticias: NewsAPI, Google News, RSS
    - 💬 Social: Reddit, Twitter
    - 💰 Finanzas: Yahoo Finance, Crypto
    - 🌤️ Clima: OpenWeatherMap
    - 📚 Conocimiento: Wikipedia
    - 🌐 Web: SearXNG (100+ motores), DuckDuckGo
    
    Detecta automáticamente el tipo de consulta y busca en fuentes relevantes.
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Log de capacidades disponibles
        capabilities = []
        if ARXIV_AVAILABLE:
            capabilities.append("ArXiv")
        if PUBMED_AVAILABLE:
            capabilities.append("PubMed")
        if SCHOLAR_AVAILABLE:
            capabilities.append("Scholar")
        if STACKOVERFLOW_AVAILABLE:
            capabilities.append("StackOverflow")
        if NEWSAPI_AVAILABLE and os.getenv("NEWS_API_KEY"):
            capabilities.append("NewsAPI")
        if GNEWS_AVAILABLE:
            capabilities.append("GoogleNews")
        if REDDIT_AVAILABLE and os.getenv("REDDIT_CLIENT_ID"):
            capabilities.append("Reddit")
        if YFINANCE_AVAILABLE:
            capabilities.append("YahooFinance")
        if CRYPTOCOMPARE_AVAILABLE:
            capabilities.append("CryptoCompare")
        if OPENWEATHER_AVAILABLE and os.getenv("OPENWEATHER_API_KEY"):
            capabilities.append("OpenWeather")
        if WIKIPEDIA_AVAILABLE:
            capabilities.append("Wikipedia")
        
        logger.info(
            f"🚀 SuperLiveSearch inicializado con {len(capabilities)} fuentes especializadas: "
            f"{', '.join(capabilities)}"
        )
    
    def detect_query_type(self, query: str) -> List[str]:
        """
        Detecta tipo de consulta para elegir fuentes relevantes
        
        Args:
            query: Consulta del usuario
            
        Returns:
            Lista de categorías: ['academic', 'news', 'code', 'weather', etc.]
        """
        query_lower = query.lower()
        categories = []
        
        # 🔬 Académico
        academic_keywords = [
            'paper', 'research', 'study', 'journal', 'científico', 'investigación',
            'artículo', 'tesis', 'teoría', 'ciencia', 'experimento'
        ]
        if any(word in query_lower for word in academic_keywords):
            categories.append('academic')
        
        # 💊 Medicina
        medical_keywords = [
            'medical', 'disease', 'treatment', 'enfermedad', 'tratamiento',
            'medicina', 'salud', 'síntoma', 'diagnóstico', 'medicamento'
        ]
        if any(word in query_lower for word in medical_keywords):
            categories.append('medical')
        
        # 📰 Noticias
        news_keywords = [
            'news', 'noticias', 'última hora', 'breaking', 'actualidad',
            'hoy', 'ayer', 'reciente', 'nuevo', 'última'
        ]
        if any(word in query_lower for word in news_keywords):
            categories.append('news')
        
        # 💻 Código
        code_keywords = [
            'code', 'código', 'programming', 'github', 'function', 'error',
            'bug', 'programación', 'desarrollo', 'api', 'library', 'framework',
            'python', 'javascript', 'java', 'c++', 'algorithm'
        ]
        if any(word in query_lower for word in code_keywords):
            categories.append('code')
        
        # 💰 Finanzas
        finance_keywords = [
            'stock', 'precio', 'bitcoin', 'eth', 'crypto', 'acción', 'bolsa',
            'inversión', 'mercado', 'trading', 'btc', 'ethereum', 'dolar',
            'euro', 'finanzas'
        ]
        # Símbolos financieros comunes
        finance_symbols = ['BTC', 'ETH', 'AAPL', 'TSLA', 'GOOGL', 'MSFT', 'AMZN']
        if any(word in query_lower for word in finance_keywords) or \
           any(symbol in query.upper() for symbol in finance_symbols):
            categories.append('finance')
        
        # 🌤️ Clima
        weather_keywords = [
            'weather', 'clima', 'temperature', 'temperatura', 'lluvia',
            'rain', 'snow', 'nieve', 'frío', 'calor', 'pronóstico'
        ]
        if any(word in query_lower for word in weather_keywords):
            categories.append('weather')
        
        # 💬 Social
        social_keywords = [
            'reddit', 'twitter', 'social', 'opinión', 'opiniones',
            'comunidad', 'discusión', 'what do people think'
        ]
        if any(word in query_lower for word in social_keywords):
            categories.append('social')
        
        # Si no detecta nada específico, usar búsqueda general
        if not categories:
            categories.append('general')
        
        logger.info(f"🎯 Categorías detectadas para '{query[:50]}...': {categories}")
        return categories
    
    # ========================================
    # 🔬 BÚSQUEDAS ACADÉMICAS
    # ========================================
    
    async def search_arxiv(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Busca papers científicos en ArXiv"""
        if not ARXIV_AVAILABLE:
            logger.warning("ArXiv no disponible (librería no instalada)")
            return []
        
        try:
            logger.info(f"🔬 Buscando en ArXiv: '{query}'")
            
            # Búsqueda asíncrona usando thread pool
            loop = asyncio.get_event_loop()
            
            def _search():
                search = arxiv.Search(
                    query=query,
                    max_results=max_results,
                    sort_by=arxiv.SortCriterion.Relevance
                )
                
                results = []
                for paper in search.results():
                    results.append({
                        "title": paper.title,
                        "url": paper.entry_id,
                        "content": paper.summary[:300] + "..." if len(paper.summary) > 300 else paper.summary,
                        "authors": [author.name for author in paper.authors[:3]],
                        "published": paper.published.strftime("%Y-%m-%d"),
                        "source": "arxiv",
                        "score": 0.9,
                        "category": "academic"
                    })
                return results
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ ArXiv encontró {len(results)} papers")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en ArXiv: {str(e)}")
            return []
    
    async def search_pubmed(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Busca papers médicos en PubMed"""
        if not PUBMED_AVAILABLE:
            logger.warning("PubMed no disponible (librería no instalada)")
            return []
        
        try:
            logger.info(f"💊 Buscando en PubMed: '{query}'")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                pubmed = PubMed(tool="SuperLiveSearch", email="search@example.com")
                results_list = []
                
                results = pubmed.query(query, max_results=max_results)
                for article in results:
                    abstract = article.abstract if article.abstract else ""
                    results_list.append({
                        "title": article.title if article.title else "Sin título",
                        "url": f"https://pubmed.ncbi.nlm.nih.gov/{article.pubmed_id}/",
                        "content": abstract[:300] + "..." if len(abstract) > 300 else abstract,
                        "authors": [author['name'] for author in (article.authors or [])][:3],
                        "published": str(article.publication_date) if article.publication_date else "",
                        "source": "pubmed",
                        "score": 0.95,
                        "category": "medical"
                    })
                return results_list
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ PubMed encontró {len(results)} papers")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en PubMed: {str(e)}")
            return []
    
    async def search_scholar(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Busca en Google Scholar"""
        if not SCHOLAR_AVAILABLE:
            logger.warning("Google Scholar no disponible (librería no instalada)")
            return []
        
        try:
            logger.info(f"🎓 Buscando en Google Scholar: '{query}'")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                search_query = scholarly.search_pubs(query)
                results = []
                
                for i, pub in enumerate(search_query):
                    if i >= max_results:
                        break
                    
                    bib = pub.get('bib', {})
                    abstract = bib.get('abstract', '')
                    
                    results.append({
                        "title": bib.get('title', 'Sin título'),
                        "url": pub.get('pub_url', pub.get('eprint_url', '')),
                        "content": abstract[:300] + "..." if len(abstract) > 300 else abstract,
                        "authors": bib.get('author', [])[:3],
                        "published": bib.get('pub_year', ''),
                        "citations": pub.get('num_citations', 0),
                        "source": "google_scholar",
                        "score": 0.9,
                        "category": "academic"
                    })
                return results
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ Google Scholar encontró {len(results)} papers")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en Google Scholar: {str(e)}")
            return []
    
    # ========================================
    # 💻 BÚSQUEDAS DE CÓDIGO
    # ========================================
    
    async def search_github_code(
        self,
        query: str,
        language: Optional[str] = None,
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Busca código en GitHub"""
        try:
            logger.info(f"💻 Buscando en GitHub: '{query}'")
            
            params = {"q": query, "per_page": max_results}
            if language:
                params["q"] += f" language:{language}"
            
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "SuperLiveSearch"
            }
            
            # Agregar token si está disponible
            github_token = os.getenv("GITHUB_TOKEN")
            if github_token:
                headers["Authorization"] = f"token {github_token}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    "https://api.github.com/search/code",
                    params=params,
                    headers=headers
                )
                
                if response.status_code == 200:
                    data = response.json()
                    results = []
                    
                    for item in data.get('items', []):
                        repo = item.get('repository', {})
                        results.append({
                            "title": item.get('name', 'Sin nombre'),
                            "url": item.get('html_url', ''),
                            "content": f"Repositorio: {repo.get('full_name', '')} | Path: {item.get('path', '')}",
                            "path": item.get('path', ''),
                            "repo_name": repo.get('full_name', ''),
                            "repo_stars": repo.get('stargazers_count', 0),
                            "source": "github",
                            "score": 0.85,
                            "category": "code"
                        })
                    
                    logger.info(f"✅ GitHub encontró {len(results)} resultados")
                    return results
                elif response.status_code == 403:
                    logger.warning("⚠️ GitHub API rate limit excedido")
                    return []
                else:
                    logger.warning(f"⚠️ GitHub API retornó status {response.status_code}")
                    return []
                    
        except Exception as e:
            logger.error(f"❌ Error en GitHub: {str(e)}")
            return []
    
    async def search_stackoverflow(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Busca en Stack Overflow"""
        if not STACKOVERFLOW_AVAILABLE:
            logger.warning("Stack Overflow no disponible (librería no instalada)")
            return []
        
        try:
            logger.info(f"📚 Buscando en Stack Overflow: '{query}'")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                SITE = StackAPI('stackoverflow')
                SITE.page_size = max_results
                SITE.max_pages = 1
                
                results_raw = SITE.fetch(
                    'search/advanced',
                    q=query,
                    sort='relevance',
                    accepted=True  # Priorizar preguntas con respuesta aceptada
                )
                
                results = []
                for item in results_raw.get('items', []):
                    results.append({
                        "title": item.get('title', 'Sin título'),
                        "url": item.get('link', ''),
                        "content": f"Score: {item.get('score', 0)} | Respuestas: {item.get('answer_count', 0)}",
                        "is_answered": item.get('is_answered', False),
                        "view_count": item.get('view_count', 0),
                        "score": item.get('score', 0),
                        "source": "stackoverflow",
                        "relevance": 0.9 if item.get('is_answered') else 0.7,
                        "category": "code"
                    })
                return results
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ Stack Overflow encontró {len(results)} preguntas")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en Stack Overflow: {str(e)}")
            return []
    
    # ========================================
    # 📰 BÚSQUEDAS DE NOTICIAS
    # ========================================
    
    async def search_news(
        self,
        query: str,
        language: str = 'es',
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Busca noticias recientes con NewsAPI"""
        if not NEWSAPI_AVAILABLE:
            logger.warning("NewsAPI no disponible (librería no instalada)")
            return []
        
        api_key = os.getenv('NEWS_API_KEY')
        if not api_key:
            logger.warning("NewsAPI key no configurada (NEWS_API_KEY)")
            return []
        
        try:
            logger.info(f"📰 Buscando en NewsAPI: '{query}'")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                newsapi = NewsApiClient(api_key=api_key)
                
                articles_data = newsapi.get_everything(
                    q=query,
                    language=language,
                    sort_by='publishedAt',
                    page_size=max_results
                )
                
                results = []
                for article in articles_data.get('articles', []):
                    description = article.get('description', '')
                    results.append({
                        "title": article.get('title', 'Sin título'),
                        "url": article.get('url', ''),
                        "content": description[:300] + "..." if len(description) > 300 else description,
                        "source": article.get('source', {}).get('name', 'Desconocido'),
                        "published": article.get('publishedAt', ''),
                        "image": article.get('urlToImage'),
                        "author": article.get('author'),
                        "category": "news",
                        "score": 0.9
                    })
                return results
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ NewsAPI encontró {len(results)} noticias")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en NewsAPI: {str(e)}")
            return []
    
    async def search_google_news(self, query: str, max_results: int = 5) -> List[Dict[str, Any]]:
        """Busca en Google News"""
        if not GNEWS_AVAILABLE:
            logger.warning("Google News no disponible (librería no instalada)")
            return []
        
        try:
            logger.info(f"📰 Buscando en Google News: '{query}'")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                google_news = GNews(
                    language='es',
                    country='MX',
                    max_results=max_results
                )
                articles = google_news.get_news(query)
                
                results = []
                for article in articles:
                    description = article.get('description', '')
                    results.append({
                        "title": article.get('title', 'Sin título'),
                        "url": article.get('url', ''),
                        "content": description[:300] + "..." if len(description) > 300 else description,
                        "source": article.get('publisher', {}).get('title', 'Desconocido'),
                        "published": article.get('published date', ''),
                        "category": "news",
                        "score": 0.85
                    })
                return results
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ Google News encontró {len(results)} noticias")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en Google News: {str(e)}")
            return []
    
    # ========================================
    # 💰 BÚSQUEDAS FINANCIERAS
    # ========================================
    
    async def search_stock(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Obtiene información de acción/cripto con Yahoo Finance"""
        if not YFINANCE_AVAILABLE:
            logger.warning("Yahoo Finance no disponible (librería no instalada)")
            return None
        
        try:
            logger.info(f"💰 Buscando en Yahoo Finance: {symbol}")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                ticker = yf.Ticker(symbol)
                info = ticker.info
                history = ticker.history(period="1d")
                
                if history.empty:
                    return None
                
                current_price = history['Close'].iloc[-1]
                open_price = history['Open'].iloc[0]
                change = current_price - open_price
                change_percent = ((current_price / open_price) - 1) * 100
                
                return {
                    "symbol": symbol,
                    "name": info.get('longName', symbol),
                    "price": float(current_price),
                    "change": float(change),
                    "change_percent": float(change_percent),
                    "market_cap": info.get('marketCap'),
                    "volume": int(history['Volume'].iloc[-1]),
                    "source": "yahoo_finance",
                    "score": 1.0,
                    "category": "finance"
                }
            
            result = await loop.run_in_executor(None, _search)
            if result:
                logger.info(f"✅ Yahoo Finance encontró info de {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en Yahoo Finance: {str(e)}")
            return None
    
    async def search_crypto(
        self,
        symbol: str,
        currency: str = 'USD'
    ) -> Optional[Dict[str, Any]]:
        """Obtiene precio de criptomoneda con CryptoCompare"""
        if not CRYPTOCOMPARE_AVAILABLE:
            logger.warning("CryptoCompare no disponible (librería no instalada)")
            return None
        
        try:
            logger.info(f"₿ Buscando en CryptoCompare: {symbol}")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                price_data = cryptocompare.get_price(symbol, currency=currency, full=True)
                
                if not price_data or symbol not in price_data:
                    return None
                
                data = price_data[symbol][currency]
                return {
                    "symbol": symbol,
                    "currency": currency,
                    "price": data.get('PRICE', 0),
                    "change_24h": data.get('CHANGE24HOUR', 0),
                    "change_pct_24h": data.get('CHANGEPCT24HOUR', 0),
                    "volume_24h": data.get('VOLUME24HOUR', 0),
                    "market_cap": data.get('MKTCAP', 0),
                    "source": "cryptocompare",
                    "score": 1.0,
                    "category": "finance"
                }
            
            result = await loop.run_in_executor(None, _search)
            if result:
                logger.info(f"✅ CryptoCompare encontró info de {symbol}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en CryptoCompare: {str(e)}")
            return None
    
    # ========================================
    # 🌤️ BÚSQUEDAS DE CLIMA
    # ========================================
    
    async def search_weather(self, city: str) -> Optional[Dict[str, Any]]:
        """Obtiene clima actual con OpenWeatherMap"""
        if not OPENWEATHER_AVAILABLE:
            logger.warning("OpenWeatherMap no disponible (librería no instalada)")
            return None
        
        api_key = os.getenv('OPENWEATHER_API_KEY')
        if not api_key:
            logger.warning("OpenWeatherMap key no configurada (OPENWEATHER_API_KEY)")
            return None
        
        try:
            logger.info(f"🌤️ Buscando clima en OpenWeatherMap: {city}")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                owm = OWM(api_key)
                mgr = owm.weather_manager()
                
                observation = mgr.weather_at_place(city)
                weather = observation.weather
                temp = weather.temperature('celsius')
                
                return {
                    "city": city,
                    "status": weather.detailed_status,
                    "temperature": temp['temp'],
                    "feels_like": temp['feels_like'],
                    "temp_min": temp['temp_min'],
                    "temp_max": temp['temp_max'],
                    "humidity": weather.humidity,
                    "wind_speed": weather.wind().get('speed', 0),
                    "description": weather.detailed_status,
                    "source": "openweathermap",
                    "score": 1.0,
                    "category": "weather"
                }
            
            result = await loop.run_in_executor(None, _search)
            if result:
                logger.info(f"✅ OpenWeatherMap encontró clima de {city}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en OpenWeatherMap: {str(e)}")
            return None
    
    # ========================================
    # 📚 BÚSQUEDAS EN WIKIPEDIA
    # ========================================
    
    async def search_wikipedia(
        self,
        query: str,
        lang: str = 'es'
    ) -> Optional[Dict[str, Any]]:
        """Busca en Wikipedia"""
        if not WIKIPEDIA_AVAILABLE:
            logger.warning("Wikipedia no disponible (librería no instalada)")
            return None
        
        try:
            logger.info(f"📚 Buscando en Wikipedia: '{query}'")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                wiki = wikipediaapi.Wikipedia(
                    language=lang,
                    user_agent='SuperLiveSearch/1.0'
                )
                page = wiki.page(query)
                
                if not page.exists():
                    return None
                
                summary = page.summary
                full_text = page.text
                
                return {
                    "title": page.title,
                    "url": page.fullurl,
                    "content": summary[:500] + "..." if len(summary) > 500 else summary,
                    "full_text": full_text[:1000] + "..." if len(full_text) > 1000 else full_text,
                    "sections": [s.title for s in page.sections][:5],
                    "source": "wikipedia",
                    "score": 0.95,
                    "category": "knowledge"
                }
            
            result = await loop.run_in_executor(None, _search)
            if result:
                logger.info(f"✅ Wikipedia encontró artículo: {result['title']}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error en Wikipedia: {str(e)}")
            return None
    
    # ========================================
    # 💬 BÚSQUEDAS SOCIALES
    # ========================================
    
    async def search_reddit(
        self,
        query: str,
        subreddit: str = 'all',
        max_results: int = 5
    ) -> List[Dict[str, Any]]:
        """Busca en Reddit"""
        if not REDDIT_AVAILABLE:
            logger.warning("Reddit no disponible (librería no instalada)")
            return []
        
        client_id = os.getenv('REDDIT_CLIENT_ID')
        client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            logger.warning("Reddit credentials no configuradas (REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET)")
            return []
        
        try:
            logger.info(f"💬 Buscando en Reddit: '{query}' en r/{subreddit}")
            
            loop = asyncio.get_event_loop()
            
            def _search():
                reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent='SuperLiveSearch/1.0'
                )
                
                subreddit_obj = reddit.subreddit(subreddit)
                results = []
                
                for submission in subreddit_obj.search(query, limit=max_results, sort='relevance'):
                    selftext = submission.selftext if submission.selftext else ""
                    results.append({
                        "title": submission.title,
                        "url": f"https://reddit.com{submission.permalink}",
                        "content": selftext[:300] + "..." if len(selftext) > 300 else selftext,
                        "score": submission.score,
                        "comments": submission.num_comments,
                        "subreddit": submission.subreddit.display_name,
                        "author": str(submission.author),
                        "created": datetime.fromtimestamp(submission.created_utc).strftime("%Y-%m-%d"),
                        "source": "reddit",
                        "relevance": 0.8,
                        "category": "social"
                    })
                return results
            
            results = await loop.run_in_executor(None, _search)
            logger.info(f"✅ Reddit encontró {len(results)} posts")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error en Reddit: {str(e)}")
            return []
    
    # ========================================
    # 🚀 BÚSQUEDA MULTI-FUENTE INTELIGENTE
    # ========================================
    
    async def search_multi_source(
        self,
        query: str,
        max_results_per_source: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Busca en múltiples fuentes según el tipo de consulta
        
        Args:
            query: Consulta del usuario
            max_results_per_source: Máximo de resultados por fuente
            
        Returns:
            Dict con resultados por fuente: {"source_name": [resultados], ...}
        """
        categories = self.detect_query_type(query)
        all_results = {}
        
        # Lista de tareas asíncronas
        tasks = []
        
        # Búsqueda web general (siempre)
        tasks.append(('web', self.search(query)))
        
        # Búsquedas especializadas según categoría
        if 'academic' in categories:
            tasks.append(('arxiv', self.search_arxiv(query, max_results_per_source)))
            tasks.append(('scholar', self.search_scholar(query, max_results_per_source)))
        
        if 'medical' in categories:
            tasks.append(('pubmed', self.search_pubmed(query, max_results_per_source)))
        
        if 'code' in categories:
            tasks.append(('github', self.search_github_code(query, max_results=max_results_per_source)))
            tasks.append(('stackoverflow', self.search_stackoverflow(query, max_results_per_source)))
        
        if 'news' in categories:
            tasks.append(('news', self.search_news(query, max_results=max_results_per_source)))
            tasks.append(('google_news', self.search_google_news(query, max_results_per_source)))
        
        if 'finance' in categories:
            # Intentar extraer símbolo
            words = query.upper().split()
            finance_symbols = ['BTC', 'ETH', 'AAPL', 'TSLA', 'GOOGL', 'MSFT', 'AMZN']
            for word in words:
                if word in finance_symbols or len(word) <= 5:
                    # Probar tanto stock como crypto
                    tasks.append(('stock', self.search_stock(word)))
                    tasks.append(('crypto', self.search_crypto(word)))
                    break
        
        if 'weather' in categories:
            # Intentar extraer ciudad
            if ' en ' in query.lower():
                city = query.lower().split(' en ')[-1].strip()
                tasks.append(('weather', self.search_weather(city)))
            elif ' in ' in query.lower():
                city = query.lower().split(' in ')[-1].strip()
                tasks.append(('weather', self.search_weather(city)))
        
        if 'social' in categories:
            tasks.append(('reddit', self.search_reddit(query, max_results=max_results_per_source)))
        
        # Wikipedia (siempre útil)
        tasks.append(('wikipedia', self.search_wikipedia(query)))
        
        # Ejecutar todas las búsquedas en paralelo
        logger.info(f"🚀 Ejecutando {len(tasks)} búsquedas en paralelo...")
        
        results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
        
        # Procesar resultados
        for (source_name, _), result in zip(tasks, results):
            if isinstance(result, Exception):
                logger.error(f"❌ Error en {source_name}: {str(result)}")
                continue
            
            if result:
                # Manejar resultados únicos (dict) vs listas
                if isinstance(result, dict):
                    all_results[source_name] = [result]
                elif isinstance(result, list) and len(result) > 0:
                    all_results[source_name] = result
        
        logger.info(
            f"✅ Búsqueda completada: {len(all_results)} fuentes con resultados "
            f"({sum(len(v) for v in all_results.values())} resultados totales)"
        )
        
        return all_results
    
    def aggregate_results(
        self,
        multi_source_results: Dict[str, List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        """
        Agrega y rankea resultados de múltiples fuentes
        
        Prioridad de fuentes:
        1. Académicas (ArXiv, PubMed, Scholar) - score x 1.2
        2. Finanzas/Clima (datos en tiempo real) - score x 1.1
        3. Noticias - score x 1.0
        4. Código (GitHub, SO) - score x 0.9
        5. Social - score x 0.85
        6. Web general - score x 0.8
        
        Args:
            multi_source_results: Dict de resultados por fuente
            
        Returns:
            Lista de resultados agregados y rankeados
        """
        aggregated = []
        
        # Multiplicadores de score por fuente
        source_multipliers = {
            'arxiv': 1.2,
            'pubmed': 1.2,
            'scholar': 1.2,
            'stock': 1.1,
            'crypto': 1.1,
            'weather': 1.1,
            'news': 1.0,
            'google_news': 0.95,
            'github': 0.9,
            'stackoverflow': 0.9,
            'wikipedia': 0.95,
            'reddit': 0.85,
            'web': 0.8
        }
        
        for source, results in multi_source_results.items():
            multiplier = source_multipliers.get(source, 1.0)
            
            for result in results:
                # Ajustar score con multiplier
                base_score = result.get('score', 0.5)
                result['adjusted_score'] = base_score * multiplier
                result['source_category'] = source
                aggregated.append(result)
        
        # Ordenar por score ajustado (descendente)
        aggregated.sort(key=lambda x: x.get('adjusted_score', 0), reverse=True)
        
        # Eliminar duplicados por URL
        seen_urls = set()
        deduplicated = []
        for result in aggregated:
            url = result.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                deduplicated.append(result)
            elif not url:
                # Incluir resultados sin URL (ej: clima, finanzas)
                deduplicated.append(result)
        
        # Limitar a top 20 resultados
        top_results = deduplicated[:20]
        
        logger.info(
            f"📊 Agregación completa: {len(aggregated)} → "
            f"{len(deduplicated)} (sin duplicados) → "
            f"{len(top_results)} (top 20)"
        )
        
        return top_results
    
    async def search_super(
        self,
        query: str,
        return_raw: bool = False,
        max_results_per_source: int = 5
    ) -> Union[List[Dict], Dict[str, List[Dict]]]:
        """
        🚀 BÚSQUEDA SÚPER POTENTE con detección automática
        
        Método principal para búsqueda inteligente multi-fuente.
        
        Args:
            query: Consulta del usuario
            return_raw: Si True, retorna resultados por fuente sin agregar
            max_results_per_source: Máximo de resultados por fuente
            
        Returns:
            - Si return_raw=False: Lista de resultados agregados y rankeados
            - Si return_raw=True: Dict de resultados por fuente
        """
        logger.info(f"🚀 SuperLiveSearch iniciando para: '{query}'")
        start_time = datetime.now()
        
        # Buscar en múltiples fuentes
        multi_source = await self.search_multi_source(query, max_results_per_source)
        
        if return_raw:
            return multi_source
        
        # Agregar y rankear
        aggregated = self.aggregate_results(multi_source)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.info(
            f"✅ SuperLiveSearch completado en {elapsed:.2f}s: "
            f"{len(aggregated)} resultados de {len(multi_source)} fuentes"
        )
        
        return aggregated


# ========================================
# 🌐 INSTANCIA GLOBAL
# ========================================

_super_livesearch_service: Optional[SuperLiveSearchService] = None


def get_super_livesearch_service() -> SuperLiveSearchService:
    """
    Obtiene la instancia global del servicio SÚPER POTENTE
    
    Returns:
        Instancia de SuperLiveSearchService
    """
    global _super_livesearch_service
    
    if _super_livesearch_service is None:
        _super_livesearch_service = SuperLiveSearchService()
    
    return _super_livesearch_service


async def search_web_super(
    query: str,
    return_raw: bool = False
) -> Union[List[Dict], Dict[str, List[Dict]]]:
    """
    🚀 Función helper para búsqueda SÚPER POTENTE
    
    Args:
        query: Consulta del usuario
        return_raw: Si True, retorna resultados por fuente
        
    Returns:
        Resultados de búsqueda (agregados o por fuente)
    """
    service = get_super_livesearch_service()
    return await service.search_super(query, return_raw=return_raw)
