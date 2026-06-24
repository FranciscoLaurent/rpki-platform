"""JWT 密钥轮换服务。

提供 JWT 签名密钥的创建、轮换、版本管理与平滑切换能力。
在密钥轮换过渡期内，新旧密钥并行可用，确保已签发的令牌仍能通过验证，
新令牌使用新密钥签发。过渡期结束后旧密钥自动失效。

密钥版本信息保存在内存中（生产环境应替换为 Redis 或数据库持久化），
包含密钥值、创建时间、状态（active/previous/retired）等元数据。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.services.key_rotation_service")


# ──────────────────────────────────────────────
# 密钥版本数据结构
# ──────────────────────────────────────────────


@dataclass
class KeyVersion:
    """JWT 密钥版本信息。

    Attributes:
        key: 密钥字符串
        created_at: 创建时间
        status: 密钥状态：active / previous / retired
        version: 版本号（递增）
    """

    key: str
    created_at: datetime
    status: str  # active / previous / retired
    version: int

    @property
    def is_active(self) -> bool:
        """是否为当前活跃密钥。"""
        return self.status == "active"

    @property
    def is_previous(self) -> bool:
        """是否为过渡期旧密钥。"""
        return self.status == "previous"

    @property
    def is_retired(self) -> bool:
        """是否已退役（不再用于验证）。"""
        return self.status == "retired"

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典。"""
        return {
            "key": self.key,
            "created_at": self.created_at.isoformat(),
            "status": self.status,
            "version": self.version,
        }


@dataclass
class KeyRotationState:
    """密钥轮换状态管理（内存实现）。

    生产环境应替换为 Redis 或数据库持久化，以保证多实例间状态一致。
    """

    versions: list[KeyVersion] = field(default_factory=list)
    current_version: int = 0

    def get_active(self) -> KeyVersion | None:
        """获取当前活跃密钥版本。"""
        for v in self.versions:
            if v.is_active:
                return v
        return None

    def get_previous(self) -> list[KeyVersion]:
        """获取所有过渡期旧密钥。"""
        return [v for v in self.versions if v.is_previous]

    def get_usable_keys(self) -> list[str]:
        """获取所有可用于验证的密钥（active + previous）。"""
        keys: list[str] = []
        active = self.get_active()
        if active:
            keys.append(active.key)
        keys.extend(v.key for v in self.get_previous())
        return keys


# 全局密钥轮换状态（内存实现）
_state: KeyRotationState = KeyRotationState()


def _init_state_from_settings() -> None:
    """从配置初始化密钥轮换状态。

    将 ``settings.SECRET_KEY`` 作为初始活跃密钥，
    ``settings.PREVIOUS_SECRET_KEYS`` 作为过渡期旧密钥。
    """
    if _state.versions:
        return  # 已初始化

    now = datetime.now(timezone.utc)
    active = KeyVersion(
        key=settings.SECRET_KEY,
        created_at=now,
        status="active",
        version=1,
    )
    _state.versions.append(active)
    _state.current_version = 1

    for idx, old_key in enumerate(settings.PREVIOUS_SECRET_KEYS, start=2):
        _state.versions.append(
            KeyVersion(
                key=old_key,
                created_at=now - timedelta(seconds=idx),
                status="previous",
                version=idx,
            )
        )

    logger.info(
        "JWT 密钥轮换状态已初始化",
        active_version=active.version,
        previous_count=len(_state.get_previous()),
    )


def get_active_key() -> str:
    """获取当前活跃的 JWT 签名密钥。

    Returns:
        当前活跃密钥字符串
    """
    _init_state_from_settings()
    active = _state.get_active()
    if active is None:
        # 理论上不会发生，初始化时已设置
        return settings.SECRET_KEY
    return active.key


def get_verification_keys() -> list[str]:
    """获取所有可用于验证的密钥列表。

    在密钥轮换过渡期内，包含活跃密钥与所有过渡期旧密钥，
    以保证旧令牌仍能通过验证。

    Returns:
        可验证密钥列表（活跃密钥在前）
    """
    _init_state_from_settings()
    keys = _state.get_usable_keys()
    if not keys:
        return [settings.SECRET_KEY]
    return keys


