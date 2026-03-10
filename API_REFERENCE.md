# API Reference - Backend Súper IA v5.0
## Guía completa para conectar el Frontend

---

## 🌐 Base URL

```
Production: https://estudente.onrender.com
Local:      http://localhost:8000
```

**Prefix API:** `/api`

---

## 🔐 Autenticación

Todos los endpoints (excepto login/register/health) requieren:

```http
Authorization: Bearer <jwt_token>
```

### Obtener Token

**POST** `/api/auth/login`

```json
{
  "email": "usuario@email.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "user": {
    "id": "uuid",
    "email": "usuario@email.com",
    "full_name": "Nombre Usuario"
  }
}
```

---

## 🤖 Chat IA (Unified Chat)

Base: `/api/unified-chat`

### Recomendado (baja latencia): WebSockets

- **Texto (WS)**: `wss://estudente.onrender.com/api/unified-chat/ws/{user_id}?token=<jwt_token>`
- **Voz streaming (WS)**: `wss://estudente.onrender.com/api/unified-chat/voice/ws?token=<jwt_token>`

Los endpoints HTTP se mantienen como fallback, pero para UX “instantánea” el frontend debe usar WS.

### 1. Chat Simple (Form Data)

**POST** `/api/unified-chat/message`

**Content-Type:** `multipart/form-data`

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| message | string | ✅ | Mensaje del usuario |
| files | File[] | ❌ | Archivos adjuntos (opcional) |
| stream | boolean | ❌ | Modo streaming (default: false) |

**Response (200):**
```json
{
  "success": true,
  "response": "¡Hola! Soy tu compañera de estudio...",
  "user_id": "uuid-del-usuario",
  "timestamp": "2026-03-09T20:30:00.000Z",
  "message_id": "msg_1234567890",
  "context": {
    "usage_percent": 45.2,
    "needs_refresh": false,
    "tasks_count": 3,
    "upcoming_tasks_count": 5
  },
  "actions": [
    {
      "type": "tasks",
      "data": [
        {"title": "Estudiar álgebra", "due_date": "2026-03-10", "priority": "high"}
      ]
    },
    {
      "type": "plan",
      "data": [
        {"step": "Repasar conceptos básicos", "duration": "30 min"}
      ]
    }
  ]
}
```

---

### 2. Chat JSON Body

**POST** `/api/unified-chat/message/json`

**Content-Type:** `application/json`

```json
{
  "message": "¿Qué tengo pendiente para hoy?",
  "session_id": "optional-session-id",
  "files": ["base64_encoded_file_1", "base64_encoded_file_2"]
}
```

**Response:** Igual que el endpoint anterior

---

### 3. Chat por Voz (HTTP - Upload Audio)

**POST** `/api/unified-chat/voice/message`

**Content-Type:** `multipart/form-data`

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| audio | File | ✅ | Archivo de audio (mp3, wav, webm, ogg) |
| language | string | ❌ | Idioma (default: "es") |

**Response (200):**
```json
{
  "success": true,
  "transcribed": "Hola, ¿qué tareas tengo para hoy?",
  "response": "Tienes 3 tareas pendientes...",
  "audio": "data:audio/mpeg;base64,//NExAAAAA...",
  "user_id": "uuid-del-usuario",
  "timestamp": "2026-03-09T20:30:00.000Z",
  "message_id": "voice_1234567890"
}
```

---

### 4. Speech-to-Text (STT)

**POST** `/api/unified-chat/stt`

**Content-Type:** `multipart/form-data`

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| audio | File | ✅ | Audio a transcribir |
| language | string | ❌ | Idioma (default: "es") |

**Response:**
```json
{
  "success": true,
  "text": "Texto transcrito del audio",
  "language": "es",
  "duration_ms": 3200,
  "timestamp": "2026-03-09T20:30:00.000Z"
}
```

---

### 5. Text-to-Speech (TTS)

**POST** `/api/unified-chat/tts`

**Content-Type:** `application/json`

```json
{
  "text": "Hola, soy tu asistente académica",
  "voice": "Antoni",
  "speed": 1.0
}
```

| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| text | string | ✅ | Texto a convertir (max 5000 chars) |
| voice | string | ❌ | Voz (default: "Antoni" para español) |
| speed | float | ❌ | Velocidad 0.5-2.0 (default: 1.0) |

**Response:**
```json
{
  "success": true,
  "audio": "data:audio/mpeg;base64,//NExAAAAA...",
  "text": "Hola, soy tu asistente académica",
  "voice": "Antoni",
  "timestamp": "2026-03-09T20:30:00.000Z"
}
```

---

### 6. WebSocket Chat Texto

**WebSocket** `wss://estudente.onrender.com/api/unified-chat/ws/{user_id}?token=<jwt_token>`

**Query Params:**
- `token` (requerido): JWT token

**Importante:** el `user_id` del path debe coincidir con el `sub` del token (si no, cierra con 1008).

**Mensaje de entrada (JSON):**
```json
{
  "message": "Hola, ¿cómo estás?",
  "fast_reasoning": true
}
```

**Mensaje de respuesta (JSON):**
```json
{
  "success": true,
  "response": "¡Hola! Estoy bien, gracias por preguntar...",
  "message_id": "ws_1234567890",
  "context": {
    "needs_refresh": false,
    "auto_refreshed": false
  },
  "timestamp": "2026-03-09T20:30:00.000Z"
}
```

---

### 7. WebSocket Voz (Streaming)

**WebSocket** `wss://tu-app.onrender.com/api/unified-chat/voice/ws`

**Query Params:**
- `token` (requerido): JWT token

**Flujo de mensajes:**

#### 1. Iniciar turno (JSON)
```json
{
  "type": "start",
  "voice": "Antoni",
  "language": "es",
  "vad": true,
  "vad_silence_ms": 900,
  "vad_threshold": 600
}
```

#### 2. Enviar audio chunks (Binary)
- Formato: PCM16 16kHz mono o WebM/Opus
- Máximo: 10MB por turno

#### 3. Finalizar turno (JSON)
```json
{
  "type": "end"
}
```

**Respuestas del servidor (JSON):**

```json
// Transcripción parcial
{
  "type": "partial",
  "text": "Hola, qué tengo...",
  "ts": "2026-03-09T20:30:00.000Z"
}

// Transcripción final + respuesta IA + audio
{
  "type": "turn",
  "transcribed": "Hola, ¿qué tareas tengo hoy?",
  "response": "Tienes 3 tareas pendientes...",
  "audio_b64": "//NExAAAAA...",
  "ts": "2026-03-09T20:30:00.000Z"
}

// Error
{
  "type": "error",
  "code": "STT_ERROR",
  "message": "No se pudo transcribir el audio",
  "ts": "2026-03-09T20:30:00.000Z"
}
```

---

### 8. Información del Servicio

**GET** `/api/unified-chat/info`

**Response:**
```json
{
  "service": "unified-chat",
  "version": "5.0",
  "model": "auto",
  "provider": "Groq",
  "features": {
    "text_chat": true,
    "voice_chat": true,
    "websocket": true,
    "context_monitoring": true,
    "auto_context_refresh": true
  },
  "limits": {
    "max_context_tokens": 32000,
    "context_threshold_percent": 85,
    "max_audio_size_mb": 10
  },
  "timestamp": "2026-03-09T20:30:00.000Z"
}
```

---

### 9. Health Check

**GET** `/api/unified-chat/health`

**Response:**
```json
{
  "status": "healthy",
  "service": "unified-chat",
  "version": "5.0",
  "features": ["text", "voice", "websocket", "context_monitoring"],
  "timestamp": "2026-03-09T20:30:00.000Z"
}
```

---

## 📊 Progreso del Usuario

Base: `/api/unified-chat`

### Obtener Progreso

**GET** `/api/unified-chat/progress`

**Response:**
```json
{
  "success": true,
  "today_tasks": [
    {"id": "task_1", "title": "Estudiar matemáticas", "due_date": "2026-03-09"}
  ],
  "week_tasks": [
    {"id": "task_2", "title": "Proyecto de física", "due_date": "2026-03-14"}
  ],
  "completed_tasks": [],
  "last_plan": [
    {"step": "Repasar conceptos", "duration": "30 min"}
  ],
  "last_interaction": "2026-03-09T20:30:00.000Z"
}
```

