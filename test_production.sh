#!/bin/bash
# Script de Test para Backend en Producción
# URL: https://estudente-msba.onrender.com

echo "=============================================="
echo "TEST BACKEND EN PRODUCCIÓN"
echo "URL: https://estudente-msba.onrender.com"
echo "=============================================="
echo ""

BASE_URL="https://estudente-msba.onrender.com"

# 1. Health Check
echo "1. TEST: Health Check"
echo "   Endpoint: GET $BASE_URL/health"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  "$BASE_URL/health" | head -20
echo ""

# 2. API Status
echo "2. TEST: API Status"
echo "   Endpoint: GET $BASE_URL/api/status"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  "$BASE_URL/api/status" | head -20
echo ""

# 3. Test Register (usuario de prueba)
TEST_EMAIL="test_$(date +%s)@test.com"
echo "3. TEST: Registro de Usuario"
echo "   Endpoint: POST $BASE_URL/api/auth/register"
echo "   Email: $TEST_EMAIL"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  -X POST \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"testpassword123\",\"full_name\":\"Test User\"}" \
  "$BASE_URL/api/auth/register" | head -30
echo ""

# 4. Test Login
echo "4. TEST: Login"
echo "   Endpoint: POST $BASE_URL/api/auth/login"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  -X POST \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"testpassword123\"}" \
  "$BASE_URL/api/auth/login" | head -30
echo ""

# 5. Test Login con credenciales inválidas (debe dar 401)
echo "5. TEST: Login con credenciales inválidas (esperado: 401)"
echo "   Endpoint: POST $BASE_URL/api/auth/login"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"noexiste@test.com","password":"wrong"}' \
  "$BASE_URL/api/auth/login" | head -10
echo ""

# 6. Test CORS (preflight)
echo "6. TEST: CORS Preflight"
echo "   Endpoint: OPTIONS $BASE_URL/api/auth/login"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  -X OPTIONS \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: Content-Type" \
  "$BASE_URL/api/auth/login" | head -10
echo ""

# 7. Test WebSocket (verificar que acepta conexión)
echo "7. TEST: WebSocket Endpoint (verificar disponibilidad)"
echo "   Endpoint: GET $BASE_URL/api/chat/ws/test"
curl -s -w "\nStatus: %{http_code}\nTime: %{time_total}s\n" \
  "$BASE_URL/api/chat/ws/test" | head -10
echo ""

echo "=============================================="
echo "TESTS COMPLETADOS"
echo "=============================================="
