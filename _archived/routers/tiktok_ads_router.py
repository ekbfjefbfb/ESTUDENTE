"""
TikTok Ads Router - API para gestión de campañas publicitarias en TikTok
Integra con TikTok Marketing API v1.3 y SlackService para notificaciones

Endpoints:
- POST /campaigns - Lista todas las campañas
- POST /insights - Insights detallados con métricas
- POST /videos - Performance de videos publicitarios
- POST /audience - Datos demográficos de audience
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from services.tiktok_ads_service import get_tiktok_ads_service
from services.slack_service import get_slack_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tiktok-ads", tags=["🎵 TikTok Ads"])


# === MODELS ===

class CampaignsRequest(BaseModel):
    advertiser_id: str = Field(..., description="ID del anunciante (BC_xxx)")
    filtering: Optional[Dict[str, Any]] = Field(None, description="Filtros: status, objective_type")
    page: int = Field(1, ge=1, description="Número de página")
    page_size: int = Field(50, ge=1, le=100, description="Elementos por página")


class InsightsRequest(BaseModel):
    advertiser_id: str
    start_date: str = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    end_date: str = Field(..., description="Fecha fin (YYYY-MM-DD)")
    level: str = Field("AUCTION_CAMPAIGN", description="AUCTION_CAMPAIGN, AUCTION_ADGROUP, AUCTION_AD")
    metrics: Optional[List[str]] = Field(None, description="Lista de métricas específicas")


class VideosRequest(BaseModel):
    advertiser_id: str
    video_ids: Optional[List[str]] = Field(None, description="IDs de videos específicos")
    start_date: Optional[str] = Field(None, description="Fecha inicio (default últimos 30 días)")
    end_date: Optional[str] = Field(None, description="Fecha fin (default hoy)")


class AudienceRequest(BaseModel):
    advertiser_id: str
    start_date: str = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    end_date: str = Field(..., description="Fecha fin (YYYY-MM-DD)")
    dimensions: List[str] = Field(["gender", "age"], description="Dimensiones: gender, age, location_id, platform")


# === ENDPOINTS ===

@router.post("/campaigns")
async def get_campaigns(request: CampaignsRequest):
    """
    Obtener todas las campañas de TikTok Ads
    
    Retorna para cada campaña:
    - ID, nombre, objetivo (REACH, TRAFFIC, CONVERSIONS, etc.)
    - Estado (ENABLE, DISABLE, DELETE)
    - Budget y modo (diario/total)
    - Fechas de creación/modificación
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/tiktok-ads/campaigns" \
      -H "Content-Type: application/json" \
      -d '{
        "advertiser_id": "BC_1234567890",
        "page": 1,
        "page_size": 50
      }'
    ```
    """
    try:
        tiktok = get_tiktok_ads_service()
        campaigns = await tiktok.get_campaigns(
            advertiser_id=request.advertiser_id,
            filtering=request.filtering,
            page=request.page,
            page_size=request.page_size
        )
        
        if not campaigns:
            return {
                "advertiser_id": request.advertiser_id,
                "campaigns": [],
                "total_campaigns": 0,
                "page": request.page,
                "page_size": request.page_size,
                "message": "No se encontraron campañas o error de API"
            }
        
        # Calcular totales de budgets
        total_budget = sum(c.get("budget", 0) for c in campaigns)
        enabled_campaigns = [c for c in campaigns if c.get("status") == "ENABLE"]
        
        return {
            "advertiser_id": request.advertiser_id,
            "campaigns": campaigns,
            "total_campaigns": len(campaigns),
            "enabled_campaigns": len(enabled_campaigns),
            "total_budget": round(total_budget, 2),
            "page": request.page,
            "page_size": request.page_size
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo campañas TikTok: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo campañas: {str(e)}")


@router.post("/insights")
async def get_insights(request: InsightsRequest):
    """
    Obtener insights detallados de campañas TikTok Ads
    
    Retorna métricas agregadas:
    - Spend total, impresiones, clicks
    - CTR, CPM, CPC promedio
    - Conversiones, CPA, tasa de conversión
    - Métricas de video: plays, watched_2s, watched_6s
    - Engagement: likes, comments, shares, follows
    
    Útil para:
    - Análisis de rendimiento por período
    - Comparación entre campañas
    - Identificar top performers
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/tiktok-ads/insights" \
      -H "Content-Type: application/json" \
      -d '{
        "advertiser_id": "BC_1234567890",
        "start_date": "2025-10-01",
        "end_date": "2025-10-31",
        "level": "AUCTION_CAMPAIGN"
      }'
    ```
    """
    try:
        tiktok = get_tiktok_ads_service()
        insights = await tiktok.get_ad_insights(
            advertiser_id=request.advertiser_id,
            start_date=request.start_date,
            end_date=request.end_date,
            level=request.level,
            metrics=request.metrics
        )
        
        if not insights:
            return {
                "advertiser_id": request.advertiser_id,
                "error": "No se pudieron obtener insights"
            }
        
        # Análisis automático
        analysis = {}
        
        if insights.get("total_spend") and insights.get("total_conversions"):
            cpa = insights["total_spend"] / insights["total_conversions"]
            
            # Benchmarks TikTok Ads promedio (industria)
            avg_cpa_benchmark = 25.0  # $25 CPA promedio
            avg_ctr_benchmark = 2.5  # 2.5% CTR promedio
            
            analysis = {
                "performance_vs_benchmark": {
                    "cpa_status": "excellent" if cpa < avg_cpa_benchmark * 0.7 else "good" if cpa < avg_cpa_benchmark else "needs_improvement",
                    "cpa_vs_benchmark": f"{((cpa / avg_cpa_benchmark - 1) * 100):+.1f}%",
                    "ctr_status": "excellent" if insights["average_ctr"] > avg_ctr_benchmark * 1.3 else "good" if insights["average_ctr"] > avg_ctr_benchmark else "needs_improvement",
                    "ctr_vs_benchmark": f"{((insights['average_ctr'] / avg_ctr_benchmark - 1) * 100):+.1f}%"
                },
                "recommendations": []
            }
            
            # Generar recomendaciones
            if cpa > avg_cpa_benchmark:
                analysis["recommendations"].append("CPA alto: Optimizar targeting y creativos")
            if insights["average_ctr"] < avg_ctr_benchmark:
                analysis["recommendations"].append("CTR bajo: Mejorar hooks de video (primeros 3 segundos)")
            if insights["total_spend"] > 0.8 * insights.get("budget_remaining", float('inf')):
                analysis["recommendations"].append("Presupuesto cerca del límite: Considerar aumentar budget")
        
        insights["analysis"] = analysis
        return insights
        
    except Exception as e:
        logger.error(f"Error obteniendo insights TikTok: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo insights: {str(e)}")


@router.post("/videos")
async def get_videos(request: VideosRequest):
    """
    Obtener performance de videos publicitarios
    
    Retorna para cada video:
    - Impresiones y video plays
    - Métricas de retención (2s, 6s, 25%, 50%, 75%, 100%)
    - Completion rate (% que ve video completo)
    - Average watch time
    - Engagement: likes, comments, shares, follows
    - Engagement rate calculado
    
    Útil para:
    - Identificar videos top performers
    - Optimizar creativos basado en retención
    - Entender qué contenido genera engagement
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/tiktok-ads/videos" \
      -H "Content-Type: application/json" \
      -d '{
        "advertiser_id": "BC_1234567890"
      }'
    ```
    """
    try:
        tiktok = get_tiktok_ads_service()
        videos = await tiktok.get_video_performance(
            advertiser_id=request.advertiser_id,
            video_ids=request.video_ids,
            start_date=request.start_date,
            end_date=request.end_date
        )
        
        if not videos:
            return {
                "advertiser_id": request.advertiser_id,
                "videos": [],
                "total_videos": 0,
                "message": "No se encontraron videos"
            }
        
        # Análisis de top performers
        top_by_engagement = sorted(videos, key=lambda x: x.get("engagement_rate", 0), reverse=True)[:5]
        top_by_completion = sorted(videos, key=lambda x: x.get("completion_rate", 0), reverse=True)[:5]
        
        # Promedios
        avg_engagement = sum(v.get("engagement_rate", 0) for v in videos) / len(videos)
        avg_completion = sum(v.get("completion_rate", 0) for v in videos) / len(videos)
        avg_watch_time = sum(v.get("average_watch_time", 0) for v in videos) / len(videos)
        
        return {
            "advertiser_id": request.advertiser_id,
            "videos": videos,
            "total_videos": len(videos),
            "analysis": {
                "top_5_by_engagement": [
                    {"ad_name": v["ad_name"], "engagement_rate": v["engagement_rate"]}
                    for v in top_by_engagement
                ],
                "top_5_by_completion": [
                    {"ad_name": v["ad_name"], "completion_rate": v["completion_rate"]}
                    for v in top_by_completion
                ],
                "averages": {
                    "engagement_rate": round(avg_engagement, 2),
                    "completion_rate": round(avg_completion, 2),
                    "watch_time_seconds": round(avg_watch_time, 2)
                },
                "recommendations": [
                    "Videos con >8% engagement rate son top performers - replicar estilo",
                    "Completion rate óptimo: >25% - mejorar storytelling si está bajo",
                    "Watch time ideal: >10s - hooks visuales en primeros 3 segundos"
                ]
            }
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo videos TikTok: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo videos: {str(e)}")


@router.post("/audience")
async def get_audience(request: AudienceRequest):
    """
    Obtener datos demográficos de audience
    
    Retorna breakdown por dimensiones:
    - **Gender**: MALE, FEMALE, OTHER (%)
    - **Age**: AGE_13_17, AGE_18_24, AGE_25_34, AGE_35_44, etc. (%)
    - **Location**: Por país/región (%)
    - **Platform**: IOS, ANDROID, PC (%)
    
    Útil para:
    - Entender quién ve tus anuncios
    - Optimizar targeting basado en demographics reales
    - Ajustar creativos para audience principal
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/tiktok-ads/audience" \
      -H "Content-Type: application/json" \
      -d '{
        "advertiser_id": "BC_1234567890",
        "start_date": "2025-10-01",
        "end_date": "2025-10-31",
        "dimensions": ["gender", "age", "platform"]
      }'
    ```
    """
    try:
        tiktok = get_tiktok_ads_service()
        audience_data = await tiktok.get_audience_data(
            advertiser_id=request.advertiser_id,
            start_date=request.start_date,
            end_date=request.end_date,
            dimensions=request.dimensions
        )
        
        if not audience_data:
            return {
                "advertiser_id": request.advertiser_id,
                "error": "No se pudieron obtener datos de audience"
            }
        
        # Análisis automático
        insights = []
        
        # Gender analysis
        if "by_gender" in audience_data:
            gender_data = audience_data["by_gender"]
            dominant_gender = max(gender_data, key=gender_data.get)
            percentage = gender_data[dominant_gender]
            
            insights.append({
                "dimension": "gender",
                "finding": f"{dominant_gender} representa {percentage}% del audience",
                "recommendation": f"Considerar creativos específicos para {dominant_gender}" if percentage > 60 else "Audience balanceado - mantener creativos universales"
            })
        
        # Age analysis
        if "by_age" in audience_data:
            age_data = audience_data["by_age"]
            dominant_age = max(age_data, key=age_data.get)
            percentage = age_data[dominant_age]
            
            # Mapeo de nombres amigables
            age_names = {
                "AGE_13_17": "13-17 años (Gen Z joven)",
                "AGE_18_24": "18-24 años (Gen Z)",
                "AGE_25_34": "25-34 años (Millennials)",
                "AGE_35_44": "35-44 años (Millennials mayores)",
                "AGE_45_54": "45-54 años (Gen X)",
                "AGE_55_PLUS": "55+ años (Boomers)"
            }
            
            insights.append({
                "dimension": "age",
                "finding": f"{age_names.get(dominant_age, dominant_age)} es el segmento principal ({percentage}%)",
                "recommendation": "Adaptar lenguaje y referencias culturales a este grupo etario"
            })
        
        audience_data["insights"] = insights
        return audience_data
        
    except Exception as e:
        logger.error(f"Error obteniendo audience TikTok: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo audience: {str(e)}")
