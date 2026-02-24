"""
Router para Google Analytics 4 (GA4)
Integración con Google Analytics Data API v1beta
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

# Google Analytics Data API
try:
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        RunReportRequest,
        DateRange,
        Dimension,
        Metric,
        OrderBy
    )
    from google.oauth2.credentials import Credentials
    GA4_AVAILABLE = True
except ImportError:
    GA4_AVAILABLE = False
    print("⚠️ google-analytics-data no instalado. Instalar: pip install google-analytics-data")

router = APIRouter(prefix="/api/google-analytics", tags=["Google Analytics 4"])


class GA4MetricsRequest(BaseModel):
    property_id: str
    start_date: str = "30daysAgo"  # o fecha YYYY-MM-DD
    end_date: str = "today"
    metrics: List[str] = ["sessions", "pageviews", "bounceRate", "conversions"]
    dimensions: Optional[List[str]] = None


class GA4MetricsResponse(BaseModel):
    property_id: str
    period: str
    metrics: Dict[str, Any]
    dimensions_data: Optional[List[Dict]] = None


@router.post("/metrics", response_model=GA4MetricsResponse)
async def get_ga4_metrics(request: GA4MetricsRequest):
    """
    Obtener métricas de Google Analytics 4
    
    Métricas disponibles:
    - sessions: Total de sesiones
    - pageviews: Total de páginas vistas
    - bounceRate: Tasa de rebote
    - conversions: Total de conversiones
    - engagementRate: Tasa de engagement
    - sessionDuration: Duración promedio de sesión
    - newUsers: Usuarios nuevos
    - activeUsers: Usuarios activos
    
    Ejemplo:
    ```
    POST /api/google-analytics/metrics
    {
        "property_id": "123456789",
        "start_date": "30daysAgo",
        "end_date": "today",
        "metrics": ["sessions", "pageviews", "bounceRate"]
    }
    ```
    """
    if not GA4_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Google Analytics Data API no disponible. Instalar: pip install google-analytics-data"
        )
    
    try:
        # Inicializar cliente GA4
        client = BetaAnalyticsDataClient()
        
        # Construir request
        request_ga = RunReportRequest(
            property=f"properties/{request.property_id}",
            date_ranges=[DateRange(
                start_date=request.start_date,
                end_date=request.end_date
            )],
            metrics=[Metric(name=m) for m in request.metrics],
            dimensions=[Dimension(name=d) for d in request.dimensions] if request.dimensions else []
        )
        
        # Ejecutar query
        response = client.run_report(request_ga)
        
        # Parsear resultados
        metrics_data = {}
        dimensions_data = []
        
        for row in response.rows:
            if request.dimensions:
                # Con dimensiones (ej: por país, por fuente)
                dim_values = {d.name: v.value for d, v in zip(request.dimensions, row.dimension_values)}
                metric_values = {m.name: v.value for m, v in zip(request.metrics, row.metric_values)}
                dimensions_data.append({**dim_values, **metric_values})
            else:
                # Sin dimensiones (agregado total)
                for metric, value in zip(request.metrics, row.metric_values):
                    metrics_data[metric.name] = parse_metric_value(value.value, metric.name)
        
        return GA4MetricsResponse(
            property_id=request.property_id,
            period=f"{request.start_date} to {request.end_date}",
            metrics=metrics_data,
            dimensions_data=dimensions_data if dimensions_data else None
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error obteniendo métricas de GA4: {str(e)}"
        )


@router.get("/metrics/quick/{property_id}")
async def get_quick_metrics(
    property_id: str,
    period: str = "last_7_days"
):
    """
    Métricas rápidas (preset común)
    
    Periods: last_7_days, last_30_days, last_90_days, this_month, last_month
    """
    if not GA4_AVAILABLE:
        raise HTTPException(status_code=503, detail="GA4 API no disponible")
    
    try:
        # Mapeo de periodos
        period_map = {
            "last_7_days": ("7daysAgo", "today"),
            "last_30_days": ("30daysAgo", "today"),
            "last_90_days": ("90daysAgo", "today"),
            "this_month": ("startOfMonth", "today"),
            "last_month": ("startOfMonth", "endOfMonth")  # Mes anterior
        }
        
        start_date, end_date = period_map.get(period, ("30daysAgo", "today"))
        
        # Métricas estándar
        request = GA4MetricsRequest(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            metrics=[
                "sessions",
                "pageviews",
                "bounceRate",
                "averageSessionDuration",
                "conversions",
                "engagementRate",
                "newUsers",
                "activeUsers"
            ]
        )
        
        return await get_ga4_metrics(request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/traffic-sources/{property_id}")
async def get_traffic_sources(
    property_id: str,
    start_date: str = "30daysAgo",
    end_date: str = "today"
):
    """
    Fuentes de tráfico (por canal, fuente, medio)
    """
    if not GA4_AVAILABLE:
        raise HTTPException(status_code=503, detail="GA4 API no disponible")
    
    try:
        request = GA4MetricsRequest(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            metrics=["sessions", "pageviews", "conversions"],
            dimensions=["sessionSource", "sessionMedium", "sessionCampaignName"]
        )
        
        return await get_ga4_metrics(request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/top-pages/{property_id}")
async def get_top_pages(
    property_id: str,
    start_date: str = "30daysAgo",
    end_date: str = "today",
    limit: int = 10
):
    """
    Páginas más visitadas
    """
    if not GA4_AVAILABLE:
        raise HTTPException(status_code=503, detail="GA4 API no disponible")
    
    try:
        client = BetaAnalyticsDataClient()
        
        request_ga = RunReportRequest(
            property=f"properties/{property_id}",
            date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
            metrics=[
                Metric(name="pageviews"),
                Metric(name="sessions"),
                Metric(name="averageSessionDuration")
            ],
            dimensions=[Dimension(name="pageTitle"), Dimension(name="pagePath")],
            order_bys=[OrderBy(metric={"metric_name": "pageviews"}, desc=True)],
            limit=limit
        )
        
        response = client.run_report(request_ga)
        
        # Parsear
        top_pages = []
        for row in response.rows:
            top_pages.append({
                "page_title": row.dimension_values[0].value,
                "page_path": row.dimension_values[1].value,
                "pageviews": int(row.metric_values[0].value),
                "sessions": int(row.metric_values[1].value),
                "avg_session_duration": float(row.metric_values[2].value)
            })
        
        return {
            "property_id": property_id,
            "period": f"{start_date} to {end_date}",
            "top_pages": top_pages
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversions/{property_id}")
async def get_conversions(
    property_id: str,
    start_date: str = "30daysAgo",
    end_date: str = "today"
):
    """
    Conversiones por evento
    """
    if not GA4_AVAILABLE:
        raise HTTPException(status_code=503, detail="GA4 API no disponible")
    
    try:
        request = GA4MetricsRequest(
            property_id=property_id,
            start_date=start_date,
            end_date=end_date,
            metrics=["conversions", "eventCount"],
            dimensions=["eventName"]
        )
        
        return await get_ga4_metrics(request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/real-time/{property_id}")
async def get_realtime_metrics(property_id: str):
    """
    Métricas en tiempo real (últimos 30 minutos)
    """
    if not GA4_AVAILABLE:
        raise HTTPException(status_code=503, detail="GA4 API no disponible")
    
    try:
        from google.analytics.data_v1beta.types import RunRealtimeReportRequest
        
        client = BetaAnalyticsDataClient()
        
        request_ga = RunRealtimeReportRequest(
            property=f"properties/{property_id}",
            metrics=[
                Metric(name="activeUsers"),
                Metric(name="screenPageViews")
            ],
            dimensions=[Dimension(name="country")]
        )
        
        response = client.run_realtime_report(request_ga)
        
        # Parsear
        realtime_data = []
        for row in response.rows:
            realtime_data.append({
                "country": row.dimension_values[0].value,
                "active_users": int(row.metric_values[0].value),
                "pageviews": int(row.metric_values[1].value)
            })
        
        return {
            "property_id": property_id,
            "timestamp": datetime.now().isoformat(),
            "realtime_data": realtime_data
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare-periods/{property_id}")
async def compare_periods(
    property_id: str,
    current_start: str,
    current_end: str,
    previous_start: str,
    previous_end: str,
    metrics: List[str] = ["sessions", "pageviews", "bounceRate", "conversions"]
):
    """
    Comparar dos periodos
    
    Ejemplo: Octubre 2025 vs Septiembre 2025
    """
    if not GA4_AVAILABLE:
        raise HTTPException(status_code=503, detail="GA4 API no disponible")
    
    try:
        # Periodo actual
        current_request = GA4MetricsRequest(
            property_id=property_id,
            start_date=current_start,
            end_date=current_end,
            metrics=metrics
        )
        current_data = await get_ga4_metrics(current_request)
        
        # Periodo anterior
        previous_request = GA4MetricsRequest(
            property_id=property_id,
            start_date=previous_start,
            end_date=previous_end,
            metrics=metrics
        )
        previous_data = await get_ga4_metrics(previous_request)
        
        # Calcular diferencias
        comparison = {}
        for metric in metrics:
            current_value = current_data.metrics.get(metric, 0)
            previous_value = previous_data.metrics.get(metric, 0)
            
            if previous_value > 0:
                change_percent = ((current_value - previous_value) / previous_value) * 100
            else:
                change_percent = 0
            
            comparison[metric] = {
                "current": current_value,
                "previous": previous_value,
                "change": current_value - previous_value,
                "change_percent": round(change_percent, 2)
            }
        
        return {
            "property_id": property_id,
            "current_period": f"{current_start} to {current_end}",
            "previous_period": f"{previous_start} to {previous_end}",
            "comparison": comparison
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Verificar estado de integración GA4"""
    return {
        "service": "Google Analytics 4",
        "status": "available" if GA4_AVAILABLE else "unavailable",
        "message": "OK" if GA4_AVAILABLE else "Instalar: pip install google-analytics-data"
    }


def parse_metric_value(value: str, metric_name: str) -> Any:
    """
    Parsear valor de métrica según tipo
    """
    try:
        # Métricas de porcentaje
        if "rate" in metric_name.lower():
            return round(float(value) * 100, 2)  # Convertir a %
        
        # Métricas de tiempo (segundos)
        if "duration" in metric_name.lower():
            return round(float(value), 2)
        
        # Métricas de conteo
        return int(float(value))
        
    except:
        return value
