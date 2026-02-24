# services/permissions_service.py
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import json
import hashlib
from sqlalchemy.orm import Session
from database.db_enterprise import get_primary_session as get_db
from models.models import UserPermissions, StorageStrategy, CostSavings
import logging

logger = logging.getLogger(__name__)

class PermissionsService:
    """🔧 Servicio de gestión de permisos de usuario y almacenamiento local"""
    
    def __init__(self):
        self.permission_types = [
            "local_storage",
            "notifications", 
            "geolocation",
            "microphone",
            "camera",
            "file_system"
        ]
    
    async def process_user_permissions(
        self, 
        user_id: str,
        permissions_granted: Dict[str, Any],
        device_info: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """
        📱 Procesa permisos otorgados durante MFA
        """
        try:
            logger.info(f"Processing permissions for user {user_id}")
            
            # 1. Guardar permisos en perfil de usuario
            permissions_record = await self._save_user_permissions(
                user_id, permissions_granted, device_info, db
            )
            
            # 2. Configurar estrategia de almacenamiento
            storage_strategy = await self._configure_storage_strategy(
                user_id, permissions_granted, db
            )
            
            # 3. Configurar notificaciones
            notification_config = await self._configure_notifications(
                user_id, permissions_granted.get('notifications', {}), db
            )
            
            # 4. Configurar geolocalización para seguridad
            location_config = await self._configure_location_security(
                user_id, permissions_granted.get('geolocation', {}), db
            )
            
            # 5. Calcular ahorro de costos
            cost_reduction = await self._calculate_cost_savings(
                user_id, storage_strategy, db
            )
            
            # 6. Generar respuesta para frontend
            frontend_config = await self._generate_frontend_config(
                permissions_granted, storage_strategy, cost_reduction
            )
            
            return {
                "success": True,
                "permissions_saved": True,
                "permissions_count": len([p for p in permissions_granted.values() if p.get('permission_granted')]),
                "storage_strategy": storage_strategy,
                "notification_config": notification_config,
                "location_config": location_config,
                "cost_reduction_estimate": cost_reduction,
                "frontend_config": frontend_config,
                "user_benefits": self._generate_user_benefits(
                    storage_strategy, cost_reduction
                )
            }
            
        except Exception as e:
            logger.error(f"Error processing permissions for user {user_id}: {str(e)}")
            raise Exception(f"Error procesando permisos: {str(e)}")
    
    async def _save_user_permissions(
        self, 
        user_id: str,
        permissions: Dict[str, Any],
        device_info: Dict[str, Any],
        db: Session
    ) -> UserPermissions:
        """💾 Guarda permisos de usuario en base de datos"""
        
        # Buscar registro existente
        existing = db.query(UserPermissions).filter(
            UserPermissions.user_id == user_id
        ).first()
        
        permissions_data = {
            "local_storage": permissions.get('local_storage', {}),
            "notifications": permissions.get('notifications', {}),
            "geolocation": permissions.get('geolocation', {}),
            "microphone": permissions.get('microphone', {}),
            "camera": permissions.get('camera', {}),
            "file_system": permissions.get('file_system', {}),
            "device_info": device_info
        }
        
        if existing:
            # Actualizar existente
            existing.permissions_data = permissions_data
            existing.granted_at = datetime.utcnow()
            existing.last_updated = datetime.utcnow()
            db.commit()
            db.refresh(existing)
            return existing
        else:
            # Crear nuevo
            new_permissions = UserPermissions(
                user_id=user_id,
                permissions_data=permissions_data,
                granted_at=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
            db.add(new_permissions)
            db.commit()
            db.refresh(new_permissions)
            return new_permissions
    
    async def _configure_storage_strategy(
        self, 
        user_id: str,
        permissions: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """🗄️ Configura estrategia de almacenamiento híbrido"""
        
        local_storage = permissions.get('local_storage', {})
        
        if local_storage.get('permission_granted'):
            # ✅ Usuario permitió almacenamiento local
            strategy_config = {
                "primary_storage": "local",
                "backup_storage": "cloud",
                "sync_frequency": "smart",  # Sync inteligente
                "local_retention_days": 30,
                "auto_cleanup": True,
                "offline_mode": True,
                "compression_enabled": True,
                "encryption_enabled": True,
                "estimated_cost_reduction": 0.75,  # 75% reducción
                "local_storage_quota_mb": local_storage.get('available_space', 0) // (1024 * 1024),
                "sync_rules": {
                    "important_messages": True,
                    "media_files": False,  # Solo local
                    "user_preferences": True,
                    "chat_history_days": 7  # Solo últimos 7 días al cloud
                }
            }
        else:
            # ❌ Sin almacenamiento local - solo cloud
            strategy_config = {
                "primary_storage": "cloud",
                "backup_storage": None,
                "sync_frequency": "immediate",
                "local_retention_days": 0,
                "auto_cleanup": False,
                "offline_mode": False,
                "compression_enabled": False,
                "encryption_enabled": True,
                "estimated_cost_reduction": 0.0,
                "local_storage_quota_mb": 0,
                "sync_rules": {
                    "important_messages": True,
                    "media_files": True,
                    "user_preferences": True,
                    "chat_history_days": 365
                }
            }
        
        # Guardar estrategia en DB
        await self._save_storage_strategy(user_id, strategy_config, db)
        
        return strategy_config
    
    async def _save_storage_strategy(
        self,
        user_id: str,
        strategy: Dict[str, Any],
        db: Session
    ):
        """💾 Guarda estrategia de almacenamiento"""
        
        existing = db.query(StorageStrategy).filter(
            StorageStrategy.user_id == user_id
        ).first()
        
        if existing:
            existing.strategy_config = strategy
            existing.last_updated = datetime.utcnow()
        else:
            new_strategy = StorageStrategy(
                user_id=user_id,
                strategy_config=strategy,
                created_at=datetime.utcnow(),
                last_updated=datetime.utcnow()
            )
            db.add(new_strategy)
        
        db.commit()
    
    async def _configure_notifications(
        self,
        user_id: str,
        notifications: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """🔔 Configura sistema de notificaciones"""
        
        if notifications.get('permission') == 'granted':
            config = {
                "enabled": True,
                "push_endpoint": notifications.get('endpoint'),
                "subscription_data": notifications.get('subscription'),
                "notification_types": {
                    "chat_messages": True,
                    "system_updates": True,
                    "security_alerts": True,
                    "cost_savings_reports": True,
                    "feature_announcements": False
                },
                "quiet_hours": {
                    "enabled": True,
                    "start": "22:00",
                    "end": "08:00"
                },
                "frequency_limits": {
                    "max_per_hour": 10,
                    "max_per_day": 50
                }
            }
        else:
            config = {
                "enabled": False,
                "push_endpoint": None,
                "notification_types": {},
                "quiet_hours": {"enabled": False},
                "frequency_limits": {}
            }
        
        return config
    
    async def _configure_location_security(
        self,
        user_id: str,
        geolocation: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """🌍 Configura geolocalización para seguridad"""
        
        if geolocation.get('permission') == 'granted':
            config = {
                "enabled": True,
                "current_location": {
                    "latitude": geolocation.get('latitude'),
                    "longitude": geolocation.get('longitude'),
                    "accuracy": geolocation.get('accuracy'),
                    "timestamp": geolocation.get('timestamp')
                },
                "security_features": {
                    "login_location_verification": True,
                    "suspicious_location_alerts": True,
                    "travel_notifications": True,
                    "location_based_mfa": True
                },
                "privacy_settings": {
                    "store_location_history": False,  # Solo ubicación actual
                    "share_with_third_parties": False,
                    "anonymize_location_data": True
                }
            }
        else:
            config = {
                "enabled": False,
                "security_features": {},
                "privacy_settings": {}
            }
        
        return config
    
    async def _calculate_cost_savings(
        self,
        user_id: str,
        storage_strategy: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """💰 Calcula ahorro de costos por almacenamiento local"""
        
        base_costs = {
            "monthly_db_requests": 20000,      # 20k requests base
            "monthly_storage_mb": 500,         # 500MB storage base
            "monthly_bandwidth_gb": 2.0,       # 2GB bandwidth base
            "monthly_compute_hours": 100       # 100 horas compute
        }
        
        cost_per_unit = {
            "db_request": 0.0001,              # $0.0001 por request
            "storage_mb": 0.02,                # $0.02 por MB
            "bandwidth_gb": 0.09,              # $0.09 por GB
            "compute_hour": 0.05               # $0.05 por hora
        }
        
        if storage_strategy["primary_storage"] == "local":
            # 📉 Reducción con almacenamiento local
            reduction_factor = storage_strategy["estimated_cost_reduction"]
            
            savings = {
                "monthly_db_requests_saved": int(base_costs["monthly_db_requests"] * reduction_factor),
                "monthly_storage_mb_saved": int(base_costs["monthly_storage_mb"] * reduction_factor),
                "monthly_bandwidth_gb_saved": base_costs["monthly_bandwidth_gb"] * reduction_factor,
                "monthly_compute_hours_saved": base_costs["monthly_compute_hours"] * 0.3,  # 30% menos compute
                
                "monthly_cost_saved_usd": round(
                    (base_costs["monthly_db_requests"] * reduction_factor * cost_per_unit["db_request"]) +
                    (base_costs["monthly_storage_mb"] * reduction_factor * cost_per_unit["storage_mb"]) +
                    (base_costs["monthly_bandwidth_gb"] * reduction_factor * cost_per_unit["bandwidth_gb"]) +
                    (base_costs["monthly_compute_hours"] * 0.3 * cost_per_unit["compute_hour"]), 2
                ),
                
                "annual_cost_saved_usd": 0,  # Se calculará después
                "carbon_footprint_reduced_kg": round(reduction_factor * 2.5, 2),  # 2.5kg CO2 base
                
                "breakdown": {
                    "database_costs_saved": round(base_costs["monthly_db_requests"] * reduction_factor * cost_per_unit["db_request"], 2),
                    "storage_costs_saved": round(base_costs["monthly_storage_mb"] * reduction_factor * cost_per_unit["storage_mb"], 2),
                    "bandwidth_costs_saved": round(base_costs["monthly_bandwidth_gb"] * reduction_factor * cost_per_unit["bandwidth_gb"], 2),
                    "compute_costs_saved": round(base_costs["monthly_compute_hours"] * 0.3 * cost_per_unit["compute_hour"], 2)
                }
            }
            
            savings["annual_cost_saved_usd"] = round(savings["monthly_cost_saved_usd"] * 12, 2)
            
        else:
            # 📈 Sin reducción - costos normales
            savings = {
                "monthly_db_requests_saved": 0,
                "monthly_storage_mb_saved": 0,
                "monthly_bandwidth_gb_saved": 0.0,
                "monthly_compute_hours_saved": 0,
                "monthly_cost_saved_usd": 0.0,
                "annual_cost_saved_usd": 0.0,
                "carbon_footprint_reduced_kg": 0.0,
                "breakdown": {
                    "database_costs_saved": 0.0,
                    "storage_costs_saved": 0.0,
                    "bandwidth_costs_saved": 0.0,
                    "compute_costs_saved": 0.0
                }
            }
        
        # Guardar métricas en DB
        await self._save_cost_savings(user_id, savings, db)
        
        return savings
    
    async def _save_cost_savings(
        self,
        user_id: str,
        savings: Dict[str, Any],
        db: Session
    ):
        """💾 Guarda métricas de ahorro de costos"""
        
        existing = db.query(CostSavings).filter(
            CostSavings.user_id == user_id
        ).first()
        
        if existing:
            existing.monthly_savings_usd = savings["monthly_cost_saved_usd"]
            existing.annual_savings_usd = savings["annual_cost_saved_usd"]
            existing.requests_saved = savings["monthly_db_requests_saved"]
            existing.storage_saved_mb = savings["monthly_storage_mb_saved"]
            existing.carbon_saved_kg = savings["carbon_footprint_reduced_kg"]
            existing.last_calculated = datetime.utcnow()
        else:
            new_savings = CostSavings(
                user_id=user_id,
                monthly_savings_usd=savings["monthly_cost_saved_usd"],
                annual_savings_usd=savings["annual_cost_saved_usd"],
                requests_saved=savings["monthly_db_requests_saved"],
                storage_saved_mb=savings["monthly_storage_mb_saved"],
                carbon_saved_kg=savings["carbon_footprint_reduced_kg"],
                created_at=datetime.utcnow(),
                last_calculated=datetime.utcnow()
            )
            db.add(new_savings)
        
        db.commit()
    
    async def _generate_frontend_config(
        self,
        permissions: Dict[str, Any],
        storage_strategy: Dict[str, Any],
        cost_reduction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """🎨 Genera configuración para el frontend"""
        
        return {
            "storage": {
                "use_local_storage": storage_strategy["primary_storage"] == "local",
                "offline_mode": storage_strategy["offline_mode"],
                "sync_frequency": storage_strategy["sync_frequency"],
                "auto_cleanup": storage_strategy["auto_cleanup"],
                "local_quota_mb": storage_strategy["local_storage_quota_mb"]
            },
            "notifications": {
                "enabled": permissions.get('notifications', {}).get('permission') == 'granted',
                "endpoint": permissions.get('notifications', {}).get('endpoint')
            },
            "location": {
                "enabled": permissions.get('geolocation', {}).get('permission') == 'granted'
            },
            "media": {
                "microphone": permissions.get('microphone', {}).get('permission') == 'granted',
                "camera": permissions.get('camera', {}).get('permission') == 'granted'
            },
            "files": {
                "native_picker": permissions.get('file_system', {}).get('permission') == 'granted'
            },
            "cost_optimization": {
                "monthly_savings": cost_reduction["monthly_cost_saved_usd"],
                "annual_savings": cost_reduction["annual_cost_saved_usd"],
                "environmental_impact": cost_reduction["carbon_footprint_reduced_kg"]
            }
        }
    
    def _generate_user_benefits(
        self,
        storage_strategy: Dict[str, Any],
        cost_reduction: Dict[str, Any]
    ) -> Dict[str, Any]:
        """🎁 Genera beneficios para mostrar al usuario"""
        
        return {
            "faster_app": storage_strategy["offline_mode"],
            "reduced_data_usage": storage_strategy["primary_storage"] == "local",
            "monthly_cost_savings": cost_reduction["monthly_cost_saved_usd"],
            "annual_cost_savings": cost_reduction["annual_cost_saved_usd"],
            "environmental_impact": cost_reduction["carbon_footprint_reduced_kg"],
            "offline_capability": storage_strategy["offline_mode"],
            "enhanced_privacy": storage_strategy["encryption_enabled"],
            "better_performance": storage_strategy["compression_enabled"]
        }
    
    async def get_user_permissions_status(
        self,
        user_id: str,
        db: Session
    ) -> Dict[str, Any]:
        """📊 Obtiene estado actual de permisos del usuario"""
        
        try:
            # Obtener permisos
            permissions = db.query(UserPermissions).filter(
                UserPermissions.user_id == user_id
            ).first()
            
            # Obtener estrategia de almacenamiento
            storage = db.query(StorageStrategy).filter(
                StorageStrategy.user_id == user_id
            ).first()
            
            # Obtener ahorros
            savings = db.query(CostSavings).filter(
                CostSavings.user_id == user_id
            ).first()
            
            return {
                "permissions": permissions.permissions_data if permissions else {},
                "storage_strategy": storage.strategy_config if storage else {},
                "cost_savings": {
                    "monthly_usd": savings.monthly_savings_usd if savings else 0.0,
                    "annual_usd": savings.annual_savings_usd if savings else 0.0,
                    "requests_saved": savings.requests_saved if savings else 0,
                    "storage_saved_mb": savings.storage_saved_mb if savings else 0,
                    "carbon_saved_kg": savings.carbon_saved_kg if savings else 0.0
                } if savings else {},
                "recommendations": await self._generate_recommendations(permissions, storage, savings)
            }
            
        except Exception as e:
            logger.error(f"Error getting permissions status for user {user_id}: {str(e)}")
            return {
                "permissions": {},
                "storage_strategy": {},
                "cost_savings": {},
                "recommendations": []
            }
    
    async def _generate_recommendations(
        self,
        permissions: Optional[UserPermissions],
        storage: Optional[StorageStrategy],
        savings: Optional[CostSavings]
    ) -> List[Dict[str, Any]]:
        """💡 Genera recomendaciones para el usuario"""
        
        recommendations = []
        
        if not permissions:
            recommendations.append({
                "type": "setup",
                "priority": "high",
                "title": "Configurar permisos",
                "description": "Permite a la app acceder a almacenamiento local para reducir costos",
                "action": "grant_permissions",
                "potential_savings_usd": 12.50
            })
        else:
            perms_data = permissions.permissions_data
            
            # Recomendación de almacenamiento local
            if not perms_data.get('local_storage', {}).get('permission_granted'):
                recommendations.append({
                    "type": "optimization",
                    "priority": "high",
                    "title": "Habilitar almacenamiento local",
                    "description": "Reduce costos hasta 75% y mejora velocidad",
                    "action": "enable_local_storage",
                    "potential_savings_usd": 9.50
                })
            
            # Recomendación de notificaciones
            if not perms_data.get('notifications', {}).get('permission_granted'):
                recommendations.append({
                    "type": "engagement",
                    "priority": "medium", 
                    "title": "Activar notificaciones",
                    "description": "Mantente informado de actualizaciones importantes",
                    "action": "enable_notifications",
                    "potential_savings_usd": 0.0
                })
        
        return recommendations
    
    async def update_storage_strategy(
        self,
        user_id: str,
        new_strategy: Dict[str, Any],
        db: Session
    ) -> Dict[str, Any]:
        """🔄 Actualiza estrategia de almacenamiento"""
        
        try:
            existing = db.query(StorageStrategy).filter(
                StorageStrategy.user_id == user_id
            ).first()
            
            if existing:
                old_strategy = existing.strategy_config.copy()
                existing.strategy_config = new_strategy
                existing.last_updated = datetime.utcnow()
                db.commit()
                
                # Recalcular ahorros
                new_savings = await self._calculate_cost_savings(user_id, new_strategy, db)
                
                return {
                    "strategy": new_strategy,
                    "impact": {
                        "cost_change": new_savings["monthly_cost_saved_usd"],
                        "performance_change": "improved" if new_strategy.get("offline_mode") else "standard",
                        "storage_change": new_strategy.get("local_storage_quota_mb", 0)
                    }
                }
            else:
                raise Exception("No se encontró estrategia existente")
                
        except Exception as e:
            logger.error(f"Error updating storage strategy for user {user_id}: {str(e)}")
            raise Exception(f"Error actualizando estrategia: {str(e)}")

# 🌐 Instancia global del servicio
permissions_service = PermissionsService()