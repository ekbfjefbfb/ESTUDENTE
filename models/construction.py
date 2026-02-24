"""
Modelos para Sector CONSTRUCCIÓN v6.0
Gestión de proyectos de obras con análisis IA
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, JSON, Text, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from database.database import Base


class ConstructionProject(Base):
    """Proyecto de construcción/obra"""
    __tablename__ = "construction_projects"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Relación con cliente
    client_id = Column(Integer, nullable=False, index=True)
    # ForeignKey a clients.id (pero sin relationship para evitar dependencias circulares)
    
    # Info básica del proyecto
    name = Column(String(255), nullable=False)  # "Torre Residencial Las Palmas"
    description = Column(Text)
    project_type = Column(String(50))  # "residential", "commercial", "industrial", "infrastructure"
    
    # Ubicación
    address = Column(String(500))
    city = Column(String(100))
    state = Column(String(100))
    country = Column(String(100), default="México")
    coordinates = Column(JSON)  # {"lat": 19.4326, "lng": -99.1332}
    
    # Timeline
    start_date = Column(DateTime)
    estimated_end_date = Column(DateTime)
    actual_end_date = Column(DateTime)
    
    # Budget
    total_budget = Column(Float)  # Budget total en pesos
    current_spent = Column(Float, default=0.0)  # Gastado hasta ahora
    
    # Estado y progreso
    status = Column(String(50), default="planning")  
    # Estados: "planning", "in_progress", "on_hold", "delayed", "completed", "cancelled"
    
    progress_percentage = Column(Float, default=0.0)  # 0-100
    last_progress_update = Column(DateTime)
    
    # Equipo
    project_manager = Column(String(255))  # Nombre del director de obra
    architect = Column(String(255))
    contractor = Column(String(255))  # Empresa constructora
    team_size = Column(Integer)  # Número de trabajadores
    
    # Configuración específica del proyecto
    sector_config = Column(JSON, default={})
    """
    Estructura:
    {
        "phases": [
            {"name": "Cimentación", "status": "completed", "progress": 100},
            {"name": "Estructura", "status": "in_progress", "progress": 60},
            {"name": "Acabados", "status": "pending", "progress": 0}
        ],
        "materials": {
            "cement": {"ordered": 1000, "delivered": 800, "used": 600},
            "steel": {"ordered": 500, "delivered": 500, "used": 400}
        },
        "safety_incidents": 0,
        "inspections_passed": 5,
        "inspections_pending": 2,
        "permits": ["construccion", "agua", "electricidad"],
        "milestones": [
            {"name": "Excavación completa", "date": "2025-11-15", "status": "completed"},
            {"name": "Estructura terminada", "date": "2026-03-01", "status": "pending"}
        ]
    }
    """
    
    # Alertas y monitoreo
    alerts_enabled = Column(Boolean, default=True)
    alert_on_delays = Column(Boolean, default=True)
    alert_on_budget_overrun = Column(Boolean, default=True)
    alert_on_safety_issues = Column(Boolean, default=True)
    
    # Reportes automáticos
    auto_reports_enabled = Column(Boolean, default=False)
    report_frequency = Column(String(20))  # "weekly", "biweekly", "monthly"
    report_recipients = Column(JSON)  # Lista de emails
    
    # Integraciones
    drive_folder_id = Column(String(255))  # Carpeta en Google Drive
    whatsapp_group_id = Column(String(255))  # ID del grupo de WhatsApp
    
    # Metadatos
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer)  # User ID
    
    notes = Column(Text)  # Notas internas
    
    # Relationships
    # photos = relationship("ProgressPhoto", back_populates="project")
    # materials = relationship("MaterialTracking", back_populates="project")
    # inspections = relationship("Inspection", back_populates="project")
    
    def __repr__(self):
        return f"<ConstructionProject {self.name} ({self.progress_percentage}%)>"
    
    def to_dict(self):
        """Convertir a diccionario para API responses"""
        return {
            "id": self.id,
            "client_id": self.client_id,
            "name": self.name,
            "description": self.description,
            "project_type": self.project_type,
            "location": {
                "address": self.address,
                "city": self.city,
                "state": self.state,
                "country": self.country,
                "coordinates": self.coordinates
            },
            "timeline": {
                "start_date": self.start_date.isoformat() if self.start_date else None,
                "estimated_end_date": self.estimated_end_date.isoformat() if self.estimated_end_date else None,
                "actual_end_date": self.actual_end_date.isoformat() if self.actual_end_date else None
            },
            "budget": {
                "total": self.total_budget,
                "spent": self.current_spent,
                "remaining": self.total_budget - self.current_spent if self.total_budget else 0,
                "percentage_spent": (self.current_spent / self.total_budget * 100) if self.total_budget else 0
            },
            "status": self.status,
            "progress": {
                "percentage": self.progress_percentage,
                "last_update": self.last_progress_update.isoformat() if self.last_progress_update else None
            },
            "team": {
                "project_manager": self.project_manager,
                "architect": self.architect,
                "contractor": self.contractor,
                "team_size": self.team_size
            },
            "config": self.sector_config or {},
            "alerts": {
                "enabled": self.alerts_enabled,
                "on_delays": self.alert_on_delays,
                "on_budget_overrun": self.alert_on_budget_overrun,
                "on_safety_issues": self.alert_on_safety_issues
            },
            "auto_reports": {
                "enabled": self.auto_reports_enabled,
                "frequency": self.report_frequency,
                "recipients": self.report_recipients or []
            },
            "integrations": {
                "drive_folder_id": self.drive_folder_id,
                "whatsapp_group_id": self.whatsapp_group_id
            },
            "metadata": {
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None,
                "created_by": self.created_by
            },
            "notes": self.notes
        }


class ProgressPhoto(Base):
    """Foto de progreso de obra con análisis IA"""
    __tablename__ = "progress_photos"
    
    id = Column(Integer, primary_key=True, index=True)
    
    project_id = Column(Integer, nullable=False, index=True)
    # ForeignKey a construction_projects.id
    
    # Info de la foto
    filename = Column(String(500), nullable=False)
    drive_file_id = Column(String(255))
    drive_link = Column(String(500))
    local_path = Column(String(500))
    
    # Metadata de la foto
    file_size = Column(Integer)  # Bytes
    dimensions = Column(String(50))  # "1920x1080"
    capture_date = Column(DateTime)
    
    # Ubicación de la foto
    location_description = Column(String(255))  # "Planta baja - área de cocina"
    phase = Column(String(100))  # "Cimentación", "Estructura", "Acabados"
    coordinates = Column(JSON)  # GPS si disponible
    
    # 🤖 ANÁLISIS IA
    ai_analysis = Column(JSON, default={})
    """
    Estructura del análisis IA:
    {
        "progress_detected": {
            "percentage": 65,
            "description": "Estructura de columnas 65% completa",
            "elements_completed": ["columnas A1-A5", "viga principal"],
            "elements_pending": ["columnas B1-B3", "losa superior"]
        },
        "quality_assessment": {
            "score": 85,
            "issues": ["pequeña grieta en columna A3"],
            "recommendations": ["revisar nivelación de losa", "aplicar sellador en grieta"]
        },
        "safety_issues": {
            "detected": true,
            "critical": false,
            "issues": ["falta casco en 1 trabajador", "materiales mal almacenados"],
            "priority": "medium"
        },
        "materials_visible": ["cemento", "varilla", "encofrado", "andamios"],
        "weather_conditions": "soleado",
        "timestamp": "2025-11-06T10:30:00Z",
        "confidence": 0.87
    }
    """
    
    ai_analyzed = Column(Boolean, default=False)
    ai_analysis_date = Column(DateTime)
    
    # Tags y categorización
    tags = Column(JSON)  # ["exterior", "estructura", "semana-45"]
    category = Column(String(100))  # "progress", "safety", "quality", "delivery"
    
    # Estado
    status = Column(String(50), default="pending_review")
    # Estados: "pending_review", "approved", "flagged", "archived"
    
    reviewed_by = Column(Integer)  # User ID
    reviewed_at = Column(DateTime)
    review_notes = Column(Text)
    
    # Comparación con foto anterior
    comparison_with_previous = Column(JSON)  # Diff con última foto
    progress_since_last = Column(Float)  # % de avance desde última foto
    
    # Metadatos
    uploaded_by = Column(Integer)  # User ID
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    notes = Column(Text)
    
    def __repr__(self):
        return f"<ProgressPhoto {self.filename} (Project {self.project_id})>"
    
    def to_dict(self):
        """Convertir a diccionario para API responses"""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "filename": self.filename,
            "drive_link": self.drive_link,
            "file_size": self.file_size,
            "dimensions": self.dimensions,
            "capture_date": self.capture_date.isoformat() if self.capture_date else None,
            "location": {
                "description": self.location_description,
                "phase": self.phase,
                "coordinates": self.coordinates
            },
            "ai_analysis": self.ai_analysis or {},
            "ai_analyzed": self.ai_analyzed,
            "ai_analysis_date": self.ai_analysis_date.isoformat() if self.ai_analysis_date else None,
            "tags": self.tags or [],
            "category": self.category,
            "status": self.status,
            "reviewed": {
                "by": self.reviewed_by,
                "at": self.reviewed_at.isoformat() if self.reviewed_at else None,
                "notes": self.review_notes
            },
            "comparison": {
                "with_previous": self.comparison_with_previous or {},
                "progress_since_last": self.progress_since_last
            },
            "metadata": {
                "uploaded_by": self.uploaded_by,
                "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None
            },
            "notes": self.notes
        }


class MaterialTracking(Base):
    """Tracking de materiales de construcción"""
    __tablename__ = "material_tracking"
    
    id = Column(Integer, primary_key=True, index=True)
    
    project_id = Column(Integer, nullable=False, index=True)
    
    # Material
    material_name = Column(String(255), nullable=False)  # "Cemento Portland"
    material_type = Column(String(100))  # "cement", "steel", "wood", "paint"
    unit = Column(String(50))  # "tons", "m3", "pieces", "liters"
    
    # Cantidades
    quantity_ordered = Column(Float)
    quantity_delivered = Column(Float, default=0.0)
    quantity_used = Column(Float, default=0.0)
    quantity_remaining = Column(Float, default=0.0)
    
    # Costos
    unit_price = Column(Float)
    total_cost = Column(Float)
    
    # Proveedor
    supplier = Column(String(255))
    supplier_contact = Column(String(255))
    
    # Timeline
    order_date = Column(DateTime)
    expected_delivery_date = Column(DateTime)
    actual_delivery_date = Column(DateTime)
    
    # Estado
    status = Column(String(50), default="ordered")
    # Estados: "ordered", "in_transit", "delivered", "in_use", "depleted"
    
    # Alertas
    alert_on_low_stock = Column(Boolean, default=True)
    low_stock_threshold = Column(Float)  # % para alerta
    
    # Metadatos
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    notes = Column(Text)
    
    def __repr__(self):
        return f"<MaterialTracking {self.material_name} (Project {self.project_id})>"


class Inspection(Base):
    """Inspecciones de obra"""
    __tablename__ = "inspections"
    
    id = Column(Integer, primary_key=True, index=True)
    
    project_id = Column(Integer, nullable=False, index=True)
    
    # Info de la inspección
    inspection_type = Column(String(100))  # "safety", "quality", "structural", "electrical"
    inspector_name = Column(String(255))
    inspector_company = Column(String(255))
    
    # Resultado
    status = Column(String(50))  # "passed", "failed", "conditional", "pending"
    score = Column(Integer)  # 0-100
    
    # Detalles
    inspection_date = Column(DateTime)
    findings = Column(JSON)  # Lista de hallazgos
    recommendations = Column(JSON)  # Lista de recomendaciones
    
    # Documentos
    report_url = Column(String(500))  # Link al reporte PDF
    photos = Column(JSON)  # Lista de IDs de fotos relacionadas
    
    # Seguimiento
    requires_followup = Column(Boolean, default=False)
    followup_date = Column(DateTime)
    followup_completed = Column(Boolean, default=False)
    
    # Metadatos
    created_at = Column(DateTime, default=datetime.utcnow)
    
    notes = Column(Text)
    
    def __repr__(self):
        return f"<Inspection {self.inspection_type} ({self.status})>"
