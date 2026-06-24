"""API 依赖注入：认证、数据库会话、权限检查、基础设施客户端等。

提供多租户隔离所需的工具函数与依赖项。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clickhouse import ClickHouseService, get_clickhouse_client
from app.core.config import settings
from app.core.database import get_db
from app.core.kafka import KafkaService, get_kafka_producer
from app.core.rbac import PermissionChecker, collect_user_permissions
from app.core.redis import get_redis
from app.core.security import decode_access_token
from app.models.api_key import ApiKey
from app.models.tenant import TenantMember
from app.models.user import Role, User
from app.services.api_key_service import verify_api_key
from app.services.auth_service import is_token_blacklisted

# OAuth2 密码流令牌获取端点
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    auto_error=False,
)


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """从 JWT 令牌解析当前登录用户。

    预加载用户的角色与权限信息，供后续权限检查使用。

    Raises:
        HTTPException 401: 令牌缺失、无效或已失效，或用户不存在。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token is None:
        raise credentials_exception

    # 检查令牌黑名单
    if is_token_blacklisted(token):
        raise credentials_exception

    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception

    token_type = payload.get("type", "access")
    if token_type != "access":
        raise credentials_exception

    user_id_str: str | None = payload.get("sub")
    if user_id_str is None:
        raise credentials_exception

    try:
        user_id = int(user_id_str)
    except (ValueError, TypeError):
        raise credentials_exception

    # 查询用户并预加载角色与权限
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """确保当前用户处于活跃状态。

    Raises:
        HTTPException 403: 用户已被禁用。
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )
    return current_user


async def get_current_superuser(
    current_user: User = Depends(get_current_active_user),
) -> User:
    """确保当前用户为超级管理员。

    Raises:
        HTTPException 403: 非超级管理员。
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限",
        )
    return current_user


async def get_current_user_optional(
    token: str | None = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User | None:
    """可选认证：未提供令牌或令牌无效时返回 None，不抛异常。

    适用于开放注册等场景。
    """
    if token is None:
        return None
    try:
        return await get_current_user(token=token, db=db)
    except HTTPException:
        return None


def require_permissions(*permissions: str):  # type: ignore[no-untyped-def]
    """权限检查依赖工厂。

    用法::

        @router.get("/users", dependencies=[Depends(require_permissions("user:read"))])
        async def list_users(...):
            ...

    或直接作为依赖参数::

        @router.get("/users")
        async def list_users(
            current_user: User = Depends(require_permissions("user:read")),
        ):
            ...

    Args:
        permissions: 所需权限码列表，满足其一即可。

    Raises:
        HTTPException 403: 权限不足。
    """

    async def permission_dependency(
        current_user: User = Depends(get_current_active_user),
    ) -> User:
        user_perms = collect_user_permissions(current_user)
        checker = PermissionChecker(list(permissions))
        if not checker.has_permission(user_perms):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"权限不足，需要以下权限之一: {', '.join(permissions)}",
            )
        return current_user

    return permission_dependency


def require_permission(permission_code: str):  # type: ignore[no-untyped-def]
    """单个权限检查依赖工厂（``require_permissions`` 的便捷封装）。

    用法::

        @router.get("/users")
        async def list_users(
            current_user: User = Depends(require_permission("user:read")),
        ):
            ...

    Args:
        permission_code: 所需权限码。

    Raises:
        HTTPException 403: 权限不足。
    """
    return require_permissions(permission_code)


# ──────────────────────────────────────────────
# API Key 认证
# ──────────────────────────────────────────────


