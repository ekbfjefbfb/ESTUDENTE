#!/bin/bash

# ===============================================
# 🔥 Celery Worker + Beat - Agencias v6.0
# ===============================================
# 
# Este script inicia:
# - Celery worker (8 workers concurrentes)
# - Celery beat (tareas periódicas: reportes semanales, mensuales, monitoreo)
#
# Usage:
#   ./start_celery.sh
#
# Detener:
#   pkill -f "celery"
#
# ===============================================

echo "🔥 Iniciando Celery Worker + Beat para Agencias v6.0"
echo ""

# Verificar Redis está corriendo
echo "📊 Verificando Redis..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✅ Redis está corriendo"
else
    echo "❌ Redis NO está corriendo. Iniciando..."
    redis-server --daemonize yes
    sleep 2
fi

echo ""
echo "🚀 Iniciando Celery Worker + Beat..."
echo ""
echo "📋 Tareas programadas:"
echo "  - Reportes semanales: Viernes 9:00 AM"
echo "  - Reportes mensuales: Día 1 9:00 AM"
echo "  - Monitoreo campañas: Cada hora"
echo "  - Detección anomalías: Cada 6 horas"
echo ""

# Iniciar Celery worker + beat
celery -A celery_config worker \
    --beat \
    --loglevel=info \
    --concurrency=8 \
    --max-tasks-per-child=1000 \
    --pool=prefork \
    --time-limit=3600 \
    --soft-time-limit=3000

echo ""
echo "✅ Celery Worker + Beat detenido"
