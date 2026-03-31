# API Endpoints para Frontend - Auth Service

## Base URL
```
https://tu-backend.onrender.com
```

---

## 1. REGISTRO DE USUARIO

**Endpoint:** `POST /api/auth/register`

**Headers:**
```
Content-Type: application/json
```

**Campos Aceptados:**
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| email | string | SÍ | Email del usuario (min 5 chars) |
| password | string | SÍ | Contraseña (min 8 chars) |
| full_name | string | NO | Nombre completo |

**Ejemplo Payload:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "miPassword123",
  "full_name": "Juan Pérez"
}
```

**Respuesta Exitosa (200):**
```json
{
  "user_id": "123",
  "email": "usuario@ejemplo.com",
  "full_name": "Juan Pérez",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

---

## 2. LOGIN DE USUARIO

**Endpoint:** `POST /api/auth/login`

**Headers:**
```
Content-Type: application/json
```

**Campos Aceptados:**
| Campo | Tipo | Requerido | Descripción |
|-------|------|-----------|-------------|
| email | string | SÍ | Email del usuario |
| password | string | SÍ | Contraseña |

**Ejemplo Payload:**
```json
{
  "email": "usuario@ejemplo.com",
  "password": "miPassword123"
}
```

**Respuesta Exitosa (200):**
```json
{
  "user_id": "123",
  "email": "usuario@ejemplo.com",
  "full_name": "Juan Pérez",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

---

## 3. REFRESH TOKEN

**Endpoint:** `POST /api/auth/refresh`

**Headers:**
```
Content-Type: application/json
```

**Campos Aceptados (múltiples formatos):**
| Campo | Tipo | Descripción |
|-------|------|-------------|
| refresh_token | string | Token de refresco |
| refreshToken | string | Alternativa camelCase |
| token | string | Alternativa simple |

**Ejemplo Payload:**
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**Respuesta Exitosa (200):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

## 4. LOGIN CON OAUTH (Google/Apple)

**Endpoint:** `POST /api/auth/oauth`

**Headers:**
```
Content-Type: application/json
```

**Campos Requeridos:**
| Campo | Tipo | Descripción |
|-------|------|-------------|
| provider | string | "google" o "apple" |
| id_token | string | ID Token JWT del proveedor |
| name | string | Nombre del usuario (opcional) |

**Ejemplo Payload:**
```json
{
  "provider": "google",
  "id_token": "eyJhbGciOiJSUzI1NiIs...",
  "name": "Juan Pérez"
}
```

**Respuesta Exitosa (200):**
```json
{
  "user_id": "123",
  "email": "usuario@gmail.com",
  "full_name": "Juan Pérez",
  "provider": "google",
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "is_new_user": false
}
```

---

## Errores Comunes

**400 Bad Request:**
```json
{
  "detail": "Email inválido"
}
```

**400 Bad Request (Usuario existe):**
```json
{
  "detail": "user_already_exists"
}
```

**401 Unauthorized (Login):**
```json
{
  "detail": "invalid_credentials"
}
```

**503 Service Unavailable (OAuth):**
```json
{
  "detail": "oauth_google_not_configured"
}
```

---

## Variables de Entorno Requeridas en Render

```bash
# JWT
SECRET_KEY=tu_secret_key_32_chars_min
JWT_SECRET_KEY=tu_jwt_secret_key_32_chars_min
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# OAuth (opcional)
GOOGLE_CLIENT_ID=tu_google_client_id
GOOGLE_CLIENT_SECRET=tu_google_client_secret

# CORS (CRÍTICO para app móvil)
CORS_ORIGINS=https://tu-frontend.com,https://www.tu-frontend.com
```

---

## CÓDIGO FRONTEND - JavaScript/TypeScript

### Configuración Base
```javascript
const API_BASE_URL = 'https://tu-backend.onrender.com';

async function apiCall(endpoint, method = 'GET', body = null, token = null) {
  const headers = {
    'Content-Type': 'application/json',
  };
  
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  
  const options = {
    method,
    headers,
  };
  
  if (body) {
    options.body = JSON.stringify(body);
  }
  
  const response = await fetch(`${API_BASE_URL}${endpoint}`, options);
  const data = await response.json();
  
  if (!response.ok) {
    throw new Error(data.detail || 'Error en la petición');
  }
  
  return data;
}
```

### 1. REGISTRO
```javascript
async function registerUser(email, password, fullName) {
  try {
    const result = await apiCall('/api/auth/register', 'POST', {
      email,
      password,
      full_name: fullName  // o fullName: fullName
    });
    
    // Guardar tokens
    localStorage.setItem('access_token', result.access_token);
    localStorage.setItem('refresh_token', result.refresh_token);
    localStorage.setItem('user', JSON.stringify(result));
    
    return result;
  } catch (error) {
    console.error('Error registro:', error.message);
    throw error;
  }
}

// Uso:
// registerUser('usuario@ejemplo.com', 'password123', 'Juan Pérez');
```

### 2. LOGIN
```javascript
async function loginUser(email, password) {
  try {
    const result = await apiCall('/api/auth/login', 'POST', {
      email,
      password
    });
    
    // Guardar tokens
    localStorage.setItem('access_token', result.access_token);
    localStorage.setItem('refresh_token', result.refresh_token);
    localStorage.setItem('user', JSON.stringify(result));
    
    return result;
  } catch (error) {
    console.error('Error login:', error.message);
    throw error;
  }
}

// Uso:
// loginUser('usuario@ejemplo.com', 'password123');
```

### 3. REFRESH TOKEN (automático)
```javascript
async function refreshToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  
  if (!refreshToken) {
    throw new Error('No refresh token');
  }
  
  try {
    const result = await apiCall('/api/auth/refresh', 'POST', {
      refresh_token: refreshToken
    });
    
    localStorage.setItem('access_token', result.access_token);
    localStorage.setItem('refresh_token', result.refresh_token);
    
    return result.access_token;
  } catch (error) {
    // Token inválido, logout
    logout();
    throw error;
  }
}

