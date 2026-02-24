#!/bin/bash
###############################################################################
# 🤖 INSTALADOR DE QWEN 2.5 OMNI 57B
# Script para instalar Ollama + Qwen 2.5 Omni
###############################################################################

set -e

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  🤖 INSTALADOR DE QWEN 2.5 OMNI 57B          ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""

# Función para imprimir mensajes
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Verificar si es Linux
if [[ "$OSTYPE" != "linux-gnu"* ]]; then
    print_error "Este script solo funciona en Linux"
    exit 1
fi

# ==============================================================================
# PASO 1: Verificar/Instalar Ollama
# ==============================================================================
print_info "Verificando Ollama..."

if command -v ollama &> /dev/null; then
    print_success "Ollama ya está instalado"
    ollama --version
else
    print_warning "Ollama no encontrado, instalando..."
    curl -fsSL https://ollama.com/install.sh | sh
    
    if [ $? -eq 0 ]; then
        print_success "Ollama instalado correctamente"
    else
        print_error "Error instalando Ollama"
        exit 1
    fi
fi

# ==============================================================================
# PASO 2: Verificar GPU (opcional)
# ==============================================================================
print_info "Verificando GPU..."

if command -v nvidia-smi &> /dev/null; then
    print_success "GPU NVIDIA detectada"
    nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
    
    VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | awk '{print int($1/1024)}')
    print_info "VRAM disponible: ${VRAM}GB"
    
    if [ $VRAM -lt 48 ]; then
        print_warning "ADVERTENCIA: Qwen 2.5 Omni 57B necesita ~114GB VRAM"
        print_warning "Tu GPU tiene ${VRAM}GB, considera usar una versión más pequeña"
        print_info "Modelos alternativos:"
        echo "   - qwen2.5:7b (4GB VRAM) ← Desarrollo/laptop"
        echo "   - qwen2.5:14b (8GB VRAM) ← Testing"
        echo "   - qwen2.5:32b (20GB VRAM) ← RTX 3090/4090"
        echo "   - qwen2.5-omni:57b (114GB VRAM) ← Producción A6000"
        echo ""
        
        read -p "¿Continuar de todas formas? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_info "Instalación cancelada"
            exit 0
        fi
    else
        print_success "GPU suficiente para Qwen 2.5 Omni 57B ✅"
    fi
else
    print_warning "No se detectó GPU NVIDIA (usará CPU, muy lento)"
    print_info "Para GPU en producción:"
    echo "   - RunPod: RTX A6000 48GB ($569/mes)"
    echo "   - Vast.ai: RTX 3090 24GB ($108/mes)"
    echo "   - Google Colab: T4 16GB (gratis)"
    echo ""
fi

# ==============================================================================
# PASO 3: Iniciar Ollama
# ==============================================================================
print_info "Iniciando servidor Ollama..."

if pgrep -x "ollama" > /dev/null; then
    print_success "Ollama ya está corriendo"
else
    print_info "Iniciando Ollama en background..."
    ollama serve > /tmp/ollama.log 2>&1 &
    sleep 3
    
    if pgrep -x "ollama" > /dev/null; then
        print_success "Ollama iniciado correctamente"
    else
        print_error "Error iniciando Ollama, revisa: /tmp/ollama.log"
        exit 1
    fi
fi

# ==============================================================================
# PASO 4: Descargar Qwen 2.5 Omni 57B
# ==============================================================================
print_info "Descargando Qwen 2.5 Omni 57B..."
print_warning "Esto descargará ~114GB, puede tardar varios minutos u horas"
print_info "Puedes cancelar con Ctrl+C si ya lo tienes instalado"

sleep 2

ollama pull qwen2.5-omni:57b

if [ $? -eq 0 ]; then
    print_success "Qwen 2.5 Omni 57B instalado correctamente ✅"
else
    print_error "Error descargando Qwen, intenta manualmente:"
    echo "   ollama pull qwen2.5-omni:57b"
    exit 1
fi

# ==============================================================================
# PASO 5: Verificar instalación
# ==============================================================================
print_info "Verificando instalación..."

ollama list | grep -q "qwen2.5-omni"
if [ $? -eq 0 ]; then
    print_success "Qwen 2.5 Omni 57B disponible ✅"
    echo ""
    print_info "Modelos instalados:"
    ollama list
else
    print_warning "Qwen 2.5 Omni no encontrado en ollama list"
fi

# ==============================================================================
# PASO 6: Test rápido
# ==============================================================================
print_info "Probando Qwen 2.5 Omni..."

RESPONSE=$(ollama run qwen2.5-omni:57b "Responde solo: OK" --verbose=false 2>/dev/null | head -n 1)

if [[ "$RESPONSE" == *"OK"* ]]; then
    print_success "Test OK - Qwen funciona correctamente ✅"
else
    print_warning "Test no concluyente, verifica manualmente:"
    echo "   ollama run qwen2.5-omni:57b"
fi

# ==============================================================================
# RESUMEN FINAL
# ==============================================================================
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ✅ INSTALACIÓN COMPLETADA                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════╝${NC}"
echo ""
print_success "Qwen 2.5 Omni 57B listo para usar"
echo ""
print_info "Comandos útiles:"
echo "   # Chatear con Qwen:"
echo "   ollama run qwen2.5-omni:57b"
echo ""
echo "   # Listar modelos instalados:"
echo "   ollama list"
echo ""
echo "   # Ver logs de Ollama:"
echo "   tail -f /tmp/ollama.log"
echo ""
echo "   # Detener Ollama:"
echo "   pkill ollama"
echo ""
print_info "Backend configurado en:"
echo "   - AI_SERVER_URL=http://localhost:11434"
echo "   - AI_MODEL=qwen2.5-omni:57b"
echo ""
print_info "Iniciar backend:"
echo "   python main.py"
echo ""
print_success "¡Listo para desarrollar! 🚀"
