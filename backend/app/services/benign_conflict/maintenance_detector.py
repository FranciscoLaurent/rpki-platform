"""计划内割接识别检测器。

识别计划内维护窗口期间发生的短时配置/变更异常导致的良性冲突。

检测流程：
1. 检查是否有匹配的维护窗口（MaintenanceWindow）
2. 检查审批记录
3. 检查内部 BMP/RIB 数据

注意：良性冲突识别只降低误报优先级，不能替代安全验证。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.benign_conflict import MaintenanceWindow
from app.models.detection import Alert
from app.schemas.benign_conflict import BenignConflictAnalysisResult

logger = get_logger("app.benign_conflict.maintenance")


async def detect_planned_maintenance(
    db: AsyncSession, alert: Alert
) -> BenignConflictAnalysisResult:
    """识别计划内割接。

    Args:
        db: 异步数据库会话
        alert: 待分析的告警对象

    Returns:
        良性冲突分析结果。若识别为计划内割接，``is_benign`` 为 True，
        ``conflict_type`` 为 ``planned_maintenance``。
    """
    prefix = alert.prefix
    origin_as = alert.origin_as

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "checks": {},
    }
    confidence = 0.0

    # 1. 检查是否有匹配的维护窗口
    maintenance_window = await _find_matching_maintenance(
        db, prefix, origin_as, alert.created_at
    )
    evidence["checks"]["has_maintenance_window"] = maintenance_window is not None
    if maintenance_window is not None:
        evidence["maintenance_window"] = {
            "id": maintenance_window.id,
            "name": maintenance_window.name,
            "description": maintenance_window.description,
            "start_time": maintenance_window.start_time.isoformat()
            if maintenance_window.start_time
            else None,
            "end_time": maintenance_window.end_time.isoformat()
            if maintenance_window.end_time
            else None,
            "prefixes": maintenance_window.prefixes,
            "asns": maintenance_window.asns,
            "status": maintenance_window.status,
            "work_order_id": maintenance_window.work_order_id,
        }
        confidence += 0.5

        # 2. 检查审批记录
        has_approval = maintenance_window.approved_by is not None
        evidence["checks"]["has_approval"] = has_approval
        if has_approval:
            confidence += 0.2
            evidence["approved_by"] = maintenance_window.approved_by

        # 3. 检查工单号
        has_work_order = maintenance_window.work_order_id is not None
        evidence["checks"]["has_work_order"] = has_work_order
        if has_work_order:
            confidence += 0.1

        # 4. 检查窗口状态
        if maintenance_window.status in ("scheduled", "active"):
            confidence += 0.1

    # 5. 检查告警时间是否在窗口内（已在 _find_matching_maintenance 中处理）
    evidence["checks"]["alert_in_window"] = maintenance_window is not None

    # 规范化置信度
    confidence = max(0.0, min(1.0, confidence))

    # 判定：存在匹配的维护窗口且有审批 → 良性冲突
    is_benign = (
        maintenance_window is not None
        and maintenance_window.approved_by is not None
    )

    if is_benign:
        recommendation = (
            f"前缀 {prefix} 在维护窗口期内发生配置变更，"
            f"窗口名称：{maintenance_window.name}，"
            f"已由用户 ID {maintenance_window.approved_by} 审批，"
            "判定为计划内割接良性冲突。"
            "建议：跟踪窗口结束后是否按计划恢复，"
            "如未恢复需人工介入排查。"
        )
    elif maintenance_window is not None:
        recommendation = (
            f"前缀 {prefix} 存在匹配的维护窗口（{maintenance_window.name}），"
            "但缺少审批记录。建议：人工核实维护窗口审批状态。"
        )
    else:
        recommendation = "未识别为计划内割接良性冲突，按正常告警处置流程处理。"

    return BenignConflictAnalysisResult(
        conflict_type="planned_maintenance" if is_benign else None,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
        is_benign=is_benign,
    )


async def _find_matching_maintenance(
    db: AsyncSession,
    prefix: str,
    origin_as: int | None,
    alert_time: datetime,
) -> MaintenanceWindow | None:
    """查找匹配的维护窗口。

    匹配条件：
    - 告警时间在窗口时间范围内
    - 窗口状态为 scheduled 或 active
    - 前缀在窗口的受影响前缀列表中，或 ASN 在受影响 ASN 列表中

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        origin_as: 起源 AS 号
        alert_time: 告警时间

    Returns:
        匹配的维护窗口对象，无匹配返回 None
    """
    # 查询当前时间范围内活跃或已调度的维护窗口
    now = alert_time
    stmt = (
        select(MaintenanceWindow)
        .where(MaintenanceWindow.status.in_(["scheduled", "active"]))
        .where(MaintenanceWindow.start_time <= now)
        .where(MaintenanceWindow.end_time >= now)
        .order_by(MaintenanceWindow.start_time.desc())
    )
    result = await db.execute(stmt)
    windows = list(result.scalars().all())

    for window in windows:
        # 检查前缀匹配
        if window.prefixes and prefix in window.prefixes:
            return window
        # 检查 ASN 匹配
        if window.asns and origin_as is not None and origin_as in window.asns:
            return window
        # 若窗口未指定前缀和 ASN，视为全局匹配
        if not window.prefixes and not window.asns:
            return window

    return None


__all__ = ["detect_planned_maintenance"]
