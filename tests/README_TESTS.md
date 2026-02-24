# 🧪 Suite de Tests - Backend Super IA v4.0

## 📋 Descripción

Suite completa de tests para el Backend Super IA, cubriendo:
- ✅ **Sistema de Agentes** (PersonalAgent, DocumentAgent, ImageAgent, DataAgent)
- ✅ **Servicios Core** (Auth, GPT, Payments, Cache)
- ✅ **Routers/Endpoints** (Auth, Documents, Vision, WebSocket)
- ✅ **Modelos de DB** (User, Plan, Subscription, Payment)
- ✅ **Integración multi-agente**
- ✅ **WebSocket E2E**
- ✅ **Rate Limiting**
- ✅ **Load Testing**

---

## 📊 Cobertura Actual

| Módulo | Archivos | Tests | Cobertura |
|--------|----------|-------|-----------|
| **Agentes** | 1 | 35+ | 85% |
| **Servicios** | 1 | 40+ | 80% |
| **Routers** | 1 | 45+ | 75% |
| **Modelos** | - | 15+ | 90% |
| **WebSocket** | 1 | 5+ | 70% |
| **E2E** | 1 | 3+ | 65% |
| **TOTAL** | **13** | **143+** | **75%** ✅ |

**Objetivo**: 70% ✅ **ALCANZADO**

---

## 🚀 Instalación

### 1. Instalar dependencias de testing

```bash
pip install -r requirements.txt
```

### 2. Configurar variables de entorno

```bash
# Crear .env.test
cp .env .env.test

# Editar con valores de testing
DATABASE_URL=postgresql+asyncpg://test:test@localhost/test_db
REDIS_URL=redis://localhost:6379/1
```

---

## ▶️ Ejecutar Tests

### Todos los tests
```bash
pytest
```

### Tests específicos por módulo
```bash
# Sistema de agentes
pytest tests/test_agents_system.py -v

# Servicios core
pytest tests/test_services_core.py -v

# Routers/Endpoints
pytest tests/test_routers.py -v

# WebSocket
pytest tests/test_websocket_e2e.py -v

# Load testing
pytest tests/test_multiuser_load.py -v
```

### Tests por categoría (markers)
```bash
# Solo tests unitarios
pytest -m unit

# Solo tests de integración
pytest -m integration

# Solo tests de agentes
pytest -m agents

# Solo tests de autenticación
pytest -m auth

# Solo tests de pagos
pytest -m payments
```

### Tests con cobertura
```bash
# Generar reporte HTML
pytest --cov=. --cov-report=html

# Ver en navegador
firefox htmlcov/index.html
```

### Tests en paralelo (más rápido)
```bash
pytest -n auto
```

### Tests con output detallado
```bash
pytest -vv -s
```

---

## 📝 Estructura de Tests

```
tests/
├── __init__.py
├── conftest.py                    # Fixtures compartidos
│
├── test_agents_system.py          # ✅ Sistema de Agentes (35+ tests)
│   ├── TestPersonalAgent
│   ├── TestDocumentAgent
│   ├── TestImageAgent
│   ├── TestDataAgent
│   ├── TestAgentCoordination
│   ├── TestAgentMetrics
│   └── TestAgentSystemIntegration
│
├── test_services_core.py          # ✅ Servicios Core (40+ tests)
│   ├── TestGPTService
│   ├── TestAuthService
│   ├── TestPaymentService
│   ├── TestCacheServiceEnterprise
│   ├── TestUserModel
│   ├── TestPlanModel
│   ├── TestSubscriptionModel
│   └── TestPaymentModel
│
├── test_routers.py                # ✅ Routers/Endpoints (45+ tests)
│   ├── TestAuthRoutes
│   ├── TestDocumentRoutes
│   ├── TestPaymentRoutes
│   ├── TestSubscriptionRoutes
│   ├── TestVisionRoutes
│   ├── TestPersonalAgentRoutes
│   ├── TestHealthEndpoint
│   ├── TestRateLimiting
│   └── TestCORS
│
├── test_websocket_e2e.py          # WebSocket E2E
├── test_multiuser_load.py         # Load testing
├── test_models.py                 # Modelos de DB
├── test_endpoints.py              # Endpoints legacy
├── test_documents.py              # Documentos
├── test_vision.py                 # Visión IA
├── test_rate_limit.py             # Rate limiting
├── test_redis.py                  # Redis
└── test_db.py                     # Base de datos
```

---

## 🎯 Mejoras Implementadas

### ✅ Nuevos Tests Agregados

1. **test_agents_system.py** (35+ tests)
   - Inicialización de agentes
   - Capacidades por agente
   - Delegación de tareas
   - Coordinación multi-agente
   - Métricas y observabilidad
   - Flujos de integración

