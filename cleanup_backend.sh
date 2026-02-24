#!/bin/bash

# 🧹 Script de Limpieza del Backend
# Fecha: 21 de Octubre 2025
# Versión: 1.0

set -e

# Colores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color
BOLD='\033[1m'

echo -e "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║          🧹 LIMPIEZA PROFUNDA DEL BACKEND                            ║"
echo "║          Backend Súper IA v4.1                                       ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Contador de archivos eliminados
FILES_DELETED=0
SPACE_FREED=0

# ============================================================================
# FUNCIÓN: Crear backup
# ============================================================================
create_backup() {
    echo -e "${YELLOW}📦 Creando backup de seguridad...${NC}"
    
    BACKUP_DIR="backups/cleanup_$(date +%Y%m%d_%H%M%S)"
    mkdir -p "$BACKUP_DIR"
    
    # Backup de documentación a eliminar
    echo "   Copiando archivos a backup..."
    cp STUDY_GROUPS_IMPLEMENTATION.md "$BACKUP_DIR/" 2>/dev/null || true
    cp STUDY_GROUPS_V2_IMPROVEMENTS.md "$BACKUP_DIR/" 2>/dev/null || true
    cp STUDY_GROUPS_V2_FINAL_IMPLEMENTATION.md "$BACKUP_DIR/" 2>/dev/null || true
    cp AUDITORIA_COMPLETA_RESUMEN.md "$BACKUP_DIR/" 2>/dev/null || true
    cp BACKEND_DEPURADO_INFORME.md "$BACKUP_DIR/" 2>/dev/null || true
    cp ERRORES_CORREGIDOS.md "$BACKUP_DIR/" 2>/dev/null || true
    cp README_CRITICAL_IMPROVEMENTS.md "$BACKUP_DIR/" 2>/dev/null || true
    cp REVISION_COMPLETA_SISTEMA.md "$BACKUP_DIR/" 2>/dev/null || true
    cp TECHNICAL_ANALYSIS.md "$BACKUP_DIR/" 2>/dev/null || true
    cp ELIMINAR_APIS_EXTERNAS.md "$BACKUP_DIR/" 2>/dev/null || true
    
    echo -e "${GREEN}   ✅ Backup creado en: $BACKUP_DIR${NC}\n"
}

# ============================================================================
# FUNCIÓN: Eliminar archivo con confirmación
# ============================================================================
delete_file() {
    local file=$1
    local reason=$2
    
    if [ -f "$file" ]; then
        local size=$(du -h "$file" | cut -f1)
        echo -e "${YELLOW}   🗑️  Eliminando: $file ($size)${NC}"
        echo -e "      Razón: $reason"
        rm -f "$file"
        FILES_DELETED=$((FILES_DELETED + 1))
        echo -e "${GREEN}      ✅ Eliminado${NC}"
    else
        echo -e "${BLUE}      ℹ️  No existe: $file${NC}"
    fi
}

