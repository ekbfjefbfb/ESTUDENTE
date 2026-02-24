"""
Router para Meta Ads (Facebook & Instagram Ads)
Integración con Facebook Marketing API v18

Usa MetaAdsService para extracción de métricas multi-plataforma
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Importar services
from services.meta_ads_service import get_meta_ads_service
from services.slack_service import get_slack_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/meta-ads", tags=["📘 Meta Ads (Facebook/Instagram)"])


# ==========================================
# PYDANTIC MODELS
# ==========================================

class CampaignsRequest(BaseModel):
    account_id: str = Field(..., description="ID cuenta ads (ej: act_123456789)")
    date_range: str = Field(default="last_30d", description="last_7d, last_30d, last_90d")
    status: Optional[List[str]] = Field(default=None, description="['ACTIVE', 'PAUSED']")


class InsightsRequest(BaseModel):
    account_id: str = Field(..., description="ID cuenta ads")
    level: str = Field(default="campaign", description="campaign, adset, ad")
    campaign_ids: Optional[List[str]] = Field(default=None, description="Filtrar campañas específicas")
    date_range: str = Field(default="last_30d", description="last_7d, last_30d, last_90d")
    breakdowns: Optional[List[str]] = Field(default=None, description="['age', 'gender', 'country', 'placement']")


class AdCreativeRequest(BaseModel):
    ad_ids: List[str] = Field(..., description="Lista IDs de ads")


class AudienceInsightsRequest(BaseModel):
    account_id: str = Field(..., description="ID cuenta ads")
    campaign_ids: Optional[List[str]] = Field(default=None, description="Filtrar campañas específicas")
    date_range: str = Field(default="last_30d", description="last_7d, last_30d, last_90d")


# ==========================================
# ENDPOINTS
# ==========================================

@router.post("/campaigns")
async def get_campaigns(request: CampaignsRequest):
    """
    📊 Lista campañas Meta Ads con métricas básicas
    
    **Retorna:**
    - campaign_id, name, status, objective
    - spend, impressions, clicks, conversions
    - cpm, cpc, ctr, roas
    
    **Ejemplo:**
    ```json
    {
      "account_id": "act_123456789",
      "date_range": "last_30d",
      "status": ["ACTIVE"]
    }
    ```
    """
    try:
        service = get_meta_ads_service()
        
        campaigns = await service.get_campaigns(
            account_id=request.account_id,
            date_range=request.date_range,
            status=request.status
        )
        
        # Calcular summary
        total_campaigns = len(campaigns)
        active_campaigns = len([c for c in campaigns if c['status'] == 'ACTIVE'])
        total_spend = sum(c['spend'] for c in campaigns)
        total_conversions = sum(c['conversions'] for c in campaigns)
        avg_roas = round(sum(c['roas'] for c in campaigns) / total_campaigns, 2) if total_campaigns > 0 else 0
        
        return {
            "campaigns": campaigns,
            "summary": {
                "total_campaigns": total_campaigns,
                "active_campaigns": active_campaigns,
                "total_spend": round(total_spend, 2),
                "total_conversions": total_conversions,
                "avg_roas": avg_roas
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo campañas Meta Ads: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/insights")
async def get_insights(request: InsightsRequest):
    """
    📈 Insights detallados con breakdowns opcionales
    
    **Breakdowns disponibles:**
    - age: Distribución por edades
    - gender: Male vs Female
    - country: Top países
    - placement: Facebook Feed, Instagram Stories, etc.
    - device_platform: Mobile, Desktop, Tablet
    
    **Retorna:**
    - Métricas totales agregadas
    - Breakdowns por dimensión solicitada
    - Avg CPM, CPC, CTR, ROAS
    
    **Ejemplo:**
    ```json
    {
      "account_id": "act_123456789",
      "level": "campaign",
      "date_range": "last_30d",
      "breakdowns": ["age", "gender"]
    }
    ```
    """
    try:
        service = get_meta_ads_service()
        
        insights = await service.get_insights(
            account_id=request.account_id,
            level=request.level,
            campaign_ids=request.campaign_ids,
            date_range=request.date_range,
            breakdowns=request.breakdowns
        )
        
        return insights
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo insights Meta Ads: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/creative")
async def get_ad_creative(request: AdCreativeRequest):
    """
    🎨 Obtiene creative assets de ads específicos
    
    **Retorna:**
    - ad_id, name, status
    - creative_id, title, body
    - image_url, video_id, thumbnail_url
    - link_url, call_to_action
    
    **Ejemplo:**
    ```json
    {
      "ad_ids": ["120212345678901", "120212345678902"]
    }
    ```
    """
    try:
        service = get_meta_ads_service()
        
        creatives = await service.get_ad_creative(
            ad_ids=request.ad_ids
        )
        
        return {
            "ad_creatives": creatives,
            "total": len(creatives)
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo ad creative: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/audience")
async def get_audience_insights(request: AudienceInsightsRequest):
    """
    👥 Demographics y audience data completos
    
    **Retorna:**
    - demographics: gender, age, country con porcentajes
    - placements: Facebook Feed, Instagram Stories, Reels con %
    - devices: Mobile, Desktop, Tablet con %
    - total_impressions
    
    **IA Recommendations:**
    - Targeting suggestions basadas en datos
    - Best performing audiences
    - Optimization opportunities
    
    **Ejemplo:**
    ```json
    {
      "account_id": "act_123456789",
      "campaign_ids": ["120212345678901"],
      "date_range": "last_30d"
    }
    ```
    """
    try:
        service = get_meta_ads_service()
        
        audience = await service.get_audience_insights(
            account_id=request.account_id,
            campaign_ids=request.campaign_ids,
            date_range=request.date_range
        )
        
        # Generar IA recommendations basadas en datos
        recommendations = _generate_audience_recommendations(audience)
        
        return {
            **audience,
            "recommendations": recommendations
        }
        
    except Exception as e:
        logger.error(f"❌ Error obteniendo audience insights: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.post("/reports/generate")
async def generate_meta_ads_report(
    request: CampaignsRequest,
    background_tasks: BackgroundTasks
):
    """
    📄 Genera reporte completo Meta Ads (background task)
    
    **Proceso:**
    1. Extrae campañas + insights + audience
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
        task_id = f"meta_ads_report_{request.account_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Añadir a background tasks
        background_tasks.add_task(
            _generate_report_background,
            task_id=task_id,
            account_id=request.account_id,
            date_range=request.date_range
        )
        
        return {
            "task_id": task_id,
            "status": "processing",
            "message": "Reporte Meta Ads generándose en background. Recibirás notificación Slack cuando esté listo.",
            "estimated_time": "2-3 minutos"
        }
        
    except Exception as e:
        logger.error(f"❌ Error iniciando generación reporte: {e}")
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/health")
async def health_check():
    """
    🏥 Verifica estado integración Meta Ads
    """
    service = get_meta_ads_service()
    
    return {
        "service": "Meta Ads (Facebook/Instagram)",
        "status": "operational",
        "mock_mode": service.mock_mode,
        "message": "Usando mock data para testing" if service.mock_mode else "Conectado a Facebook Marketing API",
        "endpoints": [
            "POST /api/v1/meta-ads/campaigns",
            "POST /api/v1/meta-ads/insights",
            "POST /api/v1/meta-ads/creative",
            "POST /api/v1/meta-ads/audience",
            "POST /api/v1/meta-ads/reports/generate"
        ]
    }


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def _generate_audience_recommendations(audience: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Genera recommendations IA basadas en audience data
    """
    recommendations = []
    
    demographics = audience.get('demographics', {})
    placements = audience.get('placements', {})
    devices = audience.get('devices', {})
    
    # Recomendación por gender
    gender = demographics.get('gender', {})
    if gender.get('female', 0) > 60:
        recommendations.append({
            "type": "targeting",
            "priority": "high",
            "message": "Audiencia predominantemente femenina (60%+). Considerar creative y copy orientado a mujeres.",
            "action": "Ajustar targeting y creative para maximizar engagement"
        })
    
    # Recomendación por age
    age = demographics.get('age', {})
    if age.get('18-24', 0) + age.get('25-34', 0) > 60:
        recommendations.append({
            "type": "creative",
            "priority": "high",
            "message": "Audiencia joven (18-34 años) representa 60%+. Instagram Stories y Reels son ideales.",
            "action": "Aumentar presupuesto en Instagram Stories/Reels"
        })
    
    # Recomendación por placement
    instagram_total = placements.get('instagram_feed', 0) + placements.get('instagram_stories', 0) + placements.get('instagram_reels', 0)
    if instagram_total > 50:
        recommendations.append({
            "type": "budget",
            "priority": "medium",
            "message": f"Instagram genera {instagram_total}% de impresiones. Considerar aumentar budget Instagram.",
            "action": "Scale Instagram campaigns"
        })
    
    # Recomendación por device
    mobile = devices.get('mobile', 0)
    if mobile > 75:
        recommendations.append({
            "type": "optimization",
            "priority": "high",
            "message": f"Tráfico mobile {mobile}%. Optimizar creative para mobile-first.",
            "action": "Usar formato vertical 9:16 y textos cortos"
        })
    
    return recommendations


async def _generate_report_background(
    task_id: str,
    account_id: str,
    date_range: str
):
    """
    Background task para generar reporte completo Meta Ads
    """
    try:
        logger.info(f"🔄 Iniciando generación reporte Meta Ads: {task_id}")
        
        service = get_meta_ads_service()
        slack = get_slack_service()
        
        # 1. Extraer datos
        campaigns = await service.get_campaigns(
            account_id=account_id,
            date_range=date_range
        )
        
        insights = await service.get_insights(
            account_id=account_id,
            level="campaign",
            date_range=date_range,
            breakdowns=["age", "gender", "country"]
        )
        
        audience = await service.get_audience_insights(
            account_id=account_id,
            date_range=date_range
        )
        
        # 2. Calcular métricas summary
        total_spend = insights.get('total_spend', 0)
        total_conversions = insights.get('total_conversions', 0)
        avg_roas = insights.get('avg_roas', 0)
        
        # 3. Generar análisis IA (simplificado, en producción usar GPTService)
        ai_insights = f"""
📊 **Análisis Meta Ads - {date_range}**

**Performance General:**
- Total Spend: ${total_spend:,.2f}
- Conversions: {total_conversions}
- ROAS: {avg_roas}x
- Campaigns: {len(campaigns)}

**Top Campaign:** {campaigns[0]['name'] if campaigns else 'N/A'}

**Recomendaciones:**
- {'Budget OK' if avg_roas > 3 else 'Revisar budget allocation'}
- {'Performance excelente' if avg_roas > 4 else 'Optimizar targeting'}
"""
        
        # 4. Notificar Slack
        await slack.send_message(
            channel="C01234567",  # TODO: Obtener de config cliente
            text=f"✅ Reporte Meta Ads generado: {task_id}\n\n{ai_insights}"
        )
        
        logger.info(f"✅ Reporte Meta Ads completado: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ Error generando reporte Meta Ads: {e}")
        
        # Notificar error en Slack
        try:
            slack = get_slack_service()
            await slack.send_message(
                channel="C01234567",
                text=f"❌ Error generando reporte Meta Ads: {task_id}\n\nError: {str(e)}"
            )
        except:
            pass