def rotate_jwt_key() -> KeyVersion:
    """生成新 JWT 密钥并执行轮换。

    轮换流程：
    1. 生成新的随机密钥（64 个十六进制字符）
    2. 当前活跃密钥降级为过渡期旧密钥（previous）
    3. 旧的过渡期密钥标记为退役（retired），不再用于验证
    4. 新密钥成为活跃密钥

    Returns:
        新创建的活跃密钥版本

    Note:
        本函数仅更新内存中的密钥状态，调用方需将新密钥与旧密钥列表
        持久化到环境变量或配置中心，以保证重启后状态一致。
    """
    _init_state_from_settings()

    new_key = secrets.token_hex(32)
    now = datetime.now(timezone.utc)
    new_version = _state.current_version + 1

    # 当前活跃密钥降级为过渡期旧密钥
    for v in _state.versions:
        if v.is_active:
            v.status = "previous"
        elif v.is_previous:
            # 旧过渡期密钥退役
            v.status = "retired"

    new_key_version = KeyVersion(
        key=new_key,
        created_at=now,
        status="active",
        version=new_version,
    )
    _state.versions.append(new_key_version)
    _state.current_version = new_version

    logger.info(
        "JWT 密钥已轮换",
        new_version=new_version,
        rotation_interval_days=settings.SECRET_KEY_ROTATION_INTERVAL_DAYS,
        previous_keys_count=len(_state.get_previous()),
    )
    return new_key_version


def retire_previous_keys() -> int:
    """将所有过渡期旧密钥标记为退役。

    在密钥轮换过渡期结束后调用，使旧密钥不再用于验证。

    Returns:
        退役的密钥数量
    """
    _init_state_from_settings()
    retired_count = 0
    for v in _state.versions:
        if v.is_previous:
            v.status = "retired"
            retired_count += 1
    if retired_count > 0:
        logger.info("过渡期旧密钥已退役", retired_count=retired_count)
    return retired_count


def encode_token(
    payload: dict[str, Any], algorithm: str | None = None
) -> str:
    """使用当前活跃密钥签发 JWT 令牌。

    Args:
        payload: 令牌载荷
        algorithm: 签名算法，未指定时使用 ``settings.ALGORITHM``

    Returns:
        签发后的 JWT 字符串
    """
    alg = algorithm or settings.ALGORITHM
    return jwt.encode(payload, get_active_key(), algorithm=alg)


def decode_token(
    token: str, algorithm: str | None = None
) -> dict[str, Any] | None:
    """使用活跃密钥或过渡期旧密钥验证 JWT 令牌。

    依次尝试所有可用密钥（活跃密钥优先）进行验证，全部失败返回 None。

    Args:
        token: JWT 令牌字符串
        algorithm: 签名算法，未指定时使用 ``settings.ALGORITHM``

    Returns:
        解码后的载荷字典，验证失败返回 None
    """
    alg = algorithm or settings.ALGORITHM
    algorithms = [alg]
    for key in get_verification_keys():
        try:
            return jwt.decode(token, key, algorithms=algorithms)
        except JWTError:
            continue
    return None


def list_key_versions() -> list[dict[str, Any]]:
    """列出所有密钥版本信息（不含密钥本身）。

    用于审计与运维查看密钥轮换状态。

    Returns:
        密钥版本信息列表（脱敏，仅返回版本号、状态、创建时间）
    """
    _init_state_from_settings()
    return [
        {
            "version": v.version,
            "status": v.status,
            "created_at": v.created_at.isoformat(),
        }
        for v in _state.versions
    ]


__all__ = [
    "KeyRotationState",
    "KeyVersion",
    "decode_token",
    "encode_token",
    "get_active_key",
    "get_verification_keys",
    "list_key_versions",
    "retire_previous_keys",
    "rotate_jwt_key",
]
