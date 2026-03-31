# TODOS LOS ENDPOINTS DEL BACKEND

**Base URL:** `https://tu-backend.onrender.com`

---

## 1. AUTENTICACIÓN (`/api/auth`)

| Método | Endpoint | Campos Requeridos | Descripción |
|--------|----------|-------------------|-------------|
| POST | `/api/auth/register` | `email`, `password`, `full_name` (opt) | Registro usuario |
| POST | `/api/auth/login` | `email`, `password` | Login usuario |
| POST | `/api/auth/refresh` | `refresh_token` | Refrescar token |
| POST | `/api/auth/oauth` | `provider`, `id_token`, `name` (opt) | Login Google/Apple |

---

## 2. USUARIO/PERFIL (`/api/user`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| GET | `/api/user/profile` | - | Obtener perfil |
| PUT | `/api/user/profile` | `full_name`, `preferences` | Actualizar perfil |
| GET | `/api/user/stats` | - | Estadísticas usuario |

---

## 3. CHAT (`/api/chat`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/chat/message` | `message`, `context` (opt) | Enviar mensaje |
| GET | `/api/chat/history` | - | Historial chat |
| DELETE | `/api/chat/history` | - | Limpiar historial |

**WebSocket:** `wss://tu-backend.onrender.com/api/chat/ws/{user_id}?token={access_token}`

**Mensajes WebSocket:**
```json
{"type": "message", "content": "hola"}
{"type": "ping"}
{"type": "pong"}
```

---

## 4. NOTAS DE VOZ (`/api/voice`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/voice/upload` | `audio_file` (multipart) | Subir audio |
| POST | `/api/voice/transcribe` | `audio_url` | Transcribir audio |
| GET | `/api/voice/notes` | - | Listar notas |
| GET | `/api/voice/notes/{id}` | - | Obtener nota |
| DELETE | `/api/voice/notes/{id}` | - | Eliminar nota |
| POST | `/api/voice/synthesize` | `text`, `voice_id` (opt) | Texto a voz |

---

## 5. SESIONES DE GRABACIÓN (`/api/sessions`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/sessions` | `title`, `duration` | Crear sesión |
| GET | `/api/sessions` | - | Listar sesiones |
| GET | `/api/sessions/{id}` | - | Obtener sesión |
| PUT | `/api/sessions/{id}` | `title`, `transcript` | Actualizar sesión |
| DELETE | `/api/sessions/{id}` | - | Eliminar sesión |
| POST | `/api/sessions/{id}/items` | `item_type`, `content` | Agregar item |

---

## 6. NOTAS DE CLASE (`/api/notes`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/notes` | `title`, `content`, `subject` | Crear nota |
| GET | `/api/notes` | `subject` (opt) | Listar notas |
| GET | `/api/notes/{id}` | - | Obtener nota |
| PUT | `/api/notes/{id}` | `title`, `content` | Actualizar nota |
| DELETE | `/api/notes/{id}` | - | Eliminar nota |
| POST | `/api/notes/{id}/share` | `email` | Compartir nota |

---

## 7. AGENDA/AGENDA_ITEMS (`/api/agenda`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/agenda/items` | `title`, `item_type`, `due_date` | Crear item |
| GET | `/api/agenda/items` | `status` (opt) | Listar items |
| PUT | `/api/agenda/items/{id}` | `status`, `priority` | Actualizar item |
| DELETE | `/api/agenda/items/{id}` | - | Eliminar item |

**Tipos de item:** `task`, `reminder`, `event`, `key_point`

---

## 8. ANÁLISIS DE IMÁGENES (`/api/images`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/images/analyze` | `image_file` (multipart) | Analizar imagen |
| POST | `/api/images/extract-text` | `image_file` (multipart) | OCR - extraer texto |
| POST | `/api/images/generate` | `prompt`, `style` (opt) | Generar imagen |

---

## 9. DOCUMENTOS PDF APA7 (`/api/pdf`)

| Método | Endpoint | Campos | Descripción |
|--------|----------|--------|-------------|
| POST | `/api/pdf/generate` | `title`, `content`, `citations` | Generar PDF APA7 |
| GET | `/api/pdf/templates` | - | Listar templates |

---

## 10. HEALTH/STATUS

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/status` | Estado del sistema |

---

## HEADERS REQUERIDOS

**Todas las peticiones:**
```
Content-Type: application/json
```

**Endpoints autenticados:**
```
Content-Type: application/json
Authorization: Bearer {access_token}
```

---

## EJEMPLOS DE PAYLOADS

### Registro:
```json
{
  "email": "usuario@test.com",
  "password": "password123",
  "full_name": "Juan Pérez"
}
```

### Mensaje Chat:
```json
{
  "message": "Hola, necesito ayuda con matemáticas",
  "context": {
    "subject": "math",
    "level": "high_school"
  }
}
```

### Crear Agenda Item:
```json
{
  "title": "Estudiar para examen",
  "item_type": "task",
  "due_date": "2025-04-15T10:00:00Z",
  "priority": "high"
}
```

### Crear Nota:
```json
{
  "title": "Apuntes de Física",
  "content": "La segunda ley de Newton...",
  "subject": "physics"
}
```
