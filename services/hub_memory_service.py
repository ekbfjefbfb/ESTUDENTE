import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from services.redis_service import get_cache, set_cache
from services.redis_service import get_redis

logger = logging.getLogger("hub_memory_service")


class HubMemoryService:
    def __init__(self):
        self.ttl_seconds = int(os.getenv("HUB_MEMORY_TTL_SECONDS", str(7 * 24 * 3600)))
        self.recent_limit = int(os.getenv("HUB_RECENT_LIMIT", "50"))

    def _memory_key(self, memory_id: str) -> str:
        return f"hub:memory:{memory_id}"

    def _recent_key(self, user_id: str) -> str:
        return f"hub:user:{user_id}:recent"

    async def save_memory(
        self,
        *,
        user_id: str,
        memory_id: Optional[str] = None,
        text: str,
        sources: List[Dict[str, str]],
        query: str,
        debug: Dict[str, Any],
    ) -> str:
        memory_id = str(memory_id or uuid.uuid4())
        payload = {
            "memory_id": memory_id,
            "user_id": str(user_id),
            "text": text,
            "sources": sources,
            "query": query,
            "debug": debug,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Fail-open: if Redis is down, still return an id so UX continues.
        try:
            await set_cache(self._memory_key(memory_id), payload, ttl=self.ttl_seconds)
        except Exception as e:
            logger.warning("hub_memory_save_failed", extra={"error": str(e)})

        # Maintain recent list as cached array (simple + compatible with existing redis_service helpers).
        try:
            recent_key = self._recent_key(str(user_id))
            redis = await get_redis()
            if redis is not None:
                try:
                    await redis.lpush(recent_key, memory_id)
                    await redis.ltrim(recent_key, 0, max(self.recent_limit - 1, 0))
                    await redis.expire(recent_key, self.ttl_seconds)
                except Exception:
                    recent = await get_cache(recent_key, default=[])
                    if not isinstance(recent, list):
                        recent = []
                    recent.insert(0, memory_id)
                    recent = recent[: self.recent_limit]
                    await set_cache(recent_key, recent, ttl=self.ttl_seconds)
            else:
                recent = await get_cache(recent_key, default=[])
                if not isinstance(recent, list):
                    recent = []
                recent.insert(0, memory_id)
                recent = recent[: self.recent_limit]
                await set_cache(recent_key, recent, ttl=self.ttl_seconds)
        except Exception as e:
            logger.warning("hub_memory_recent_update_failed", extra={"error": str(e)})

        return memory_id

    async def get_memory(self, *, memory_id: str) -> Optional[Dict[str, Any]]:
        try:
            data = await get_cache(self._memory_key(memory_id))
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    async def get_recent(self, *, user_id: str, limit: int = 20) -> List[str]:
        try:
            recent_key = self._recent_key(str(user_id))
            redis = await get_redis()
            if redis is not None:
                try:
                    items = await redis.lrange(recent_key, 0, max(int(limit) - 1, 0))
                    return [str(x) for x in (items or [])]
                except Exception:
                    pass

            recent = await get_cache(recent_key, default=[])
            if not isinstance(recent, list):
                return []
            return [str(x) for x in recent[:limit]]
        except Exception:
            return []


hub_memory_service = HubMemoryService()
