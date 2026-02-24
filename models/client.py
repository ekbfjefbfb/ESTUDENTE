"""
Modelo de Cliente para agencias de marketing
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, Text, Float
from sqlalchemy.orm import relationship
from datetime import datetime
from database.database import Base


class Client(Base):
    __tablename__ = "clients"
    
    id = Column(Integer, primary_key=True, index=True)
    
        # Info básica
    name = Column(String(255), nullable=False)
    company = Column(String(255))
    
    # 🆕 MULTI-SECTOR v6.0
    sector = Column(String(50), nullable=False, default="marketing")
    # Valores: "marketing", "construction", "healthcare", "education", "finance"
    
    industry = Column(String(100))  # e.g. "deportes", "tecnología", "moda"
    website = Column(String(512))
    
    # Estado
    active = Column(Boolean, default=True)
    status = Column(String(50), default="active")  # "active", "paused", "churned"
    
    # Contactos
    primary_contact_name = Column(String(255))
    primary_contact_email = Column(String(255))
    primary_contact_phone = Column(String(50))
    
    # Integraciones
    google_analytics_property_id = Column(String(255))  # GA4 property ID
    meta_ads_account_id = Column(String(255))  # Facebook Ads account ID
    google_ads_customer_id = Column(String(255))  # Google Ads customer ID
    
    # Slack
    slack_workspace_id = Column(String(255))
    slack_channel = Column(String(255))  # Canal para notificaciones
    slack_channel_id = Column(String(255))
    
    # Google Workspace
    google_drive_folder_id = Column(String(255))  # Carpeta raíz en Drive
    google_workspace_email = Column(String(255))  # Email de la cuenta conectada
    
    # Reportes automáticos
    auto_reports_enabled = Column(Boolean, default=False)
    report_frequency = Column(String(20))  # "weekly", "monthly", "biweekly"
    report_day = Column(String(20))  # "monday", "friday", "1" (día del mes)
    report_time = Column(String(10), default="09:00")  # HH:MM
    report_recipients = Column(JSON)  # Lista de emails: ["cliente@empresa.com", "manager@agencia.com"]
    report_include_sections = Column(JSON)  # ["overview", "metrics", "insights", "recommendations"]
    
    # Monitoreo proactivo
    monitoring_enabled = Column(Boolean, default=True)
    alert_on_ctr_drop = Column(Boolean, default=True)
    alert_on_budget_overspend = Column(Boolean, default=True)
    alert_on_zero_impressions = Column(Boolean, default=True)
    
    # Budget y facturación
    monthly_budget = Column(Float)  # Budget del cliente (opcional)
    contract_start_date = Column(DateTime)
    contract_end_date = Column(DateTime)
    
    # Personalización
    brand_colors = Column(JSON)  # {"primary": "#FF6900", "secondary": "#000000"}
    logo_url = Column(String(500))
    
    # Preferencias de IA
    ai_personality = Column(String(50), default="emprendedor")  # Personalidad por defecto
    ai_tone = Column(String(50), default="professional")  # "casual", "professional", "friendly"
    
    # 🆕 MULTI-SECTOR v6.0: Configuración específica por sector
    sector_config = Column(JSON, default={})
    """
    Configuración flexible por sector:
    
    MARKETING: {"google_analytics_property_id": "...", "meta_ads_account_id": "...", "monthly_ad_budget": 5000}
    CONSTRUCTION: {"projects": [...], "photo_analysis_enabled": true}
    HEALTHCARE: {"specialties": [...], "appointment_reminders": true}
    EDUCATION: {"courses": [...], "auto_grading_enabled": true}
    FINANCE: {"accounting_system": "quickbooks", "alert_thresholds": {...}}
    """
    
    # Metadatos
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(Integer)  # User ID del creador
    
    # Notas internas
    notes = Column(Text)  # Notas del account manager
    
    # Configuración adicional
    config = Column(JSON)  # Configuración flexible
    
    # Relationships
    # report_logs = relationship("ReportLog", back_populates="client")
    # tasks = relationship("Task", back_populates="client")
    # assets = relationship("Asset", back_populates="client")
    
    def __repr__(self):
        return f"<Client {self.name} (ID: {self.id})>"
    
    def to_dict(self):
        """Convertir a diccionario para API responses"""
        return {
            "id": self.id,
            "name": self.name,
            "company": self.company,
            "industry": self.industry,
            "website": self.website,
            "active": self.active,
            "status": self.status,
            "primary_contact": {
                "name": self.primary_contact_name,
                "email": self.primary_contact_email,
                "phone": self.primary_contact_phone
            },
            "integrations": {
                "google_analytics": {
                    "property_id": self.google_analytics_property_id,
                    "connected": bool(self.google_analytics_property_id)
                },
                "meta_ads": {
                    "account_id": self.meta_ads_account_id,
                    "connected": bool(self.meta_ads_account_id)
                },
                "google_ads": {
                    "customer_id": self.google_ads_customer_id,
                    "connected": bool(self.google_ads_customer_id)
                },
                "slack": {
                    "channel": self.slack_channel,
                    "connected": bool(self.slack_channel_id)
                },
                "google_drive": {
                    "folder_id": self.google_drive_folder_id,
                    "connected": bool(self.google_drive_folder_id)
                }
            },
            "auto_reports": {
                "enabled": self.auto_reports_enabled,
                "frequency": self.report_frequency,
                "day": self.report_day,
                "time": self.report_time,
                "recipients": self.report_recipients or [],
                "sections": self.report_include_sections or []
            },
            "monitoring": {
                "enabled": self.monitoring_enabled,
                "alerts": {
                    "ctr_drop": self.alert_on_ctr_drop,
                    "budget_overspend": self.alert_on_budget_overspend,
                    "zero_impressions": self.alert_on_zero_impressions
                }
            },
            "budget": {
                "monthly": self.monthly_budget,
                "contract_start": self.contract_start_date.isoformat() if self.contract_start_date else None,
                "contract_end": self.contract_end_date.isoformat() if self.contract_end_date else None
            },
            "brand": {
                "colors": self.brand_colors or {},
                "logo_url": self.logo_url
            },
            "ai_preferences": {
                "personality": self.ai_personality,
                "tone": self.ai_tone
            },
            "metadata": {
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None,
                "created_by": self.created_by
            },
            "notes": self.notes
        }


class ReportLog(Base):
    """Log de reportes enviados"""
    __tablename__ = "report_logs"
    
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, nullable=False, index=True)
    
    report_type = Column(String(50))  # "weekly", "monthly", "on-demand"
    status = Column(String(50))  # "sent", "failed", "pending"
    
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    
    sent_at = Column(DateTime, default=datetime.utcnow)
    drive_link = Column(String(500))
    recipients = Column(Text)  # Comma-separated emails
    
    error_message = Column(Text)  # Si falló
    
    extra_metadata = Column(JSON)  # Info adicional (renamed from metadata to avoid SQLAlchemy conflict)
    
    def __repr__(self):
        return f"<ReportLog {self.report_type} for Client {self.client_id}>"


class Task(Base):
    """Tareas del equipo por cliente"""
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, nullable=False, index=True)
    
    title = Column(String(500), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="pending")  # "pending", "in_progress", "completed", "cancelled"
    priority = Column(String(20), default="medium")  # "low", "medium", "high", "urgent"
    
    assigned_to = Column(Integer)  # User ID
    created_by = Column(Integer)  # User ID
    
    deadline = Column(DateTime)
    completed_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    slack_message_ts = Column(String(100))  # Timestamp del mensaje en Slack
    
    extra_metadata = Column(JSON)  # Renamed from metadata to avoid SQLAlchemy conflict
    
    def __repr__(self):
        return f"<Task {self.title} for Client {self.client_id}>"


class Asset(Base):
    """Assets (imágenes, videos, documentos) por cliente"""
    __tablename__ = "assets"
    
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, nullable=False, index=True)
    
    filename = Column(String(500), nullable=False)
    file_type = Column(String(50))  # "image", "video", "document", "design"
    category = Column(String(100))  # "banner", "post", "story", "ad", "logo"
    
    # Storage
    drive_file_id = Column(String(255))  # Google Drive file ID
    drive_link = Column(String(500))
    local_path = Column(String(500))  # Si se guarda local también
    
    # Metadata del archivo
    file_size = Column(Integer)  # Bytes
    dimensions = Column(String(50))  # "1080x1080" para imágenes
    duration = Column(Integer)  # Segundos para videos
    
    # Análisis IA
    ai_analysis = Column(JSON)  # Resultado de vision pipeline
    tags = Column(JSON)  # ["nike", "shoes", "summer", "ad"]
    
    # Aprobaciones
    requires_approval = Column(Boolean, default=False)
    status = Column(String(50), default="draft")  # "draft", "pending_approval", "approved", "rejected"
    approved_by = Column(Integer)  # User ID
    approved_at = Column(DateTime)
    rejection_reason = Column(Text)
    
    # Metadata
    uploaded_by = Column(Integer)  # User ID
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    
    notes = Column(Text)
    extra_metadata = Column(JSON)  # Renamed from metadata to avoid SQLAlchemy conflict
    
    def __repr__(self):
        return f"<Asset {self.filename} for Client {self.client_id}>"
