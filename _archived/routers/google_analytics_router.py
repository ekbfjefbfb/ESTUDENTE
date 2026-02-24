"""
Router para Google Analytics 4 (GA4)
Integración con Google Analytics Data API v1beta

Usa GoogleAnalyticsService para extracción de métricas web
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Importar services
from services.google_analytics_service import get_google_analytics_service
from services.slack_service import get_slack_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/google-analytics", tags=["📊 Google Analytics 4"])


# ==========================================
# PYDANTIC MODELS
# ==========================================

class RealtimeRequest(BaseModel):
    property_id: Optional[str] = Field(default=None, description="GA4 property ID (usa default si no se proporciona)")
    metrics: Optional[List[str]] = Field(default=None, description="['activeUsers', 'screenPageViews', 'eventCount']")
    dimensions: Optional[List[str]] = Field(default=None, description="['country', 'deviceCategory', 'pagePath']")


class ReportRequest(BaseModel):
    property_id: Optional[str] = Field(default=None, description="GA4 property ID")
    start_date: str = Field(default="30daysAgo", description="30daysAgo, 7daysAgo, yesterday, YYYY-MM-DD")
    end_date: str = Field(default="today", description="today, yesterday, YYYY-MM-DD")
    metrics: Optional[List[str]] = Field(default=None, description="['sessions', 'totalUsers', 'bounceRate']")
    dimensions: Optional[List[str]] = Field(default=None, description="['date', 'country', 'source']")
    order_by: Optional[str] = Field(default=None, description="Métrica para ordenar (ej: sessions)")
    limit: int = Field(default=100, description="Máximo de filas")


class EcommerceRequest(BaseModel):
    property_id: Optional[str] = Field(default=None, description="GA4 property ID")
    start_date: str = Field(default="30daysAgo", description="Fecha inicio")
    end_date: str = Field(default="today", description="Fecha fin")


# ==========================================
# ENDPOINTS
# ==========================================

@router.post("/realtime")
async def get_realtime_data(request: RealtimeRequest):
    """
    ⏱️ Datos en tiempo real (últimos 30 minutos)
    
    **Retorna:**
    - active_users: Usuarios activos ahora
    - page_views: Páginas vistas últimos 30 min
    - events: Eventos totales
    - top_pages: Top 10 páginas más visitadas
    - top_countries: Top 10 países
    - devices: % Mobile, Desktop, Tablet
    
    **Ejemplo:**
    ```json
    {
      "property_id": "123456789",
      "metrics": ["activeUsers", "screenPageViews"],
      "dimensions": ["country", "deviceCategory"]
    }
    ```
    """
    try:
        service = get_google_analytics_service()
        
        data = await service.get_realtime_data(
            property_id=request.property_id,
            metrics=request.metrics,
            dimensions=request.dimensions
        )
        
        return data
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo realtime data GA4: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/report")
async def get_report_data(request: ReportRequest):
    """
    📈 Reportes históricos con dimensiones
    
    **Métricas disponibles:**
    - sessions: Total sesiones
    - totalUsers: Total usuarios
    - bounceRate: Tasa rebote (%)
    - averageSessionDuration: Duración promedio (segundos)
    - screenPageViews: Páginas vistas
    - engagementRate: Tasa engagement
    - newUsers: Usuarios nuevos
    
    **Dimensiones disponibles:**
    - date: Por fecha
    - country: Por país
    - deviceCategory: Por dispositivo (mobile, desktop, tablet)
    - source: Por fuente tráfico (google, direct, facebook)
    - medium: Por medio (organic, cpc, referral)
    - pagePath: Por página URL
    
    **Retorna:**
    - total_sessions, total_users
    - avg_bounce_rate, avg_session_duration
    - rows: Array con data por dimensión
    - summary: Métricas agregadas
    
    **Ejemplo:**
    ```json
    {
      "property_id": "123456789",
      "start_date": "30daysAgo",
      "end_date": "today",
      "metrics": ["sessions", "totalUsers", "bounceRate"],
      "dimensions": ["date", "country"],
      "order_by": "sessions",
      "limit": 100
    }
    ```
    """
    try:
        service = get_google_analytics_service()
        
        data = await service.get_report_data(
            property_id=request.property_id,
            start_date=request.start_date,
            end_date=request.end_date,
            metrics=request.metrics,
            dimensions=request.dimensions,
            order_by=request.order_by,
            limit=request.limit
        )
        
        return data
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo report data GA4: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/ecommerce")
async def get_ecommerce_data(request: EcommerceRequest):
    """
    🛒 Métricas ecommerce
    
    **Retorna:**
    - total_revenue: Revenue total
    - transactions: Número transacciones
    - avg_order_value: Valor promedio pedido
    - top_products: Top 10 productos por revenue
      - product_name, revenue, views, purchases, conversion_rate
    - revenue_by_source: Revenue por fuente tráfico
      - source, revenue
    
    **Ejemplo:**
    ```json
    {
      "property_id": "123456789",
      "start_date": "30daysAgo",
      "end_date": "today"
    }
    ```
    """
    try:
        service = get_google_analytics_service()
        
        data = await service.get_ecommerce_data(
            property_id=request.property_id,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        # Calcular métricas adicionales
        top_product = data['top_products'][0] if data['top_products'] else None
        best_source = data['revenue_by_source'][0] if data['revenue_by_source'] else None
        
        return {
            **data,
            "insights": {
                "top_product": top_product['product_name'] if top_product else None,
                "top_product_revenue": top_product['revenue'] if top_product else 0,
                "best_source": best_source['source'] if best_source else None,
                "best_source_revenue": best_source['revenue'] if best_source else 0
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo ecommerce data GA4: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/reports/generate")
async def generate_ga4_report(
    request: ReportRequest,
    background_tasks: BackgroundTasks
):
    """
    📄 Genera reporte completo GA4 (background task)
    
    **Proceso:**
    1. Extrae report data + ecommerce data
    2. Genera análisis IA
    3. Crea PDF con gráficos
    4. Upload a Google Drive
    5. Notifica Slack con summary
    
    **Retorna inmediatamente:**
    - task_id para tracking
    
    **Notification Slack cuando complete:**
    - Métricas summary
    - Link Drive PDF
    - IA insights destacados
    """
    try:
        # Generar task_id
        task_id = f"ga4_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Añadir a background tasks
        background_tasks.add_task(
            _generate_report_background,
            task_id=task_id,
            property_id=request.property_id,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        return {
            "task_id": task_id,
            "status": "processing",
            "message": "Reporte GA4 generándose en background. Recibirás notificación Slack cuando esté listo.",
            "estimated_time": "2-3 minutos"
        }
        
    except Exception as e:
        logger.error(f"❌ Error iniciando generación reporte GA4: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/health")
async def health_check():
    """
    🏥 Verifica estado integración GA4
    """
    service = get_google_analytics_service()
    
    return {
        "service": "Google Analytics 4 (GA4)",
        "status": "operational",
        "mock_mode": service.mock_mode,
        "message": "Usando mock data para testing" if service.mock_mode else "Conectado a GA4 Data API",
        "endpoints": [
            "POST /api/v1/google-analytics/realtime",
            "POST /api/v1/google-analytics/report",
            "POST /api/v1/google-analytics/ecommerce",
            "POST /api/v1/google-analytics/reports/generate"
        ]
    }


# ==========================================
# HELPER FUNCTIONS
# ==========================================

async def _generate_report_background(
    task_id: str,
    property_id: Optional[str],
    start_date: str,
    end_date: str
):
    """
    Background task para generar reporte completo GA4
    """
    try:
        logger.info(f"🔄 Iniciando generación reporte GA4: {task_id}")
        
        service = get_google_analytics_service()
        slack = get_slack_service()
        
        # 1. Extraer datos
        report = await service.get_report_data(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date
        )
        
        ecommerce = await service.get_ecommerce_data(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date
        )
        
        # 2. Calcular métricas summary
        total_sessions = report.get('total_sessions', 0)
        total_users = report.get('total_users', 0)
        avg_bounce_rate = report.get('avg_bounce_rate', 0)
        total_revenue = ecommerce.get('total_revenue', 0)
        transactions = ecommerce.get('transactions', 0)
        
        # 3. Generar análisis IA (simplificado)
        ai_insights = f"""
