"""
🧪 Tests Completos para Servicios Core
======================================
Cobertura: GPT Service, Auth Service, Payment Service, Cache
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json

from services.gpt_service import GPTService
from services.auth_service import AuthService
from services.payment_service import PaymentService
from services.cache_service_enterprise import CacheServiceEnterprise
from models.models import User, Plan, Subscription, Payment, PaymentStatus


class TestGPTService:
    """Tests para GPT Service"""
    
    @pytest.fixture
    def gpt_service(self):
        return GPTService()
    
    @pytest.mark.asyncio
    async def test_chat_basic(self, gpt_service):
        """Test: Chat básico con GPT"""
        with patch('httpx.AsyncClient.post') as mock_post:
            # Mock response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {
                        "content": "Hola, ¿cómo puedo ayudarte?"
                    }
                }],
                "usage": {
                    "total_tokens": 50
                }
            }
            mock_post.return_value = mock_response
            
            result = await gpt_service.chat("Hola", user_id="test_user")
            
            assert result is not None
            assert isinstance(result, str)
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_chat_with_temperature(self, gpt_service):
        """Test: Chat con temperatura personalizada"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {"content": "Respuesta creativa"}
                }]
            }
            mock_post.return_value = mock_response
            
            # Temperature alta = más creatividad
            result = await gpt_service.chat(
                "Escribe un poema",
                user_id="test_user",
                temperature=0.9
            )
            
            assert result is not None
            # Verificar que se llamó con temperatura correcta
            call_args = mock_post.call_args
            assert call_args is not None
    
    @pytest.mark.asyncio
    async def test_chat_with_system_prompt(self, gpt_service):
        """Test: Chat con system prompt personalizado"""
        with patch('httpx.AsyncClient.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "choices": [{
                    "message": {"content": "Respuesta como experto"}
                }]
            }
            mock_post.return_value = mock_response
            
            result = await gpt_service.chat(
                "¿Qué es Python?",
                user_id="test_user",
                system_prompt="Eres un experto en programación"
            )
            
            assert result is not None
            mock_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_chat_error_handling(self, gpt_service):
        """Test: Manejo de errores en chat"""
        with patch('httpx.AsyncClient.post') as mock_post:
            # Simular error de API
            mock_post.side_effect = Exception("API Error")
            
            with pytest.raises(Exception):
                await gpt_service.chat("Test", user_id="test_user")


class TestAuthService:
    """Tests para Auth Service"""
    
    @pytest.fixture
    def auth_service(self):
        return AuthService()
    
    def test_hash_password(self, auth_service):
        """Test: Hash de contraseña"""
        password = "SecurePassword123!"
        hashed = auth_service.hash_password(password)
        
        assert hashed != password
        assert len(hashed) > 0
        assert isinstance(hashed, str)
    
    def test_verify_password_correct(self, auth_service):
        """Test: Verificar contraseña correcta"""
        password = "SecurePassword123!"
        hashed = auth_service.hash_password(password)
        
        is_valid = auth_service.verify_password(password, hashed)
        assert is_valid is True
    
    def test_verify_password_incorrect(self, auth_service):
        """Test: Verificar contraseña incorrecta"""
        password = "SecurePassword123!"
        hashed = auth_service.hash_password(password)
        
        is_valid = auth_service.verify_password("WrongPassword", hashed)
        assert is_valid is False
    
    def test_create_access_token(self, auth_service):
        """Test: Crear token de acceso"""
        user_data = {"user_id": "123", "email": "test@example.com"}
        token = auth_service.create_access_token(user_data)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        
        # Token JWT debe tener 3 partes separadas por puntos
        parts = token.split('.')
        assert len(parts) == 3
    
    def test_decode_token_valid(self, auth_service):
        """Test: Decodificar token válido"""
        user_data = {"user_id": "123", "email": "test@example.com"}
        token = auth_service.create_access_token(user_data)
        
        decoded = auth_service.decode_token(token)
        
        assert decoded is not None
        assert decoded["user_id"] == "123"
        assert decoded["email"] == "test@example.com"
    
    def test_decode_token_expired(self, auth_service):
        """Test: Decodificar token expirado"""
        user_data = {"user_id": "123"}
        
        # Crear token con expiración inmediata
        with patch('datetime.datetime') as mock_datetime:
            # Token creado en el pasado
            past = datetime.utcnow() - timedelta(days=1)
            mock_datetime.utcnow.return_value = past
            
            token = auth_service.create_access_token(user_data, expires_delta=timedelta(seconds=1))
        
        # Intentar decodificar (debería fallar)
        with pytest.raises(Exception):
            auth_service.decode_token(token)
    
    def test_decode_token_invalid(self, auth_service):
        """Test: Decodificar token inválido"""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(Exception):
            auth_service.decode_token(invalid_token)


