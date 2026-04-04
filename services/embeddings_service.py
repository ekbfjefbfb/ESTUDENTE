"""
🧠 Embeddings Service - RAG (Retrieval-Augmented Generation)
Sistema de vectorización y búsqueda semántica para documentos
Usa OpenAI embeddings + búsqueda por similaridad coseno
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime
import hashlib
import json

logger = logging.getLogger("embeddings")

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logger.warning("OpenAI no instalado, embeddings deshabilitados")

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False
    logger.warning("sentence-transformers no instalado")


class EmbeddingsService:
    """
    Servicio de embeddings para RAG (Retrieval-Augmented Generation) y Cache Semántico
    """
    
    def __init__(self, use_openai: bool = True, model: str = "text-embedding-3-small"):
        self.use_openai = use_openai and OPENAI_AVAILABLE
        self.model = model

        self._logged_no_provider: bool = False
        
        # Cache en memoria para embeddings
        self.embeddings_cache: Dict[str, np.ndarray] = {}
        self.documents_cache: Dict[str, Dict[str, Any]] = {}
        
        # Pareto 80/20: Cache Semántico para respuestas de IA
        self.semantic_response_cache: List[Dict[str, Any]] = []
        self.max_semantic_cache_size = 100
        
        # Modelo local fallback
        self.local_model = None
        if not self.use_openai and SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                logger.info("Cargando modelo local de embeddings...")
                self.local_model = SentenceTransformer('all-MiniLM-L6-v2')
                logger.info("✅ Modelo local cargado")
            except Exception as e:
                logger.error(f"Error cargando modelo local: {e}")

        self.enabled = bool(self.use_openai or self.local_model)
        
        logger.info(f"EmbeddingsService inicializado (OpenAI: {self.use_openai})")
    
    def _generate_doc_id(self, content: str, metadata: Dict = None) -> str:
        """Genera ID único para documento basado en contenido"""
        hash_input = content + json.dumps(metadata or {}, sort_keys=True)
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    async def generate_embedding(self, text: str) -> np.ndarray:
        """
        Genera embedding para texto
        
        Args:
            text: Texto a vectorizar
            
        Returns:
            Vector numpy de embeddings
        """
        try:
            # Limpiar texto
            text = text.strip()
            if not text:
                return np.zeros(1536 if self.use_openai else 384)
            
            # Truncar si es muy largo
            max_tokens = 8000 if self.use_openai else 500
            text = text[:max_tokens * 4]  # Aprox 4 chars por token
            
            if self.use_openai:
                # OpenAI embeddings
                response = await asyncio.to_thread(
                    openai.embeddings.create,
                    input=text,
                    model=self.model
                )
                embedding = response.data[0].embedding
                return np.array(embedding)
            
            elif self.local_model:
                # Modelo local
                embedding = await asyncio.to_thread(
                    self.local_model.encode,
                    text,
                    convert_to_numpy=True
                )
                return embedding
            
            else:
                # Fallback: embedding simple basado en características del texto
                # No requiere librerías externas
                embedding = self._simple_text_embedding(text)
                if not self._logged_no_provider:
                    logger.warning("No hay proveedor de embeddings disponible, usando fallback simple")
                    self._logged_no_provider = True
                return embedding
                
        except Exception as e:
            logger.error(f"Error generando embedding: {e}")
            # Retornar vector cero en caso de error
            return np.zeros(1536 if self.use_openai else 384)
    
    async def index_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Indexa documento generando su embedding
        
        Args:
            doc_id: ID único del documento
            content: Contenido del documento
            metadata: Metadata adicional (título, autor, fecha, etc.)
            
        Returns:
            Info del documento indexado
        """
        try:
            # Generar embedding
            embedding = await self.generate_embedding(content)
            
            # Guardar en cache
            self.embeddings_cache[doc_id] = embedding
            self.documents_cache[doc_id] = {
                "doc_id": doc_id,
                "content": content,
                "metadata": metadata or {},
                "indexed_at": datetime.utcnow().isoformat(),
                "embedding_dim": len(embedding)
            }
            
            logger.info(f"✅ Documento indexado: {doc_id} (dim: {len(embedding)})")
            
            return {
                "success": True,
                "doc_id": doc_id,
                "embedding_dim": len(embedding),
                "indexed_at": self.documents_cache[doc_id]["indexed_at"]
            }
            
        except Exception as e:
            logger.error(f"Error indexando documento {doc_id}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def index_documents_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Indexa múltiples documentos en batch
        
        Args:
            documents: Lista de {doc_id, content, metadata}
        """
        results = []
        
        for doc in documents:
            result = await self.index_document(
                doc_id=doc.get("doc_id"),
                content=doc.get("content", ""),
                metadata=doc.get("metadata")
            )
            results.append(result)
        
        success_count = sum(1 for r in results if r["success"])
        
        return {
            "success": True,
            "total": len(documents),
            "indexed": success_count,
            "failed": len(documents) - success_count,
            "results": results
        }
    
    def _cosine_similarity(self, vec1: np.ndarray, vec2: np.ndarray) -> float:
        """Calcula similaridad coseno entre dos vectores"""
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return float(dot_product / (norm1 * norm2))

    def _simple_text_embedding(self, text: str) -> np.ndarray:
        """
        Embedding simple basado en características del texto.
        No requiere librerías externas. Funciona para caché semántico básico.
        """
        import re
        
        text_lower = text.lower()
        
        # 1. Frecuencia de caracteres a-z (26 dims)
        char_freq = np.zeros(26)
        for c in text_lower:
            if 'a' <= c <= 'z':
                char_freq[ord(c) - ord('a')] += 1
        if len(text) > 0:
            char_freq = char_freq / (len(text) + 1e-8)
        
        # 2. Frecuencia de dígitos 0-9 (10 dims)
        digit_freq = np.zeros(10)
        for c in text:
            if '0' <= c <= '9':
                digit_freq[ord(c) - ord('0')] += 1
        if len(text) > 0:
            digit_freq = digit_freq / (len(text) + 1e-8)
        
        # 3. Estadísticas del texto (10 dims)
        words = text.split()
        sentences = re.split(r'[.!?]+', text)
        
        stats = np.array([
            len(text) / 1000.0,
            len(words) / 100.0,
            len(words) / (len(text) + 1e-8) * 10,
            len(sentences) / 10.0,
            np.mean([len(w) for w in words]) / 10.0 if words else 0,
            max([len(w) for w in words]) / 20.0 if words else 0,
            text.count('?') / 10.0,
            text.count('!') / 10.0,
            sum(1 for c in text if c.isupper()) / (len(text) + 1e-8) * 10,
            len(set(words)) / (len(words) + 1e-8) * 10,
        ])
        
        # 4. Hash del texto distribuido (338 dims)
        hash_val = hashlib.md5(text.encode()).hexdigest()
        hash_features = np.zeros(338)
        for i, hex_char in enumerate(hash_val):
            idx = i % 338
            hash_features[idx] += int(hex_char, 16) / 16.0
        
        # Concatenar y normalizar
        embedding = np.concatenate([char_freq, digit_freq, stats, hash_features])
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        return embedding
    
    async def semantic_search(
        self,
        query: str,
        top_k: int = 5,
        min_similarity: float = 0.3,
        filter_metadata: Optional[Dict] = None
    ) -> List[Dict[str, Any]]:
        """
        Búsqueda semántica por similaridad
        
        Args:
            query: Texto de búsqueda
            top_k: Número de resultados a retornar
            min_similarity: Similaridad mínima (0-1)
            filter_metadata: Filtros por metadata (ej: {"group_id": "abc"})
            
        Returns:
            Lista de documentos más relevantes con scores
        """
        try:
            if not self.documents_cache:
                return []
            
            # Generar embedding del query
            query_embedding = await self.generate_embedding(query)
            
            # Calcular similaridad con todos los documentos
            similarities = []
            
            for doc_id, doc_data in self.documents_cache.items():
                # Aplicar filtros de metadata
                if filter_metadata:
                    doc_metadata = doc_data.get("metadata", {})
                    if not all(doc_metadata.get(k) == v for k, v in filter_metadata.items()):
                        continue
                
                # Obtener embedding del documento
                doc_embedding = self.embeddings_cache.get(doc_id)
                if doc_embedding is None:
                    continue
                
                # Calcular similaridad
                similarity = self._cosine_similarity(query_embedding, doc_embedding)
                
                if similarity >= min_similarity:
                    similarities.append({
                        "doc_id": doc_id,
                        "content": doc_data["content"],
                        "metadata": doc_data["metadata"],
                        "similarity": similarity,
                        "indexed_at": doc_data["indexed_at"]
                    })
            
            # Ordenar por similaridad descendente
            similarities.sort(key=lambda x: x["similarity"], reverse=True)
            
            # Retornar top_k resultados
            results = similarities[:top_k]
            
            logger.info(f"🔍 Búsqueda semántica: '{query[:50]}...' → {len(results)} resultados")
            
            return results
            
        except Exception as e:
            logger.error(f"Error en búsqueda semántica: {e}")
            return []
    
    async def find_similar_documents(
        self,
        doc_id: str,
        top_k: int = 5,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Encuentra documentos similares a uno dado
        
        Args:
            doc_id: ID del documento de referencia
            top_k: Número de similares a retornar
            min_similarity: Similaridad mínima
        """
        if doc_id not in self.embeddings_cache:
            return []
        
        doc_embedding = self.embeddings_cache[doc_id]
        similarities = []
        
        for other_id, other_embedding in self.embeddings_cache.items():
            if other_id == doc_id:
                continue
            
            similarity = self._cosine_similarity(doc_embedding, other_embedding)
            
            if similarity >= min_similarity:
                similarities.append({
                    "doc_id": other_id,
                    "content": self.documents_cache[other_id]["content"],
                    "metadata": self.documents_cache[other_id]["metadata"],
                    "similarity": similarity
                })
        
        similarities.sort(key=lambda x: x["similarity"], reverse=True)
        return similarities[:top_k]
    
    async def get_cached_response(self, query: str, threshold: float = 0.92) -> Optional[str]:
        """Busca una respuesta similar en el cache semántico (Pareto Optimization)"""
        if not self.semantic_response_cache:
            return None
            
        query_embedding = await self.generate_embedding(query)
        
        for item in self.semantic_response_cache:
            similarity = self._cosine_similarity(query_embedding, item["embedding"])
            if similarity >= threshold:
                logger.info(f"🎯 Semantic Cache Hit (sim: {similarity:.4f})")
                return item["response"]
        return None

    async def add_to_semantic_cache(self, query: str, response: str):
        """Añade una interacción al cache semántico"""
        embedding = await self.generate_embedding(query)
        self.semantic_response_cache.insert(0, {
            "query": query,
            "response": response,
            "embedding": embedding,
            "timestamp": datetime.utcnow()
        })
        # Mantener tamaño máximo (LRU simple)
        if len(self.semantic_response_cache) > self.max_semantic_cache_size:
            self.semantic_response_cache.pop()

    async def get_relevant_context(
        self,
        query: str,
        group_id: Optional[str] = None,
        max_tokens: int = 4000
    ) -> str:
        """
        Obtiene contexto relevante para una query (para RAG)
        
        Args:
            query: Pregunta del usuario
            group_id: ID del grupo (opcional, para filtrar)
            max_tokens: Máximo de tokens de contexto
            
        Returns:
            String con contexto relevante concatenado
        """
        # Buscar documentos relevantes
        filter_metadata = {"group_id": group_id} if group_id else None
        
        results = await self.semantic_search(
            query=query,
            top_k=10,
            min_similarity=0.3,
            filter_metadata=filter_metadata
        )
        
        if not results:
            return ""
        
        # Concatenar contexto hasta max_tokens
        context_parts = []
        total_chars = 0
        max_chars = max_tokens * 4  # Aprox 4 chars por token
        
        for result in results:
            content = result["content"]
            metadata = result["metadata"]
            similarity = result["similarity"]
            
            # Formato del contexto
            context_piece = f"[Documento: {metadata.get('title', 'Sin título')} | Relevancia: {similarity:.2f}]\n{content}\n\n"
            
            if total_chars + len(context_piece) > max_chars:
                break
            
            context_parts.append(context_piece)
            total_chars += len(context_piece)
        
        context = "".join(context_parts)
        
        logger.info(f"📚 Contexto RAG: {len(results)} docs, {total_chars} chars")
        
        return context
    
    def remove_document(self, doc_id: str) -> bool:
        """Elimina documento del índice"""
        if doc_id in self.embeddings_cache:
            del self.embeddings_cache[doc_id]
        if doc_id in self.documents_cache:
            del self.documents_cache[doc_id]
        return True
    
    def clear_cache(self):
        """Limpia toda la cache de embeddings"""
        self.embeddings_cache.clear()
        self.documents_cache.clear()
        logger.info("🗑️ Cache de embeddings limpiada")
    
    def get_stats(self) -> Dict[str, Any]:
        """Obtiene estadísticas del servicio"""
        cache_size_mb = 0.0
        if self.embeddings_cache:
            cache_size_mb = sum(
                embedding.nbytes / (1024 * 1024)
                for embedding in self.embeddings_cache.values()
            )

        return {
            "total_documents": len(self.documents_cache),
            "indexed_documents": len(self.documents_cache),
            "total_embeddings": len(self.embeddings_cache),
            "embeddings_cached": len(self.embeddings_cache),
            "cache_size_mb": cache_size_mb,
            "use_openai": self.use_openai,
            "backend": "openai" if self.use_openai else "local",
            "model": self.model if self.use_openai else "local",
            "embedding_dim": 1536 if self.use_openai else 384,
        }


# =============================================
# INSTANCIA GLOBAL
# =============================================
embeddings_service = EmbeddingsService()


# =============================================
# HELPER FUNCTIONS
# =============================================

async def index_group_documents(group_id: str, documents: List[Dict]) -> Dict:
    """
    Helper para indexar documentos de un grupo
    
    Args:
        group_id: ID del grupo
        documents: Lista de {id, title, content}
    """
    docs_to_index = [
        {
            "doc_id": f"{group_id}_{doc['id']}",
            "content": doc.get("content", ""),
            "metadata": {
                "group_id": group_id,
                "title": doc.get("title", "Sin título"),
                "document_id": doc["id"],
                "indexed_at": datetime.utcnow().isoformat()
            }
        }
        for doc in documents
    ]
    
    return await embeddings_service.index_documents_batch(docs_to_index)


async def search_in_group(group_id: str, query: str, top_k: int = 5) -> List[Dict]:
    """
    Helper para buscar en documentos de un grupo
    """
    return await embeddings_service.semantic_search(
        query=query,
        top_k=top_k,
        filter_metadata={"group_id": group_id}
    )
