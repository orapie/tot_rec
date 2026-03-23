import json
import time
from abc import ABC, abstractmethod
from typing import Any

import redis.asyncio as redis

from app.config import get_settings


DEFAULT_INSTRUCTION = "自然承接用户话题，用简短问句澄清偏好。"


class StrategyStore(ABC):
    @abstractmethod
    async def get(self, session_id: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def set_instruction(self, session_id: str, instruction: str) -> dict[str, Any]:
        pass


class MemoryStrategyStore(StrategyStore):
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, session_id: str) -> dict[str, Any]:
        row = self._data.get(session_id)
        if not row:
            return {
                "instruction": DEFAULT_INSTRUCTION,
                "version": 0,
                "updated_at": None,
            }
        return dict(row)

    async def set_instruction(self, session_id: str, instruction: str) -> dict[str, Any]:
        prev = self._data.get(session_id, {})
        ver = int(prev.get("version", 0)) + 1
        row = {
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
            "version": ver,
            "updated_at": time.time(),
        }
        self._data[session_id] = row
        return row


class RedisStrategyStore(StrategyStore):
    def __init__(self, client: redis.Redis) -> None:
        self._r = client
        self._ttl_seconds = 86400 * 7

    def _key(self, session_id: str) -> str:
        return f"strategy:{session_id}"

    async def get(self, session_id: str) -> dict[str, Any]:
        raw = await self._r.get(self._key(session_id))
        if not raw:
            return {
                "instruction": DEFAULT_INSTRUCTION,
                "version": 0,
                "updated_at": None,
            }
        data = json.loads(raw)
        return {
            "instruction": data.get("instruction", DEFAULT_INSTRUCTION),
            "version": int(data.get("version", 0)),
            "updated_at": data.get("updated_at"),
        }

    async def set_instruction(self, session_id: str, instruction: str) -> dict[str, Any]:
        prev_raw = await self._r.get(self._key(session_id))
        prev_ver = 0
        if prev_raw:
            prev_ver = int(json.loads(prev_raw).get("version", 0))
        ver = prev_ver + 1
        row = {
            "instruction": instruction.strip() or DEFAULT_INSTRUCTION,
            "version": ver,
            "updated_at": time.time(),
        }
        await self._r.set(
            self._key(session_id),
            json.dumps(row, ensure_ascii=False),
            ex=self._ttl_seconds,
        )
        return row


_memory_singleton: MemoryStrategyStore | None = None
_redis_singleton: RedisStrategyStore | None = None
_redis_client: redis.Redis | None = None


async def get_strategy_store() -> StrategyStore:
    global _memory_singleton, _redis_singleton, _redis_client
    settings = get_settings()
    if settings.redis_url:
        if _redis_singleton is None:
            _redis_client = redis.from_url(settings.redis_url, decode_responses=True)
            _redis_singleton = RedisStrategyStore(_redis_client)
        return _redis_singleton
    if _memory_singleton is None:
        _memory_singleton = MemoryStrategyStore()
    return _memory_singleton