function logout() {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  localStorage.removeItem('user');
  // Redirigir a login
}
```

### 4. LLAMADA AUTENTICADA (con auto-refresh)
```javascript
async function authenticatedCall(endpoint, method = 'GET', body = null) {
  let token = localStorage.getItem('access_token');
  
  try {
    return await apiCall(endpoint, method, body, token);
  } catch (error) {
    if (error.message === 'token_expired') {
      // Refresh y reintentar
      token = await refreshToken();
      return await apiCall(endpoint, method, body, token);
    }
    throw error;
  }
}

// Uso:
// authenticatedCall('/api/user/profile', 'GET');
```

### 5. LOGIN CON GOOGLE
```javascript
async function loginWithGoogle(idToken, name) {
  try {
    const result = await apiCall('/api/auth/oauth', 'POST', {
      provider: 'google',
      id_token: idToken,
      name: name
    });
    
    localStorage.setItem('access_token', result.access_token);
    localStorage.setItem('refresh_token', result.refresh_token);
    localStorage.setItem('user', JSON.stringify(result));
    
    return result;
  } catch (error) {
    console.error('Error OAuth:', error.message);
    throw error;
  }
}
```

---

## EJEMPLO COMPLETO - React/Vue/Angular

```javascript
// auth.js - Servicio de autenticación completo
class AuthService {
  constructor() {
    this.apiUrl = 'https://tu-backend.onrender.com';
  }
  
  async register(email, password, fullName) {
    const response = await fetch(`${this.apiUrl}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name: fullName })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Error en registro');
    }
    
    const data = await response.json();
    this.setSession(data);
    return data;
  }
  
  async login(email, password) {
    const response = await fetch(`${this.apiUrl}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password })
    });
    
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Error en login');
    }
    
    const data = await response.json();
    this.setSession(data);
    return data;
  }
  
  setSession(data) {
    localStorage.setItem('access_token', data.access_token);
    localStorage.setItem('refresh_token', data.refresh_token);
    localStorage.setItem('user', JSON.stringify(data));
  }
  
  getToken() {
    return localStorage.getItem('access_token');
  }
  
  isAuthenticated() {
    return !!this.getToken();
  }
  
  logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user');
  }
}

export const authService = new AuthService();
```

---

## IMPORTANTE - CORS

El backend está configurado para aceptar tu dominio frontend. Si usas desarrollo local:

```bash
# En Render, agrega a CORS_ORIGINS:
CORS_ORIGINS=https://tu-frontend.com,https://www.tu-frontend.com,http://localhost:3000,http://localhost:8080
```
