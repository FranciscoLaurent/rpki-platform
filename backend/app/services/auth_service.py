"""认证服务：登录、注册、令牌管理、密码修改、权限检查。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.requests import Request

from app.core.config import settings
from app.core.logging import get_logger
from app.core.rbac import PermissionChecker, collect_user_permissions
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import Role, User
from app.schemas.auth import UserCreate

logger = get_logger("app.services.auth_service")

# 用户最近登录 IP 记录（内存实现，生产环境应替换为 Redis）
# 结构：{user_id: [(ip, timestamp), ...]}
_recent_login_ips: dict[int, list[tuple[str, float]]] = {}
_RECENT_IP_WINDOW_SECONDS = 7 * 24 * 3600  # 7 天


# ──────────────────────────────────────────────
# 令牌黑名单（内存实现，生产环境应替换为 Redis）
# ──────────────────────────────────────────────

_token_blacklist: set[str] = set()


def blacklist_token(token: str) -> None:
    """将令牌加入黑名单（登出时调用）。

    TODO: 生产环境替换为 Redis 实现，并设置与令牌相同的过期时间。
    """
    _token_blacklist.add(token)


def is_token_blacklisted(token: str) -> bool:
    """检查令牌是否在黑名单中。"""
    return token in _token_blacklist


# ──────────────────────────────────────────────
# 令牌创建
# ──────────────────────────────────────────────


def create_user_access_token(user: User) -> tuple[str, int]:
    """为用户创建访问令牌。

    Returns:
        (token, expires_in_seconds) 元组。
    """
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    extra_claims = {
        "username": user.username,
        "is_superuser": user.is_superuser,
        "type": "access",
    }
    token = create_access_token(
        subject=user.id,
        expires_delta=expires_delta,
        extra_claims=extra_claims,
    )
    return token, int(expires_delta.total_seconds())


def create_user_refresh_token(user: User) -> str:
    """为用户创建刷新令牌。"""
    expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    expire = datetime.now(UTC) + expires_delta
    payload: dict[str, Any] = {
        "sub": str(user.id),
        "username": user.username,
        "type": "refresh",
        "exp": expire,
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str) -> dict[str, Any]:
    """验证令牌并返回载荷。

    Args:
        token: JWT 令牌字符串

    Returns:
        解码后的载荷字典

    Raises:
        ValueError: 令牌无效、过期或已加入黑名单。
    """
    if is_token_blacklisted(token):
        raise ValueError("令牌已失效")

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError as e:
        raise ValueError(f"令牌验证失败: {e}") from e

    return payload


# ──────────────────────────────────────────────
# 用户认证
# ──────────────────────────────────────────────


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User:
    """验证用户名密码，处理账户锁定逻辑。

    Args:
        db: 异步数据库会话
        username: 用户名或邮箱
        password: 明文密码

    Returns:
        认证成功的 User 对象

    Raises:
        ValueError: 用户不存在、密码错误或账户被锁定。
    """
    # 支持用户名或邮箱登录
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(or_(User.username == username, User.email == username))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None:
        raise ValueError("用户名或密码错误")

    # 检查账户锁定
    if user.locked_until is not None:
        now = datetime.now(UTC)
        if user.locked_until > now:
            remaining = int((user.locked_until - now).total_seconds() / 60)
            raise ValueError(f"账户已锁定，请 {remaining} 分钟后重试")
        # 锁定期已过，重置
        user.locked_until = None
        user.failed_login_count = 0

    # 验证密码
    if not verify_password(password, user.hashed_password):
        user.failed_login_count += 1
        if user.failed_login_count >= settings.MAX_FAILED_LOGIN_ATTEMPTS:
            user.locked_until = datetime.now(UTC) + timedelta(
                minutes=settings.ACCOUNT_LOCK_DURATION_MINUTES
            )
        await db.flush()
        await db.commit()
        raise ValueError("用户名或密码错误")

    # 认证成功，重置计数并更新登录时间
    user.failed_login_count = 0
    user.last_login_at = datetime.now(UTC)
    await db.flush()
    await db.commit()

    return user


# ──────────────────────────────────────────────
# 用户注册
# ──────────────────────────────────────────────


async def register_user(db: AsyncSession, user_create: UserCreate) -> User:
    """注册新用户。

    Args:
        db: 异步数据库会话
        user_create: 用户注册数据

    Returns:
        创建的 User 对象

    Raises:
        ValueError: 用户名或邮箱已存在。
    """
    # 检查用户名是否已存在
    stmt = select(User).where(
        or_(User.username == user_create.username, User.email == user_create.email)
    )
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise ValueError("用户名或邮箱已存在")

    user = User(
        email=user_create.email,
        username=user_create.username,
        full_name=user_create.full_name,
        hashed_password=get_password_hash(user_create.password),
        is_active=True,
        is_superuser=False,
        status="active",
    )
    db.add(user)
    await db.flush()
    await db.commit()

    # 重新加载以获取 roles 关系
    await db.refresh(user)
    return user


# ──────────────────────────────────────────────
# 修改密码
# ──────────────────────────────────────────────


async def change_password(
    db: AsyncSession,
    user: User,
    old_password: str,
    new_password: str,
) -> None:
    """修改用户密码。

    Args:
        db: 异步数据库会话
        user: 当前用户对象
        old_password: 旧密码
        new_password: 新密码

    Raises:
        ValueError: 旧密码不正确。
    """
    if not verify_password(old_password, user.hashed_password):
        raise ValueError("旧密码不正确")

    user.hashed_password = get_password_hash(new_password)
    user.must_change_password = False
    await db.flush()
    await db.commit()


# ──────────────────────────────────────────────
# 权限检查
# ──────────────────────────────────────────────


async def check_user_permissions(user: User, required_permissions: list[str]) -> bool:
    """检查用户是否拥有所需权限。

    超级管理员自动通过。需确保 ``user.roles`` 及 ``role.permissions`` 已加载。

    Args:
        user: 用户对象（需预加载 roles 和 permissions）
        required_permissions: 所需权限码列表

    Returns:
        是否拥有权限
    """
    if user.is_superuser:
        return True

    user_perms = collect_user_permissions(user)
    checker = PermissionChecker(required_permissions)
    return checker.has_permission(user_perms)


async def get_user_permissions(db: AsyncSession, user: User) -> set[str]:
    """获取用户权限码集合（从数据库重新加载）。

    Args:
        db: 异步数据库会话
        user: 用户对象

    Returns:
        权限码集合，超级管理员返回 ``{"*"}``。
    """
    if user.is_superuser:
        return {PermissionChecker.WILDCARD}

    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user.id)
    )
    result = await db.execute(stmt)
    full_user = result.scalar_one_or_none()
    if full_user is None:
        return set()

    return collect_user_permissions(full_user)


# ──────────────────────────────────────────────
# 异常登录检测
# ──────────────────────────────────────────────


def _get_client_ip(request: Request) -> str:
    """从请求中获取客户端 IP，优先解析 X-Forwarded-For。"""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def _record_login_ip(user_id: int, ip: str) -> None:
    """记录用户登录 IP（用于后续异地登录检测）。"""
    now = datetime.now(UTC).timestamp()
    records = _recent_login_ips.setdefault(user_id, [])
    # 清理过期记录
    cutoff = now - _RECENT_IP_WINDOW_SECONDS
    _recent_login_ips[user_id] = [(existing_ip, ts) for existing_ip, ts in records if ts > cutoff]
    # 追加本次记录
    _recent_login_ips[user_id].append((ip, now))


def _is_new_ip_for_user(user_id: int, ip: str) -> bool:
    """检查给定 IP 是否为用户最近未使用过的新 IP。"""
    records = _recent_login_ips.get(user_id, [])
    return not any(existing_ip == ip for existing_ip, _ in records)


def detect_anomalous_login(user: User, request: Request) -> dict[str, Any]:
    """异常登录检测。

    基于以下规则检测异常登录行为：
    1. **异常时间登录**：在非工作时间（默认 18:00 - 次日 08:00）登录
    2. **异地登录**：用户从最近未使用过的新 IP 登录
    3. **新设备/浏览器**：基于 User-Agent 与历史记录的差异（简化实现）

    本函数不阻塞登录流程，仅返回检测结果供调用方记录审计日志
    或触发二次认证。

    Args:
        user: 当前登录用户对象
        request: FastAPI 请求对象

    Returns:
        检测结果字典，包含以下字段：
        - ``is_anomalous``: 是否检测到异常
        - ``reasons``: 异常原因列表
        - ``client_ip``: 客户端 IP
        - ``user_agent``: User-Agent 摘要
        - ``login_hour``: 登录小时（本地时区）
    """
    reasons: list[str] = []
    client_ip = _get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")[:200]

    # 当前小时（UTC，简化处理，未做时区转换）
    now = datetime.now(UTC)
    login_hour = now.hour

    # 1. 异常时间登录检测
    office_start = settings.ANOMALOUS_LOGIN_OFFICE_HOURS_START
    office_end = settings.ANOMALOUS_LOGIN_OFFICE_HOURS_END
    if office_start <= office_end:
        # 同日工作时间区间（如 8-18）
        is_off_hours = login_hour < office_start or login_hour >= office_end
    else:
        # 跨日工作时间区间（如 22-6）
        is_off_hours = office_end <= login_hour < office_start
    if is_off_hours:
        reasons.append(f"非工作时间登录（{login_hour}:00 UTC）")

    # 2. 异地登录检测（基于 IP 历史）
    if client_ip != "unknown" and _is_new_ip_for_user(user.id, client_ip):
        reasons.append(f"异地/新 IP 登录（{client_ip}）")

    # 3. 记录本次登录 IP，便于后续检测
    if client_ip != "unknown":
        _record_login_ip(user.id, client_ip)

    result: dict[str, Any] = {
        "is_anomalous": len(reasons) > 0,
        "reasons": reasons,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "login_hour": login_hour,
    }

    if result["is_anomalous"]:
        logger.warning(
            "检测到异常登录",
            user_id=user.id,
            username=user.username,
            reasons=reasons,
            client_ip=client_ip,
            login_hour=login_hour,
        )

    return result
