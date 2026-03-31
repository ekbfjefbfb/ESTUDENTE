# Auditoría y Refactorización Nivel "Enterprise" (Contexto, Búsqueda, Grabador y Agenda)

Este documento contiene la auditoría completa de la fricción restante en los super-servicios de tu backend y las acciones técnicas "brutales" que necesitamos aplicar para que la IA, las grabaciones y la agenda automatizada se sientan **mágicas e instantáneas**.

## User Review Required

> [!IMPORTANT]
> Lee detalladamente el cuello de botella detectado en el WebSocket de grabación de audio. Si un estudiante habla durante 2 horas continuas en la app, la estructura actual es propensa a congelarse temporalmente. Requiero tu aprobación explícita para transformar el pipeline a un flujo asíncrono no-bloqueante puro.

## Hallazgos de la Auditoría y Fricciones Detectadas

### 1. Cuello de Botella en el Grabador de Clases WebSockets (`recording_session_router.py`)
**El Problema:** Actualmente, cuando el WebSocket recibe ~2 segundos de audio (`32000 bytes`), la conexión pausa su ciclo temporalmente haciendo un `await recording_session_service.process_audio_chunk()`. Si la API de transcripción externa (Groq Whisper) tarda 800ms en responder, el WebSocket se bloquea 800ms. Si el alumno o teléfono envía ráfagas, FastAPI puede saturar las colas de recepción.
**La Solución:** Desacoplar el procesamiento de red. El WebSocket solo se encargará de añadir bytes a una "Cola de Tareas en Memoria" (Asyncio Queue) y una tarea en segundo plano (`background worker`) se encargará de enviarlo a Whisper y guardar en la Base de Datos. El WebSocket emitirá eventos al teléfono de forma paralela y jamás bloqueará el hilo de recepción, garantizando fluidez infinita así el internet de la API esté lento.

### 2. Sincronía Deficiente en la Agenda Inteligente (`scheduled_recording_router.py`)
**El Problema:** La extracción de contexto en `/from-chat` ejecuta una recolección secuencial. El servidor SQL busca clases recientes y el extractor (`chat_intent_extractor.py`) llama a la IA, consumiendo preciosos milisegundos de manera lineal. Además, la búsqueda del endpoint de `/pending` puede generar colisiones de estado si varios pings compiten por bloquear una grabación al mismo tiempo.
**La Solución:** Implementar concurrencia masiva en la inyección de contexto usando `asyncio.gather()` para paralelizar todo DB hit. Usar un bloqueo a nivel de Postgres con `FOR UPDATE SKIP LOCKED` (o `session.refresh`) para el endpoint `/pending` de la agenda, de modo que si el teléfono bombardea la ruta con peticiones asíncronas de "Ping-Location", no iniciemos dos veces la misma clase.

### 3. Fricción en Contexto Continuo de IA (`groq_ai_service.py`)
**El Problema:** Aunque tu estructura de Modelos (20B, 70B, Vision) es exquisita, la inyección del `user_context` (que hace un SELECT de `users` y `agenda_items`) dispara 3 consultas SQL distintas en cascada ("SELECT users", "SELECT agenda_items", "SELECT agenda_sessions") rompiendo el patrón "N+1" para consultas.
**La Solución:** Refactorizar la función `_get_user_personal_context()` combinando las sentencias SQL o paralelizándolas en una única transacción ultra-rápida. Más contexto inyectado en la IA con el doble de velocidad.

### 4. Search Tool Latency en Conversaciones Vivas (`chat_search.py` y Web Search)
**El Problema:** Cuando el LLM decide usar la herramienta de "Web Search", invoca la función, luego nuestro servidor llama a `Tavily` (y un fallback a `Serper` si falla) en hasta ~2-3 segundos combinados. En un streaming directo, esto crea una "pausa cardíaca" notable para el humano. No lo podemos evitar totalmente (es física de redes), pero debemos inyectar un *Heartbeat* estructurado al frontend informando la acción "Status: Searching..." pre-calculado, antes de que el LLM termine el request con el proxy externo.

## Proposed Changes

---

### Módulo de Grabaciones (Class Recorder)
#### [MODIFY] `routers/recording_session_router.py`
- Refactorizaremos el loop temporal del WebSocket `while True` implementando dos hilos de corrutinas (`asyncio.create_task`): uno exclusivo para recibir (Receive Loop) y otro para transcribir y procesar a base de datos (Processor Worker Loop). Esto convertirá el grabador de un servicio "secuencial por pedazos" a un "pipeline asíncrono real".

### Módulo de Contexto y Groq AI
#### [MODIFY] `services/groq_ai_service.py`
- Se optimizará `_get_user_personal_context` reemplazando los 3 comandos SQL asíncronos en serie por un envoltorio de compilación única usando `asyncio.gather(task1, task2, task3)`. Reduciremos la fricción de arranque del motor de razonamiento de ~15ms a ~4ms nativos.

### Módulo de Agenda Automatizada (Automated Scheduler)
#### [MODIFY] `routers/scheduled_recording_router.py`
- Se agregará una optimización en el endpoint `/pending` que llama la app periódicamente. Si detecta una sesión pendiente en progreso, se implementará concurrencia atómica sobre el estado del ORM para evitar fallas o corrupciones de estado cuando el estudiante entre y salga de ubicaciones perimetrales oscilantemente.

## Open Questions

**Feedback del Usuario Requerido:**
1. Sobre el WebSocket de grabación de voz: Cuando enviemos los "pedazos" de audio de forma paralela en background, el orden puede verse ligeramente comprometido si Groq resuelve el Pedazo #2 antes que el #1 por velocidad de red.  Ya existe un `timestamp_seconds` en base de datos. ¿Estás de acuerdo con añadir una cola FIFO estricta que garantice a tu Frontend el orden sin asfixiar la conexión de voz?

## Verification Plan

### Automated Tests
1. Verificación de WS mediante scripts de control Python con bytes basura asegurando la no-bloqueabilidad del socket.

### Manual Verification
1. Hacer ping concurrente al servidor desde 2 terminales usando `curl` directo al endpoint de agenda inteligente para confirmar los mutex lock condicionales.
2. Analizar logs de backend post-refactor en donde confirmemos que 3 queries en cascada se convirtieron en queries paralelos.
