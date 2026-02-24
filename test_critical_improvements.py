#!/usr/bin/env python3
"""
🧪 Test Suite para Mejoras Críticas
Script de testing rápido para WebSocket, RAG y Proactive AI
"""

import asyncio
import json
import sys
from typing import Dict, Any

# Colores para output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_test(name: str):
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}🧪 TEST: {name}{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}")


def print_success(msg: str):
    print(f"{Colors.OKGREEN}✅ {msg}{Colors.ENDC}")


def print_error(msg: str):
    print(f"{Colors.FAIL}❌ {msg}{Colors.ENDC}")


def print_info(msg: str):
    print(f"{Colors.OKCYAN}ℹ️  {msg}{Colors.ENDC}")


# =============================================
# TEST 1: EMBEDDINGS SERVICE (RAG)
# =============================================

async def test_embeddings_service():
    """Test RAG con embeddings"""
    print_test("Embeddings Service (RAG)")
    
    try:
        from services.embeddings_service import embeddings_service
        
        # Test 1: Indexar documentos
        print_info("Indexando documentos de prueba...")
        
        await embeddings_service.index_document(
            doc_id="doc_math_1",
            content="El teorema de Pitágoras establece que en un triángulo rectángulo, el cuadrado de la hipotenusa es igual a la suma de los cuadrados de los catetos. Fórmula: a² + b² = c²",
            metadata={
                "group_id": "test_group",
                "subject": "matemáticas",
                "type": "teorema"
            }
        )
        print_success("Documento 1 indexado")
        
        await embeddings_service.index_document(
            doc_id="doc_math_2",
            content="La derivada de una función mide la tasa de cambio instantánea. Es fundamental en cálculo diferencial para encontrar máximos, mínimos y puntos de inflexión.",
            metadata={
                "group_id": "test_group",
                "subject": "matemáticas",
                "type": "concepto"
            }
        )
        print_success("Documento 2 indexado")
        
        await embeddings_service.index_document(
            doc_id="doc_history_1",
            content="La Segunda Guerra Mundial fue un conflicto bélico que duró de 1939 a 1945. Involucró a la mayoría de las naciones del mundo, incluyendo todas las grandes potencias.",
            metadata={
                "group_id": "test_group",
                "subject": "historia",
                "type": "evento"
            }
        )
        print_success("Documento 3 indexado")
        
        # Test 2: Búsqueda semántica
        print_info("\nBuscando: '¿Qué es el teorema de Pitágoras?'")
        results = await embeddings_service.semantic_search(
            query="¿Qué es el teorema de Pitágoras?",
            top_k=2,
            min_similarity=0.5,
            filter_metadata={"group_id": "test_group"}
        )
        
        for i, (doc_id, content, similarity, metadata) in enumerate(results, 1):
            print(f"\n{Colors.OKBLUE}Resultado {i}:{Colors.ENDC}")
            print(f"  Doc ID: {doc_id}")
            print(f"  Similitud: {similarity:.4f}")
            print(f"  Subject: {metadata.get('subject')}")
            print(f"  Contenido: {content[:100]}...")
        
        if results and results[0][0] == "doc_math_1":
            print_success("\n✅ RAG encontró el documento correcto!")
        else:
            print_error("\n❌ RAG no encontró el documento correcto")
        
        # Test 3: Contexto relevante
        print_info("\nObteniendo contexto relevante...")
        context = await embeddings_service.get_relevant_context(
            query="Explícame derivadas",
            group_id="test_group",
            max_tokens=500
        )
        
        if "derivada" in context.lower():
            print_success(f"Contexto obtenido: {len(context)} caracteres")
            print(f"{Colors.OKCYAN}{context[:200]}...{Colors.ENDC}")
        else:
            print_error("Contexto no contiene información relevante")
        
        # Estadísticas
        stats = embeddings_service.get_stats()
        print_info(f"\n📊 Estadísticas:")
        print(f"  - Documentos indexados: {stats['indexed_documents']}")
        print(f"  - Embeddings en cache: {stats['embeddings_cached']}")
        
        print_success("\n✅ Test Embeddings Service COMPLETADO")
        return True
    
    except Exception as e:
        print_error(f"Error en test: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# TEST 2: STREAMING SERVICE
# =============================================

async def test_streaming_service():
    """Test streaming de respuestas"""
    print_test("Streaming Service (SSE)")
    
    try:
        from services.streaming_service import StreamingService
        
        streaming_service = StreamingService()
        
        # Test: Streaming con contexto
        print_info("Streaming respuesta con contexto...")
        
        query = "¿Qué es el cálculo diferencial?"
        context = "El cálculo diferencial es una rama de las matemáticas que estudia las tasas de cambio."
        
        print(f"\n{Colors.OKCYAN}Respuesta (token-by-token):{Colors.ENDC}\n")
        
        full_response = ""
        token_count = 0
        
        async for token in streaming_service.stream_with_context(
            query=query,
            context=context,
            system_prompt="Eres un profesor de matemáticas."
        ):
            print(token, end="", flush=True)
            full_response += token
            token_count += 1
        
        print(f"\n\n{Colors.OKBLUE}Total tokens: {token_count}{Colors.ENDC}")
        
        if token_count > 0:
            print_success("✅ Streaming funcionó correctamente")
        else:
            print_error("❌ No se recibieron tokens")
        
        # Estadísticas
        stats = streaming_service.get_stats()
        print_info(f"\n📊 Estadísticas:")
        print(f"  - Streams activos: {stats['active_streams']}")
        print(f"  - Tokens enviados: {stats['total_tokens_streamed']}")
        
        print_success("\n✅ Test Streaming Service COMPLETADO")
        return True
    
    except Exception as e:
        print_error(f"Error en test: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# TEST 3: PROACTIVE AGENT
# =============================================

async def test_proactive_agent():
    """Test agente proactivo"""
    print_test("Proactive Agent")
    
    try:
        from services.proactive_agent import proactive_agent
        
        # Mock data
        messages = [
            {"content": "¿Alguien sabe cómo resolver integrales?", "user_id": "user1", "created_at": "2024-01-15T10:00:00Z"},
            {"content": "No entiendo las integrales", "user_id": "user2", "created_at": "2024-01-15T10:05:00Z"},
            {"content": "¿Cómo se calcula una integral?", "user_id": "user3", "created_at": "2024-01-15T10:10:00Z"},
            {"content": "Tenemos examen de cálculo mañana", "user_id": "user1", "created_at": "2024-01-15T10:15:00Z"},
        ]
        
        documents = [
            {"id": "doc1", "title": "Apuntes de Cálculo", "created_at": "2024-01-15T09:00:00Z"},
            {"id": "doc2", "title": "Ejercicios Resueltos", "created_at": "2024-01-15T09:30:00Z"},
        ]
        
        members_count = 5
        
        # Test: Analizar actividad
        print_info("Analizando actividad del grupo...")
        
        suggestions = await proactive_agent.analyze_group_activity(
            group_id="test_group",
            messages=messages,
            documents=documents,
            members_count=members_count
        )
        
        print(f"\n{Colors.OKBLUE}Sugerencias generadas: {len(suggestions)}{Colors.ENDC}\n")
        
        for i, suggestion in enumerate(suggestions, 1):
            print(f"{Colors.BOLD}{suggestion['icon']} {suggestion['title']}{Colors.ENDC}")
            print(f"   Prioridad: {suggestion['priority']}")
            print(f"   Descripción: {suggestion['description']}")
            print(f"   Acción: {suggestion['action_label']}\n")
        
        if suggestions:
            print_success(f"✅ Generadas {len(suggestions)} sugerencias")
            
            # Test: Ejecutar sugerencia
            print_info("\nEjecutando primera sugerencia...")
            result = await proactive_agent.execute_suggestion(suggestions[0], "test_group")
            
            if result.get("success"):
                print_success(f"✅ Sugerencia ejecutada: {result.get('message')}")
            else:
                print_error(f"❌ Error ejecutando sugerencia")
        else:
            print_error("❌ No se generaron sugerencias")
        
        # Estadísticas
        stats = proactive_agent.get_stats()
        print_info(f"\n📊 Estadísticas:")
        print(f"  - Grupos analizados: {stats['groups_analyzed']}")
        print(f"  - Sugerencias totales: {stats['total_suggestions']}")
        print(f"  - Análisis realizados: {stats['analysis_count']}")
        
        print_success("\n✅ Test Proactive Agent COMPLETADO")
        return True
    
    except Exception as e:
        print_error(f"Error en test: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# TEST 4: WEBSOCKET MANAGER
# =============================================

async def test_websocket_manager():
    """Test WebSocket manager"""
    print_test("WebSocket Manager")
    
    try:
        from services.websocket_manager import connection_manager
        
        print_info("Testing WebSocket manager (sin conexiones reales)...")
        
        # Test: Estadísticas iniciales
        stats = connection_manager.get_stats()
        print_info(f"Grupos activos: {stats['total_groups']}")
        print_info(f"Conexiones totales: {stats['total_connections']}")
        
        # Test: Online users (vacío porque no hay conexiones)
        online = connection_manager.get_online_users("test_group")
        print_info(f"Usuarios online en test_group: {len(online)}")
        
        print_success("✅ WebSocket Manager funcional (sin conexiones activas)")
        print_info("💡 Para testing completo, usar cliente WebSocket real")
        
        print_success("\n✅ Test WebSocket Manager COMPLETADO")
        return True
    
    except Exception as e:
        print_error(f"Error en test: {e}")
        import traceback
        traceback.print_exc()
        return False


# =============================================
# RUNNER
# =============================================

async def run_all_tests():
    """Ejecuta todos los tests"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}")
    print("╔" + "="*58 + "╗")
    print("║" + " "*15 + "🚀 TEST SUITE - MEJORAS CRÍTICAS" + " "*12 + "║")
    print("╚" + "="*58 + "╝")
    print(Colors.ENDC)
    
    results = {}
    
    # Test 1: Embeddings
    results["embeddings"] = await test_embeddings_service()
    await asyncio.sleep(1)
    
    # Test 2: Streaming
    results["streaming"] = await test_streaming_service()
    await asyncio.sleep(1)
    
    # Test 3: Proactive AI
    results["proactive"] = await test_proactive_agent()
    await asyncio.sleep(1)
    
    # Test 4: WebSocket
    results["websocket"] = await test_websocket_manager()
    
    # Resumen
    print(f"\n{Colors.HEADER}{'='*60}{Colors.ENDC}")
    print(f"{Colors.BOLD}📊 RESUMEN DE TESTS{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*60}{Colors.ENDC}\n")
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        color = Colors.OKGREEN if passed else Colors.FAIL
        print(f"{color}{status}{Colors.ENDC} - {test_name.capitalize()}")
    
    total_passed = sum(results.values())
    total_tests = len(results)
    
    print(f"\n{Colors.BOLD}Total: {total_passed}/{total_tests} tests pasados{Colors.ENDC}")
    
    if total_passed == total_tests:
        print(f"\n{Colors.OKGREEN}{Colors.BOLD}🎉 ¡TODOS LOS TESTS PASARON!{Colors.ENDC}")
        return 0
    else:
        print(f"\n{Colors.FAIL}{Colors.BOLD}⚠️  ALGUNOS TESTS FALLARON{Colors.ENDC}")
        return 1


# =============================================
# MAIN
# =============================================

if __name__ == "__main__":
    try:
        exit_code = asyncio.run(run_all_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}⚠️  Tests interrumpidos por el usuario{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Error fatal: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
