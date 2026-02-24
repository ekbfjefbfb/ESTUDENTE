"""
Backend Super IA - Enterprise Production v3.0
Entry point para el servidor
"""
from main import app

if __name__ == "__main__":
    import uvicorn
    import os
    
    # Configuración del servidor
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    workers = int(os.getenv("WORKERS", "4"))
    reload = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")
    
    print(f"""
    ╔═══════════════════════════════════════════════════════════════╗
    ║                                                               ║
    ║           🚀 BACKEND SUPER IA - ENTERPRISE v3.0              ║
    ║                                                               ║
    ║           Modelo IA: Grok-2 Fast Reasoning                   ║
    ║           Host: {host}:{port}                                  ║
    ║           Workers: {workers}                                   ║
    ║           Debug: {reload}                                      ║
    ║                                                               ║
    ╚═══════════════════════════════════════════════════════════════╝
    """)
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=reload,
        workers=1 if reload else workers,
        log_level="info",
        access_log=True
    )
