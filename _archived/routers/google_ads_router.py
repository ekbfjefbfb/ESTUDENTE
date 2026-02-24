"""
Google Ads Router - API para gestión de campañas publicitarias
Integra con Google Ads API v14 y SlackService para notificaciones

Endpoints:
- GET /campaigns - Lista todas las campañas con métricas
- GET /keywords - Performance de keywords
- GET /costs - Datos de costos detallados
- GET /conversions - Datos de conversiones
- POST /reports/generate - Genera reporte automático con IA
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from services.google_ads_service import get_google_ads_service
from services.slack_service import get_slack_service
from services.gpt_service import GPTService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/google-ads", tags=["💰 Google Ads"])


# === MODELS ===

class CampaignsRequest(BaseModel):
    customer_id: str = Field(..., description="ID del cliente de Google Ads (sin guiones)")
    date_range: str = Field("LAST_30_DAYS", description="LAST_7_DAYS, LAST_30_DAYS, LAST_90_DAYS, THIS_MONTH, etc.")


class KeywordsRequest(BaseModel):
    customer_id: str
    campaign_id: Optional[str] = None
    date_range: str = "LAST_30_DAYS"
    min_impressions: int = Field(100, description="Filtrar keywords con menos impresiones")


class CostsRequest(BaseModel):
    customer_id: str
    start_date: str = Field(..., description="Fecha inicio (YYYY-MM-DD)")
    end_date: str = Field(..., description="Fecha fin (YYYY-MM-DD)")
    group_by: str = Field("day", description="Agrupar por: day, week, month")


class ConversionsRequest(BaseModel):
    customer_id: str
    date_range: str = "LAST_30_DAYS"


class ReportGenerateRequest(BaseModel):
    customer_id: str
    client_name: str = Field(..., description="Nombre del cliente para el reporte")
    date_range: str = "LAST_30_DAYS"
    slack_channel: Optional[str] = Field(None, description="Canal de Slack para notificar (ej: #marketing)")
    include_keywords: bool = Field(True, description="Incluir análisis de keywords")
    include_costs: bool = Field(True, description="Incluir desglose de costos")


# === ENDPOINTS ===

@router.post("/campaigns")
async def get_campaigns(request: CampaignsRequest):
    """
    Obtener todas las campañas de Google Ads con métricas
    
    Retorna para cada campaña:
    - ID, nombre, estado (ENABLED, PAUSED, REMOVED)
    - Impresiones, clicks, CTR
    - Costo total, CPC promedio
    - Conversiones, CPA, valor de conversiones
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/google-ads/campaigns" \
      -H "Content-Type: application/json" \
      -d '{
        "customer_id": "1234567890",
        "date_range": "LAST_30_DAYS"
      }'
    ```
    """
    try:
        google_ads = get_google_ads_service()
        campaigns = await google_ads.get_campaigns(
            customer_id=request.customer_id,
            date_range=request.date_range
        )
        
        if not campaigns:
            return {
                "customer_id": request.customer_id,
                "date_range": request.date_range,
                "campaigns": [],
                "total_campaigns": 0,
                "message": "No se encontraron campañas o error de API"
            }
        
        # Calcular totales
        total_impressions = sum(c["impressions"] for c in campaigns)
        total_clicks = sum(c["clicks"] for c in campaigns)
        total_cost = sum(c["cost"] for c in campaigns)
        total_conversions = sum(c["conversions"] for c in campaigns)
        
        avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        avg_cpa = (total_cost / total_conversions) if total_conversions > 0 else 0
        
        return {
            "customer_id": request.customer_id,
            "date_range": request.date_range,
            "campaigns": campaigns,
            "total_campaigns": len(campaigns),
            "summary": {
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_cost": round(total_cost, 2),
                "total_conversions": round(total_conversions, 2),
                "average_ctr": round(avg_ctr, 2),
                "average_cpa": round(avg_cpa, 2)
            }
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo campañas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo campañas: {str(e)}")


@router.post("/keywords")
async def get_keywords(request: KeywordsRequest):
    """
    Obtener performance de keywords
    
    Retorna para cada keyword:
    - Texto, tipo de concordancia (EXACT, PHRASE, BROAD)
    - Quality Score (1-10)
    - Impresiones, clicks, CTR, costo
    - Conversiones, CPA
    
    Útil para:
    - Identificar keywords top performers
    - Detectar keywords con bajo Quality Score
    - Optimizar pujas por keyword
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/google-ads/keywords" \
      -H "Content-Type: application/json" \
      -d '{
        "customer_id": "1234567890",
        "campaign_id": "12345",
        "min_impressions": 500
      }'
    ```
    """
    try:
        google_ads = get_google_ads_service()
        keywords = await google_ads.get_keywords_performance(
            customer_id=request.customer_id,
            campaign_id=request.campaign_id,
            date_range=request.date_range,
            min_impressions=request.min_impressions
        )
        
        if not keywords:
            return {
                "customer_id": request.customer_id,
                "campaign_id": request.campaign_id,
                "keywords": [],
                "total_keywords": 0,
                "message": "No se encontraron keywords con los filtros especificados"
            }
        
        # Análisis de keywords
        top_10_by_clicks = sorted(keywords, key=lambda x: x["clicks"], reverse=True)[:10]
        low_quality_score = [k for k in keywords if k.get("quality_score") and k["quality_score"] < 5]
        high_cpa = [k for k in keywords if k.get("cost_per_conversion", 0) > 0 and k["cost_per_conversion"] > 50]
        
        return {
            "customer_id": request.customer_id,
            "campaign_id": request.campaign_id,
            "date_range": request.date_range,
            "keywords": keywords,
            "total_keywords": len(keywords),
            "analysis": {
                "top_10_by_clicks": [{"keyword": k["keyword_text"], "clicks": k["clicks"]} for k in top_10_by_clicks],
                "low_quality_score_count": len(low_quality_score),
                "high_cpa_count": len(high_cpa)
            }
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo keywords: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo keywords: {str(e)}")


@router.post("/costs")
async def get_costs(request: CostsRequest):
    """
    Obtener datos de costos detallados
    
    Retorna:
    - Costo total, clicks totales, impresiones totales
    - CPC promedio, CPA promedio
    - Desglose por día/semana/mes
    
    Útil para:
    - Control de presupuesto
    - Identificar días/semanas de alto gasto
    - Proyectar costos futuros
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/google-ads/costs" \
      -H "Content-Type: application/json" \
      -d '{
        "customer_id": "1234567890",
        "start_date": "2025-10-01",
        "end_date": "2025-10-31",
        "group_by": "day"
      }'
    ```
    """
    try:
        google_ads = get_google_ads_service()
        cost_data = await google_ads.get_cost_data(
            customer_id=request.customer_id,
            start_date=request.start_date,
            end_date=request.end_date,
            group_by=request.group_by
        )
        
        if not cost_data:
            return {
                "customer_id": request.customer_id,
                "error": "No se pudieron obtener datos de costos"
            }
        
        # Calcular tendencias si hay breakdown
        if cost_data.get("cost_breakdown"):
            breakdown = cost_data["cost_breakdown"]
            costs = [item["cost"] for item in breakdown]
            
            # Detectar picos de gasto (>150% del promedio)
            avg_cost = sum(costs) / len(costs)
            high_spend_days = [item for item in breakdown if item["cost"] > avg_cost * 1.5]
            
            cost_data["analysis"] = {
                "average_daily_cost": round(avg_cost, 2),
                "high_spend_periods": len(high_spend_days),
                "highest_spend_day": max(breakdown, key=lambda x: x["cost"]) if breakdown else None
            }
        
        return cost_data
        
    except Exception as e:
        logger.error(f"Error obteniendo costos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo costos: {str(e)}")


@router.post("/conversions")
async def get_conversions(request: ConversionsRequest):
    """
    Obtener datos de conversiones
    
    Retorna:
    - Conversiones totales, valor total de conversiones
    - Tasa de conversión promedio
    - Desglose por campaña
    
    Útil para:
    - Medir ROI de campañas
    - Identificar campañas más rentables
    - Optimizar presupuesto por conversión
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/google-ads/conversions" \
      -H "Content-Type: application/json" \
      -d '{
        "customer_id": "1234567890",
        "date_range": "LAST_30_DAYS"
      }'
    ```
    """
    try:
        google_ads = get_google_ads_service()
        conversion_data = await google_ads.get_conversion_data(
            customer_id=request.customer_id,
            date_range=request.date_range
        )
        
        if not conversion_data:
            return {
                "customer_id": request.customer_id,
                "error": "No se pudieron obtener datos de conversiones"
            }
        
        # Análisis de conversiones
        if conversion_data.get("conversions_by_campaign"):
            campaigns = conversion_data["conversions_by_campaign"]
            
            # Top 5 campañas por conversiones
            top_5_campaigns = sorted(campaigns, key=lambda x: x["conversions"], reverse=True)[:5]
            
            # Campañas con mejor CPA (top 3)
            best_cpa = sorted(
                [c for c in campaigns if c["cost_per_conversion"] > 0],
                key=lambda x: x["cost_per_conversion"]
            )[:3]
            
            conversion_data["analysis"] = {
                "top_5_campaigns_by_conversions": [
                    {"name": c["campaign_name"], "conversions": c["conversions"]}
                    for c in top_5_campaigns
                ],
                "best_cpa_campaigns": [
                    {"name": c["campaign_name"], "cpa": c["cost_per_conversion"]}
                    for c in best_cpa
                ]
            }
        
        return conversion_data
        
    except Exception as e:
        logger.error(f"Error obteniendo conversiones: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error obteniendo conversiones: {str(e)}")


@router.post("/reports/generate")
async def generate_report(
    request: ReportGenerateRequest,
    background_tasks: BackgroundTasks
):
    """
    Generar reporte automático de Google Ads con análisis IA
    
    Proceso:
    1. Extrae datos de campañas, keywords, costos, conversiones
    2. IA analiza y genera insights
    3. Crea reporte con recomendaciones
    4. Notifica en Slack (si se especifica canal)
    
    Retorna inmediatamente (< 3 segundos) y procesa en background.
    
    **Ejemplo de uso:**
    ```bash
    curl -X POST "http://localhost:8000/api/google-ads/reports/generate" \
      -H "Content-Type: application/json" \
      -d '{
        "customer_id": "1234567890",
        "client_name": "Nike Inc",
        "date_range": "LAST_30_DAYS",
        "slack_channel": "#marketing-reports",
        "include_keywords": true,
        "include_costs": true
      }'
    ```
    """
    try:
        # Respuesta inmediata
        background_tasks.add_task(
            generate_report_async,
            customer_id=request.customer_id,
            client_name=request.client_name,
            date_range=request.date_range,
            slack_channel=request.slack_channel,
            include_keywords=request.include_keywords,
            include_costs=request.include_costs
        )
        
        return {
            "status": "processing",
            "message": f"🔄 Generando reporte de Google Ads para {request.client_name}...",
            "estimated_time": "30-60 segundos",
            "customer_id": request.customer_id,
            "date_range": request.date_range,
            "notification": f"Te notificaremos en {request.slack_channel}" if request.slack_channel else "Sin notificación Slack configurada"
        }
        
    except Exception as e:
        logger.error(f"Error iniciando generación de reporte: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error iniciando reporte: {str(e)}")


# === BACKGROUND TASKS ===

async def generate_report_async(
    customer_id: str,
    client_name: str,
    date_range: str,
    slack_channel: Optional[str],
    include_keywords: bool,
    include_costs: bool
):
    """
    Tarea en background: Generar reporte completo de Google Ads
    """
    try:
        google_ads = get_google_ads_service()
        slack = get_slack_service()
        # gpt = GPTService()  # Para análisis IA (opcional)
        
        logger.info(f"🔄 Iniciando generación de reporte Google Ads para {client_name}")
        
        # 1. Extraer datos de campañas
        campaigns = await google_ads.get_campaigns(customer_id, date_range)
        
        # 2. Extraer keywords (si se solicita)
        keywords = []
        if include_keywords and campaigns:
            keywords = await google_ads.get_keywords_performance(
                customer_id=customer_id,
                date_range=date_range,
                min_impressions=100
            )
        
        # 3. Extraer datos de costos (si se solicita)
        cost_data = {}
        if include_costs:
            # Calcular fechas para último mes
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            cost_data = await google_ads.get_cost_data(
                customer_id=customer_id,
                start_date=start_date.strftime("%Y-%m-%d"),
                end_date=end_date.strftime("%Y-%m-%d"),
                group_by="day"
            )
        
        # 4. Extraer conversiones
        conversion_data = await google_ads.get_conversion_data(customer_id, date_range)
        
        # 5. Calcular métricas consolidadas
        if campaigns:
            total_impressions = sum(c["impressions"] for c in campaigns)
            total_clicks = sum(c["clicks"] for c in campaigns)
            total_cost = sum(c["cost"] for c in campaigns)
            total_conversions = sum(c["conversions"] for c in campaigns)
            avg_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            avg_cpa = (total_cost / total_conversions) if total_conversions > 0 else 0
            
            metrics = {
                "impressions": total_impressions,
                "clicks": total_clicks,
                "ctr": round(avg_ctr, 2),
                "cost": round(total_cost, 2),
                "conversions": round(total_conversions, 2),
                "cpa": round(avg_cpa, 2)
            }
        else:
            metrics = {
                "impressions": 0,
                "clicks": 0,
                "ctr": 0,
                "cost": 0,
                "conversions": 0,
                "cpa": 0
            }
        
        # 6. TODO: Análisis con IA (opcional)
        # ai_analysis = await gpt.analyze_google_ads_data(campaigns, keywords, cost_data)
        
        # 7. Enviar notificación a Slack (si se especificó canal)
        if slack_channel and slack.client:
            # Usar el formatter de marketing que ya existe en SlackService
            blocks = slack.format_marketing_report_blocks(
                client_name=client_name,
                period=date_range,
                metrics=metrics,
                report_url=None  # TODO: Link a Drive cuando se implemente PDF
            )
            
            await slack.send_blocks(
                channel=slack_channel,
                text=f"✅ Reporte Google Ads de {client_name} listo!",
                blocks=blocks
            )
            
            logger.info(f"✅ Reporte enviado a Slack: {slack_channel}")
        
        logger.info(f"✅ Reporte de Google Ads completado para {client_name}")
        
    except Exception as e:
        logger.error(f"❌ Error generando reporte: {str(e)}")
        
        # Notificar error en Slack si se configuró
        if slack_channel:
            try:
                slack = get_slack_service()
                await slack.send_message(
                    channel=slack_channel,
                    text=f"❌ Error generando reporte de Google Ads para {client_name}: {str(e)}"
                )
            except:
                pass
