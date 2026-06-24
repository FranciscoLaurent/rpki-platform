"""审计日志相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuditLogExportRequest(BaseModel):
    """审计日志导出请求。

    支持按用户、租户、操作动作、资源类型、时间范围过滤，
    并指定导出格式与记录数上限。
    """

    format: str = Field(
        default="csv",
        description="导出格式：csv 或 json",
        pattern="^(csv|json)$",
    )
    user_id: int | None = Field(
        None, description="按用户 ID 过滤"
    )
    tenant_id: int | None = Field(
        None, description="按租户 ID 过滤"
    )
    action: str | None = Field(
        None, description="按操作动作过滤"
    )
    resource_type: str | None = Field(
        None, description="按资源类型过滤"
    )
    resource_id: str | None = Field(
        None, description="按资源 ID 过滤"
    )
    start_date: datetime | None = Field(
        None, description="起始时间"
    )
    end_date: datetime | None = Field(
        None, description="截止时间"
    )
    limit: int = Field(
        default=10000,
        ge=1,
        le=100000,
        description="导出记录数上限",
    )


class AuditLogExportResponse(BaseModel):
    """审计日志导出响应（元信息）。"""

    format: str = Field(..., description="导出格式")
    count: int = Field(..., description="导出记录数")
    exported_at: datetime = Field(
        ..., description="导出时间"
    )
    filename: str = Field(
        ..., description="建议的文件名"
    )

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    """审计日志响应。"""

    id: int
    user_id: int | None
    tenant_id: int | None
    action: str
    resource_type: str | None
    resource_id: str | None
    details: dict[str, Any] | None
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogListResponse(BaseModel):
    """审计日志列表响应（带分页信息）。"""

    items: list[AuditLogResponse]
    total: int
    skip: int
    limit: int


__all__ = [
    "AuditLogExportRequest",
    "AuditLogExportResponse",
    "AuditLogListResponse",
    "AuditLogResponse",
]
