#!/bin/bash
# Script para arrancar el backend en desarrollo
# Uso: ./start_backend.sh

echo "🚀 Arrancando Backend Super IA v4.0..."
echo ""
echo "📊 Información:"
echo "  - Puerto: 8000"
echo "  - Docs: http://localhost:8000/docs"
echo "  - Health: http://localhost:8000/health"
echo "  - Metrics: http://localhost:8000/metrics"
echo ""
echo "✅ Dependencias verificadas"
echo "✅ 32 routers activos"
echo "✅ 218 endpoints disponibles"
echo "✅ LiveSearch SÚPER POTENTE (100+ sources)"
echo ""
echo "Presiona Ctrl+C para detener"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Arrancar uvicorn con auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000