async def require_api_key(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    """从 ``X-API-Key`` 请求头验证 API Key。

    验证成功后将 ApiKey 对象挂载到 ``request.state`` 供后续使用，
    并返回 ApiKey 对象。

    Raises:
        HTTPException 401: 未提供 API Key 或 API Key 无效/已过期。
    """
    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供 API Key，请在 X-API-Key 请求头中携带",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    api_key = await verify_api_key(db, x_api_key)
    if api_key is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API Key 无效或已过期",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # 挂载到 request.state 供审计等中间件使用
    request.state.api_key = api_key
    return api_key


# ──────────────────────────────────────────────
# 统一认证入口
# ──────────────────────────────────────────────


async def get_current_principal(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    db: AsyncSession = Depends(get_db),
) -> User | ApiKey:
    """统一认证入口：优先 JWT，其次 API Key。

    用于同时支持 JWT 与 API Key 两种认证方式的接口。
    认证成功后将主体对象挂载到 ``request.state.principal``。

    Raises:
        HTTPException 401: 未提供任何凭据或凭据无效。
    """
    # 优先尝试 JWT
    if token is not None:
        try:
            user = await get_current_user(token=token, db=db)
            request.state.principal = user
            request.state.principal_type = "user"
            return user
        except HTTPException:
            pass  # JWT 无效，继续尝试 API Key

    # 其次尝试 API Key
    if x_api_key is not None:
        api_key = await verify_api_key(db, x_api_key)
        if api_key is not None:
            request.state.principal = api_key
            request.state.principal_type = "api_key"
            request.state.api_key = api_key
            return api_key

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="未提供有效凭据，请使用 Bearer Token 或 X-API-Key",
        headers={"WWW-Authenticate": "Bearer, ApiKey"},
    )


# ──────────────────────────────────────────────
# 限流
# ──────────────────────────────────────────────

# 内存限流计数器（Redis 不可用时的降级方案）
# 结构：{key: [(timestamp, count), ...]}
_memory_rate_limit: dict[str, list[float]] = {}

# 默认限流配置：每分钟 60 次
DEFAULT_RATE_LIMIT = 60
DEFAULT_RATE_WINDOW = 60  # 秒


async def rate_limit(
    request: Request,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    limit: int = DEFAULT_RATE_LIMIT,
    window: int = DEFAULT_RATE_WINDOW,
) -> None:
    """基于客户端 IP + API Key 的简单限流依赖。

    优先使用 Redis 滑动窗口限流；Redis 不可用时降级为内存限流。

    Args:
        request: FastAPI 请求对象
        x_api_key: X-API-Key 请求头
        limit: 时间窗口内允许的请求数
        window: 时间窗口（秒）

    Raises:
        HTTPException 429: 超过限流阈值。
    """
    # 构建限流键：客户端 IP + API Key 前缀（如有）
    client_ip = "unknown"
    if request.client:
        client_ip = request.client.host
    # 支持 X-Forwarded-For
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    key_suffix = ""
    if x_api_key:
        # 仅取前缀部分作为标识，避免泄露完整密钥
        key_suffix = f":{x_api_key.split('.', 1)[0]}"
    rate_key = f"rl:{client_ip}{key_suffix}"

    now = datetime.now(timezone.utc).timestamp()

    # 尝试使用 Redis
    try:
        redis = get_redis()
        # 使用 Redis 有序集合实现滑动窗口限流
        import json

        # 移除窗口外的记录
        await redis.zremrangebyscore(rate_key, 0, now - window)
        # 获取当前窗口内的请求数
        current = await redis.zcard(rate_key)
        if current >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"请求过于频繁，每 {window} 秒限 {limit} 次",
                headers={"Retry-After": str(window)},
            )
        # 记录本次请求
        await redis.zadd(rate_key, {str(now): now})
        await redis.expire(rate_key, window)
        return
    except HTTPException:
        raise
    except Exception:
        # Redis 不可用，降级为内存限流
        pass

    # 内存限流（滑动窗口）
    window_start = now - window
    if rate_key not in _memory_rate_limit:
        _memory_rate_limit[rate_key] = []
    # 清理窗口外的记录
    _memory_rate_limit[rate_key] = [
        ts for ts in _memory_rate_limit[rate_key] if ts > window_start
    ]
    if len(_memory_rate_limit[rate_key]) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"请求过于频繁，每 {window} 秒限 {limit} 次",
            headers={"Retry-After": str(window)},
        )
    _memory_rate_limit[rate_key].append(now)


