# kiis

Backend slim (FastAPI) para asistente estudiantil: autenticación, chat (Groq) y búsqueda web.

## Requisitos
- Python 3.10+

## Variables de entorno
Crea un archivo `.env` (no lo subas a git) con:

- `GROQ_API_KEY=...`
- `GROQ_LLM_FAST_MODEL=meta-llama/llama-4-scout-17b-16e-instruct` (opcional)
- `GROQ_LLM_REASONING_MODEL=openai/gpt-oss-120b` (opcional)
- `GROQ_LLM_REASONING_EFFORT=medium` (opcional)

Para búsqueda web (opcional, recomendado):
- `SERPAPI_KEY=...`

Para DB (si usas SQLite por default, no hace falta configurar nada).

## Instalar y correr
```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# Dev
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## Endpoints (HTTP)

### Auth
Base: `/api/auth`

- `POST /api/auth/oauth`
  - **Body (JSON)**
    - `provider`: `"google" | "apple"`
    - `id_token`: string
    - `name` (opcional): string
  - **Response (JSON)**: tokens + objeto `user` (según `services/auth_service.py`).

- `POST /api/auth/refresh`
  - **Body (JSON)**
    - `refresh_token`: string
  - **Response (JSON)**: nuevo `access_token`.

### Chat
Base: `/api/unified-chat`

- `POST /api/unified-chat/message`
  - **Body**
    - `message`: string (query/form)
    - `files` (opcional): multipart
  - **Auth**: `Authorization: Bearer <token>`
  - **Response (JSON)**
    - `success`: bool
    - `response`: string
    - `user_id`: string
    - `timestamp`: ISO string

- `WS /api/unified-chat/ws/{user_id}`
  - **Input**: JSON `{ "message": "..." }`
  - **Output**: texto JSON con respuesta del modelo.

### Búsqueda web
En esta variante slim, no hay un router HTTP dedicado para búsqueda web.
La búsqueda se integra dentro de `POST /api/unified-chat/message` y `POST /api/unified-chat/message/json`.

## Deploy
Este repo incluye `Procfile` para Render/Heroku:
- `web: uvicorn main:app --host 0.0.0.0 --port $PORT --workers 2`

## GitHub (subir repo)
Ejemplo (ajusta tu URL):
```bash
git init
git add .
git commit -m "init"
git branch -M main
git remote add origin git@github.com:ekbfjefbfb/kiis.git
git push -u origin main
```
# Force redeploy 
