import os


class Settings:
    SILICONFLOW_API_KEY: str = os.getenv("SILICONFLOW_API_KEY", "").strip()
    SILICONFLOW_BASE_URL: str = os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1").strip()

    # Models
    LLM_MODEL: str = os.getenv("SILICONFLOW_LLM_MODEL", "deepseek-ai/DeepSeek-V3.2-Exp").strip()
    STT_MODEL: str = os.getenv("SILICONFLOW_STT_MODEL", "FunAudioLLM/SenseVoiceSmall").strip()

    # Storage
    SQLITE_PATH: str = os.getenv("NOTES_SQLITE_PATH", "notes.db").strip()

    # Server
    GRPC_HOST: str = os.getenv("GRPC_HOST", "0.0.0.0").strip()
    GRPC_PORT: int = int(os.getenv("GRPC_PORT", "50051"))


settings = Settings()