---

### Completar Tarea

**POST** `/api/unified-chat/progress/complete/{task_id}`

**Response:**
```json
{
  "success": true,
  "message": "Tarea completada"
}
```

---

### Guardar Plan

**POST** `/api/unified-chat/progress/plan`

```json
[
  {"step": "Estudiar capítulo 1", "duration": "45 min"},
  {"step": "Hacer ejercicios", "duration": "30 min"}
]
```

**Response:**
```json
{
  "success": true,
  "message": "Plan guardado"
}
```

---

### Estadísticas

**GET** `/api/unified-chat/progress/stats`

**Response:**
```json
{
  "success": true,
  "stats": {
    "tasks_today": 3,
    "tasks_completed_today": 1,
    "tasks_upcoming": 5,
    "completion_rate": 33.3
  }
}
```

---

## 👤 Autenticación (Auth)

Base: `/api/auth`

### Login Email/Password

**POST** `/api/auth/login`

```json
{
  "email": "usuario@email.com",
  "password": "password123"
}
```

---

### Registro

**POST** `/api/auth/register`

```json
{
  "email": "nuevo@email.com",
  "password": "password123",
  "full_name": "Nuevo Usuario"
}
```

---

### OAuth (Google/Apple)

**POST** `/api/auth/oauth`

```json
{
  "provider": "google",
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "name": "Nombre Usuario"
}
```

---

### Refresh Token

**POST** `/api/auth/refresh`

```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

---

## 📚 Agenda / Clases

Base: `/api/agenda`

### Listar Sesiones

**GET** `/api/agenda/sessions`

**Response:** Lista de sesiones de clase con transcripciones

---

### Crear Sesión

**POST** `/api/agenda/sessions`

```json
{
  "class_name": "Matemáticas Avanzadas",
  "topic": "Derivadas",
  "language": "es"
}
```

---

### Obtener Sesión

**GET** `/api/agenda/sessions/{session_id}`

---

### WebSocket Sesión en Vivo

**WebSocket** `wss://tu-app.onrender.com/api/agenda/ws/{session_id}`

**Query Params:**
- `token`: JWT token

**Eventos:**
- `start`: Iniciar grabación
- `audio_chunk`: Enviar audio (binary)
- `extract_agenda`: Extraer agenda automáticamente
- `ask_ai`: Preguntar a la IA sobre la clase

---

### Resumen de Sesión

**GET** `/api/agenda/sessions/{session_id}/summary`

---

### Eliminar Sesión

**DELETE** `/api/agenda/sessions/{session_id}`

---

## ⚠️ Códigos de Error

| Código HTTP | Error Code | Descripción |
|-------------|------------|-------------|
| 400 | `audio_too_large_max_10mb` | Archivo de audio excede 10MB |
| 400 | `text_empty_or_too_long_max_5000` | Texto vacío o > 5000 caracteres |
| 401 | `UNAUTHORIZED` | Token JWT inválido o faltante |
| 401 | `missing_token` | No se envió token |
| 401 | `invalid_token` | Token JWT malformado |
| 403 | `FORBIDDEN` | Acceso no permitido |
| 404 | `NOT_FOUND` | Recurso no encontrado |
| 429 | `RATE_LIMIT_EXCEEDED` | Límite de requests (100/min) |
| 500 | `CHAT_ERROR` | Error interno del chat |
| 500 | `STT_ERROR` | Error en Speech-to-Text |
| 500 | `TTS_ERROR` | Error en Text-to-Speech |
| 500 | `VOICE_CHAT_ERROR` | Error en chat de voz |
| 500 | `WS_ERROR` | Error en WebSocket |

---

## 📝 Headers Requeridos

### Todos los endpoints (excepto auth/health):

```http
Authorization: Bearer <jwt_token>
Content-Type: application/json
```

### Upload de archivos:

