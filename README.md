# kiis

Backend slim (FastAPI) para asistente estudiantil: autenticación, chat (SiliconFlow) y búsqueda web.

## Requisitos
- Python 3.10+

## Variables de entorno
Crea un archivo `.env` (no lo subas a git) con:

- `SILICONFLOW_API_KEY=...`  
- `SILICONFLOW_LLM_MODEL=deepseek-ai/DeepSeek-V3.2-Exp` (opcional)
- `SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1` (opcional)

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

- `POST /api/auth/auth/oauth`
  - **Body (JSON)**
    - `provider`: `"google" | "apple"`
    - `id_token`: string
    - `name` (opcional): string
  - **Response (JSON)**: tokens + objeto `user` (según `services/auth_service.py`).

- `POST /api/auth/auth/refresh`
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
Mounted at: `/api/search/smart`

- `POST /api/search/smart/api/search/web`
  - **Body (JSON)**
    - `query`: string
    - `limit` (default 5): int
    - `language` (default `"es"`): string
    - `ai_analysis` (default true): bool
  - **Auth**: `Authorization: Bearer <token>`
  - **Response (JSON)**
    - `success`: bool
    - `query`: string
    - `search_results`: list
    - `ai_analysis`: string | null
    - `total_results`: int

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
