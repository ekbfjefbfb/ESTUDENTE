"""
Script para crear las tablas de clientes directamente
Sin depender de migraciones Alembic
"""

from sqlalchemy import create_engine
from models.client import Base, Client, ReportLog, Task, Asset
from config import DATABASE_URL_SYNC

def create_tables():
    """Crear todas las tablas de clientes"""
    
    # Usar SQLite local para desarrollo
    database_url = DATABASE_URL_SYNC or "sqlite:///./backend_super.db"
    
    print(f"📊 Conectando a: {database_url}")
    
    engine = create_engine(database_url, echo=True)
    
    print("\n🔨 Creando tablas...")
    
    # Crear solo las tablas de client.py
    Base.metadata.create_all(
        bind=engine,
        tables=[
            Client.__table__,
            ReportLog.__table__,
            Task.__table__,
            Asset.__table__
        ]
    )
    
    print("\n✅ Tablas creadas exitosamente!")
    print("\n📋 Tablas disponibles:")
    print("  - clients (con campos sector y sector_config)")
    print("  - report_logs")
    print("  - tasks")
    print("  - assets")
    
    print("\n🎯 Próximo paso: Insertar cliente de prueba")
    print("   python insert_test_client.py")


if __name__ == "__main__":
    create_tables()
