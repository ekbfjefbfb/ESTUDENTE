# 📊 Database Schema Documentation - ESTUDENTE Backend

## Tabla: `users`

### Columnas Principales

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | VARCHAR(PK) | Identificador único del usuario |
| `username` | VARCHAR(50) | Nombre de usuario único (requerido) |
| `email` | VARCHAR(100) | Email del usuario (único, puede ser null para registro con teléfono) |
| `phone_number` | VARCHAR(20) | Número de teléfono (único, opcional) |
| `phone_verified` | BOOLEAN | Si el teléfono está verificado |
| `phone_verified_at` | TIMESTAMP | Fecha de verificación del teléfono |
| `full_name` | VARCHAR(100) | Nombre completo del usuario |
| `bio` | TEXT | Biografía/descripción del usuario |
| `hashed_password` | VARCHAR(255) | Contraseña hasheada (null para OAuth/teléfono) |
| `is_active` | BOOLEAN | Si el usuario está activo (default: true) |

### Columnas de Plan/Suscripción

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `plan_id` | INTEGER(FK) | Referencia al plan activo |
| `plan_started_at` | TIMESTAMP | Inicio del plan actual |
| `plan_ends_at` | TIMESTAMP | Fin del plan actual |
| `subscription_expires_at` | TIMESTAMP | **CRÍTICO** - Fecha de expiración de suscripción |
| `requests_used_this_month` | INTEGER | Contador de requests mensuales |
| `last_request_reset` | TIMESTAMP | Último reset del contador |
| `last_activity` | TIMESTAMP | Última actividad registrada |

### Columnas de Demo

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `demo_until` | TIMESTAMP | Fin del período demo |
| `demo_requests_today` | INTEGER | Requests usados hoy |
| `demo_last_reset` | TIMESTAMP | Último reset demo |
| `demo_count` | INTEGER | Contador de demos usados |
| `last_demo_date` | TIMESTAMP | Fecha último demo |

### Columnas de Perfil OAuth

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `oauth_profile` | JSONB | Datos completos del perfil OAuth |
| `profile_picture_url` | VARCHAR(500) | URL foto de perfil |
| `timezone` | VARCHAR(50) | Zona horaria (default: UTC) |
| `preferred_language` | VARCHAR(10) | Idioma (default: en) |
| `interests` | JSONB | Lista de intereses |
| `oauth_provider` | VARCHAR(20) | Proveedor (google, microsoft, github, apple) |
| `oauth_access_token` | VARCHAR(500) | Token de acceso OAuth |
| `oauth_refresh_token` | VARCHAR(500) | Token de refresco |
| `oauth_token_expires_at` | TIMESTAMP | Expiración del token |

### Columnas de Datos/Preferencias

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `profile_data` | JSONB | Datos adicionales de perfil |
| `preferences` | JSONB | Preferencias del usuario |
| `created_at` | TIMESTAMP | Fecha de creación |
| `updated_at` | TIMESTAMP | Última actualización |

## Tabla: `plans`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL(PK) | ID del plan |
| `name` | VARCHAR(50) | Identificador (demo, normal, pro, enterprise) |
| `display_name` | VARCHAR(100) | Nombre visible |
| `description` | TEXT | Descripción del plan |
| `price` | FLOAT | Precio mensual |
| `currency` | VARCHAR(3) | Moneda (default: USD) |
| `requests_per_month` | INTEGER | Límite de requests |
| `max_file_size_mb` | INTEGER | Tamaño máximo de archivo |
| `features` | JSONB | Lista de características |
| `is_active` | BOOLEAN | Si está activo |
| `is_demo` | BOOLEAN | Si es plan demo |
| `sort_order` | INTEGER | Orden de visualización |

## Ejecución de Migraciones

### En Render (PostgreSQL):

1. Ve a tu servicio en Render Dashboard
2. Click en "Shell" tab
3. Ejecuta:

```bash
# Conectar a PostgreSQL
psql $DATABASE_URL

# O si tienes un archivo local:
psql -f migrations/001_update_users_schema.sql $DATABASE_URL
psql -f migrations/002_create_plans_table.sql $DATABASE_URL
```

### Local:

```bash
# Asegúrate de tener DATABASE_URL configurada
psql -f migrations/001_update_users_schema.sql $DATABASE_URL
psql -f migrations/002_create_plans_table.sql $DATABASE_URL
```

## Funciones del Sistema

### Auth Service
- `register_email_password_v2()` - Registro con email/password
- `login_email_password()` - Login con credenciales
- `oauth_login_or_register()` - Login/Registro OAuth
- `refresh_access_token_service()` - Refrescar tokens JWT

### Voice Note Service
- `acquire_job()` - Adquirir job de procesamiento
- `process_single_job()` - Procesar nota de voz
- `worker_loop()` - Loop del worker background

## Notas Importantes

⚠️ **Columnas CRÍTICAS que causaban errores:**
- `subscription_expires_at` - Necesaria para INSERT de usuarios
- `phone_number` / `phone_verified` / `phone_verified_at` - Para sistema de teléfono
- `plan_id` - Referencia a tabla plans

✅ **Estado después de migración:**
- Registro funciona con solo: username, email, hashed_password
- Columnas opcionales tienen defaults NULL o valores por defecto
- Índices creados para búsquedas eficientes