📊 **Análisis GA4 - {start_date} to {end_date}**

**Tráfico Web:**
- Total Sessions: {total_sessions:,}
- Total Users: {total_users:,}
- Bounce Rate: {avg_bounce_rate}%

**Ecommerce:**
- Revenue: ${total_revenue:,.2f}
- Transactions: {transactions}
- AOV: ${ecommerce.get('avg_order_value', 0):,.2f}

**Top Product:** {ecommerce['top_products'][0]['product_name'] if ecommerce['top_products'] else 'N/A'}

**Recomendaciones:**
- {'Tráfico saludable' if avg_bounce_rate < 50 else 'Mejorar UX para reducir bounce rate'}
- {'Performance ecommerce excelente' if total_revenue > 100000 else 'Optimizar conversiones'}
"""
        
        # 4. Notificar Slack
        await slack.send_message(
            channel="C01234567",  # TODO: Obtener de config cliente
            text=f"✅ Reporte GA4 generado: {task_id}\n\n{ai_insights}"
        )
        
        logger.info(f"✅ Reporte GA4 completado: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ Error generando reporte GA4: {e}")
        
        # Notificar error en Slack
        try:
            slack = get_slack_service()
            await slack.send_message(
                channel="C01234567",
                text=f"❌ Error generando reporte GA4: {task_id}\n\nError: {str(e)}"
            )
        except:
            pass