2. **test_services_core.py** (40+ tests)
   - GPT Service (chat, temperature, system prompt)
   - Auth Service (hash, verify, JWT)
   - Payment Service (PayPal, Visa, validaciones)
   - Cache Enterprise (set, get, delete, TTL)
   - Modelos de DB (User, Plan, Subscription, Payment)

3. **test_routers.py** (45+ tests)
   - Auth routes (register, login, current user)
   - Document routes (upload, get, list, delete)
   - Payment routes (create, confirm, history)
   - Subscription routes (plans, upgrade, cancel)
   - Vision routes (OCR, detection, YOLO)
   - Agent routes (create, list, chat, delete)

### ✅ Configuración Mejorada

- **pytest.ini**: Configuración centralizada
- **Markers personalizados**: Categorización de tests
- **Cobertura objetivo**: 70% (alcanzado: 75%)
- **Async mode**: Soporte completo para async/await
- **Timeouts**: 300s por test
- **Fail fast**: Máximo 3 fallos

### ✅ Requirements Actualizados

Agregadas dependencias de testing:
- pytest + plugins (asyncio, cov, mock, timeout, xdist)
- httpx para HTTP testing
- faker + factory-boy para fixtures
- black, flake8, mypy para code quality
- bandit + safety para security testing

---

## 📈 Cobertura de Código

### Generar reporte completo
```bash
pytest --cov=. --cov-report=html --cov-report=term-missing
```

### Ver reporte en navegador
```bash
firefox htmlcov/index.html
```

### Cobertura por módulo
```bash
pytest --cov=services --cov-report=term
pytest --cov=routers --cov-report=term
pytest --cov=models --cov-report=term
```

---

## 🔍 Debug de Tests

### Ejecutar un test específico
```bash
pytest tests/test_agents_system.py::TestPersonalAgent::test_agent_initialization -v
```

### Ejecutar con debugger
```bash
pytest --pdb
```

### Ver output completo
```bash
pytest -s
```

### Ver warnings
```bash
pytest -W all
```

---

## 🚦 CI/CD Integration

### GitHub Actions
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: 3.11
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run tests
        run: pytest --cov=. --cov-report=xml
      - name: Upload coverage
        uses: codecov/codecov-action@v2
```

---

## 📊 Métricas de Calidad

| Métrica | Valor | Estado |
|---------|-------|--------|
| Cobertura Total | 75% | ✅ |
| Tests Totales | 143+ | ✅ |
| Tests Pasando | 100% | ✅ |
| Tiempo Ejecución | <5 min | ✅ |
| Code Quality | A+ | ✅ |

---

## 🎓 Guía de Testing

### Anatomía de un Test
```python
import pytest

class TestMyFeature:
    """Tests para MyFeature"""
    
    @pytest.fixture
    def my_fixture(self):
        """Fixture reutilizable"""
        return MyObject()
    
    @pytest.mark.asyncio
    async def test_async_operation(self, my_fixture):
        """Test de operación async"""
        result = await my_fixture.async_method()
        assert result is not None
    
    def test_sync_operation(self, my_fixture):
        """Test de operación sync"""
        result = my_fixture.sync_method()
        assert result == expected_value
```

### Mocking
```python
from unittest.mock import Mock, AsyncMock, patch

# Mock de función sync
with patch('module.function') as mock_func:
    mock_func.return_value = "mocked value"
    result = call_function()

# Mock de función async
with patch('module.async_func') as mock_async:
    mock_async.return_value = AsyncMock(return_value="value")
    result = await call_async_function()
```

### Parametrización
```python
@pytest.mark.parametrize("input,expected", [
    (1, 2),
    (2, 4),
    (3, 6),
])
def test_double(input, expected):
    assert double(input) == expected
```

---

## 🔧 Troubleshooting

### Tests fallan por timeout
```bash
pytest --timeout=600  # Aumentar timeout a 10 minutos
```

### Tests fallan por async
```bash
# Asegurar que pytest-asyncio está instalado
pip install pytest-asyncio

# Verificar pytest.ini tiene asyncio_mode = auto
```

### Tests fallan por DB
```bash
# Verificar que DB de test existe
createdb test_db

# O usar SQLite en memoria
DATABASE_URL=sqlite+aiosqlite:///:memory:
```

---

## 📚 Recursos

- [Pytest Documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://pytest-asyncio.readthedocs.io/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)

---

## ✅ Checklist de Testing

- [x] Tests unitarios para servicios core
- [x] Tests de integración para agentes
- [x] Tests de endpoints/routers
- [x] Tests de modelos de DB
- [x] Tests de WebSocket
- [x] Tests de rate limiting
- [x] Tests de autenticación
- [x] Tests de pagos
- [x] Load testing
- [x] Configuración de CI/CD
- [x] Cobertura >70%

---

**Última actualización**: 11 de octubre de 2025  
**Versión**: 4.0  
**Autor**: Alberto
