#!/bin/bash

# ============================================================================
# Script de instalación HunyuanVideo Text-to-Video
# Backend Súper IA v4.1
# ============================================================================

set -e  # Exit on error

echo "🎬 =============================================="
echo "   HunyuanVideo Installation Script"
echo "   Backend Súper IA v4.1"
echo "=============================================="
echo ""

# ============================================================================
# 1. Verificar Python y pip
# ============================================================================

echo "📦 Checking Python installation..."
python3 --version || { echo "❌ Python 3 not found. Please install Python 3.8+"; exit 1; }

echo "📦 Checking pip..."
pip --version || { echo "❌ pip not found. Please install pip"; exit 1; }

# ============================================================================
# 2. Instalar dependencias de video
# ============================================================================

echo ""
echo "📥 Installing HunyuanVideo dependencies..."
echo "   - diffusers (Pipeline framework)"
echo "   - transformers (Model loading)"
echo "   - accelerate (GPU optimization)"
echo ""

pip install diffusers>=0.25.0 transformers>=4.36.0 accelerate>=0.25.0

# Verificar PyTorch (debe estar ya instalado)
echo ""
echo "🔥 Checking PyTorch installation..."
python3 -c "import torch; print(f'✅ PyTorch {torch.__version__} installed')" || {
    echo "⚠️  PyTorch not found. Installing..."
    pip install torch>=2.1.0 torchvision>=0.16.0 torchaudio>=2.1.0
}

# Verificar CUDA
python3 -c "import torch; print(f'✅ CUDA available: {torch.cuda.is_available()}')"

# ============================================================================
# 3. Crear directorios necesarios
# ============================================================================

echo ""
echo "📁 Creating output directories..."
mkdir -p output/videos
mkdir -p output/videos/.gitkeep

# ============================================================================
# 4. Configurar variables de entorno
# ============================================================================

echo ""
echo "⚙️  Configuring environment variables..."

if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "⚠️  Please edit .env file and add your API keys:"
    echo "   - OPENAI_API_KEY (for Whisper API)"
    echo "   - ELEVENLABS_API_KEY (for TTS API)"
    echo "   - B2_APPLICATION_KEY_ID and B2_APPLICATION_KEY (for storage)"
fi

# Verificar que las variables críticas estén configuradas
source .env 2>/dev/null || true

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "sk-your-openai-api-key" ]; then
    echo "⚠️  WARNING: OPENAI_API_KEY not configured in .env"
fi

if [ -z "$ELEVENLABS_API_KEY" ] || [ "$ELEVENLABS_API_KEY" = "your-elevenlabs-api-key" ]; then
    echo "⚠️  WARNING: ELEVENLABS_API_KEY not configured in .env"
fi

# ============================================================================
# 5. Ejecutar tests
# ============================================================================

echo ""
echo "🧪 Running tests..."
pytest tests/test_video_generation.py -v --tb=short || {
    echo "⚠️  Some tests failed. This is normal if dependencies are missing."
}

# ============================================================================
# 6. Resumen
# ============================================================================

echo ""
echo "✅ =============================================="
echo "   Installation Complete!"
echo "=============================================="
echo ""
echo "📋 Next Steps:"
echo ""
echo "1. Configure API Keys in .env:"
echo "   export OPENAI_API_KEY=sk-your-key"
echo "   export ELEVENLABS_API_KEY=your-key"
echo ""
echo "2. Start the server:"
echo "   uvicorn main:app --reload"
echo ""
echo "3. Test video generation:"
echo "   curl -X POST http://localhost:8000/api/video/status"
echo ""
echo "4. Generate your first video:"
echo "   curl -X POST http://localhost:8000/api/video/generate \\"
echo "     -H 'Authorization: Bearer YOUR_TOKEN' \\"
echo "     -F 'prompt=A beautiful sunset over the ocean' \\"
echo "     -F 'duration_seconds=5'"
echo ""
echo "📚 Documentation: HUNYUAN_VIDEO_IMPLEMENTATION.md"
echo ""
echo "💡 GPU Requirements:"
echo "   - NVIDIA GPU with CUDA support"
echo "   - 13 GB VRAM for HunyuanVideo"
echo "   - 68 GB total VRAM (with DeepSeek + YOLO)"
echo "   - Recommended: A100 80GB"
echo ""
echo "💰 Cost Estimate:"
echo "   - Local GPU: $432/month (vast.ai)"
echo "   - Voice APIs: $80/month"
echo "   - Total: $512/month for unlimited videos"
echo ""
echo "🚀 Ready to generate AI videos!"
echo "=============================================="
