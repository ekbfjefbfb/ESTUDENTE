import asyncio
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, Optional, Sequence, cast

from fastapi import HTTPException, Request
from prometheus_client import Counter
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from services.redis_service import get_redis_client

logger = logging.getLogger("rate_limit")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        (
            '{"time": "%(asctime)s", "level": "%(levelname)s", '
            '"message": "%(message)s"}'
        )
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel("INFO")

RATE_LIMIT_REDIS_TIMEOUT_SECONDS = max(
    0.05,
    float(os.getenv("RATE_LIMIT_REDIS_TIMEOUT_SECONDS", "0.25")),
)

RATE_LIMIT_EXCEEDED = Counter(
    "rate_limit_exceeded_total",
    "Número de requests bloqueadas por rate limit",
    ["key", "user_id", "ip", "task_type"]
)

LUA_RATE_LIMIT = """
local counter_key = KEYS[1]
local block_key = KEYS[2]
local limit = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local block_seconds = tonumber(ARGV[3])

local blocked_ttl = redis.call("PTTL", block_key)
if blocked_ttl and blocked_ttl > 0 then
    local current_value = redis.call("GET", counter_key) or "0"
    return {0, tonumber(current_value), 0, math.ceil(blocked_ttl / 1000), 1}
end

local current = redis.call("INCR", counter_key)
if current == 1 then
    redis.call("PEXPIRE", counter_key, window_ms)
end

if current > limit then
    redis.call("SET", block_key, "1", "EX", block_seconds)
    local retry_after = redis.call("PTTL", block_key)
    return {0, current, 0, math.ceil(retry_after / 1000), 1}
end

local ttl_ms = redis.call("PTTL", counter_key)
if ttl_ms < 0 then
    ttl_ms = window_ms
end

return {1, current, math.max(limit - current, 0), math.ceil(ttl_ms / 1000), 0}
"""


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    scope: str
    max_requests: int
    window_seconds: int
    block_seconds: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    rule_name: str
    scope: str
    limit: int
    current: int
    remaining: int
    retry_after: int
    blocked: bool
    backend: str
    identifier: Optional[str]


class _FallbackRecord:
    __slots__ = ("hits", "block_until")

    def __init__(self) -> None:
        self.hits: Deque[float] = deque()
        self.block_until = 0.0


class _FallbackRateLimiter:
    def __init__(self) -> None:
        self._records: Dict[str, _FallbackRecord] = {}
        self._lock = asyncio.Lock()

    async def evaluate(
        self,
        key: str,
        rule: RateLimitRule,
    ) -> RateLimitDecision:
        now = time.monotonic()
        async with self._lock:
            record = self._records.get(key)
            if record is None:
                record = _FallbackRecord()
                self._records[key] = record

            if record.block_until > now:
                retry_after = max(1, math.ceil(record.block_until - now))
                return RateLimitDecision(
                    allowed=False,
                    rule_name=rule.name,
                    scope=rule.scope,
                    limit=rule.max_requests,
                    current=len(record.hits),
                    remaining=0,
                    retry_after=retry_after,
                    blocked=True,
                    backend="memory",
                    identifier=None,
                )

            cutoff = now - rule.window_seconds
            while record.hits and record.hits[0] <= cutoff:
                record.hits.popleft()

            record.hits.append(now)
            current = len(record.hits)

            if current > rule.max_requests:
                record.block_until = now + rule.block_seconds
                return RateLimitDecision(
                    allowed=False,
                    rule_name=rule.name,
                    scope=rule.scope,
                    limit=rule.max_requests,
                    current=current,
                    remaining=0,
                    retry_after=max(1, rule.block_seconds),
                    blocked=True,
                    backend="memory",
                    identifier=None,
                )

            if current == 0:
                retry_after = rule.window_seconds
            else:
                retry_after = max(
                    1,
                    math.ceil((record.hits[0] + rule.window_seconds) - now),
                )

            return RateLimitDecision(
                allowed=True,
                rule_name=rule.name,
                scope=rule.scope,
                limit=rule.max_requests,
                current=current,
                remaining=max(rule.max_requests - current, 0),
                retry_after=retry_after,
                blocked=False,
                backend="memory",
                identifier=None,
            )


_fallback_rate_limiter = _FallbackRateLimiter()


def _build_storage_key(
    namespace: str,
    rule: RateLimitRule,
    identifier: str,
) -> str:
    safe_namespace = namespace.replace(" ", "_")
    return f"rate_limit:{safe_namespace}:{rule.scope}:{rule.name}:{identifier}"


def build_rate_limit_headers(decision: RateLimitDecision) -> Dict[str, str]:
    headers = {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(max(decision.remaining, 0)),
        "X-RateLimit-Policy": decision.rule_name,
        "X-RateLimit-Scope": decision.scope,
    }
    if decision.retry_after > 0:
        headers["Retry-After"] = str(decision.retry_after)
    return headers


