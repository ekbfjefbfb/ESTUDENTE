#!/bin/bash

###############################################################################
# SCRIPT DE DEPLOYMENT AUTOMÁTICO PARA HYPERSTACK
# Backend SaaS IA - Versión 5.0 Production
# Uso: ./deploy_hyperstack.sh
###############################################################################

set -e  # Exit on error

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Funciones de utilidad
print_header() {
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${NC}  $1"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════════════════════════╝${NC}"
}

print_info() {
    echo -e "${BLUE}➜${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

check_command() {
    if ! command -v $1 &> /dev/null; then
        print_error "$1 no está instalado"
        return 1
    fi
    print_success "$1 está instalado"
    return 0
}

# Verificar que estamos en la carpeta correcta
if [ ! -f "main.py" ]; then
    print_error "Este script debe ejecutarse desde la raíz del proyecto (donde está main.py)"
    exit 1
fi

print_header "DEPLOYMENT AUTOMÁTICO - HYPERSTACK"

# =====================================================
# 1. VERIFICAR SISTEMA
# =====================================================
print_header "1. Verificando Sistema"

# Verificar OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    print_info "OS: $NAME $VERSION"
else
    print_error "No se pudo detectar el sistema operativo"
    exit 1
fi

# Verificar GPUs NVIDIA
print_info "Verificando GPUs NVIDIA..."
if ! command -v nvidia-smi &> /dev/null; then
    print_warning "nvidia-smi no encontrado. ¿Tienes GPUs NVIDIA?"
else
    GPU_COUNT=$(nvidia-smi --query-gpu=name --format=csv,noheader | wc -l)
    print_success "Detectadas $GPU_COUNT GPU(s) NVIDIA"
    nvidia-smi --query-gpu=name,memory.total --format=csv
fi

# =====================================================
# 2. INSTALAR DEPENDENCIAS DEL SISTEMA
# =====================================================
print_header "2. Instalando Dependencias del Sistema"

print_info "Actualizando repositorios..."
sudo apt update

print_info "Instalando Python 3.11..."
sudo add-apt-repository ppa:deadsnakes/ppa -y || true
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

print_info "Instalando PostgreSQL..."
sudo apt install -y postgresql postgresql-contrib

print_info "Instalando Redis..."
sudo apt install -y redis-server

print_info "Instalando Nginx..."
sudo apt install -y nginx

print_info "Instalando herramientas de compilación..."
sudo apt install -y build-essential git curl wget

print_info "Instalando Supervisor..."
sudo apt install -y supervisor

print_info "Instalando Certbot (SSL)..."
sudo apt install -y certbot python3-certbot-nginx

print_success "Dependencias del sistema instaladas"

# =====================================================
# 3. CONFIGURAR POSTGRESQL
# =====================================================
print_header "3. Configurando PostgreSQL"

# Verificar si la base de datos ya existe
if sudo -u postgres psql -lqt | cut -d \| -f 1 | grep -qw saas_db; then
    print_warning "Base de datos 'saas_db' ya existe. Omitiendo creación..."
else
    print_info "Creando base de datos..."
    sudo -u postgres psql << EOF
CREATE DATABASE saas_db;
CREATE USER saas_user WITH PASSWORD 'change_me_in_production';
GRANT ALL PRIVILEGES ON DATABASE saas_db TO saas_user;
ALTER USER saas_user CREATEDB;
EOF
    print_success "Base de datos creada"
    print_warning "⚠️  IMPORTANTE: Cambia la contraseña de PostgreSQL en producción!"
fi

# =====================================================
# 4. CONFIGURAR REDIS
# =====================================================
print_header "4. Configurando Redis"

sudo systemctl enable redis-server
sudo systemctl start redis-server

if redis-cli ping | grep -q PONG; then
    print_success "Redis está funcionando correctamente"
else
    print_error "Redis no está respondiendo"
    exit 1
fi

# =====================================================
# 5. CREAR ESTRUCTURA DE DIRECTORIOS
# =====================================================
print_header "5. Creando Estructura de Directorios"

# Directorio principal de la aplicación
APP_DIR="/opt/saas-backend"
print_info "Directorio de aplicación: $APP_DIR"

if [ ! -d "$APP_DIR" ]; then
    sudo mkdir -p "$APP_DIR"
    sudo chown $USER:$USER "$APP_DIR"
    print_success "Directorio creado: $APP_DIR"
else
    print_info "Directorio ya existe: $APP_DIR"
fi

# Directorios de modelos
print_info "Creando directorios para modelos IA..."
mkdir -p "$APP_DIR/models"/{qwen,whisper,coqui,sdxl,hunyuan}

# Directorios de logs
print_info "Creando directorios de logs..."
sudo mkdir -p /var/log/saas-backend /var/log/celery
sudo chown $USER:$USER /var/log/saas-backend /var/log/celery

# Directorios de cache
mkdir -p "$APP_DIR/cache" "$APP_DIR/temp_audio" "$APP_DIR/voice_cache"

print_success "Estructura de directorios creada"

# =====================================================
# 6. COPIAR ARCHIVOS DE LA APLICACIÓN
# =====================================================
print_header "6. Copiando Archivos de la Aplicación"

print_info "Copiando archivos al directorio de producción..."
rsync -av --progress \
    --exclude 'venv' \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '.git' \
    --exclude 'node_modules' \
    --exclude '.env' \
    ./ "$APP_DIR/"

print_success "Archivos copiados"

# =====================================================
# 7. CREAR VIRTUAL ENVIRONMENT E INSTALAR DEPENDENCIAS
# =====================================================
print_header "7. Configurando Virtual Environment"

cd "$APP_DIR"

if [ ! -d "venv" ]; then
    print_info "Creando virtual environment..."
    python3.11 -m venv venv
    print_success "Virtual environment creado"
else
    print_info "Virtual environment ya existe"
fi

print_info "Activando virtual environment e instalando dependencias..."
source venv/bin/activate

print_info "Actualizando pip..."
pip install --upgrade pip

print_info "Instalando requirements.txt..."
pip install -r requirements.txt

print_success "Dependencias instaladas"

# =====================================================
# 8. CONFIGURAR VARIABLES DE ENTORNO
# =====================================================
print_header "8. Configurando Variables de Entorno"

if [ ! -f ".env" ]; then
    print_info "Creando archivo .env..."
    cat > .env << 'EOF'
# ====================================
# PRODUCTION ENVIRONMENT VARIABLES
# ====================================

# ---- BASIC CONFIGURATION ----
ENV=production
DEBUG=False
LOG_LEVEL=info
API_VERSION=v1

# ---- SERVER ----
HOST=0.0.0.0
PORT=8000
WORKERS=4

# ---- DATABASE ----
DATABASE_URL=postgresql+asyncpg://saas_user:change_me_in_production@localhost:5432/saas_db
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=10

# ---- REDIS ----
REDIS_URL=redis://localhost:6379/0
REDIS_MAX_CONNECTIONS=50

# ---- JWT SECRETS ----
SECRET_KEY=CHANGE_THIS_TO_A_RANDOM_32_CHAR_STRING
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# ---- CORS ----
CORS_ORIGINS=["http://localhost:3000"]
CORS_CREDENTIALS=True

# ---- GPU CONFIGURATION ----
CUDA_VISIBLE_DEVICES=0,1,2,3
PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# ---- AI MODELS PATHS ----
QWEN_MODEL_PATH=./models/qwen
WHISPER_MODEL_PATH=./models/whisper
COQUI_MODEL_PATH=./models/coqui
SDXL_MODEL_PATH=./models/sdxl
HUNYUAN_MODEL_PATH=./models/hunyuan

# ---- PAYMENT GATEWAYS ----
# IMPORTANTE: Agregar tus claves reales aquí
STRIPE_SECRET_KEY=
STRIPE_PUBLISHABLE_KEY=
STRIPE_WEBHOOK_SECRET=

PAYPAL_CLIENT_ID=
PAYPAL_CLIENT_SECRET=
PAYPAL_MODE=sandbox

MERCADOPAGO_ACCESS_TOKEN=
MERCADOPAGO_PUBLIC_KEY=

# ---- EXTERNAL APIS ----
OPENAI_API_KEY=
PERPLEXITY_API_KEY=
ELEVENLABS_API_KEY=

# ---- GOOGLE WORKSPACE ----
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=

# ---- TWILIO ----
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# ---- SLACK ----
SLACK_CLIENT_ID=
SLACK_CLIENT_SECRET=
SLACK_SIGNING_SECRET=

# ---- GITHUB ----
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=

# ---- FIREBASE ----
FIREBASE_CREDENTIALS_PATH=./config/firebase-adminsdk.json
FIREBASE_PROJECT_ID=

# ---- SENTRY ----
SENTRY_DSN=
SENTRY_ENVIRONMENT=production

# ---- CELERY ----
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ---- STORAGE ----
STORAGE_BACKEND=local
S3_BUCKET_NAME=
S3_REGION=
S3_ACCESS_KEY=
S3_SECRET_KEY=

# ---- EMAIL ----
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=

EOF
    print_success "Archivo .env creado"
    print_warning "⚠️  IMPORTANTE: Edita /opt/saas-backend/.env con tus claves reales!"
else
    print_info "Archivo .env ya existe"
fi

# =====================================================
# 9. EJECUTAR MIGRACIONES DE BASE DE DATOS
# =====================================================
print_header "9. Ejecutando Migraciones de Base de Datos"

if [ -f "alembic.ini" ]; then
    print_info "Ejecutando migraciones con Alembic..."
    source venv/bin/activate
    alembic upgrade head || print_warning "Alembic falló, puede ser que no haya migraciones"
    print_success "Migraciones ejecutadas"
else
    print_warning "No se encontró alembic.ini, omitiendo migraciones"
fi

# =====================================================
# 10. CONFIGURAR SUPERVISOR
# =====================================================
print_header "10. Configurando Supervisor"

print_info "Creando configuración de Supervisor..."
sudo tee /etc/supervisor/conf.d/saas-backend.conf > /dev/null << EOF
[program:saas-backend]
directory=$APP_DIR
command=$APP_DIR/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
user=$USER
autostart=true
autorestart=true
stderr_logfile=/var/log/saas-backend/err.log
stdout_logfile=/var/log/saas-backend/out.log
environment=
    PATH="$APP_DIR/venv/bin",
    CUDA_VISIBLE_DEVICES="0,1,2,3",
    PYTORCH_CUDA_ALLOC_CONF="max_split_size_mb:512"

[program:celery-worker]
directory=$APP_DIR
command=$APP_DIR/venv/bin/celery -A celery_config worker --loglevel=info
user=$USER
autostart=true
autorestart=true
stderr_logfile=/var/log/celery/worker_err.log
stdout_logfile=/var/log/celery/worker_out.log

[program:celery-beat]
directory=$APP_DIR
command=$APP_DIR/venv/bin/celery -A celery_config beat --loglevel=info
user=$USER
autostart=true
autorestart=true
stderr_logfile=/var/log/celery/beat_err.log
stdout_logfile=/var/log/celery/beat_out.log
EOF

print_info "Recargando configuración de Supervisor..."
sudo supervisorctl reread
sudo supervisorctl update

print_info "Iniciando servicios..."
sudo supervisorctl start saas-backend celery-worker celery-beat

print_success "Supervisor configurado"

# =====================================================
# 11. CONFIGURAR NGINX
# =====================================================
print_header "11. Configurando Nginx"

# Solicitar dominio
read -p "Ingresa tu dominio (ej: api.tudominio.com) o presiona Enter para omitir: " DOMAIN

if [ -z "$DOMAIN" ]; then
    print_warning "Sin dominio. Configurando Nginx solo para localhost..."
    DOMAIN="localhost"
fi

print_info "Creando configuración de Nginx para $DOMAIN..."
sudo tee /etc/nginx/sites-available/saas-backend > /dev/null << EOF
upstream backend {
    server 127.0.0.1:8000;
}

server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 100M;

    location / {
        proxy_pass http://backend;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # Timeouts para operaciones IA
        proxy_connect_timeout 600s;
        proxy_send_timeout 600s;
        proxy_read_timeout 600s;
    }

    # WebSocket support
    location /ws/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_read_timeout 86400;
    }

    location /health {
        access_log off;
        proxy_pass http://backend;
    }
}
EOF

