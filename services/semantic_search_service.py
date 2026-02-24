# services/semantic_search_service.py
"""
Semantic Search Service v1.0 - Vector Embeddings y Búsqueda Semántica
Sistema avanzado de búsqueda semántica con embeddings, vector databases y similarity search.
"""
import asyncio
import logging
import os
import json
import time
import hashlib
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
import numpy as np
from datetime import datetime

# Vector embeddings y ML
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    SentenceTransformer = None

try:
    import faiss
    FAISS_AVAILABLE = True
except ImportError:
    FAISS_AVAILABLE = False
    faiss = None

# Core dependencies
from utils.safe_metrics import Counter, Histogram, Gauge
from services.redis_service import redis, redis_set, redis_get

logger = logging.getLogger("semantic_search")

# ===============================================
# 📊 CONFIGURACIÓN Y MÉTRICAS
# ===============================================

@dataclass
class SemanticSearchConfig:
    """Configuración para búsqueda semántica"""
    model_name: str = "all-MiniLM-L6-v2"  # Modelo ligero y eficiente
    vector_dimension: int = 384
    similarity_threshold: float = 0.7
    max_results: int = 10
    cache_ttl: int = 3600
    enable_gpu: bool = False

# Métricas Prometheus
SEMANTIC_SEARCH_REQUESTS = Counter(
    'semantic_search_requests_total',
    'Total semantic search requests',
    ['user_id', 'search_type', 'status']
)

SEMANTIC_SEARCH_DURATION = Histogram(
    'semantic_search_duration_seconds',
    'Semantic search duration',
    ['user_id', 'search_type']
)

VECTOR_EMBEDDINGS_CACHE = Gauge(
    'vector_embeddings_cache_size',
    'Number of cached vector embeddings'
)

# ===============================================
# 🧠 VECTOR EMBEDDINGS MANAGER
# ===============================================

