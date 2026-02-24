"""
Router para Meta Ads (Facebook & Instagram Ads)
Integración con Facebook Marketing API v18

Usa MetaAdsService para extracción de métricas
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

# Importar service
from services.meta_ads_service import get_meta_ads_service
from services.slack_service import get_slack_service

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/meta-ads", tags=["📘 Meta Ads (Facebook/Instagram)"])


class MetaAdsMetricsRequest(BaseModel):
    account_id: str
    date_range: str = "last_30d"  # last_7d, last_30d, last_90d, o custom
    level: str = "account"  # account, campaign, adset, ad
    metrics: Optional[List[str]] = None


@router.on_event("startup")
async def init_meta_ads_api():
    """Inicializar Facebook Ads API"""
    if META_ADS_AVAILABLE:
        access_token = os.getenv("META_ACCESS_TOKEN")
        app_secret = os.getenv("META_APP_SECRET")
        app_id = os.getenv("META_APP_ID")
        
        if access_token:
            FacebookAdsApi.init(
                app_id=app_id,
                app_secret=app_secret,
                access_token=access_token
            )


@router.get("/accounts")
async def list_ad_accounts():
    """
    Listar cuentas de ads disponibles
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Facebook Business SDK no disponible. Instalar: pip install facebook-business"
        )
    
    try:
        from facebook_business.adobjects.user import User
        
        # Usuario actual
        me = User(fbid='me')
        accounts = me.get_ad_accounts(fields=[
            'id',
            'name',
            'account_status',
            'currency',
            'timezone_name'
        ])
        
        return {
            "accounts": [
                {
                    "id": acc['id'],
                    "name": acc['name'],
                    "status": acc['account_status'],
                    "currency": acc['currency'],
                    "timezone": acc['timezone_name']
                }
                for acc in accounts
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@router.get("/campaigns/{account_id}")
async def list_campaigns(
    account_id: str,
    status: Optional[str] = None  # ACTIVE, PAUSED, DELETED, ARCHIVED
):
    """
    Listar campañas de una cuenta
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        account = AdAccount(f'act_{account_id}')
        
        params = {
            'fields': [
                'id',
                'name',
                'status',
                'objective',
                'daily_budget',
                'lifetime_budget',
                'start_time',
                'stop_time',
                'created_time',
                'updated_time'
            ]
        }
        
        if status:
            params['filtering'] = [{'field': 'status', 'operator': 'EQUAL', 'value': status}]
        
        campaigns = account.get_campaigns(params=params)
        
        return {
            "account_id": account_id,
            "campaigns": [
                {
                    "id": c['id'],
                    "name": c['name'],
                    "status": c['status'],
                    "objective": c.get('objective'),
                    "daily_budget": int(c.get('daily_budget', 0)) / 100 if c.get('daily_budget') else None,
                    "lifetime_budget": int(c.get('lifetime_budget', 0)) / 100 if c.get('lifetime_budget') else None,
                    "start_time": c.get('start_time'),
                    "stop_time": c.get('stop_time'),
                    "created_time": c.get('created_time'),
                    "updated_time": c.get('updated_time')
                }
                for c in campaigns
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics/{account_id}")
async def get_account_metrics(
    account_id: str,
    date_preset: str = "last_30d",  # today, yesterday, last_7d, last_30d, last_90d
    breakdowns: Optional[List[str]] = None
):
    """
    Métricas agregadas de cuenta
    
    Métricas principales:
    - impressions: Impresiones totales
    - reach: Alcance único
    - clicks: Clicks totales
    - ctr: Click-through rate (%)
    - spend: Gasto total
    - cpc: Costo por click
    - cpm: Costo por 1000 impresiones
    - conversions: Conversiones totales
    - cost_per_conversion: Costo por conversión
    
    Breakdowns opcionales:
    - age, gender, country, region, placement, device_platform
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        account = AdAccount(f'act_{account_id}')
        
        params = {
            'time_range': {'since': '', 'until': ''},  # Se llena con date_preset
            'date_preset': date_preset,
            'level': 'account',
            'fields': [
                'impressions',
                'reach',
                'clicks',
                'ctr',
                'spend',
                'cpc',
                'cpm',
                'frequency',
                'actions',  # Incluye conversiones
                'cost_per_action_type',
                'action_values'
            ]
        }
        
        if breakdowns:
            params['breakdowns'] = breakdowns
        
        insights = account.get_insights(params=params)
        
        # Parsear resultados
        if not insights:
            return {
                "account_id": account_id,
                "period": date_preset,
                "metrics": {},
                "message": "No data available"
            }
        
        insight = insights[0]
        
        # Extraer conversiones
        conversions = 0
        cost_per_conversion = 0
        if 'actions' in insight:
            for action in insight['actions']:
                if action['action_type'] in ['purchase', 'lead', 'complete_registration', 'add_to_cart']:
                    conversions += int(action['value'])
        
        if 'cost_per_action_type' in insight:
            for cost_action in insight['cost_per_action_type']:
                if cost_action['action_type'] in ['purchase', 'lead']:
                    cost_per_conversion = float(cost_action['value'])
                    break
        
        metrics = {
            "impressions": int(insight.get('impressions', 0)),
            "reach": int(insight.get('reach', 0)),
            "clicks": int(insight.get('clicks', 0)),
            "ctr": round(float(insight.get('ctr', 0)), 2),
            "spend": round(float(insight.get('spend', 0)), 2),
            "cpc": round(float(insight.get('cpc', 0)), 2),
            "cpm": round(float(insight.get('cpm', 0)), 2),
            "frequency": round(float(insight.get('frequency', 0)), 2),
            "conversions": conversions,
            "cost_per_conversion": round(cost_per_conversion, 2)
        }
        
        return {
            "account_id": account_id,
            "period": date_preset,
            "metrics": metrics
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/campaign-performance/{campaign_id}")
async def get_campaign_performance(
    campaign_id: str,
    date_preset: str = "last_30d"
):
    """
    Performance detallado de una campaña específica
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        campaign = Campaign(fbid=campaign_id)
        
        params = {
            'date_preset': date_preset,
            'level': 'campaign',
            'fields': [
                'impressions',
                'reach',
                'clicks',
                'ctr',
                'spend',
                'cpc',
                'cpm',
                'conversions',
                'cost_per_conversion',
                'actions',
                'cost_per_action_type'
            ]
        }
        
        insights = campaign.get_insights(params=params)
        
        if not insights:
            return {
                "campaign_id": campaign_id,
                "message": "No data available"
            }
        
        insight = insights[0]
        
        return {
            "campaign_id": campaign_id,
            "period": date_preset,
            "performance": {
                "impressions": int(insight.get('impressions', 0)),
                "reach": int(insight.get('reach', 0)),
                "clicks": int(insight.get('clicks', 0)),
                "ctr": round(float(insight.get('ctr', 0)), 2),
                "spend": round(float(insight.get('spend', 0)), 2),
                "cpc": round(float(insight.get('cpc', 0)), 2),
                "cpm": round(float(insight.get('cpm', 0)), 2)
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adsets/{campaign_id}")
async def get_campaign_adsets(campaign_id: str):
    """
    Listar ad sets de una campaña
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        campaign = Campaign(fbid=campaign_id)
        
        adsets = campaign.get_ad_sets(fields=[
            'id',
            'name',
            'status',
            'daily_budget',
            'lifetime_budget',
            'targeting',
            'optimization_goal',
            'billing_event'
        ])
        
        return {
            "campaign_id": campaign_id,
            "adsets": [
                {
                    "id": adset['id'],
                    "name": adset['name'],
                    "status": adset['status'],
                    "daily_budget": int(adset.get('daily_budget', 0)) / 100 if adset.get('daily_budget') else None,
                    "optimization_goal": adset.get('optimization_goal'),
                    "billing_event": adset.get('billing_event')
                }
                for adset in adsets
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ads/{adset_id}")
async def get_adset_ads(adset_id: str):
    """
    Listar anuncios de un ad set
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        adset = AdSet(fbid=adset_id)
        
        ads = adset.get_ads(fields=[
            'id',
            'name',
            'status',
            'creative',
            'tracking_specs',
            'conversion_specs'
        ])
        
        return {
            "adset_id": adset_id,
            "ads": [
                {
                    "id": ad['id'],
                    "name": ad['name'],
                    "status": ad['status']
                }
                for ad in ads
            ]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/compare-periods/{account_id}")
async def compare_periods(
    account_id: str,
    current_period: str = "last_30d",
    previous_period: str = "last_30d"  # Usar date_preset o custom range
):
    """
    Comparar dos periodos (ej: este mes vs mes pasado)
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        # Periodo actual
        current_data = await get_account_metrics(account_id, current_period)
        
        # Periodo anterior (calcular fechas)
        # TODO: Implementar lógica para calcular periodo anterior
        # Por ahora usar same preset
        
        account = AdAccount(f'act_{account_id}')
        
        # Insights periodo anterior
        # ... (similar a get_account_metrics pero con fechas diferentes)
        
        return {
            "account_id": account_id,
            "comparison": {
                "current": current_data,
                "previous": {},  # TODO
                "changes": {}
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/breakdown/age-gender/{account_id}")
async def get_age_gender_breakdown(
    account_id: str,
    date_preset: str = "last_30d"
):
    """
    Breakdown por edad y género
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        return await get_account_metrics(
            account_id=account_id,
            date_preset=date_preset,
            breakdowns=['age', 'gender']
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/breakdown/placement/{account_id}")
async def get_placement_breakdown(
    account_id: str,
    date_preset: str = "last_30d"
):
    """
    Breakdown por placement (Facebook Feed, Instagram Stories, etc.)
    """
    if not META_ADS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Meta Ads API no disponible")
    
    try:
        return await get_account_metrics(
            account_id=account_id,
            date_preset=date_preset,
            breakdowns=['publisher_platform', 'platform_position']
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def health_check():
    """Verificar estado de integración Meta Ads"""
    access_token = os.getenv("META_ACCESS_TOKEN")
    
    return {
        "service": "Meta Ads (Facebook/Instagram)",
        "status": "available" if META_ADS_AVAILABLE else "unavailable",
        "configured": bool(access_token),
        "message": "OK" if META_ADS_AVAILABLE and access_token else "Configurar META_ACCESS_TOKEN en .env"
    }


@router.post("/webhook")
async def meta_ads_webhook(request: dict):
    """
    Webhook para recibir notificaciones de Meta
    
    Eventos:
    - Campaña pausada
    - Budget agotado
    - Anuncio rechazado
    - Performance alerts
    """
    # TODO: Implementar lógica de webhook
    # Verificar firma HMAC
    # Procesar eventos
    # Notificar en Slack si es relevante
    
    return {"status": "received"}