```http
Authorization: Bearer <jwt_token>
Content-Type: multipart/form-data
```

### WebSocket:

```
wss://tu-app.onrender.com/api/unified-chat/ws/{user_id}?token=<jwt_token>
wss://tu-app.onrender.com/api/unified-chat/voice/ws?token=<jwt_token>
```

---

## 🔧 Configuración del Frontend

### Ejemplo de conexión HTTP (fetch):

```javascript
const API_BASE = 'https://tu-app.onrender.com/api';
const token = localStorage.getItem('access_token');

// Chat simple
const response = await fetch(`${API_BASE}/unified-chat/message/json`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    message: "¿Qué tareas tengo hoy?"
  })
});

const data = await response.json();
console.log(data.response); // Respuesta de la IA
```

### Ejemplo WebSocket Chat:

```javascript
const ws = new WebSocket(
  `wss://tu-app.onrender.com/api/unified-chat/ws/${userId}?token=${token}`
);

ws.onopen = () => {
  ws.send(JSON.stringify({
    message: "Hola, ¿cómo estás?",
    fast_reasoning: true
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.response);
};
```

### Ejemplo WebSocket Voz:

```javascript
const ws = new WebSocket(
  `wss://tu-app.onrender.com/api/unified-chat/voice/ws?token=${token}`
);

// Iniciar turno
ws.onopen = () => {
  ws.send(JSON.stringify({
    type: 'start',
    voice: 'Antoni',
    language: 'es',
    vad: true
  }));
};

// Enviar audio desde micrófono
navigator.mediaDevices.getUserMedia({ audio: true })
  .then(stream => {
    const mediaRecorder = new MediaRecorder(stream);
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        ws.send(e.data); // Enviar blob de audio
      }
    };
    mediaRecorder.start(100); // chunks cada 100ms
  });

// Recibir respuestas
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'partial') {
    console.log('Transcribiendo:', data.text);
  } else if (data.type === 'turn') {
    console.log('Respuesta:', data.response);
    // Reproducir audio
    const audio = new Audio(`data:audio/mpeg;base64,${data.audio_b64}`);
    audio.play();
  }
};
```

---

## 📋 Resumen de Endpoints

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login email/password |
| POST | `/api/auth/register` | Registro usuario |
| POST | `/api/auth/oauth` | OAuth Google/Apple |
| POST | `/api/auth/refresh` | Refresh token |
| POST | `/api/unified-chat/message` | Chat (form-data) |
| POST | `/api/unified-chat/message/json` | Chat (JSON) |
| POST | `/api/unified-chat/voice/message` | Chat por voz HTTP |
| POST | `/api/unified-chat/stt` | Speech-to-Text |
| POST | `/api/unified-chat/tts` | Text-to-Speech |
| GET | `/api/unified-chat/info` | Info del servicio |
| GET | `/api/unified-chat/health` | Health check |
| WS | `/api/unified-chat/ws/{user_id}` | WebSocket chat |
| WS | `/api/unified-chat/voice/ws` | WebSocket voz |
| GET | `/api/unified-chat/progress` | Progreso usuario |
| POST | `/api/unified-chat/progress/complete/{id}` | Completar tarea |
| POST | `/api/unified-chat/progress/plan` | Guardar plan |
| GET | `/api/unified-chat/progress/stats` | Estadísticas |
| GET | `/api/agenda/sessions` | Listar sesiones |
| POST | `/api/agenda/sessions` | Crear sesión |
| GET | `/api/agenda/sessions/{id}` | Ver sesión |
| WS | `/api/agenda/ws/{id}` | WebSocket sesión |
| GET | `/api/agenda/sessions/{id}/summary` | Resumen |
| DELETE | `/api/agenda/sessions/{id}` | Eliminar sesión |

---

**Notas:**
- Todos los timestamps están en formato ISO 8601 UTC
- Audio en WebSocket soporta: PCM16 16kHz, WebM/Opus, Ogg/Opus
- TTS en español usa ElevenLabs (voz "Antoni")
- TTS en inglés usa Groq TTS
- Máximo 10MB por archivo de audio
