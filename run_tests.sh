#!/bin/bash
# 🧪 Script de Testing - Backend Super IA v4.0

set -e

# Colores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}🧪 Backend Super IA - Test Suite${NC}"
echo "================================="
echo ""

# Función para mostrar uso
show_usage() {
    echo "Uso: ./run_tests.sh [opción]"
    echo ""
    echo "Opciones:"
    echo "  all           - Ejecutar todos los tests (default)"
    echo "  agents        - Tests del sistema de agentes"
    echo "  services      - Tests de servicios core"
    echo "  routers       - Tests de routers/endpoints"
    echo "  integration   - Tests de integración"
    echo "  unit          - Solo tests unitarios"
    echo "  coverage      - Tests con reporte de cobertura HTML"
    echo "  fast          - Tests en paralelo (más rápido)"
    echo "  watch         - Modo watch (re-ejecuta al cambiar archivos)"
    echo "  clean         - Limpiar archivos de test"
    echo ""
    echo "Ejemplos:"
    echo "  ./run_tests.sh all"
    echo "  ./run_tests.sh agents"
    echo "  ./run_tests.sh coverage"
}

# Función para limpiar
clean_tests() {
    echo -e "${YELLOW}🧹 Limpiando archivos de test...${NC}"
    rm -rf .pytest_cache
    rm -rf htmlcov
    rm -rf .coverage
    rm -rf __pycache__
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    echo -e "${GREEN}✅ Limpieza completada${NC}"
}

# Verificar que pytest está instalado
check_dependencies() {
    if ! command -v pytest &> /dev/null; then
        echo -e "${RED}❌ pytest no está instalado${NC}"
        echo "Instalando dependencias..."
        pip install -r requirements.txt
    fi
}

# Función para ejecutar tests
run_tests() {
    local test_type=$1
    
    case $test_type in
        all)
            echo -e "${YELLOW}🚀 Ejecutando todos los tests...${NC}"
            pytest -v
            ;;
        
        agents)
            echo -e "${YELLOW}🤖 Ejecutando tests de agentes...${NC}"
            pytest tests/test_agents_system.py -v
            ;;
        
        services)
            echo -e "${YELLOW}⚙️  Ejecutando tests de servicios...${NC}"
            pytest tests/test_services_core.py -v
            ;;
        
        routers)
            echo -e "${YELLOW}🛣️  Ejecutando tests de routers...${NC}"
            pytest tests/test_routers.py -v
            ;;
        
        integration)
            echo -e "${YELLOW}🔗 Ejecutando tests de integración...${NC}"
            pytest -m integration -v
            ;;
        
        unit)
            echo -e "${YELLOW}📦 Ejecutando tests unitarios...${NC}"
            pytest -m unit -v
            ;;
        
        coverage)
            echo -e "${YELLOW}📊 Ejecutando tests con cobertura...${NC}"
            pytest --cov=. --cov-report=html --cov-report=term-missing
            echo ""
            echo -e "${GREEN}✅ Reporte de cobertura generado en: htmlcov/index.html${NC}"
            echo -e "${YELLOW}💡 Abrir con: firefox htmlcov/index.html${NC}"
            ;;
        
        fast)
            echo -e "${YELLOW}⚡ Ejecutando tests en paralelo...${NC}"
            pytest -n auto -v
            ;;
        
        watch)
            echo -e "${YELLOW}👀 Modo watch activado (Ctrl+C para salir)...${NC}"
            pytest-watch -v
            ;;
        
        clean)
            clean_tests
            ;;
        
        *)
            show_usage
            exit 1
            ;;
    esac
}

# Main
main() {
    # Si no hay argumentos, mostrar ayuda
    if [ $# -eq 0 ]; then
        test_type="all"
    else
        test_type=$1
    fi
    
    # Verificar dependencias
    check_dependencies
    
    # Ejecutar tests
    run_tests $test_type
    
    # Mostrar resumen
    if [ $? -eq 0 ]; then
        echo ""
        echo -e "${GREEN}✅ Tests completados exitosamente${NC}"
    else
        echo ""
        echo -e "${RED}❌ Algunos tests fallaron${NC}"
        exit 1
    fi
}

# Ejecutar
main "$@"