async def evaluate_rate_limit(
    namespace: str,
    identifier: Optional[str],
    rule: RateLimitRule,
) -> RateLimitDecision:
    if not identifier:
        return RateLimitDecision(
            allowed=True,
            rule_name=rule.name,
            scope=rule.scope,
            limit=rule.max_requests,
            current=0,
            remaining=rule.max_requests,
            retry_after=rule.window_seconds,
            blocked=False,
            backend="skipped",
            identifier=None,
        )

    storage_key = _build_storage_key(namespace, rule, identifier)
    try:
        redis_client = await asyncio.wait_for(
            get_redis_client(),
            timeout=RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning(
            {
                "event": "rate_limit_redis_connect_timeout",
                "namespace": namespace,
                "rule": rule.name,
                "scope": rule.scope,
                "identifier": identifier,
                "timeout_seconds": RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
            }
        )
        redis_client = None

    if redis_client is not None:
        try:
            result = await asyncio.wait_for(
                cast(Any, redis_client).eval(
                    LUA_RATE_LIMIT,
                    2,
                    storage_key,
                    f"{storage_key}:blocked",
                    rule.max_requests,
                    rule.window_seconds * 1000,
                    rule.block_seconds,
                ),
                timeout=RATE_LIMIT_REDIS_TIMEOUT_SECONDS,
            )
            decision = RateLimitDecision(
                allowed=bool(int(result[0])),
                rule_name=rule.name,
                scope=rule.scope,
                limit=rule.max_requests,
                current=int(result[1]),
                remaining=max(int(result[2]), 0),
                retry_after=max(int(result[3]), 1),
                blocked=bool(int(result[4])),
                backend="redis",
                identifier=identifier,
            )
            if not decision.allowed:
                RATE_LIMIT_EXCEEDED.labels(
                    key=namespace,
                    user_id=(
                        identifier if rule.scope == "user" else "anonymous"
                    ),
                    ip=identifier if rule.scope == "ip" else "unknown",
                    task_type=rule.name,
                ).inc()
            return decision
        except Exception as exc:
            logger.error(
                {
                    "event": "rate_limit_redis_error",
                    "namespace": namespace,
                    "rule": rule.name,
                    "scope": rule.scope,
                    "identifier": identifier,
                    "error": str(exc),
                },
                exc_info=True,
            )

    decision = await _fallback_rate_limiter.evaluate(storage_key, rule)
    if not decision.allowed:
        RATE_LIMIT_EXCEEDED.labels(
            key=namespace,
            user_id=identifier if rule.scope == "user" else "anonymous",
            ip=identifier if rule.scope == "ip" else "unknown",
            task_type=rule.name,
        ).inc()
    return RateLimitDecision(
        allowed=decision.allowed,
        rule_name=decision.rule_name,
        scope=decision.scope,
        limit=decision.limit,
        current=decision.current,
        remaining=decision.remaining,
        retry_after=decision.retry_after,
        blocked=decision.blocked,
        backend=decision.backend,
        identifier=identifier,
    )


async def evaluate_rate_limits(
    namespace: str,
    identifiers: Dict[str, Optional[str]],
    rules: Sequence[RateLimitRule],
) -> list[RateLimitDecision]:
    decisions: list[RateLimitDecision] = []
    for rule in rules:
        decisions.append(
            await evaluate_rate_limit(
                namespace=namespace,
                identifier=identifiers.get(rule.scope),
                rule=rule,
            )
        )
    return decisions


async def rate_limit(
    key: str,
    max_calls: int,
    period_seconds: int,
    user_id: str | None = None,
    ip: str | None = None,
    task_type: str | None = None,
    raise_on_exceed: bool = True,
    fail_open: bool = True
) -> bool:
    rule = RateLimitRule(
        name=task_type or key,
        scope="user" if user_id else "ip",
        max_requests=max_calls,
        window_seconds=period_seconds,
        block_seconds=period_seconds,
    )
    identifier = user_id or ip

    try:
        decision = await evaluate_rate_limit(key, identifier, rule)
        if decision.allowed:
            return True
        if raise_on_exceed:
            raise HTTPException(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {key}",
                headers=build_rate_limit_headers(decision),
            )
        return False
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            {
                "event": "rate_limit_unexpected_error",
                "key": key,
                "user_id": user_id,
                "ip": ip,
                "task_type": task_type,
                "error": str(exc),
            },
            exc_info=True,
        )
        return fail_open


async def rate_limit_request(
    request: Request,
    key: str,
    max_calls: int,
    period_seconds: int,
    task_type: str,
):
    ip = request.client.host if request.client else None
    user_id = getattr(request.state, "user_id", None)
    return await rate_limit(
        key=key,
        max_calls=max_calls,
        period_seconds=period_seconds,
        user_id=user_id,
        ip=ip,
        task_type=task_type,
    )
