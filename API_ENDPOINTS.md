# 📚 ENDPOINTS API - ESTUDENTE Backend

Base URL: `https://estudente.onrender.com/api/unified-chat`

---

## 🎙️ 1. SPEECH-TO-TEXT (STT)
Convierte audio a texto usando Groq Whisper.

**Endpoint:** `POST /stt`  
**Content-Type:** `multipart/form-data`

### Campos de Entrada:
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `audio` | File | ✅ | Archivo de audio (mp3, wav, webm, ogg) |
| `language` | string | ❌ | Código de idioma (default: "es") |

### Respuesta (STTResponse):
```json
{
  "success": true,
  "text": "Hola necesito ayuda con mi tarea",
  "language": "es",
  "duration_ms": 2450,
  "timestamp": "2026-03-12T00:45:00.000000"
}
```

---

## 🔊 2. TEXT-TO-SPEECH (TTS)
Convierte texto a audio usando Groq TTS o ElevenLabs.

**Endpoint:** `POST /tts`  
**Content-Type:** `application/json`

### Campos de Entrada:
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `text` | string | ✅ | Texto a convertir (max 5000 chars) |
| `voice` | string | ❌ | ID de voz (default: "hannah") |
| `speed` | float | ❌ | Velocidad 0.5-2.0 (default: 1.0) |
| `language` | string | ❌ | "es" o "en" (default: "es") |

### Voces disponibles (Groq):
- `autumn`, `diana`, `hannah`, `austin`, `daniel`, `troy`

### Respuesta (TTSResponse):
```json
{
  "success": true,
  "audio": "data:audio/mpeg;base64,//uQxAAAAAA...",
  "text": "Hola estudiante",
  "voice": "hannah",
  "timestamp": "2026-03-12T00:45:00.000000"
}
```

---

## 💬 3. CHAT CON IA (JSON)
Chat con contexto estructurado, tareas y plan de estudio.

**Endpoint:** `POST /message/json`  
**Content-Type:** `application/json`

### Campos de Entrada:
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `message` | string | ✅ | Mensaje del usuario |
| `files` | array[string] | ❌ | URLs de archivos adjuntos |
| `session_id` | string | ❌ | ID de sesión para continuar conversación |

### Respuesta (ChatResponse):
```json
{
  "success": true,
  "response": "✅ Tarea agendada. 📚 Revisar capítulo 3 para el viernes.",
  "user_id": "8e0a2830-aac7-47f9-a31e-ea7dc898760b",
  "timestamp": "2026-03-12T00:45:00.000000",
  "context": {
    "usage_percent": 45.2,
    "messages_count": 12,
    "last_check": "2026-03-12T00:30:00.000000",
    "cache_hit": false
  },
  "message_id": "msg_1234567890",
  "actions": [
    {
      "type": "schedule_class",
      "data": {
        "title": "Clase de Cálculo",
        "start_time": "2026-03-15T08:00:00",
        "recording": true,
        "recurring": "weekly"
      }
    }
  ]
}
```

---

## 🎤 4. CHAT POR VOZ (HTTP)
Flujo completo: Audio → STT → IA → TTS.

**Endpoint:** `POST /voice/message`  
**Content-Type:** `multipart/form-data`

### Campos de Entrada:
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| `audio` | File | ✅ | Audio del usuario |
| `language` | string | ❌ | Idioma (default: "es") |
| `voice` | string | ❌ | Voz para respuesta TTS |

### Respuesta (VoiceChatResponse):
```json
{
  "success": true,
  "transcribed": "Agenda mi clase de mañana",
  "response": "✅ Clase agendada 8am. Grabación ON.",
  "audio": "data:audio/mpeg;base64,//uQxAAAAAA...",
  "user_id": "8e0a2830-aac7-47f9-a31e-ea7dc898760b",
  "timestamp": "2026-03-12T00:45:00.000000",
  "message_id": "voice_1234567890"
}
```

---

## 📝 5. PROGRESO DEL USUARIO

### Obtener progreso:
**Endpoint:** `GET /progress`

### Respuesta:
```json
{
  "success": true,
  "today_tasks": [
    {"title": "Revisar notas", "due_date": "2026-03-12", "priority": "high"}
  ],
  "week_tasks": [...],
  "completed_tasks": [...],
  "last_plan": [...],
  "last_interaction": "2026-03-12T00:30:00.000000"
}
```

### Completar tarea:
**Endpoint:** `POST /progress/complete/{task_id}`

### Guardar plan:
**Endpoint:** `POST /progress/plan`  
**Body:** `[{"step": "Leer capítulo 3", "duration": "30 min"}, ...]`

---

## 🔄 WEBSOCKETS

### Chat en tiempo real:
**URL:** `wss://estudente.onrender.com/unified-chat/ws/{user_id}?token={JWT}`

### Grabación de voz (streaming STT):
**URL:** `wss://estudente.onrender.com/unified-chat/voice/ws?token={JWT}`

---

## 📋 ESQUEMAS DE DATOS (Schemas)

### STTRequest:
```python
{
  "language": "es"  # Opcional
}
```

### TTSRequest:
```python
{
  "text": "string",        # Requerido, max 5000 chars
  "voice": "hannah",       # Opcional
  "speed": 1.0,            # Opcional, 0.5-2.0
  "language": "es"         # Opcional
}
```

### ChatMessageRequest:
```python
{
  "message": "string",     # Requerido
  "files": ["url1", "url2"],  # Opcional
  "session_id": "string"   # Opcional
}
```

---

## 🔐 AUTENTICACIÓN

Todos los endpoints (excepto health/info) requieren **JWT Token** en header:

```
Authorization: Bearer <token>
```

O en WebSocket como query param:
```
?token=<JWT>
```

---

## ⚡ LÍMITES Y RATE LIMITING

- **STT:** Máximo 10MB de audio por request
- **TTS:** Máximo 5000 caracteres
- **Chat:** Rate limit por plan (50-ilimitado requests/mes)
- **WebSocket:** Auto-reconexión con backoff exponencial

---

## 🎯 EJEMPLOS DE USO

### cURL - STT:
```bash
curl -X POST https://estudente.onrender.com/api/unified-chat/stt \
  -H "Authorization: Bearer $TOKEN" \
  -F "audio=@grabacion.mp3" \
  -F "language=es"
```

### cURL - TTS:
```bash
curl -X POST https://estudente.onrender.com/api/unified-chat/tts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"text": "Hola estudiante", "voice": "hannah"}'
```

### cURL - Chat:
```bash
curl -X POST https://estudente.onrender.com/api/unified-chat/message/json \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"message": "Agenda mi clase de mañana 8am"}'
```

### JavaScript - WebSocket Chat:
```javascript
const ws = new WebSocket(
  'wss://estudente.onrender.com/unified-chat/ws/USER_ID?token=JWT'
);

ws.onopen = () => {
  ws.send(JSON.stringify({
    message: "Necesito ayuda con cálculo",
    session_id: null
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('IA:', data.response);
};
```

---

**Nota:** Todos los campos `timestamp` están en formato ISO 8601 UTC.
