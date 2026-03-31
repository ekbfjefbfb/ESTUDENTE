# Integración Deepgram Voice Agent ("Bring Your Own LLM")

He analizado a fondo la documentación de la recién lanzada API de Deepgram Voice Agent y el payload de configuración que enviaste. Implementaremos esto con **latencia ultra-baja y sin tocar la lógica existente**.

## Estrategia Arquitectónica 🧠

En lugar de que Deepgram hable de forma cruda con OpenAI/Groq, **nosotros construiremos un puerto "Custom LLM"** en el backend. 
El flujo móvil será:
1. Tu app celular abre un WebSocket directo a Deepgram y le manda el audio (Logrando fluidez casi mágica de <300ms).
2. Deepgram traduce a Texto de forma nativa.
3. Deepgram envía ese texto a **NUESTRO Backend** mediante una llamada HTTP haciéndose pasar por un cliente OpenAI compatible.
4. Nuestro Backend recibe la llamada, valida el `Bearer Token` de tu usuario, inyecta su Contexto (Agenda, Info, Búsquedas) y consulta a nuestra IA (Groq).
5. Nuestro Backend le regresa el stream de bytes de Groq a Deepgram.
6. Deepgram le habla al usuario final.

¡Con esto mantienes lo mejor de ambos mundos! La velocidad brutal de Deepgram Voice Agent + El Nivel Cognitivo Enterprise de tu servidor.

## User Review Required

> [!IMPORTANT]
> Para lograrlo, necesito crear un nuevo "router" exclusivo llamado `routers/deepgram_agent_router.py`. Éste expondrá la ruta `POST /api/deepgram/chat` que Deepgram Agent va a llamar.
> 
> En tu frontend (Mobile), cuando configures el Agente, deberás agregar nuestro Token JWT en los headers de configuración así:
> ```json
> "think": {
>   "provider": { "type": "custom" },
>   "endpoint": {
>       "url": "https://TU-BACKEND.com/api/deepgram/chat",
>       "headers": [
>         {"key": "Authorization", "value": "Bearer <AQUÍ_VA_TU_JWT_DE_USUARIO>"}
>       ]
>   }
> }
> ```
> ¿Estás de acuerdo con inyectar tu token JWT al momento de abrir el WebSocket de Deepgram desde Flutter/Swift para autenticar que realmente es el usuario?

## Proposed Changes

---

### Módulo de Agente Deepgram
#### [NEW] `routers/deepgram_agent_router.py`
- Expondrá `POST /api/deepgram/chat`.
- Implementará una dependencia de FastAPI para extraer explícitamente el token JWT y decodificar el `user_id`.
- Interceptará el arreglo de `messages` enviado por Deepgram, inyectará en la primera posición nuestro ultra-eficiente prompt maestro (usando `get_user_personal_context` directo de RAM).
- Llamará al `chat_with_ai(stream=True)`.
- Envolverá la respuesta en el protocolo `Server-Sent Events (SSE)` idéntico a OpenAI para engañar sanamente a Deepgram Agent.

### Registro en el Servidor
#### [MODIFY] `main.py`
- Añadiremos el comando `app.include_router(deepgram_agent_router.router)` para dejar encendida la API.

## Open Questions

1. En Deepgram, el `speak: provider` que pasaste (`aura-2-aquila-es`) es el último modelo de TTS. ¿Deseas que desde la parte del backend también inyectemos la instrucción "responde en español nativo neutro, sé súper corto y conversacional" para forzar al límite al LLM a comportarse como un humano por teléfono? (Evita al máximo que use viñetas, markdown o textos largos).

## Verification Plan

### Manual Verification
1. Prograbaré un mock request imitando el payload de Deepgram para asegurar que el backend emite `data: {"model": "groq", "choices": [{"delta": {"content": "hola"}}]}` de manera correcta.
2. Confirmaremos que la ruta esté libre de Rate Limits asfixiantes para evitar que el flujo conversacional de la voz se detenga.
