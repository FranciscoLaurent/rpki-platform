"""资源迁移识别检测器。

识别 IP 资源迁移/转让导致的 ROA/BGP 良性冲突。

检测流程：
1. 检查 IPAM/CMDB 状态变化（Prefix 表状态与归属）
2. 检查组织归属变化（customer_id 变化）
3. 检查历史 ROA 变化
4. 检查 IRR 变化（暂为占位，需对接 IRR 数据源）

注意：良性冲突识别只降低误报优先级，不能替代安全验证。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.benign_conflict import BenignConflictRecord
from app.models.detection import Alert
from app.models.prefix import Prefix
from app.models.rpki import ROA
from app.schemas.benign_conflict import BenignConflictAnalysisResult

logger = get_logger("app.benign_conflict.resource_transfer")


async def detect_resource_transfer(
    db: AsyncSession, alert: Alert
) -> BenignConflictAnalysisResult:
    """识别资源迁移/转让。

    Args:
        db: 异步数据库会话
        alert: 待分析的告警对象

    Returns:
        良性冲突分析结果。若识别为资源迁移，``is_benign`` 为 True，
        ``conflict_type`` 为 ``resource_transfer``。
    """
    prefix = alert.prefix
    origin_as = alert.origin_as

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "checks": {},
    }
    confidence = 0.0

    # 1. 检查 IPAM/CMDB 状态变化（查询当前前缀资产台账）
    prefix_record = await _get_prefix_record(db, prefix)
    if prefix_record is not None:
        evidence["prefix_record"] = {
            "id": prefix_record.id,
            "prefix": prefix_record.prefix,
            "status": prefix_record.status,
            "customer_id": prefix_record.customer_id,
            "business_service": prefix_record.business_service,
            "region": prefix_record.region,
            "updated_at": prefix_record.updated_at.isoformat()
            if prefix_record.updated_at
            else None,
        }
        # 前缀状态为 reserved 或 deprecated 可能表示资源迁移中
        if prefix_record.status in ("reserved", "deprecated"):
            evidence["checks"]["prefix_in_transition"] = True
            confidence += 0.2

    # 2. 检查历史 ROA 变化（最近 30 天内是否有 ROA 变更）
    recent_roa_changes = await _check_recent_roa_changes(db, prefix)
    evidence["checks"]["has_recent_roa_changes"] = recent_roa_changes["has_changes"]
    evidence["roa_changes"] = recent_roa_changes
    if recent_roa_changes["has_changes"]:
        confidence += 0.3

    # 3. 检查是否存在已确认的资源迁移记录
    existing_transfer = await _check_existing_transfer_record(db, prefix)
    evidence["checks"]["has_existing_transfer_record"] = existing_transfer is not None
    if existing_transfer is not None:
        evidence["existing_transfer"] = {
            "id": existing_transfer.id,
            "conflict_type": existing_transfer.conflict_type,
            "status": existing_transfer.status,
            "confidence": existing_transfer.confidence,
            "related_work_order": existing_transfer.related_work_order,
        }
        confidence += 0.3

    # 4. 检查 IRR 变化（占位，需对接 IRR 数据源）
    evidence["checks"]["irr_check"] = "not_implemented"

    # 规范化置信度
    confidence = max(0.0, min(1.0, confidence))

    # 判定：存在资源迁移记录或近期 ROA 变更 → 疑似良性冲突
    is_benign = (
        existing_transfer is not None
        or (
            recent_roa_changes["has_changes"]
            and prefix_record is not None
            and prefix_record.status in ("reserved", "deprecated")
        )
    )

    if is_benign:
        recommendation = (
            f"前缀 {prefix} 疑似发生资源迁移，"
            "存在近期 ROA 变更或已有迁移记录。"
            "建议：核实 IPAM/CMDB 资产归属变更记录，"
            "确认资源迁移待治理状态；"
            "如确认为计划内迁移，更新 ROA 授权并跟踪迁移完成。"
        )
    elif recent_roa_changes["has_changes"]:
        recommendation = (
            f"前缀 {prefix} 存在近期 ROA 变更，"
            "但缺少明确的迁移记录。建议：人工核实资源归属变化。"
        )
    else:
        recommendation = "未识别为资源迁移良性冲突，按正常告警处置流程处理。"

    return BenignConflictAnalysisResult(
        conflict_type="resource_transfer" if is_benign else None,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
        is_benign=is_benign,
    )


async def _get_prefix_record(db: AsyncSession, prefix: str) -> Prefix | None:
    """查询前缀资产台账记录。"""
    stmt = select(Prefix).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _check_recent_roa_changes(
    db: AsyncSession, prefix: str, lookback_days: int = 30
) -> dict[str, Any]:
    """检查近期 ROA 变更。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        lookback_days: 回溯天数

    Returns:
        包含变更信息的字典
    """
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    stmt = (
        select(ROA)
        .where(ROA.prefix == prefix)
        .where(ROA.updated_at >= since)
        .order_by(ROA.updated_at.desc())
    )
    result = await db.execute(stmt)
    roas = list(result.scalars().all())

    return {
        "has_changes": len(roas) > 0,
        "change_count": len(roas),
        "recent_roas": [
            {
                "id": roa.id,
                "prefix": roa.prefix,
                "origin_as": roa.origin_as,
                "status": roa.status,
                "updated_at": roa.updated_at.isoformat()
                if roa.updated_at
                else None,
            }
            for roa in roas[:5]  # 仅保留最近 5 条
        ],
        "lookback_days": lookback_days,
    }


async def _check_existing_transfer_record(
    db: AsyncSession, prefix: str
) -> BenignConflictRecord | None:
    """检查是否存在已确认的资源迁移记录。"""
    stmt = (
        select(BenignConflictRecord)
        .where(BenignConflictRecord.prefix == prefix)
        .where(BenignConflictRecord.conflict_type == "resource_transfer")
        .where(BenignConflictRecord.status.in_(["suspected", "confirmed"]))
        .order_by(BenignConflictRecord.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


__all__ = ["detect_resource_transfer"]
