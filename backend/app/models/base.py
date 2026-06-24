"""SQLAlchemy 声明性基类与通用混入。

提供所有模型共享的基类（带 to_dict 方法）以及时间戳、多租户混入。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """SQLAlchemy 声明式基类，所有模型继承此类。

    提供 to_dict 方法用于将模型实例序列化为字典。
    """

    def to_dict(self) -> dict[str, Any]:
        """将模型实例转换为字典。

        datetime 类型字段自动转为 ISO 8601 字符串。

        Returns:
            包含所有列名与对应值的字典
        """
        result: dict[str, Any] = {}
        for column in self.__table__.columns:
            value = getattr(self, column.name)
            if isinstance(value, datetime):
                value = value.isoformat()
            result[column.name] = value
        return result


class TimestampMixin:
    """时间戳混入，提供 created_at 和 updated_at 字段。

    created_at 在记录插入时自动设置，updated_at 在记录更新时自动刷新。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="创建时间",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="更新时间",
    )


class TenantMixin:
    """多租户混入，提供 tenant_id 字段用于数据隔离。

    所有业务模型应混入此类以支持多租户场景。
    """

    tenant_id: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="租户 ID，用于多租户数据隔离，为空表示全局数据",
    )
