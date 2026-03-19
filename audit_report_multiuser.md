# Informe de Auditoría OBSESIVA Brutal: Multiusuario y Robustez

He analizado el backend línea por línea enfocándome en el aislamiento de usuarios, concurrencia y gestión de recursos. Aquí están los hallazgos críticos:

## 1. Hallazgos Críticos de Seguridad (Aislamiento de Datos)
*   **HALLAZGO #1 (Grave - Fuga de Datos):** En `routers/class_notes_router.py`, el método `_get_storage()` inicializa un singleton de Storage que usa SQLite directamente (`settings.SQLITE_PATH`). 
    *   **Por qué falla:** SQLite no es ideal para multiusuario real en esta configuración. Peor aún, los métodos `list_notes`, `list_tasks`, etc., en `Storage` (dentro de `notes_grpc/storage.py`) NO parecen filtrar por `user_id` en las consultas raw SQL. **Cualquier usuario logueado podría ver las notas de otros.**
*   **HALLAZGO #2 (Aislamiento en WebSocket):** En `routers/recording_session_router.py`, el WebSocket `/ws/{session_id}` valida el token pero **NO verifica que la `session_id` pertenezca al `user_id`** del token antes de empezar a procesar audio.
    *   **Riesgo:** Un usuario con un token válido puede inyectar audio o finalizar sesiones de otros si conoce el UUID de la sesión.

## 2. Hallazgos de Concurrencia y Estabilidad
*   **HALLAZGO #3 (Pool de Conexiones Estrangulado):** En `database/db_enterprise.py`, el `primary_pool_size` está en **2**.
    *   **Por qué falla:** En una app multiusuario, 2 conexiones se agotan instantáneamente. Si 3 usuarios hacen una petición al mismo tiempo, el tercero esperará hasta el timeout. Esto causará errores 500 bajo carga mínima.
*   **HALLAZGO #4 (Race Conditions en Middlewares):** Tienes `RateLimitMiddleware` y `PreValidationMiddleware` corriendo secuencialmente. 
    *   Ambos inicializan sus propios clientes Redis/DB. Si una conexión falla o se bloquea, puede dejar colgado el event loop de la petición.
    *   **Falta de Sincronización:** El `PreValidationMiddleware` guarda `user_id` en `request.state`, pero si un middleware posterior falla, el error handler global no siempre tiene acceso limpio a ese estado para logging/sentry detallado.

## 3. Gestión de Recursos
*   **HALLAZGO #5 (Fuga de Descriptores de Archivo):** En `services/recording_session_service.py`, se crean tareas de IA en background. Si el usuario desconecta el WebSocket abruptamente, no hay una limpieza clara de los buffers de audio temporales en algunos flujos.

# Plan de Acción Inmediato
1.  **Corregir el pool de conexiones:** Subir de 2 a 20 (mínimo) para evitar bloqueos.
2.  **Blindar Routers:** Asegurar que CADA `select`, `update` y `delete` tenga un `.where(Model.user_id == user_id)`.
3.  **Refactorizar Storage de Notas:** Forzar el filtrado por usuario en la capa de persistencia de `notes_grpc`.