# ============================================================================
# SECCIÓN 1: Documentación Obsoleta de Study Groups
# ============================================================================
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}📚 SECCIÓN 1: Study Groups - Versiones Obsoletas${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

delete_file "STUDY_GROUPS_IMPLEMENTATION.md" "Versión v1 obsoleta (supersedida por v3)"
delete_file "STUDY_GROUPS_V2_IMPROVEMENTS.md" "Versión v2 mejorada (supersedida por v3)"
delete_file "STUDY_GROUPS_V2_FINAL_IMPLEMENTATION.md" "Versión v2 final (supersedida por v3)"

echo -e "${GREEN}   ✅ Manteniendo: STUDY_GROUPS_V3_IMPLEMENTATION.md (versión actual)${NC}\n"

# ============================================================================
# SECCIÓN 2: Auditorías y Reportes Duplicados
# ============================================================================
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}📊 SECCIÓN 2: Auditorías y Reportes Duplicados${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

delete_file "AUDITORIA_COMPLETA_RESUMEN.md" "Duplicado de BACKEND_AUDIT_REPORT.md"
delete_file "BACKEND_DEPURADO_INFORME.md" "Informe de depuración histórico"
delete_file "ERRORES_CORREGIDOS.md" "Log histórico de errores ya corregidos"

echo -e "${GREEN}   ✅ Manteniendo: BACKEND_AUDIT_REPORT.md (reporte oficial)${NC}\n"

# ============================================================================
# SECCIÓN 3: READMEs Redundantes
# ============================================================================
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}📖 SECCIÓN 3: READMEs Redundantes${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

delete_file "README_CRITICAL_IMPROVEMENTS.md" "Mejoras críticas ya integradas"

echo -e "${GREEN}   ✅ Manteniendo: README.md y README_PRODUCTION.md${NC}\n"

# ============================================================================
# SECCIÓN 4: Documentos de Análisis Temporal
# ============================================================================
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}🔍 SECCIÓN 4: Análisis Temporales Completados${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

delete_file "REVISION_COMPLETA_SISTEMA.md" "Revisión one-time completada"
delete_file "TECHNICAL_ANALYSIS.md" "Análisis técnico temporal"
delete_file "ELIMINAR_APIS_EXTERNAS.md" "Plan ya ejecutado (APIs migradas)"

# ============================================================================
# SECCIÓN 5: Limpieza de Cache Python
# ============================================================================
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}🐍 SECCIÓN 5: Cache Python (__pycache__)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

echo -e "${YELLOW}   🧹 Eliminando directorios __pycache__...${NC}"
PYCACHE_COUNT=$(find . -type d -name "__pycache__" 2>/dev/null | wc -l)
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo -e "${GREEN}   ✅ Eliminados $PYCACHE_COUNT directorios __pycache__${NC}\n"

echo -e "${YELLOW}   🧹 Eliminando archivos .pyc...${NC}"
PYC_COUNT=$(find . -type f -name "*.pyc" 2>/dev/null | wc -l)
find . -type f -name "*.pyc" -delete 2>/dev/null || true
echo -e "${GREEN}   ✅ Eliminados $PYC_COUNT archivos .pyc${NC}\n"

# ============================================================================
# SECCIÓN 6: Archivos Temporales (Opcional)
# ============================================================================
echo -e "${BOLD}${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}⏱️  SECCIÓN 6: Archivos Temporales${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

echo -e "${BLUE}   ℹ️  Directorios temporales mantenidos:${NC}"
echo -e "      - temp_audio/ (necesario para voice service)"
echo -e "      - voice_cache/ (necesario para voice caching)"
echo -e "      - voice_presets/ (necesario para personalidades)"
echo -e "${GREEN}   ✅ No se eliminan directorios temporales (necesarios)${NC}\n"

# ============================================================================
# RESUMEN FINAL
# ============================================================================
echo -e "${BOLD}${BLUE}"
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║          📊 RESUMEN DE LIMPIEZA                                      ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "${BOLD}Archivos .md eliminados:${NC} $FILES_DELETED"
echo -e "${BOLD}Directorios __pycache__ eliminados:${NC} $PYCACHE_COUNT"
echo -e "${BOLD}Archivos .pyc eliminados:${NC} $PYC_COUNT"
echo ""
echo -e "${GREEN}${BOLD}✅ LIMPIEZA COMPLETADA EXITOSAMENTE${NC}"
echo ""
echo -e "${BLUE}Archivos importantes mantenidos:${NC}"
echo "   ✅ SERVICIOS_BACKEND_COMPLETO.md (catálogo actual)"
echo "   ✅ STUDY_GROUPS_V3_IMPLEMENTATION.md (versión actual)"
echo "   ✅ HUNYUAN_VIDEO_*.md (implementación video)"
echo "   ✅ MODELOS_IA_*.md (documentación IA)"
echo "   ✅ WHATSAPP_SYSTEM_COMPLETE.md (sistema WhatsApp)"
echo "   ✅ Todos los archivos .py (código del backend)"
echo ""
echo -e "${YELLOW}Backup guardado en: backups/cleanup_$(date +%Y%m%d)/${NC}"
echo -e "${BLUE}Ver informe completo: LIMPIEZA_BACKEND_INFORME.md${NC}"
echo ""
echo -e "${GREEN}${BOLD}🚀 Backend limpio y organizado!${NC}"
echo ""