class VectorEmbeddingsManager:
    """Manager para embeddings de vectores"""
    
    def __init__(self, config: SemanticSearchConfig):
        self.config = config
        self.model = None
        self.vector_index = None
        self.document_store: Dict[int, Dict[str, Any]] = {}
        self.initialized = False
        
    async def initialize(self):
        """Inicializa el modelo de embeddings"""
        try:
            if not SENTENCE_TRANSFORMERS_AVAILABLE:
                logger.warning("⚠️ sentence-transformers no disponible. Semantic search limitado.")
                return
                
            logger.info(f"🚀 Inicializando modelo de embeddings: {self.config.model_name}")
            
            # Cargar modelo en un thread separado para no bloquear
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None, 
                self._load_model
            )
            
            # Inicializar índice FAISS si está disponible
            if FAISS_AVAILABLE:
                self.vector_index = faiss.IndexFlatIP(self.config.vector_dimension)
                logger.info("✅ Índice FAISS inicializado")
            else:
                logger.warning("⚠️ FAISS no disponible. Usando búsqueda por similaridad simple.")
            
            self.initialized = True
            logger.info("✅ Vector Embeddings Manager inicializado")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando embeddings: {e}")
            raise
    
    def _load_model(self) -> SentenceTransformer:
        """Carga el modelo de sentence transformers"""
        device = 'cuda' if self.config.enable_gpu else 'cpu'
        return SentenceTransformer(self.config.model_name, device=device)
    
    async def encode_text(self, text: str, use_cache: bool = True) -> np.ndarray:
        """Genera embedding para texto"""
        if not self.initialized or not self.model:
            raise ValueError("Vector Embeddings Manager no inicializado")
        
        start_time = time.time()
        
        # Cache key
        cache_key = f"embedding:{hashlib.md5(text.encode()).hexdigest()}"
        
        # Verificar cache
        if use_cache:
            cached_embedding = await redis_get(cache_key)
            if cached_embedding:
                logger.debug(f"Cache hit para embedding: {text[:50]}...")
                return np.array(cached_embedding)
        
        try:
            # Generar embedding en thread separado
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                self.model.encode,
                text
            )
            
            # Guardar en cache
            if use_cache:
                await redis_set(
                    cache_key, 
                    embedding.tolist(), 
                    self.config.cache_ttl
                )
            
            duration = time.time() - start_time
            logger.debug(f"Embedding generado en {duration:.3f}s: {text[:50]}...")
            
            return embedding
            
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            raise
    
    async def encode_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Genera embeddings para múltiples textos en batch"""
        if not self.initialized or not self.model:
            raise ValueError("Vector Embeddings Manager no inicializado")
        
        start_time = time.time()
        
        try:
            # Procesar en batch para mayor eficiencia
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                self.model.encode,
                texts
            )
            
            duration = time.time() - start_time
            logger.info(f"Batch de {len(texts)} embeddings generado en {duration:.3f}s")
            
            return embeddings
            
        except Exception as e:
            logger.error(f"Error generando batch embeddings: {e}")
            raise
    
    async def add_document(self, doc_id: str, text: str, metadata: Dict[str, Any] = None):
        """Agrega documento al índice de vectores"""
        if not self.initialized:
            await self.initialize()
        
        try:
            # Generar embedding
            embedding = await self.encode_text(text)
            
            # Almacenar documento
            doc_data = {
                'id': doc_id,
                'text': text,
                'embedding': embedding,
                'metadata': metadata or {},
                'created_at': datetime.now().isoformat()
            }
            
            # Agregar al índice FAISS si está disponible
            if self.vector_index is not None:
                next_id = len(self.document_store)
                self.vector_index.add(embedding.reshape(1, -1))
                self.document_store[next_id] = doc_data
            else:
                # Usar store simple si no hay FAISS
                doc_hash = hashlib.md5(doc_id.encode()).hexdigest()
                self.document_store[doc_hash] = doc_data
            
            logger.debug(f"Documento agregado al índice: {doc_id}")
            VECTOR_EMBEDDINGS_CACHE.set(len(self.document_store))
            
        except Exception as e:
            logger.error(f"Error agregando documento: {e}")
            raise
    
    async def search_similar(
        self, 
        query: str, 
        limit: int = None, 
        threshold: float = None
    ) -> List[Dict[str, Any]]:
        """Busca documentos similares"""
        if not self.initialized:
            await self.initialize()
        
        limit = limit or self.config.max_results
        threshold = threshold or self.config.similarity_threshold
        
        try:
            # Generar embedding para query
            query_embedding = await self.encode_text(query)
            
            if self.vector_index is not None and len(self.document_store) > 0:
                # Búsqueda con FAISS
                scores, indices = self.vector_index.search(
                    query_embedding.reshape(1, -1), 
                    min(limit, len(self.document_store))
                )
                
                results = []
                for score, idx in zip(scores[0], indices[0]):
                    if score >= threshold and idx in self.document_store:
                        doc = self.document_store[idx].copy()
                        doc['similarity_score'] = float(score)
                        results.append(doc)
                
                return results
            else:
                # Búsqueda simple por similaridad coseno
                results = []
                for doc_id, doc_data in self.document_store.items():
                    doc_embedding = doc_data['embedding']
                    similarity = np.dot(query_embedding, doc_embedding) / (
                        np.linalg.norm(query_embedding) * np.linalg.norm(doc_embedding)
                    )
                    
                    if similarity >= threshold:
                        doc = doc_data.copy()
                        doc['similarity_score'] = float(similarity)
                        results.append(doc)
                
                # Ordenar por similaridad
                results.sort(key=lambda x: x['similarity_score'], reverse=True)
                return results[:limit]
                
        except Exception as e:
            logger.error(f"Error en búsqueda similar: {e}")
            raise

# ===============================================
# 🔍 SEMANTIC SEARCH SERVICE PRINCIPAL
# ===============================================

class SemanticSearchService:
    """Servicio principal de búsqueda semántica"""
    
    def __init__(self):
        self.config = SemanticSearchConfig()
        self.embeddings_manager = VectorEmbeddingsManager(self.config)
        self.initialized = False
    
    async def initialize(self):
        """Inicializa el servicio de búsqueda semántica"""
        try:
            logger.info("🚀 Inicializando Semantic Search Service")
            
            await self.embeddings_manager.initialize()
            
            # Cargar datos iniciales si existen
            await self._load_initial_data()
            
            self.initialized = True
            logger.info("✅ Semantic Search Service inicializado")
            
        except Exception as e:
            logger.error(f"❌ Error inicializando Semantic Search: {e}")
            raise
    
    async def _load_initial_data(self):
        """Carga datos iniciales para indexar"""
        try:
            # Aquí podrías cargar documentos existentes de la base de datos
            sample_docs = [
                {
                    "id": "doc_1",
                    "text": "Inteligencia artificial y machine learning para análisis de datos",
                    "metadata": {"category": "AI", "source": "system"}
                },
                {
                    "id": "doc_2", 
                    "text": "Desarrollo de aplicaciones web con FastAPI y Python",
                    "metadata": {"category": "Development", "source": "system"}
                },
                {
                    "id": "doc_3",
                    "text": "Análisis de documentos y procesamiento de texto con IA",
                    "metadata": {"category": "NLP", "source": "system"}
                }
            ]
            
            for doc in sample_docs:
                await self.embeddings_manager.add_document(
                    doc["id"], 
                    doc["text"], 
                    doc["metadata"]
                )
            
            logger.info(f"✅ {len(sample_docs)} documentos de ejemplo indexados")
            
        except Exception as e:
            logger.warning(f"⚠️ Error cargando datos iniciales: {e}")
    
    async def semantic_search(
        self,
        query: str,
        user_id: str,
        search_type: str = "general",
        limit: int = 10,
        threshold: float = 0.7
    ) -> Dict[str, Any]:
        """Realiza búsqueda semántica"""
        start_time = time.time()
        
        if not self.initialized:
            await self.initialize()
        
        try:
            logger.info(f"🔍 Búsqueda semántica: '{query}' por usuario {user_id}")
            
            # Realizar búsqueda
            results = await self.embeddings_manager.search_similar(
                query=query,
                limit=limit,
                threshold=threshold
            )
            
            # Formatear respuesta
            response = {
                "query": query,
                "results_count": len(results),
                "results": [
                    {
                        "id": result["id"],
                        "text": result["text"],
                        "similarity_score": result["similarity_score"],
                        "metadata": result.get("metadata", {}),
                        "created_at": result.get("created_at")
                    }
                    for result in results
                ],
                "search_metadata": {
                    "search_type": search_type,
                    "threshold_used": threshold,
                    "user_id": user_id,
                    "timestamp": datetime.now().isoformat()
                }
            }
            
            # Métricas
            duration = time.time() - start_time
            SEMANTIC_SEARCH_REQUESTS.labels(
                user_id=user_id, 
                search_type=search_type, 
                status="success"
            ).inc()
            SEMANTIC_SEARCH_DURATION.labels(
                user_id=user_id, 
                search_type=search_type
            ).observe(duration)
            
            logger.info(f"✅ Búsqueda completada: {len(results)} resultados en {duration:.3f}s")
            
            return response
            
        except Exception as e:
            SEMANTIC_SEARCH_REQUESTS.labels(
                user_id=user_id, 
                search_type=search_type, 
                status="error"
            ).inc()
            logger.error(f"❌ Error en búsqueda semántica: {e}")
            raise
    
    async def add_document_to_index(
        self,
        doc_id: str,
        content: str,
        metadata: Dict[str, Any] = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Agrega documento al índice semántico"""
        if not self.initialized:
            await self.initialize()
        
        try:
            await self.embeddings_manager.add_document(doc_id, content, metadata)
            
            logger.info(f"📄 Documento indexado: {doc_id} por usuario {user_id}")
            
            return {
                "status": "indexed",
                "document_id": doc_id,
                "content_length": len(content),
                "metadata": metadata,
                "indexed_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Error indexando documento: {e}")
            raise
    
    async def get_similar_documents(
        self,
        reference_doc_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """Encuentra documentos similares a uno de referencia"""
        if not self.initialized:
            await self.initialize()
        
        try:
            # Buscar documento de referencia
            reference_doc = None
            for doc_data in self.embeddings_manager.document_store.values():
                if doc_data["id"] == reference_doc_id:
                    reference_doc = doc_data
                    break
            
            if not reference_doc:
                raise ValueError(f"Documento de referencia no encontrado: {reference_doc_id}")
            
            # Usar el texto del documento de referencia para búsqueda
            results = await self.embeddings_manager.search_similar(
                query=reference_doc["text"],
                limit=limit + 1  # +1 porque incluirá el documento original
            )
            
            # Filtrar el documento original
            similar_docs = [
                result for result in results 
                if result["id"] != reference_doc_id
            ][:limit]
            
            return similar_docs
            
        except Exception as e:
            logger.error(f"❌ Error buscando documentos similares: {e}")
            raise
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check del servicio"""
        return {
            "status": "ok" if self.initialized else "initializing",
            "service": "semantic_search_service",
            "model_name": self.config.model_name,
            "vector_dimension": self.config.vector_dimension,
            "documents_indexed": len(self.embeddings_manager.document_store),
            "sentence_transformers_available": SENTENCE_TRANSFORMERS_AVAILABLE,
            "faiss_available": FAISS_AVAILABLE,
            "cache_enabled": True
        }

# ===============================================
# 🌟 INSTANCIA GLOBAL Y UTILIDADES
# ===============================================

# Instancia global del servicio
semantic_search_service = SemanticSearchService()

async def semantic_search(
    query: str,
    user_id: str,
    search_type: str = "general",
    limit: int = 10
) -> Dict[str, Any]:
    """Función de utilidad para búsqueda semántica"""
    return await semantic_search_service.semantic_search(
        query=query,
        user_id=user_id,
        search_type=search_type,
        limit=limit
    )

async def index_document(
    doc_id: str,
    content: str,
    metadata: Dict[str, Any] = None,
    user_id: str = None
) -> Dict[str, Any]:
    """Función de utilidad para indexar documentos"""
    return await semantic_search_service.add_document_to_index(
        doc_id=doc_id,
        content=content,
        metadata=metadata,
        user_id=user_id
    )

# ===============================================
# 📊 EXPORTS
# ===============================================

__all__ = [
    "SemanticSearchService",
    "VectorEmbeddingsManager", 
    "SemanticSearchConfig",
    "semantic_search_service",
    "semantic_search",
    "index_document"
]

logger.info("🔍 Semantic Search Service Module cargado exitosamente")