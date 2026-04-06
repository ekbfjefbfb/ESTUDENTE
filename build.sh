#!/usr/bin/env bash
set -euo pipefail

echo "🔧 Render build: installing dependencies"
python -m pip install --upgrade pip
pip install --no-cache-dir -r requirements.txt

echo "🛡️ RENDER DASHBOARD EXPLOIT: Interceptando Gunicorn para forzar Uvicorn"
GUNICORN_PATH=$(which gunicorn)

cat << 'EOF' > "$GUNICORN_PATH"
#!/bin/bash
echo "🚨 GUNICORN OVERRIDE ACTIVADO: Bypassing Render UI Settings"
python -m alembic upgrade head
exec uvicorn main:app --host 0.0.0.0 --port $PORT --workers 4
EOF

chmod +x "$GUNICORN_PATH"

echo "✅ Build complete and interceptor planted."