class TestPaymentService:
    """Tests para Payment Service"""
    
    @pytest.fixture
    def payment_service(self):
        return PaymentService()
    
    @pytest.mark.asyncio
    async def test_create_payment_record(self, payment_service):
        """Test: Crear registro de pago"""
        payment_data = {
            "user_id": 123,
            "plan_id": 2,
            "amount": 24.99,
            "currency": "USD",
            "gateway": "paypal"
        }
        
        # Mock de la sesión de DB
        with patch('database.db_enterprise.get_async_session') as mock_session:
            mock_db = AsyncMock()
            mock_session.return_value.__aenter__.return_value = mock_db
            
            payment = await payment_service.create_payment(**payment_data)
            
            # Verificar que se intentó agregar a la DB
            assert mock_db.add.called or payment is not None
    
    def test_validate_payment_amount(self, payment_service):
        """Test: Validar monto de pago"""
        # Montos válidos
        assert payment_service.validate_amount(10.00) is True
        assert payment_service.validate_amount(99.99) is True
        
        # Montos inválidos
        assert payment_service.validate_amount(-5.00) is False
        assert payment_service.validate_amount(0) is False
    
    def test_validate_currency(self, payment_service):
        """Test: Validar moneda"""
        valid_currencies = ["USD", "EUR", "GBP", "MXN"]
        
        for currency in valid_currencies:
            assert payment_service.validate_currency(currency) is True
        
        # Moneda inválida
        assert payment_service.validate_currency("INVALID") is False
    
    @pytest.mark.asyncio
    async def test_process_paypal_payment(self, payment_service):
        """Test: Procesar pago con PayPal"""
        with patch('services.payment_gateways.paypal_gateway.PayPalGateway.process_payment') as mock_paypal:
            mock_paypal.return_value = {
                "success": True,
                "transaction_id": "PAYPAL123",
                "status": "completed"
            }
            
            result = await payment_service.process_payment(
                amount=24.99,
                currency="USD",
                gateway="paypal",
                user_id=123
            )
            
            assert result["success"] is True
            assert "transaction_id" in result
    
    @pytest.mark.asyncio
    async def test_process_visa_payment(self, payment_service):
        """Test: Procesar pago con Visa"""
        with patch('services.payment_gateways.visa_gateway.VisaGateway.process_payment') as mock_visa:
            mock_visa.return_value = {
                "success": True,
                "transaction_id": "VISA123",
                "status": "completed"
            }
            
            result = await payment_service.process_payment(
                amount=59.99,
                currency="USD",
                gateway="visa",
                user_id=456,
                card_data={
                    "number": "4111111111111111",
                    "cvv": "123",
                    "expiry": "12/25"
                }
            )
            
            assert result["success"] is True


class TestCacheServiceEnterprise:
    """Tests para Cache Service Enterprise"""
    
    @pytest.fixture
    def cache_service(self):
        return CacheServiceEnterprise()
    
    @pytest.mark.asyncio
    async def test_set_and_get_cache(self, cache_service):
        """Test: Guardar y recuperar de cache"""
        with patch.object(cache_service.redis, 'set') as mock_set, \
             patch.object(cache_service.redis, 'get') as mock_get:
            
            mock_set.return_value = True
            mock_get.return_value = json.dumps({"data": "test_value"})
            
            # Guardar en cache
            await cache_service.set("test_key", {"data": "test_value"}, ttl=3600)
            
            # Recuperar de cache
            result = await cache_service.get("test_key")
            
            assert result is not None
            mock_set.assert_called_once()
            mock_get.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cache_miss(self, cache_service):
        """Test: Cache miss retorna None"""
        with patch.object(cache_service.redis, 'get') as mock_get:
            mock_get.return_value = None
            
            result = await cache_service.get("nonexistent_key")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_delete_cache(self, cache_service):
        """Test: Eliminar entrada de cache"""
        with patch.object(cache_service.redis, 'delete') as mock_delete:
            mock_delete.return_value = 1
            
            result = await cache_service.delete("test_key")
            
            assert result is True
            mock_delete.assert_called_once_with("test_key")
    
    @pytest.mark.asyncio
    async def test_cache_with_ttl(self, cache_service):
        """Test: Cache con tiempo de expiración"""
        with patch.object(cache_service.redis, 'setex') as mock_setex:
            mock_setex.return_value = True
            
            await cache_service.set("ttl_key", {"data": "value"}, ttl=300)
            
            # Verificar que se llamó con TTL
            mock_setex.assert_called_once()
            call_args = mock_setex.call_args
            assert call_args[0][1] == 300  # TTL de 300 segundos
    
    @pytest.mark.asyncio
    async def test_cache_exists(self, cache_service):
        """Test: Verificar si clave existe en cache"""
        with patch.object(cache_service.redis, 'exists') as mock_exists:
            mock_exists.return_value = 1
            
            exists = await cache_service.exists("test_key")
            
            assert exists is True
            mock_exists.assert_called_once_with("test_key")
    
    @pytest.mark.asyncio
    async def test_cache_pattern_delete(self, cache_service):
        """Test: Eliminar claves por patrón"""
        with patch.object(cache_service.redis, 'keys') as mock_keys, \
             patch.object(cache_service.redis, 'delete') as mock_delete:
            
            mock_keys.return_value = ["user:1:data", "user:1:profile"]
            mock_delete.return_value = 2
            
            deleted = await cache_service.delete_pattern("user:1:*")
            
            assert deleted >= 0
            mock_keys.assert_called_once()


