#!/bin/bash
# run_tests_enhanced.sh
# Enhanced Testing Script con Coverage y Reports
# Versión: 2.0 - Noviembre 2025

set -e

echo "=================================="
echo "🧪 BACKEND TEST SUITE v2.0"
echo "=================================="
echo ""

# Colores
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuración
export ENVIRONMENT=testing
export DEBUG=false
export DATABASE_URL="sqlite:///./test.db"
export REDIS_URL="redis://localhost:6379/1"

# Limpiar archivos de test anteriores
echo "🧹 Cleaning previous test artifacts..."
rm -f test.db
rm -rf htmlcov/
rm -f .coverage
rm -rf .pytest_cache/

# Verificar dependencias
echo ""
echo "📦 Checking test dependencies..."
python -c "import pytest" 2>/dev/null || pip install pytest
python -c "import pytest_cov" 2>/dev/null || pip install pytest-cov
python -c "import pytest_asyncio" 2>/dev/null || pip install pytest-asyncio

# Ejecutar tests con coverage
echo ""
echo "🚀 Running tests with coverage..."
echo "=================================="

pytest tests/ \
    --cov=. \
    --cov-report=html \
    --cov-report=term-missing \
    --cov-report=xml \
    -v \
    --tb=short \
    --maxfail=5 \
    -x

TEST_EXIT_CODE=$?

# Resultados
echo ""
echo "=================================="
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED${NC}"
else
    echo -e "${RED}❌ TESTS FAILED${NC}"
fi
echo "=================================="

# Coverage summary
echo ""
echo "📊 Coverage Report:"
echo "=================================="
coverage report --skip-empty --skip-covered

# Reporte HTML
if [ -d "htmlcov" ]; then
    echo ""
    echo -e "${GREEN}✅ HTML Coverage Report generated: htmlcov/index.html${NC}"
    echo "   Open with: xdg-open htmlcov/index.html"
fi

# Coverage badge (opcional)
if [ -f ".coverage" ]; then
    COVERAGE_PERCENT=$(coverage report | tail -1 | awk '{print $NF}' | sed 's/%//')
    echo ""
    echo "📈 Overall Coverage: ${COVERAGE_PERCENT}%"
    
    if (( $(echo "$COVERAGE_PERCENT > 80" | bc -l) )); then
        echo -e "${GREEN}   Excellent coverage! 🎉${NC}"
    elif (( $(echo "$COVERAGE_PERCENT > 60" | bc -l) )); then
        echo -e "${YELLOW}   Good coverage, aim for 80%+${NC}"
    else
        echo -e "${RED}   Coverage below 60%, needs improvement${NC}"
    fi
fi

# Limpiar base de datos de test
echo ""
echo "🧹 Cleaning up test database..."
rm -f test.db

echo ""
echo "=================================="
echo "🏁 Test suite completed"
echo "=================================="

exit $TEST_EXIT_CODE
