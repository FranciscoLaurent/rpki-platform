"""密钥轮换服务。

提供 JWT 签名密钥与 API Key 签名密钥的统一轮换管理，记录轮换历史，
并支持过渡期内新旧密钥并行验证。

本模块聚焦于密钥轮换的协调与历史记录，具体的令牌签发与验证逻辑
仍由 :mod:`app.core.security` 与 :mod:`app.services.key_rotation_service`
提供。

轮换历史保存在内存中（生产环境应替换为 Redis 或数据库持久化），
包含密钥类型、版本号、轮换时间、操作者等元数据。
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.core.key_rotation")


# ──────────────────────────────────────────────
# 密钥轮换历史记录
# ──────────────────────────────────────────────


@dataclass
class KeyRotationRecord:
    """密钥轮换历史记录。

    Attributes:
        key_type: 密钥类型：``jwt`` / ``api_key`` / ``encryption``
        version: 版本号（递增）
        rotated_at: 轮换时间
        rotated_by: 操作者标识（用户 ID 或系统标识）
        previous_version: 上一版本号
        reason: 轮换原因（定期轮换/紧急轮换等）
    """

    key_type: str
    version: int
    rotated_at: datetime
    rotated_by: str | None = None
    previous_version: int | None = None
    reason: str = "scheduled"

    def to_dict(self) -> dict[str, Any]:
        """转换为可序列化字典（不含密钥本身）。"""
        return {
            "key_type": self.key_type,
            "version": self.version,
            "rotated_at": self.rotated_at.isoformat(),
            "rotated_by": self.rotated_by,
            "previous_version": self.previous_version,
            "reason": self.reason,
        }


@dataclass
class KeyRotationHistory:
    """密钥轮换历史管理（内存实现）。

    生产环境应替换为 Redis 或数据库持久化，以保证多实例间状态一致。
    """

    records: list[KeyRotationRecord] = field(default_factory=list)

    def add(self, record: KeyRotationRecord) -> None:
        """添加轮换记录。"""
        self.records.append(record)
        # 仅保留最近 100 条记录，避免内存无限增长
        if len(self.records) > 100:
            self.records = self.records[-100:]

    def list_records(
        self, key_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        """查询轮换历史记录。"""
        records = self.records
        if key_type is not None:
            records = [r for r in records if r.key_type == key_type]
        # 按时间倒序返回
        sorted_records = sorted(
            records, key=lambda r: r.rotated_at, reverse=True
        )
        return [r.to_dict() for r in sorted_records[:limit]]

    def latest_version(self, key_type: str) -> int | None:
        """获取指定类型密钥的最新版本号。"""
        type_records = [r for r in self.records if r.key_type == key_type]
        if not type_records:
            return None
        return max(r.version for r in type_records)


# 全局轮换历史（内存实现）
_history: KeyRotationHistory = KeyRotationHistory()


# ──────────────────────────────────────────────
# JWT 密钥轮换
# ──────────────────────────────────────────────


def rotate_jwt_key(
    rotated_by: str | None = None,
    reason: str = "scheduled",
) -> str:
    """轮换 JWT 签名密钥。

    生成新的随机密钥，并将当前密钥归档到旧密钥列表以支持过渡期验证。
    本函数仅生成新密钥并记录历史，调用方需将新密钥与旧密钥列表
    持久化到环境变量或配置中心。

    Args:
        rotated_by: 操作者标识（用户 ID 或系统标识）
        reason: 轮换原因

    Returns:
        新生成的 JWT 密钥字符串（64 个十六进制字符）
    """
    new_key = secrets.token_hex(32)
    now = datetime.now(timezone.utc)

    previous_version = _history.latest_version("jwt")
    new_version = (previous_version or 0) + 1

    _history.add(
        KeyRotationRecord(
            key_type="jwt",
            version=new_version,
            rotated_at=now,
            rotated_by=rotated_by,
            previous_version=previous_version,
            reason=reason,
        )
    )

    logger.info(
        "JWT 密钥已轮换",
        new_version=new_version,
        rotated_by=rotated_by,
        reason=reason,
        rotation_interval_days=settings.SECRET_KEY_ROTATION_INTERVAL_DAYS,
    )
    return new_key


def get_jwt_rotation_history(limit: int = 50) -> list[dict[str, Any]]:
    """查询 JWT 密钥轮换历史。"""
    return _history.list_records(key_type="jwt", limit=limit)


# ──────────────────────────────────────────────
# API Key 密钥轮换
# ──────────────────────────────────────────────


def rotate_api_key_secret(
    rotated_by: str | None = None,
    reason: str = "scheduled",
) -> str:
    """轮换 API Key 签名密钥。

    生成新的随机密钥用于 API Key 的签名与验证。本函数仅生成新密钥
    并记录历史，调用方需将新密钥持久化到配置中。

    Args:
        rotated_by: 操作者标识（用户 ID 或系统标识）
        reason: 轮换原因

    Returns:
        新生成的 API Key 签名密钥字符串（64 个十六进制字符）
    """
    new_key = secrets.token_hex(32)
    now = datetime.now(timezone.utc)

    previous_version = _history.latest_version("api_key")
    new_version = (previous_version or 0) + 1

    _history.add(
        KeyRotationRecord(
            key_type="api_key",
            version=new_version,
            rotated_at=now,
            rotated_by=rotated_by,
            previous_version=previous_version,
            reason=reason,
        )
    )

    logger.info(
        "API Key 密钥已轮换",
        new_version=new_version,
        rotated_by=rotated_by,
        reason=reason,
    )
    return new_key


def get_api_key_rotation_history(limit: int = 50) -> list[dict[str, Any]]:
    """查询 API Key 密钥轮换历史。"""
    return _history.list_records(key_type="api_key", limit=limit)


# ──────────────────────────────────────────────
# 通用查询接口
# ──────────────────────────────────────────────


def get_rotation_history(
    key_type: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    """查询密钥轮换历史。

    Args:
        key_type: 密钥类型过滤（``jwt`` / ``api_key`` / ``encryption``），
            为 None 时返回所有类型
        limit: 返回记录数上限

    Returns:
        轮换历史记录列表（按时间倒序）
    """
    return _history.list_records(key_type=key_type, limit=limit)


def is_rotation_due(key_type: str) -> bool:
    """检查指定类型密钥是否到达轮换周期。

    Args:
        key_type: 密钥类型

    Returns:
        是否需要轮换
    """
    if key_type == "jwt":
        interval_days = settings.SECRET_KEY_ROTATION_INTERVAL_DAYS
    else:
        interval_days = settings.KEY_ROTATION_INTERVAL_DAYS

    records = [r for r in _history.records if r.key_type == key_type]
    if not records:
        return False

    latest = max(records, key=lambda r: r.rotated_at)
    now = datetime.now(timezone.utc)
    return now - latest.rotated_at >= timedelta(days=interval_days)


__all__ = [
    "KeyRotationHistory",
    "KeyRotationRecord",
    "get_api_key_rotation_history",
    "get_jwt_rotation_history",
    "get_rotation_history",
    "is_rotation_due",
    "rotate_api_key_secret",
    "rotate_jwt_key",
]
