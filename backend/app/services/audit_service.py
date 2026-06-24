"""审计日志服务：记录与查询操作日志。"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def log_action(
    db: AsyncSession,
    user_id: int | None,
    tenant_id: int | None,
    action: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """记录审计日志。

    Args:
        db: 异步数据库会话
        user_id: 操作用户 ID
        tenant_id: 租户 ID
        action: 操作动作
        resource_type: 资源类型
        resource_id: 资源 ID
        details: 操作详情
        ip: 客户端 IP 地址
        user_agent: 客户端 User-Agent
        request_id: 请求追踪 ID

    Returns:
        创建的 AuditLog 对象
    """
    log_entry = AuditLog(
        user_id=user_id,
        tenant_id=tenant_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=ip,
        user_agent=user_agent,
        request_id=request_id,
    )
    db.add(log_entry)
    await db.flush()
    await db.commit()
    return log_entry


async def get_audit_logs(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[AuditLog]:
    """查询审计日志。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``user_id``、``tenant_id``、``action``、
            ``resource_type``、``start_date``、``end_date``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        审计日志列表
    """
    stmt = select(AuditLog)

    if filters:
        if filters.get("user_id") is not None:
            stmt = stmt.where(AuditLog.user_id == filters["user_id"])
        if filters.get("tenant_id") is not None:
            stmt = stmt.where(AuditLog.tenant_id == filters["tenant_id"])
        if filters.get("action"):
            stmt = stmt.where(AuditLog.action == filters["action"])
        if filters.get("resource_type"):
            stmt = stmt.where(AuditLog.resource_type == filters["resource_type"])
        if filters.get("start_date"):
            stmt = stmt.where(AuditLog.created_at >= filters["start_date"])
        if filters.get("end_date"):
            stmt = stmt.where(AuditLog.created_at <= filters["end_date"])

    stmt = stmt.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_audit_logs(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计审计日志数量。"""
    from sqlalchemy import func

    stmt = select(func.count(AuditLog.id))

    if filters:
        if filters.get("user_id") is not None:
            stmt = stmt.where(AuditLog.user_id == filters["user_id"])
        if filters.get("tenant_id") is not None:
            stmt = stmt.where(AuditLog.tenant_id == filters["tenant_id"])
        if filters.get("action"):
            stmt = stmt.where(AuditLog.action == filters["action"])
        if filters.get("resource_type"):
            stmt = stmt.where(AuditLog.resource_type == filters["resource_type"])
        if filters.get("start_date"):
            stmt = stmt.where(AuditLog.created_at >= filters["start_date"])
        if filters.get("end_date"):
            stmt = stmt.where(AuditLog.created_at <= filters["end_date"])

    result = await db.execute(stmt)
    return result.scalar_one()


# ──────────────────────────────────────────────
# 审计日志导出
# ──────────────────────────────────────────────


# CSV 导出列顺序
_CSV_COLUMNS = [
    "id",
    "user_id",
    "tenant_id",
    "action",
    "resource_type",
    "resource_id",
    "details",
    "ip_address",
    "user_agent",
    "request_id",
    "created_at",
]


def _audit_log_to_row(log: AuditLog) -> dict[str, Any]:
    """将 AuditLog 对象转换为可序列化的字典行。"""
    return {
        "id": log.id,
        "user_id": log.user_id,
        "tenant_id": log.tenant_id,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "details": log.details,
        "ip_address": log.ip_address,
        "user_agent": log.user_agent,
        "request_id": log.request_id,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }


async def export_audit_logs(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    format: str = "csv",
    limit: int = 10000,
) -> str:
    """导出审计日志。

    支持导出为 CSV 或 JSON 格式。导出量通过 ``limit`` 限制以避免内存溢出。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，与 :func:`get_audit_logs` 一致
        format: 导出格式，``"csv"`` 或 ``"json"``
        limit: 导出记录数上限（默认 10000）

    Returns:
        导出的字符串内容（CSV 或 JSON）

    Raises:
        ValueError: 不支持的导出格式。
    """
    logs = await get_audit_logs(db, filters=filters, skip=0, limit=limit)
    rows = [_audit_log_to_row(log) for log in logs]

    if format.lower() == "csv":
        return _export_to_csv(rows)
    if format.lower() == "json":
        return _export_to_json(rows)
    raise ValueError(f"不支持的导出格式: {format}（仅支持 csv 或 json）")


def _export_to_csv(rows: list[dict[str, Any]]) -> str:
    """将审计日志行列表导出为 CSV 字符串。"""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=_CSV_COLUMNS,
        quoting=csv.QUOTE_MINIMAL,
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in rows:
        # details 字段序列化为 JSON 字符串，便于 CSV 存储
        csv_row = dict(row)
        if csv_row.get("details") is not None:
            csv_row["details"] = json.dumps(
                csv_row["details"], ensure_ascii=False
            )
        writer.writerow(csv_row)
    return output.getvalue()


def _export_to_json(rows: list[dict[str, Any]]) -> str:
    """将审计日志行列表导出为 JSON 字符串。"""
    return json.dumps(
        {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "count": len(rows),
            "items": rows,
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