print_info "Habilitando sitio en Nginx..."
sudo ln -sf /etc/nginx/sites-available/saas-backend /etc/nginx/sites-enabled/

print_info "Eliminando configuración default si existe..."
sudo rm -f /etc/nginx/sites-enabled/default

print_info "Verificando configuración de Nginx..."
sudo nginx -t

print_info "Recargando Nginx..."
sudo systemctl reload nginx

print_success "Nginx configurado"

# Configurar SSL si hay dominio válido
if [ "$DOMAIN" != "localhost" ]; then
    read -p "¿Deseas configurar SSL con Let's Encrypt? (s/n): " SETUP_SSL
    if [ "$SETUP_SSL" = "s" ] || [ "$SETUP_SSL" = "S" ]; then
        print_info "Configurando SSL..."
        sudo certbot --nginx -d $DOMAIN
        print_success "SSL configurado"
    fi
fi

# =====================================================
# 12. VERIFICACIÓN FINAL
# =====================================================
print_header "12. Verificación Final"

print_info "Esperando que el backend inicie..."
sleep 10

# Verificar estado de servicios
print_info "Estado de servicios:"
sudo supervisorctl status

# Health check
print_info "Realizando health check..."
if [ "$DOMAIN" = "localhost" ]; then
    HEALTH_URL="http://localhost"