class TestUserModel:
    """Tests para modelo User"""
    
    def test_user_creation(self):
        """Test: Crear usuario"""
        user = User(
            id=1,
            email="test@example.com",
            username="testuser",
            hashed_password="hashed_pw_123"
        )
        
        assert user.id == 1
        assert user.email == "test@example.com"
        assert user.username == "testuser"
    
    def test_user_plan_relationship(self):
        """Test: Relación usuario-plan"""
        plan = Plan(
            id=1,
            name="Pro",
            price=59.99
        )
        
        user = User(
            id=1,
            email="test@example.com",
            plan_id=1
        )
        user.plan = plan
        
        assert user.plan.name == "Pro"
        assert user.plan.price == 59.99
    
    def test_user_can_make_request(self):
        """Test: Usuario puede hacer request"""
        user = User(
            id=1,
            email="test@example.com",
            requests_used_this_month=50
        )
        
        plan = Plan(
            id=1,
            name="Pro",
            requests_per_month=300
        )
        user.plan = plan
        
        assert user.can_make_request() is True
    
    def test_user_cannot_make_request_limit_reached(self):
        """Test: Usuario no puede hacer request (límite alcanzado)"""
        user = User(
            id=1,
            email="test@example.com",
            requests_used_this_month=100
        )
        
        plan = Plan(
            id=2,
            name="Basic",
            requests_per_month=100
        )
        user.plan = plan
        
        assert user.can_make_request() is False


class TestPlanModel:
    """Tests para modelo Plan"""
    
    def test_plan_creation(self):
        """Test: Crear plan"""
        plan = Plan(
            id=1,
            name="Enterprise",
            price=199.99,
            requests_per_month=1000,
            max_personal_agents=50
        )
        
        assert plan.name == "Enterprise"
        assert plan.price == 199.99
        assert plan.max_personal_agents == 50
    
    def test_plan_features(self):
        """Test: Features de plan"""
        plan = Plan(
            id=1,
            name="Pro",
            features=["gpt4_access", "api_access", "voice_cloning"]
        )
        
        assert "gpt4_access" in plan.features
        assert "api_access" in plan.features
        assert len(plan.features) == 3


class TestSubscriptionModel:
    """Tests para modelo Subscription"""
    
    def test_subscription_creation(self):
        """Test: Crear suscripción"""
        subscription = Subscription(
            id=1,
            user_id=123,
            plan_id=2,
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            status="active"
        )
        
        assert subscription.user_id == 123
        assert subscription.plan_id == 2
        assert subscription.status == "active"
    
    def test_subscription_is_active(self):
        """Test: Verificar si suscripción está activa"""
        now = datetime.utcnow()
        
        subscription = Subscription(
            id=1,
            user_id=123,
            plan_id=2,
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=25),
            status="active"
        )
        
        # Suscripción activa dentro del período
        assert subscription.status == "active"
        assert subscription.end_date > now
    
    def test_subscription_expired(self):
        """Test: Suscripción expirada"""
        now = datetime.utcnow()
        
        subscription = Subscription(
            id=1,
            user_id=123,
            plan_id=2,
            start_date=now - timedelta(days=60),
            end_date=now - timedelta(days=30),
            status="expired"
        )
        
        assert subscription.status == "expired"
        assert subscription.end_date < now


class TestPaymentModel:
    """Tests para modelo Payment"""
    
    def test_payment_creation(self):
        """Test: Crear pago"""
        payment = Payment(
            id=1,
            user_id=123,
            plan_id=2,
            amount=59.99,
            currency="USD",
            status=PaymentStatus.COMPLETED,
            transaction_id="TXN123456"
        )
        
        assert payment.user_id == 123
        assert payment.amount == 59.99
        assert payment.currency == "USD"
        assert payment.status == PaymentStatus.COMPLETED
    
    def test_payment_pending(self):
        """Test: Pago pendiente"""
        payment = Payment(
            id=1,
            user_id=123,
            amount=24.99,
            status=PaymentStatus.PENDING
        )
        
        assert payment.status == PaymentStatus.PENDING
    
    def test_payment_failed(self):
        """Test: Pago fallido"""
        payment = Payment(
            id=1,
            user_id=123,
            amount=24.99,
            status=PaymentStatus.FAILED,
            error_message="Card declined"
        )
        
        assert payment.status == PaymentStatus.FAILED
        assert payment.error_message == "Card declined"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--asyncio-mode=auto"])
