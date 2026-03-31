# API Backend - Mobile App (iOS/Android)

**Base URL:** `https://tu-backend.onrender.com`

---

## AUTENTICACIÓN

### 1. Registro Email/Password
**POST** `/api/auth/register`

**Campos (JSON):**
```json
{
  "email": "string (required, min 5 chars)",
  "password": "string (required, min 8 chars)",
  "full_name": "string (optional)"
}
```

**Respuesta (200):**
```json
{
  "user_id": "string",
  "email": "string",
  "full_name": "string",
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer"
}
```

---

### 2. Login Email/Password
**POST** `/api/auth/login`

**Campos (JSON):**
```json
{
  "email": "string (required)",
  "password": "string (required)"
}
```

**Respuesta (200):**
```json
{
  "user_id": "string",
  "email": "string",
  "full_name": "string",
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer"
}
```

---

### 3. Refresh Token
**POST** `/api/auth/refresh`

**Campos (JSON):**
```json
{
  "refresh_token": "string (required)"
}
```

**Respuesta (200):**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

### 4. Login OAuth (Google/Apple)
**POST** `/api/auth/oauth`

**Campos (JSON):**
```json
{
  "provider": "string (required: 'google' o 'apple')",
  "id_token": "string (required - JWT del proveedor)",
  "name": "string (optional)"
}
```

**Respuesta (200):**
```json
{
  "user_id": "string",
  "email": "string",
  "full_name": "string",
  "provider": "google|apple",
  "access_token": "string",
  "refresh_token": "string",
  "is_new_user": boolean
}
```

---

## HEADERS REQUERIDOS

### Headers por defecto (todas las peticiones):
```
Content-Type: application/json
```

### Headers autenticadas (endpoints protegidos):
```
Content-Type: application/json
Authorization: Bearer {access_token}
```

---

## CÓDIGOS DE ERROR

| Código | Significado |
|--------|-------------|
| 400 | Petición inválida - revisar campos |
| 401 | No autorizado - token inválido o expirado |
| 403 | Prohibido - sin permisos |
| 422 | Validación fallida - formato incorrecto |
| 429 | Rate limit - demasiadas peticiones |
| 500 | Error interno del servidor |

### Mensajes de error comunes (400):
```json
{"detail": "Email inválido"}
{"detail": "user_already_exists"}
{"detail": "invalid_credentials"}
{"detail": "token_expired"}
```

---

## EJEMPLOS PAYLOADS VÁLIDOS

### Registro:
```json
{
  "email": "usuario@ejemplo.com",
  "password": "miPassword123",
  "full_name": "Juan Pérez"
}
```

### Login:
```json
{
  "email": "usuario@ejemplo.com",
  "password": "miPassword123"
}
```

### Google OAuth:
```json
{
  "provider": "google",
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "name": "Juan Pérez"
}
```

---

## VARIABLES DE ENTORNO (RENDER)

Las variables que debes configurar en Render:

```
SECRET_KEY=generar_con_openssl_rand_hex_32
JWT_SECRET_KEY=generar_otro_con_openssl_rand_hex_32
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7
DATABASE_URL=postgresql://...
REDIS_URL=rediss://...
GROQ_API_KEY=tu_api_key

# CORS - IMPORTANTE para móvil:
CORS_ORIGINS=https://tu-frontend.com,https://www.tu-frontend.com
```

---

## NOTAS PARA DESARROLLADOR MÓVIL

1. **Tokens:** Guardar `access_token` y `refresh_token` en almacenamiento seguro (Keychain iOS / Keystore Android)

2. **Auto-refresh:** Cuando recibas 401, llamar a `/api/auth/refresh` con el `refresh_token`

3. **Campos opcionales:** Si envías campos extra, el backend los ignorará sin error

4. **Nombres de campos:** El backend acepta múltiples formatos:
   - `full_name`, `fullName`, o `name` → todos funcionan
   - `email` o `Email` → ambos funcionan
