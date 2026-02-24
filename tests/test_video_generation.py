"""
Tests para el sistema de generación de videos HunyuanVideo
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path

# ============================================================================
# SERVICE TESTS
# ============================================================================

class TestHunyuanVideoService:
    """Tests para HunyuanVideoService"""
    
    @pytest.mark.asyncio
    async def test_service_initialization(self):
        """Test inicialización del servicio"""
        from services.hunyuan_video_service import get_hunyuan_video_service, HUNYUAN_AVAILABLE
        
        service = get_hunyuan_video_service()
        
        assert service is not None
        assert service.model_path == "tencent/hunyuan-video"
        assert service.output_dir.exists()
        assert not service.is_loaded
        assert not service.is_generating
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HUNYUAN_AVAILABLE, reason="HunyuanVideo dependencies not available")
    async def test_get_status(self):
        """Test obtener estado del servicio"""
        from services.hunyuan_video_service import get_hunyuan_video_service
        
        service = get_hunyuan_video_service()
        status = service.get_status()
        
        assert "is_loaded" in status
        assert "is_generating" in status
        assert "device" in status
        assert "vram_used_gb" in status
        assert status["device"] in ["cuda", "cpu"]
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(HUNYUAN_AVAILABLE, reason="Test for missing dependencies")
    async def test_service_unavailable(self):
        """Test servicio cuando dependencias no disponibles"""
        from services.hunyuan_video_service import HUNYUAN_AVAILABLE
        
        assert not HUNYUAN_AVAILABLE
    
    @pytest.mark.asyncio
    async def test_generate_video_mock(self):
        """Test generación de video con mock"""
        from services.hunyuan_video_service import get_hunyuan_video_service
        
        service = get_hunyuan_video_service()
        
        # Mock the pipeline
        with patch.object(service, 'pipeline') as mock_pipeline:
            mock_pipeline.return_value = Mock()
            
            # Mock para simular generación exitosa
            with patch('torch.cuda.is_available', return_value=True):
                with patch.object(service, 'is_loaded', True):
                    result = await service.generate_video(
                        prompt="A serene waterfall",
                        num_frames=120,
                        width=1280,
                        height=720,
                        user_id="test_user"
                    )
                    
                    # Verificar estructura del resultado
                    assert "video_id" in result
                    assert "filename" in result
                    assert "video_path" in result
                    assert "duration_seconds" in result
                    assert "resolution" in result


# ============================================================================
# ROUTER TESTS
# ============================================================================

class TestVideoGenerationRouter:
    """Tests para video_generation_router"""
    
    @pytest.mark.asyncio
    async def test_status_endpoint(self, client):
        """Test endpoint /api/video/status"""
        response = await client.get("/api/video/status")
        
        assert response.status_code == 200
        data = response.json()
        
        if data.get("available"):
            assert "status" in data
            assert "is_loaded" in data["status"]
        else:
            assert "error" in data
            assert "install_command" in data
    
    @pytest.mark.asyncio
    async def test_generate_video_unauthorized(self, client):
        """Test generar video sin autenticación"""
        response = await client.post(
            "/api/video/generate",
            data={
                "prompt": "Beautiful sunset",
                "duration_seconds": 5
            }
        )
        
        assert response.status_code == 401  # Unauthorized
    
    @pytest.mark.asyncio
    async def test_generate_video_invalid_duration(self, client, auth_headers):
        """Test generar video con duración inválida"""
        # Duración demasiado corta
        response = await client.post(
            "/api/video/generate",
            headers=auth_headers,
            data={
                "prompt": "Test video",
                "duration_seconds": 2  # Menos de 4 segundos
            }
        )
        
        assert response.status_code == 400
        assert "Duration must be between" in response.json()["detail"]
        
        # Duración demasiado larga
        response = await client.post(
            "/api/video/generate",
            headers=auth_headers,
            data={
                "prompt": "Test video",
                "duration_seconds": 15  # Más de 10 segundos
            }
        )
        
        assert response.status_code == 400
    
    @pytest.mark.asyncio
    async def test_generate_video_invalid_resolution(self, client, auth_headers):
        """Test generar video con resolución inválida"""
        response = await client.post(
            "/api/video/generate",
            headers=auth_headers,
            data={
                "prompt": "Test video",
                "duration_seconds": 5,
                "width": 3840,  # Mayor a 1920
                "height": 2160
            }
        )
        
        assert response.status_code == 400
        assert "Max resolution" in response.json()["detail"]
    
    @pytest.mark.asyncio
    async def test_generate_video_short_prompt(self, client, auth_headers):
        """Test generar video con prompt muy corto"""
        response = await client.post(
            "/api/video/generate",
            headers=auth_headers,
            data={
                "prompt": "short",  # Menos de 10 caracteres
                "duration_seconds": 5
            }
        )
        
        # FastAPI valida automáticamente min_length
        assert response.status_code in [400, 422]
    
    @pytest.mark.asyncio
    async def test_generate_story_unauthorized(self, client):
        """Test generar story sin autenticación"""
        response = await client.post(
            "/api/video/generate-story",
            data={"prompt": "Motivational quote"}
        )
        
        assert response.status_code == 401
    
    @pytest.mark.asyncio
    async def test_download_video_not_found(self, client, auth_headers):
        """Test descargar video inexistente"""
        response = await client.get(
            "/api/video/download/nonexistent_video_id",
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HUNYUAN_AVAILABLE, reason="HunyuanVideo not available")
    async def test_load_model_endpoint(self, client, auth_headers):
        """Test endpoint para cargar modelo"""
        response = await client.post(
            "/api/video/load-model",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "message" in data
    
    @pytest.mark.asyncio
    @pytest.mark.skipif(not HUNYUAN_AVAILABLE, reason="HunyuanVideo not available")
    async def test_unload_model_endpoint(self, client, auth_headers):
        """Test endpoint para descargar modelo"""
        response = await client.post(
            "/api/video/unload-model",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestVideoWhatsAppIntegration:
    """Tests para integración con WhatsApp Stories"""
    
    @pytest.mark.asyncio
    async def test_generate_and_create_story_flow(self, client, auth_headers):
        """Test flujo completo: generar video + crear story"""
        
        # Paso 1: Generar video optimizado para story
        video_response = await client.post(
            "/api/video/generate-story",
            headers=auth_headers,
            data={
                "prompt": "Inspirational sunrise with motivational quote"
            }
        )
        
        if video_response.status_code == 503:
            pytest.skip("Video generation service not available")
        
        assert video_response.status_code == 200
        video_data = video_response.json()
        
        assert video_data["success"] is True
        assert "video" in video_data
        assert video_data["video"]["resolution"] == "720x1280"  # Vertical
        assert video_data["ready_for_whatsapp"] is True
        
        # Paso 2: Crear WhatsApp Story con el video
        story_response = await client.post(
            "/api/whatsapp/stories",
            headers=auth_headers,
            json={
                "content_type": "VIDEO",
                "content_url": video_data["video"]["video_url"],
                "caption": "🎬 AI-generated story!",
                "privacy": "PUBLIC"
            }
        )
        
        assert story_response.status_code == 200
        story_data = story_response.json()
        
        assert story_data["success"] is True
        assert story_data["story"]["content_type"] == "VIDEO"
        assert story_data["story"]["content_url"] == video_data["video"]["video_url"]


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================

class TestVideoGenerationPerformance:
    """Tests de performance para generación de videos"""
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_generation_time_low_quality(self):
        """Test tiempo de generación con calidad baja"""
        from services.hunyuan_video_service import get_hunyuan_video_service
        import time
        
        service = get_hunyuan_video_service()
        
        if not service.is_loaded:
            pytest.skip("Model not loaded")
        
        start_time = time.time()
        
        result = await service.generate_video(
            prompt="Simple test video",
            num_frames=120,  # 4 segundos
            width=1280,
            height=720,
            num_inference_steps=30,  # Calidad baja
            user_id="test_perf"
        )
        
        elapsed = time.time() - start_time
        
        # Calidad baja debería ser < 35 segundos
        assert elapsed < 35
        assert result["generation_time_seconds"] < 35
    
    @pytest.mark.asyncio
    async def test_vram_usage_monitoring(self):
        """Test monitoreo de uso de VRAM"""
        from services.hunyuan_video_service import get_hunyuan_video_service
        
        service = get_hunyuan_video_service()
        status = service.get_status()
        
        if status["device"] == "cuda":
            # Si hay GPU, debería reportar VRAM
            assert status["vram_used_gb"] >= 0
            assert status["vram_total_gb"] > 0
            
            # Si modelo está cargado, debería usar VRAM
            if service.is_loaded:
                assert status["vram_used_gb"] > 10  # Mínimo 10 GB


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def client():
    """Cliente HTTP para tests"""
    from httpx import AsyncClient
    from main import app
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers():
    """Headers de autenticación para tests"""
    # Mock token - en producción usar token real de test
    return {
        "Authorization": "Bearer test_token_12345"
    }


# ============================================================================
# CONFTEST
# ============================================================================

from services.hunyuan_video_service import HUNYUAN_AVAILABLE

def pytest_configure(config):
    """Configuración de pytest"""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    
    if not HUNYUAN_AVAILABLE:
        print("\n⚠️  HunyuanVideo dependencies not installed. Some tests will be skipped.")
        print("Install with: pip install diffusers transformers accelerate\n")
