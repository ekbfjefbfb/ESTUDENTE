import os


class Settings:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()

    # Ambos modelos usan llama-4-scout para vision/transcripción/resumen
    LLM_FAST_MODEL: str = os.getenv(
        "GROQ_LLM_FAST_MODEL",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ).strip()
    LLM_REASONING_MODEL: str = os.getenv(
        "GROQ_LLM_REASONING_MODEL",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    ).strip()

    # SQLITE_PATH mantenido solo por compatibilidad — NO se usa en producción
    # El storage migró a Nhost PostgreSQL (notes_grpc/storage.py)
    SQLITE_PATH: str = os.getenv("NOTES_SQLITE_PATH", "notes.db").strip()

    GRPC_HOST: str = os.getenv("GRPC_HOST", "0.0.0.0").strip()
    GRPC_PORT: int = int(os.getenv("GRPC_PORT", "50051"))


settings = Settings()