else
    HEALTH_URL="http://$DOMAIN"
fi

if curl -f -s "$HEALTH_URL/health" > /dev/null 2>&1; then
    print_success "Health check OK"
else
    print_warning "Health check falló. Verifica los logs:"
    print_info "  sudo tail -f /var/log/saas-backend/err.log"
fi

# Verificar GPUs
if command -v nvidia-smi &> /dev/null; then
    print_info "Estado de GPUs:"
    nvidia-smi --query-gpu=index,name,memory.used,memory.total --format=csv
fi

# =====================================================
# RESUMEN FINAL
# =====================================================
print_header "✅ DEPLOYMENT COMPLETADO"

cat << EOF

╔══════════════════════════════════════════════════════════════════════════════╗
║                          🎉 DEPLOYMENT EXITOSO 🎉                           ║
╚══════════════════════════════════════════════════════════════════════════════╝

📍 INFORMACIÓN DEL DEPLOYMENT:

   • Backend: $APP_DIR
   • URL: $HEALTH_URL
   • API Docs: $HEALTH_URL/docs
   • Logs: /var/log/saas-backend/

🔧 COMANDOS ÚTILES:

   # Ver logs en tiempo real
   sudo tail -f /var/log/saas-backend/out.log

   # Ver errores
   sudo tail -f /var/log/saas-backend/err.log

   # Reiniciar backend
   sudo supervisorctl restart saas-backend

   # Ver estado de servicios
   sudo supervisorctl status

   # Monitorear GPUs
   watch -n 1 nvidia-smi

⚠️  PRÓXIMOS PASOS IMPORTANTES:

   1. Edita las variables de entorno:
      sudo nano $APP_DIR/.env

   2. Cambia la contraseña de PostgreSQL:
      sudo -u postgres psql
      ALTER USER saas_user PASSWORD 'nueva_password_segura';

   3. Configura las claves API de producción en .env

   4. Verifica que todos los endpoints funcionen:
      curl $HEALTH_URL/docs

   5. Configura monitoreo (Sentry, Prometheus, etc)

   6. Configura backups automáticos

📚 DOCUMENTACIÓN:

   • Guía completa: $APP_DIR/PRODUCCION_HYPERSTACK_GUIA_COMPLETA.md
   • Todos los endpoints: $APP_DIR/README.md
   • Troubleshooting: Ver sección en guía completa

╚══════════════════════════════════════════════════════════════════════════════╝

EOF

print_success "Deployment completado exitosamente! 🚀"
