"""Redis 异步客户端与缓存服务。

提供全局 Redis 客户端管理、FastAPI 依赖注入以及缓存工具类。
支持多租户键命名空间隔离。
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import HTTPException, status
from structlog.stdlib import BoundLogger

from app.core.config import settings
from app.core.logging import get_logger

logger: BoundLogger = get_logger("app.redis")

# 全局 Redis 客户端单例
_redis_client: aioredis.Redis | None = None

# 租户键命名空间前缀模板
_TENANT_KEY_PREFIX = "tenant:{tenant_id}:{key}"


def get_tenant_cache_key(tenant_id: int | None, key: str) -> str:
    """构造租户感知的缓存键。

    当 ``tenant_id`` 为 None 时，返回不带租户前缀的原始键，
    适用于全局数据或未启用多租户的场景。

    Args:
        tenant_id: 租户 ID，可为 None
        key: 原始缓存键

    Returns:
        带租户命名空间前缀的缓存键，如 ``tenant:42:user:settings``；
        若 tenant_id 为 None 则返回原始键。
    """
    if tenant_id is None:
        return key
    return _TENANT_KEY_PREFIX.format(tenant_id=tenant_id, key=key)


async def init_redis() -> None:
    """初始化全局 Redis 连接。

    在应用启动时调用，连接失败会记录日志并抛出异常。
    """
    global _redis_client
    try:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            max_connections=20,
        )
        # 测试连接是否正常
        await _redis_client.ping()
        logger.info("Redis 连接成功", url=settings.REDIS_URL)
    except Exception as e:
        logger.error("Redis 连接失败", url=settings.REDIS_URL, error=str(e))
        _redis_client = None
        raise


async def close_redis() -> None:
    """关闭全局 Redis 连接。

    在应用关闭时调用，释放连接池资源。
    """
    global _redis_client
    if _redis_client is not None:
        await _redis_client.aclose()
        _redis_client = None
        logger.info("Redis 连接已关闭")


def get_redis_client() -> aioredis.Redis:
    """获取全局 Redis 客户端实例。

    Returns:
        Redis 异步客户端

    Raises:
        RuntimeError: Redis 客户端未初始化
    """
    if _redis_client is None:
        raise RuntimeError("Redis 客户端未初始化，请先调用 init_redis()")
    return _redis_client


async def get_redis() -> aioredis.Redis:
    """FastAPI 依赖注入：获取 Redis 客户端。

    用法::

        @router.get("/cache/{key}")
        async def get_cache_value(redis: Redis = Depends(get_redis)):
            ...
    """
    try:
        return get_redis_client()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis 服务不可用: {e}",
        ) from e


class CacheService:
    """缓存工具类，封装常用的 Redis 操作。

    自动处理 JSON 序列化与反序列化，简化缓存读写。
    支持租户感知的键命名空间隔离：当 ``tenant_id`` 提供时，
    所有键自动添加 ``tenant:{tenant_id}:`` 前缀。
    """

    def __init__(
        self,
        client: aioredis.Redis,
        tenant_id: int | None = None,
    ) -> None:
        """初始化缓存服务。

        Args:
            client: Redis 异步客户端
            tenant_id: 租户 ID，提供后所有键将自动添加租户前缀。
                为 None 时表示全局缓存（不隔离）。
        """
        self._client = client
        self._tenant_id = tenant_id

    def _make_key(self, key: str) -> str:
        """构造实际的 Redis 键，按需添加租户前缀。"""
        return get_tenant_cache_key(self._tenant_id, key)

    async def get(self, key: str) -> Any | None:
        """获取缓存值，自动 JSON 反序列化。

        Args:
            key: 缓存键（不含租户前缀，由服务自动添加）

        Returns:
            缓存值（已反序列化），键不存在时返回 None
        """
        value = await self._client.get(self._make_key(key))
        if value is None:
            return None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            # 非 JSON 数据直接返回原始值
            return value

    async def set(
        self,
        key: str,
        value: Any,
        expire: int | None = None,
    ) -> bool:
        """设置缓存值，自动 JSON 序列化。

        Args:
            key: 缓存键（不含租户前缀，由服务自动添加）
            value: 缓存值（任意可序列化对象）
            expire: 过期时间（秒），不设置则永久有效

        Returns:
            是否设置成功
        """
        serialized = json.dumps(value, ensure_ascii=False, default=str)
        result = await self._client.set(self._make_key(key), serialized, ex=expire)
        return bool(result)

    async def delete(self, key: str) -> int:
        """删除缓存键。

        Args:
            key: 缓存键（不含租户前缀，由服务自动添加）

        Returns:
            删除的键数量
        """
        return await self._client.delete(self._make_key(key))

    async def exists(self, key: str) -> bool:
        """判断键是否存在。

        Args:
            key: 缓存键（不含租户前缀，由服务自动添加）

        Returns:
            键存在返回 True
        """
        return bool(await self._client.exists(self._make_key(key)))

    async def expire(self, key: str, seconds: int) -> bool:
        """设置键的过期时间。

        Args:
            key: 缓存键（不含租户前缀，由服务自动添加）
            seconds: 过期时间（秒）

        Returns:
            设置成功返回 True（键不存在时返回 False）
        """
        return bool(await self._client.expire(self._make_key(key), seconds))