def get_kafka() -> KafkaService:
    """FastAPI 依赖注入：获取 Kafka 生产者服务。

    Raises:
        HTTPException: Kafka 生产者未初始化时返回 503
    """
    try:
        producer = get_kafka_producer()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Kafka 服务不可用: {e}",
        ) from e
    return KafkaService(producer)


def get_clickhouse() -> ClickHouseService:
    """FastAPI 依赖注入：获取 ClickHouse 查询服务。

    Raises:
        HTTPException: ClickHouse 客户端未初始化时返回 503
    """
    try:
        client = get_clickhouse_client()
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ClickHouse 服务不可用: {e}",
        ) from e
    return ClickHouseService(client)


# ──────────────────────────────────────────────
# 多租户隔离
# ──────────────────────────────────────────────


def get_user_tenant_id(user: User) -> int | None:
    """安全获取用户的租户 ID。

    User 模型可能未直接持有 ``tenant_id`` 字段（例如超级管理员或
    历史数据），此处使用 ``getattr`` 安全访问，缺失时返回 None。

    Args:
        user: 当前登录用户

    Returns:
        用户所属租户 ID，无租户时返回 None
    """
    return getattr(user, "tenant_id", None)


async def get_tenant_filter(
    current_user: User = Depends(get_current_active_user),
) -> int | None:
    """获取当前用户的租户过滤条件。

    用于业务查询时按租户隔离数据。超级管理员返回 None（可查看全部租户数据），
    普通用户返回其所属租户 ID。

    用法::

        @router.get("/items")
        async def list_items(
            tenant_id: int | None = Depends(get_tenant_filter),
            db: AsyncSession = Depends(get_db),
        ):
            stmt = select(Item)
            if tenant_id is not None:
                stmt = stmt.where(Item.tenant_id == tenant_id)
            ...

    Returns:
        当前用户的租户 ID，超级管理员返回 None
    """
    if current_user.is_superuser:
        return None
    return get_user_tenant_id(current_user)


async def require_tenant_access(
    tenant_id: int,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """验证当前用户有权访问指定租户。

    通过检查用户是否为该租户的成员（或在 ``tenant_members`` 表中存在记录）
    来判断访问权限。超级管理员可访问任意租户。

    用法::

        @router.get("/tenants/{tenant_id}/members")
        async def list_members(
            tenant_id: int,
            _: None = Depends(require_tenant_access),
            db: AsyncSession = Depends(get_db),
        ):
            ...

    Args:
        tenant_id: 待访问的租户 ID（从路径参数获取）
        current_user: 当前登录用户
        db: 异步数据库会话

    Raises:
        HTTPException 403: 用户无权访问该租户
    """
    # 超级管理员可访问任意租户
    if current_user.is_superuser:
        return

    # 用户所属租户与请求租户一致时直接通过
    user_tenant_id = get_user_tenant_id(current_user)
    if user_tenant_id is not None and user_tenant_id == tenant_id:
        return

    # 检查用户是否为该租户的成员
    stmt = select(TenantMember).where(
        TenantMember.user_id == current_user.id,
        TenantMember.tenant_id == tenant_id,
    )
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"用户无权访问租户 ID {tenant_id}",
        )


__all__ = [
    "DEFAULT_RATE_LIMIT",
    "DEFAULT_RATE_WINDOW",
    "get_clickhouse",
    "get_current_active_user",
    "get_current_principal",
    "get_current_superuser",
    "get_current_user",
    "get_current_user_optional",
    "get_db",
    "get_kafka",
    "get_redis",
    "get_tenant_filter",
    "get_user_tenant_id",
    "rate_limit",
    "require_api_key",
    "require_permission",
    "require_permissions",
    "require_tenant_access",
]
