"""
Script para crear las tablas de Construcción
"""

from sqlalchemy import create_engine
from models.construction import Base, ConstructionProject, ProgressPhoto, MaterialTracking, Inspection
from config import DATABASE_URL_SYNC

def create_construction_tables():
    """Crear todas las tablas de construcción"""
    
    # Usar SQLite local para desarrollo
    database_url = DATABASE_URL_SYNC or "sqlite:///./backend_super.db"
    
    print(f"🏗️ Conectando a: {database_url}")
    
    engine = create_engine(database_url, echo=True)
    
    print("\n🔨 Creando tablas de Construcción...")
    
    # Crear solo las tablas de construction.py
    Base.metadata.create_all(
        bind=engine,
        tables=[
            ConstructionProject.__table__,
            ProgressPhoto.__table__,
            MaterialTracking.__table__,
            Inspection.__table__
        ]
    )
    
    print("\n✅ Tablas de Construcción creadas exitosamente!")
    print("\n📋 Tablas disponibles:")
    print("  - construction_projects (proyectos de obra)")
    print("  - progress_photos (fotos con análisis IA)")
    print("  - material_tracking (seguimiento materiales)")
    print("  - inspections (inspecciones de obra)")
    
    print("\n🎯 Próximo paso: Crear router y servicio")
    print("   - routers/construction_router.py")
    print("   - services/construction_service.py")


if __name__ == "__main__":
    create_construction_tables()
