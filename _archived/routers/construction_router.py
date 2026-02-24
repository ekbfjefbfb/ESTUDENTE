"""
Router para Sector CONSTRUCCIÓN v6.0
Gestión de proyectos de obras con análisis IA de fotos
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

from database.database import get_async_db
from models.construction import ConstructionProject, ProgressPhoto, MaterialTracking, Inspection
from services.construction_service import construction_service

logger = logging.getLogger("construction_router")
router = APIRouter(prefix="/construction", tags=["Construction"])


# ============================================
# PYDANTIC SCHEMAS
# ============================================

class ProjectCreate(BaseModel):
    client_id: int
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = "residential"
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "México"
    start_date: Optional[datetime] = None
    estimated_end_date: Optional[datetime] = None
    total_budget: Optional[float] = None
    project_manager: Optional[str] = None
    architect: Optional[str] = None
    contractor: Optional[str] = None
    team_size: Optional[int] = None
    sector_config: Optional[dict] = {}
    auto_reports_enabled: bool = False
    report_frequency: Optional[str] = "weekly"
    report_recipients: Optional[List[str]] = []


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    progress_percentage: Optional[float] = None
    current_spent: Optional[float] = None
    estimated_end_date: Optional[datetime] = None
    actual_end_date: Optional[datetime] = None
    sector_config: Optional[dict] = None
    notes: Optional[str] = None


class PhotoUpload(BaseModel):
    location_description: Optional[str] = None
    phase: Optional[str] = None
    category: str = "progress"
    tags: Optional[List[str]] = []


class MaterialCreate(BaseModel):
    project_id: int
    material_name: str
    material_type: str
    unit: str = "tons"
    quantity_ordered: float
    unit_price: Optional[float] = None
    supplier: Optional[str] = None
    expected_delivery_date: Optional[datetime] = None


class InspectionCreate(BaseModel):
    project_id: int
    inspection_type: str
    inspector_name: str
    inspector_company: Optional[str] = None
    status: str = "pending"
    inspection_date: Optional[datetime] = None
    findings: Optional[List[str]] = []
    recommendations: Optional[List[str]] = []


# ============================================
# PROYECTOS - CRUD
# ============================================

@router.post("/projects", status_code=201)
async def create_project(
    project: ProjectCreate,
    user_email: Optional[str] = None,  # Para crear carpetas en Drive
    db: AsyncSession = Depends(get_async_db)
):
    """
    Crear nuevo proyecto de construcción
    
    Si se provee user_email, también crea estructura de carpetas en Google Drive
    
    Body:
    ```json
    {
        "client_id": 1,
        "name": "Torre Residencial Las Palmas",
        "project_type": "residential",
        "address": "Av. Principal 123",
        "city": "Ciudad de México",
        "start_date": "2025-11-01T00:00:00",
        "estimated_end_date": "2026-12-31T00:00:00",
        "total_budget": 5000000.00,
        "project_manager": "Ing. Juan Pérez",
        "contractor": "Constructora ABC S.A.",
        "auto_reports_enabled": true,
        "report_frequency": "weekly",
        "report_recipients": ["cliente@empresa.com", "gerente@constructora.com"]
    }
    ```
    
    Query params:
    - user_email: Email para crear carpetas en Google Drive (opcional)
    """
    
    new_project = ConstructionProject(**project.dict())
    new_project.created_at = datetime.utcnow()
    new_project.updated_at = datetime.utcnow()
    
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)
    
    response = {
        "success": True,
        "message": f"Proyecto '{project.name}' creado exitosamente",
        "project": new_project.to_dict()
    }
    
    # Crear estructura de carpetas en Drive si se provee email
    if user_email:
        try:
            drive_structure = await construction_service.create_project_drive_folder(
                user_email=user_email,
                project_name=project.name,
                project_id=new_project.id
            )
            
            if drive_structure.get('success'):
                # Actualizar proyecto con folder_id
                new_project.drive_folder_id = drive_structure['subcarpetas']['fotos_progreso']['id']
                await db.commit()
                
                response["drive"] = {
                    "created": True,
                    "structure_url": drive_structure.get('structure_url'),
                    "folders": {
                        "main": drive_structure['main_folder']['id'],
                        "photos": drive_structure['subcarpetas']['fotos_progreso']['id'],
                        "reports": drive_structure['subcarpetas']['reportes']['id'],
                        "inspections": drive_structure['subcarpetas']['inspecciones']['id'],
                        "materials": drive_structure['subcarpetas']['materiales']['id']
                    }
                }
            else:
                response["drive"] = {
                    "created": False,
                    "error": drive_structure.get('error')
                }
        
        except Exception as e:
            logger.error(f"Error creando estructura Drive: {str(e)}")
            response["drive"] = {"created": False, "error": str(e)}
    
    return response


@router.get("/projects")
async def list_projects(
    client_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Listar proyectos de construcción
    
    Query params:
    - client_id: Filtrar por cliente
    - status: Filtrar por estado (planning, in_progress, completed, etc.)
    - skip: Offset para paginación
    - limit: Límite de resultados
    """
    
    query = select(ConstructionProject)
    
    if client_id:
        query = query.where(ConstructionProject.client_id == client_id)
    if status:
        query = query.where(ConstructionProject.status == status)
    
    query = query.offset(skip).limit(limit).order_by(ConstructionProject.created_at.desc())
    
    result = await db.execute(query)
    projects = result.scalars().all()
    
    return {
        "success": True,
        "count": len(projects),
        "projects": [p.to_dict() for p in projects]
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Obtener detalles de un proyecto específico"""
    
    query = select(ConstructionProject).where(ConstructionProject.id == project_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Proyecto {project_id} no encontrado")
    
    # También traer fotos recientes
    photos_query = select(ProgressPhoto).where(
        ProgressPhoto.project_id == project_id
    ).order_by(ProgressPhoto.uploaded_at.desc()).limit(10)
    
    photos_result = await db.execute(photos_query)
    recent_photos = photos_result.scalars().all()
    
    return {
        "success": True,
        "project": project.to_dict(),
        "recent_photos": [p.to_dict() for p in recent_photos]
    }


@router.put("/projects/{project_id}")
async def update_project(
    project_id: int,
    updates: ProjectUpdate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Actualizar proyecto de construcción
    
    Body (todos opcionales):
    ```json
    {
        "status": "in_progress",
        "progress_percentage": 45.5,
        "current_spent": 2250000.00,
        "notes": "Fase de estructura completada"
    }
    ```
    """
    
    # Verificar que existe
    query = select(ConstructionProject).where(ConstructionProject.id == project_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Proyecto {project_id} no encontrado")
    
    # Actualizar campos
    update_data = updates.dict(exclude_unset=True)
    update_data["updated_at"] = datetime.utcnow()
    
    if "progress_percentage" in update_data:
        update_data["last_progress_update"] = datetime.utcnow()
    
    stmt = update(ConstructionProject).where(
        ConstructionProject.id == project_id
    ).values(**update_data)
    
    await db.execute(stmt)
    await db.commit()
    
    # Refrescar
    await db.refresh(project)
    
    return {
        "success": True,
        "message": f"Proyecto '{project.name}' actualizado",
        "project": project.to_dict()
    }


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Eliminar proyecto de construcción"""
    
    # Verificar que existe
    query = select(ConstructionProject).where(ConstructionProject.id == project_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Proyecto {project_id} no encontrado")
    
    project_name = project.name
    
    # Eliminar
    stmt = delete(ConstructionProject).where(ConstructionProject.id == project_id)
    await db.execute(stmt)
    await db.commit()
    
    return {
        "success": True,
        "message": f"Proyecto '{project_name}' eliminado"
    }


# ============================================
# FOTOS DE PROGRESO
# ============================================

@router.post("/projects/{project_id}/photos")
async def upload_progress_photo(
    project_id: int,
    file: UploadFile = File(...),
    location_description: Optional[str] = Form(None),
    phase: Optional[str] = Form(None),
    category: str = Form("progress"),
    user_email: Optional[str] = Form(None),  # Para integración Drive
    db: AsyncSession = Depends(get_async_db)
):
    """
    Subir foto de progreso con análisis IA automático
    
    Multipart form:
    - file: Imagen (JPG, PNG)
    - location_description: "Planta baja - cocina"
    - phase: "Estructura" | "Acabados" | etc.
    - category: "progress" | "safety" | "quality"
    - user_email: Email para subir a Google Drive (opcional)
    
    La foto se:
    1. Sube a Google Drive (si user_email provisto)
    2. Analiza automáticamente con IA
    3. Detecta: progreso, seguridad, calidad, materiales
    """
    
    # Verificar que el proyecto existe
    query = select(ConstructionProject).where(ConstructionProject.id == project_id)
    result = await db.execute(query)
    project = result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Proyecto {project_id} no encontrado")
    
    # Leer contenido del archivo
    file_content = await file.read()
    
    drive_info = None
    
    # Subir a Google Drive si se provee email
    if user_email and project.drive_folder_id:
        try:
            drive_info = await construction_service.upload_progress_photo_to_drive(
                user_email=user_email,
                photo_file=file_content,
                photo_filename=file.filename,
                project_folder_id=project.drive_folder_id,
                date=datetime.utcnow()
            )
            
            if not drive_info.get('success'):
                logger.warning(f"Foto no subida a Drive: {drive_info.get('error')}")
        
        except Exception as e:
            logger.error(f"Error subiendo a Drive: {str(e)}")
            # Continuar aunque falle Drive
    
    # TODO: Analizar con IA (GPT-4 Vision)
    # ai_analysis = await construction_service.analyze_progress_photo(
    #     photo_path=drive_info['web_content_link'] if drive_info else None,
    #     project_context=project.to_dict()
    # )
    
    # Crear registro en DB
    new_photo = ProgressPhoto(
        project_id=project_id,
        filename=file.filename,
        drive_file_id=drive_info.get('file_id') if drive_info else None,
        drive_link=drive_info.get('web_view_link') if drive_info else None,
        location_description=location_description,
        phase=phase,
        category=category,
        uploaded_at=datetime.utcnow(),
        status="pending_review",
        ai_analyzed=False  # Se analizará en background
    )
    
    db.add(new_photo)
    await db.commit()
    await db.refresh(new_photo)
    
    response = {
        "success": True,
        "message": f"Foto '{file.filename}' subida exitosamente",
        "photo": new_photo.to_dict()
    }
    
    if drive_info and drive_info.get('success'):
        response["drive"] = {
            "uploaded": True,
            "link": drive_info.get('web_view_link'),
            "folder": drive_info.get('month_folder')
        }
    
    response["note"] = "Análisis IA pendiente - se procesará en segundo plano"
    
    return response


@router.get("/projects/{project_id}/photos")
async def list_project_photos(
    project_id: int,
    phase: Optional[str] = None,
    category: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Listar fotos de un proyecto
    
    Query params:
    - phase: Filtrar por fase ("Cimentación", "Estructura", etc.)
    - category: Filtrar por categoría ("progress", "safety", "quality")
    """
    
    query = select(ProgressPhoto).where(ProgressPhoto.project_id == project_id)
    
    if phase:
        query = query.where(ProgressPhoto.phase == phase)
    if category:
        query = query.where(ProgressPhoto.category == category)
    
    query = query.order_by(ProgressPhoto.uploaded_at.desc()).offset(skip).limit(limit)
    
    result = await db.execute(query)
    photos = result.scalars().all()
    
    return {
        "success": True,
        "project_id": project_id,
        "count": len(photos),
        "photos": [p.to_dict() for p in photos]
    }


@router.get("/photos/{photo_id}/analysis")
async def get_photo_analysis(
    photo_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Obtener análisis IA de una foto específica"""
    
    query = select(ProgressPhoto).where(ProgressPhoto.id == photo_id)
    result = await db.execute(query)
    photo = result.scalar_one_or_none()
    
    if not photo:
        raise HTTPException(status_code=404, detail=f"Foto {photo_id} no encontrada")
    
    if not photo.ai_analyzed:
        return {
            "success": False,
            "message": "Análisis IA aún no disponible",
            "photo_id": photo_id,
            "status": "pending"
        }
    
    return {
        "success": True,
        "photo": photo.to_dict(),
        "analysis": photo.ai_analysis
    }


# ============================================
# MATERIALES
# ============================================

@router.post("/materials")
async def create_material_tracking(
    material: MaterialCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Crear registro de seguimiento de material
    
    Body:
    ```json
    {
        "project_id": 1,
        "material_name": "Cemento Portland",
        "material_type": "cement",
        "unit": "tons",
        "quantity_ordered": 100.0,
        "unit_price": 150.00,
        "supplier": "Cemex",
        "expected_delivery_date": "2025-11-15T00:00:00"
    }
    ```
    """
    
    new_material = MaterialTracking(**material.dict())
    new_material.created_at = datetime.utcnow()
    new_material.order_date = datetime.utcnow()
    
    # Calcular costo total
    if material.unit_price and material.quantity_ordered:
        new_material.total_cost = material.unit_price * material.quantity_ordered
    
    db.add(new_material)
    await db.commit()
    await db.refresh(new_material)
    
    return {
        "success": True,
        "message": f"Material '{material.material_name}' registrado",
        "material": {
            "id": new_material.id,
            "material_name": new_material.material_name,
            "quantity_ordered": new_material.quantity_ordered,
            "total_cost": new_material.total_cost,
            "status": new_material.status
        }
    }


@router.get("/projects/{project_id}/materials")
async def list_project_materials(
    project_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Listar materiales de un proyecto"""
    
    query = select(MaterialTracking).where(
        MaterialTracking.project_id == project_id
    ).order_by(MaterialTracking.created_at.desc())
    
    result = await db.execute(query)
    materials = result.scalars().all()
    
    # Calcular totales
    total_cost = sum(m.total_cost or 0 for m in materials)
    total_delivered = sum(m.quantity_delivered or 0 for m in materials)
    total_ordered = sum(m.quantity_ordered or 0 for m in materials)
    
    return {
        "success": True,
        "project_id": project_id,
        "count": len(materials),
        "totals": {
            "total_cost": total_cost,
            "delivery_rate": (total_delivered / total_ordered * 100) if total_ordered > 0 else 0
        },
        "materials": [{
            "id": m.id,
            "material_name": m.material_name,
            "material_type": m.material_type,
            "quantity_ordered": m.quantity_ordered,
            "quantity_delivered": m.quantity_delivered,
            "quantity_used": m.quantity_used,
            "quantity_remaining": m.quantity_remaining,
            "total_cost": m.total_cost,
            "supplier": m.supplier,
            "status": m.status
        } for m in materials]
    }


# ============================================
# INSPECCIONES
# ============================================

@router.post("/inspections")
async def create_inspection(
    inspection: InspectionCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Registrar nueva inspección
    
    Body:
    ```json
    {
        "project_id": 1,
        "inspection_type": "safety",
        "inspector_name": "Ing. María González",
        "inspector_company": "Seguridad Total S.A.",
        "status": "passed",
        "score": 92,
        "inspection_date": "2025-11-06T10:00:00",
        "findings": ["Todos los trabajadores usan casco", "Andamios bien asegurados"],
        "recommendations": ["Mejorar señalización en zona de carga"]
    }
    ```
    """
    
    new_inspection = Inspection(**inspection.dict())
    new_inspection.created_at = datetime.utcnow()
    
    db.add(new_inspection)
    await db.commit()
    await db.refresh(new_inspection)
    
    return {
        "success": True,
        "message": f"Inspección de {inspection.inspection_type} registrada",
        "inspection": {
            "id": new_inspection.id,
            "inspection_type": new_inspection.inspection_type,
            "inspector_name": new_inspection.inspector_name,
            "status": new_inspection.status,
            "score": new_inspection.score
        }
    }


@router.get("/projects/{project_id}/inspections")
async def list_project_inspections(
    project_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Listar inspecciones de un proyecto"""
    
    query = select(Inspection).where(
        Inspection.project_id == project_id
    ).order_by(Inspection.inspection_date.desc())
    
    result = await db.execute(query)
    inspections = result.scalars().all()
    
    # Calcular score promedio
    scores = [i.score for i in inspections if i.score is not None]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    return {
        "success": True,
        "project_id": project_id,
        "count": len(inspections),
        "average_score": round(avg_score, 2),
        "inspections": [{
            "id": i.id,
            "inspection_type": i.inspection_type,
            "inspector_name": i.inspector_name,
            "status": i.status,
            "score": i.score,
            "inspection_date": i.inspection_date.isoformat() if i.inspection_date else None,
            "findings": i.findings,
            "recommendations": i.recommendations
        } for i in inspections]
    }


# ============================================
# REPORTES
# ============================================

@router.get("/projects/{project_id}/progress-report")
async def generate_progress_report(
    project_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generar reporte de progreso del proyecto
    
    Incluye:
    - Estado general y % de avance
    - Fotos recientes con análisis IA
    - Materiales entregados vs pendientes
    - Inspecciones recientes
    - Alertas activas
    - Proyección de finalización
    """
    
    # Obtener proyecto
    project_query = select(ConstructionProject).where(ConstructionProject.id == project_id)
    project_result = await db.execute(project_query)
    project = project_result.scalar_one_or_none()
    
    if not project:
        raise HTTPException(status_code=404, detail=f"Proyecto {project_id} no encontrado")
    
    # Fotos recientes
    photos_query = select(ProgressPhoto).where(
        ProgressPhoto.project_id == project_id
    ).order_by(ProgressPhoto.uploaded_at.desc()).limit(5)
    photos_result = await db.execute(photos_query)
    recent_photos = photos_result.scalars().all()
    
    # Materiales
    materials_query = select(MaterialTracking).where(MaterialTracking.project_id == project_id)
    materials_result = await db.execute(materials_query)
    materials = materials_result.scalars().all()
    
    # Inspecciones recientes
    inspections_query = select(Inspection).where(
        Inspection.project_id == project_id
    ).order_by(Inspection.inspection_date.desc()).limit(3)
    inspections_result = await db.execute(inspections_query)
    recent_inspections = inspections_result.scalars().all()
    
    # Calcular métricas
    budget_spent_percentage = (project.current_spent / project.total_budget * 100) if project.total_budget else 0
    
    return {
        "success": True,
        "report": {
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "progress_percentage": project.progress_percentage,
                "start_date": project.start_date.isoformat() if project.start_date else None,
                "estimated_end_date": project.estimated_end_date.isoformat() if project.estimated_end_date else None
            },
            "budget": {
                "total": project.total_budget,
                "spent": project.current_spent,
                "remaining": project.total_budget - project.current_spent if project.total_budget else 0,
                "percentage_spent": round(budget_spent_percentage, 2)
            },
            "recent_photos": [p.to_dict() for p in recent_photos],
            "materials_summary": {
                "total_items": len(materials),
                "total_cost": sum(m.total_cost or 0 for m in materials),
                "delivered": sum(1 for m in materials if m.status == "delivered")
            },
            "recent_inspections": [{
                "inspection_type": i.inspection_type,
                "status": i.status,
                "score": i.score,
                "date": i.inspection_date.isoformat() if i.inspection_date else None
            } for i in recent_inspections]
        },
        "generated_at": datetime.utcnow().isoformat()
    }
