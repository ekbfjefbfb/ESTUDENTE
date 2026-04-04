"""
📍 UserContextService - Gestión de contexto del usuario para automatización inteligente
Ubicación, documentos, decisiones de auto-grabación
"""
import logging
from datetime import datetime, date
from typing import Optional, List
from math import radians, sin, cos, sqrt, atan2

from models.models import UserContext, UserDocumentIndex, ScheduledRecording
from database.db_enterprise import get_primary_session

logger = logging.getLogger("user_context_service")


class UserContextService:
    """
    Servicio para mantener y utilizar el contexto del usuario
    para decisiones inteligentes de automatización.
    """

    def __init__(self):
        logger.info("📍 UserContextService inicializado")

    async def update_location(
        self,
        user_id: str,
        lat: float,
        lng: float,
        device_id: Optional[str] = None,
        battery_level: Optional[int] = None,
        device_platform: Optional[str] = None
    ) -> UserContext:
        """
        Actualiza ubicación y contexto del usuario.

        Args:
            user_id: ID del usuario
            lat: Latitud
            lng: Longitud
            device_id: ID del dispositivo
            battery_level: Nivel de batería (0-100)
            device_platform: ios/android

        Returns:
            UserContext actualizado
        """
        async with await get_primary_session() as session:
            context = await session.get(UserContext, user_id)

            if not context:
                context = UserContext(
                    user_id=user_id,
                    current_location_lat=lat,
                    current_location_lng=lng,
                    location_updated_at=datetime.utcnow(),
                    device_id=device_id,
                    device_battery_level=battery_level,
                    device_platform=device_platform,
                    last_device_ping=datetime.utcnow()
                )
                session.add(context)
            else:
                context.current_location_lat = lat
                context.current_location_lng = lng
                context.location_updated_at = datetime.utcnow()
                context.last_device_ping = datetime.utcnow()

                if device_id:
                    context.device_id = device_id
                if battery_level is not None:
                    context.device_battery_level = battery_level
                if device_platform:
                    context.device_platform = device_platform

            await session.commit()
            logger.debug(f"📍 Ubicación actualizada: {user_id} @ ({lat}, {lng})")
            return context

    async def get_context(self, user_id: str) -> Optional[UserContext]:
        """Obtiene el contexto actual del usuario"""
        async with await get_primary_session() as session:
            return await session.get(UserContext, user_id)

    async def find_documents_for_class(
        self,
        user_id: str,
        class_name: str,
        limit: int = 5
    ) -> List[UserDocumentIndex]:
        """
        Busca documentos relevantes para una clase específica.

        Args:
            user_id: ID del usuario
            class_name: Nombre de la clase (ej: "Cálculo I")
            limit: Máximo de documentos a retornar

        Returns:
            Lista de documentos relevantes
        """
        async with await get_primary_session() as session:
            # Estrategia de búsqueda:
            # 1. Buscar por related_class exacto
            # 2. Buscar por keywords que coincidan con class_name
            # 3. Buscar por filename que contenga palabras de class_name

            from sqlalchemy import or_, desc, select

            # Normalizar class_name para búsqueda
            search_terms = class_name.lower().split()

            stmt = (
                select(UserDocumentIndex)
                .where(
                    UserDocumentIndex.user_id == user_id,
                    UserDocumentIndex.is_deleted_on_device.is_(False),
                    or_(
                        UserDocumentIndex.related_class.ilike(f"%{class_name}%"),
                        UserDocumentIndex.document_type.in_(["syllabus", "notes"]),
                        *[
                            or_(
                                UserDocumentIndex.filename.ilike(f"%{term}%"),
                                UserDocumentIndex.keywords.ilike(f"%{term}%"),
                            )
                            for term in search_terms
                            if len(term) > 3
                        ],
                    ),
                )
                .order_by(desc(UserDocumentIndex.last_sync))
                .limit(limit)
            )

            result = await session.execute(stmt)
            documents = result.scalars().all()

            logger.info(f"📄 Encontrados {len(documents)} documentos para '{class_name}'")
            return list(documents)

    async def should_start_recording(
        self,
        scheduled: ScheduledRecording,
        current_lat: Optional[float],
        current_lng: Optional[float],
        battery_level: Optional[int]
    ) -> tuple[bool, str]:
        """
        Decide si iniciar grabación automáticamente basado en múltiples factores.

        Args:
            scheduled: ScheduledRecording a evaluar
            current_lat: Latitud actual del usuario
            current_lng: Longitud actual del usuario
            battery_level: Nivel de batería del dispositivo

        Returns:
            (should_start, reason)
        """
        # 1. Verificar que no esté ya grabando
        context = await self.get_context(scheduled.user_id)
        if context and context.is_recording:
            return False, "Ya hay una grabación en progreso"

        # 2. Verificar batería
        if battery_level is not None and battery_level < 20:
            return False, "Batería muy baja (< 20%)"

        # 3. Verificar ubicación si está configurada
        if scheduled.location_lat is not None and scheduled.location_lng is not None:
            if current_lat is None or current_lng is None:
                return False, "Se requiere ubicación para esta grabación"

            distance = self._calculate_distance(
                current_lat, current_lng,
                scheduled.location_lat, scheduled.location_lng
            )

            if distance > scheduled.location_radius_meters:
                location_name = scheduled.location_name or "la ubicación"
                return False, f"Debes estar en {location_name} (distancia: {int(distance)}m)"

        # 4. Verificar tiempo (± 2 minutos de margen)
        now = datetime.utcnow()
        time_diff = abs((now - scheduled.scheduled_at).total_seconds())
        if time_diff > 120:  # 2 minutos
            return False, f"Fuera de horario programado (diferencia: {int(time_diff)}s)"

        return True, "OK"

    async def increment_daily_count(self, user_id: str) -> int:
        """
        Incrementa el contador de grabaciones automáticas del día.
        Resetea si es un nuevo día.

        Returns:
            Nuevo contador
        """
        async with await get_primary_session() as session:
            context = await session.get(UserContext, user_id)

            if not context:
                return 0

            today = date.today()

            # Reset si es un nuevo día
            if context.daily_auto_recordings_date != today:
                context.daily_auto_recordings_date = today
                context.daily_auto_recordings_count = 1
            else:
                context.daily_auto_recordings_count += 1

            await session.commit()
            return context.daily_auto_recordings_count

    def _calculate_distance(self, lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """
        Calcula distancia en metros entre dos puntos usando Haversine.
        """
        R = 6371000  # Radio de la Tierra en metros

        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lng = radians(lng2 - lng1)

        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lng / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return R * c


# Instancia global
user_context_service = UserContextService()
