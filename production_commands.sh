#!/bin/bash
# production_commands.sh - Comandos útiles para producción
# Backend Súper IA v4.0

echo "🚀 Backend Súper IA v4.0 - Comandos de Producción"
echo ""

# Función para mostrar comandos
show_help() {
    cat << EOF
Comandos disponibles:

VALIDACIÓN Y LIMPIEZA:
  ./production_commands.sh validate      # Validar configuración completa
  ./production_commands.sh cleanup-docs  # Limpiar documentación
  ./production_commands.sh test          # Ejecutar tests

SERVIDOR:
  ./production_commands.sh dev           # Servidor desarrollo
  ./production_commands.sh prod          # Servidor producción
  ./production_commands.sh stop          # Detener servidor

BASE DE DATOS:
  ./production_commands.sh db-upgrade    # Aplicar migraciones
  ./production_commands.sh db-current    # Ver migración actual
  ./production_commands.sh db-create     # Crear nueva migración

MONITOREO:
  ./production_commands.sh health        # Health check
  ./production_commands.sh metrics       # Ver métricas
  ./production_commands.sh logs          # Ver logs en tiempo real

MANTENIMIENTO:
  ./production_commands.sh backup-db     # Backup de base de datos
  ./production_commands.sh clear-cache   # Limpiar caché Redis
  ./production_commands.sh restart       # Reiniciar servicios

INFORMACIÓN:
  ./production_commands.sh status        # Estado del sistema
  ./production_commands.sh help          # Mostrar esta ayuda

EOF
}

# Comandos principales
case "${1}" in
    validate)
        echo "🔍 Validando configuración..."
        python validate_config.py
        ;;
    
    cleanup-docs)
        echo "🧹 Limpiando documentación..."
        ./cleanup_docs.sh
        ;;
    
    test)
        echo "🧪 Ejecutando tests..."
        pytest tests/ -v --cov=. --cov-report=term-missing
        ;;
    
    dev)
        echo "🔧 Iniciando servidor de desarrollo..."
        uvicorn main:app --reload --host 0.0.0.0 --port 8000
        ;;
    
    prod)
        echo "🚀 Iniciando servidor de producción..."
        gunicorn main:app \
            -w 4 \
            -k uvicorn.workers.UvicornWorker \
            --bind 0.0.0.0:8000 \
            --timeout 120 \
            --keep-alive 5 \
            --max-requests 1000 \
            --max-requests-jitter 100 \
            --access-logfile logs/access.log \
            --error-logfile logs/error.log \
            --log-level info
        ;;
    
    stop)
        echo "🛑 Deteniendo servidor..."
        pkill -f "gunicorn main:app"
        echo "✅ Servidor detenido"
        ;;
    
    db-upgrade)
        echo "📊 Aplicando migraciones..."
        alembic upgrade head
        echo "✅ Migraciones aplicadas"
        ;;
    
    db-current)
        echo "📊 Migración actual:"
        alembic current
        ;;
    
    db-create)
        if [ -z "$2" ]; then
            echo "❌ Error: Debes especificar un mensaje"
            echo "Uso: ./production_commands.sh db-create 'mensaje de la migración'"
            exit 1
        fi
        echo "📊 Creando nueva migración..."
        alembic revision --autogenerate -m "$2"
        ;;
    
    health)
        echo "❤️  Health check..."
        curl -s http://localhost:8000/api/health | python -m json.tool
        ;;
    
    metrics)
        echo "📊 Métricas Prometheus..."
        curl -s http://localhost:8000/metrics | head -n 50
        echo ""
        echo "Ver métricas completas: http://localhost:8000/metrics"
        ;;
    
    logs)
        echo "📝 Logs en tiempo real (Ctrl+C para salir)..."
        if [ -f "logs/error.log" ]; then
            tail -f logs/error.log logs/access.log
        else
            echo "⚠️  No se encontraron archivos de log"
            echo "Los logs se mostrarán en consola cuando inicies el servidor"
        fi
        ;;
    
    backup-db)
        echo "💾 Backup de base de datos..."
        timestamp=$(date +%Y%m%d_%H%M%S)
        backup_file="backups/db_backup_${timestamp}.sql"
        mkdir -p backups
        
        # Detectar tipo de base de datos
        if echo $DATABASE_URL | grep -q "postgresql"; then
            pg_dump $DATABASE_URL > $backup_file
            echo "✅ Backup creado: $backup_file"
        elif echo $DATABASE_URL | grep -q "sqlite"; then
            cp backend_super.db "backups/backend_super_${timestamp}.db"
            echo "✅ Backup creado: backups/backend_super_${timestamp}.db"
        else
            echo "⚠️  Tipo de base de datos no soportado para backup automático"
        fi
        ;;
    
    clear-cache)
        echo "🧹 Limpiando caché Redis..."
        redis-cli FLUSHDB
        echo "✅ Caché limpiado"
        ;;
    
    restart)
        echo "🔄 Reiniciando servicios..."
        ./production_commands.sh stop
        sleep 2
        ./production_commands.sh prod &
        echo "✅ Servicios reiniciados"
        ;;
    
    status)
        echo "📊 Estado del Sistema"
        echo "===================="
        echo ""
        
        # Servidor
        if pgrep -f "gunicorn main:app" > /dev/null; then
            echo "✅ Servidor: CORRIENDO"
        else
            echo "❌ Servidor: DETENIDO"
        fi
        
        # Redis
        if redis-cli ping > /dev/null 2>&1; then
            echo "✅ Redis: CONECTADO"
        else
            echo "❌ Redis: NO DISPONIBLE"
        fi
        
        # PostgreSQL
        if pg_isready > /dev/null 2>&1; then
            echo "✅ PostgreSQL: CONECTADO"
        else
            echo "⚠️  PostgreSQL: NO DISPONIBLE (puede estar usando SQLite)"
        fi
        
        # Ollama (DeepSeek-VL)
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo "✅ Ollama (IA): CONECTADO"
        else
            echo "❌ Ollama (IA): NO DISPONIBLE"
        fi
        
        echo ""
        echo "Health Check completo:"
        curl -s http://localhost:8000/api/health | python -m json.tool 2>/dev/null || echo "⚠️  Servidor no responde"
        ;;
    
    help|*)
        show_help
        ;;
esac
