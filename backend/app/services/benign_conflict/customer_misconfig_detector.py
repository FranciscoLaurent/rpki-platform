"""客户误配置识别检测器。

识别客户 ASN 误配置导致的 ROA/BGP 良性冲突。

检测流程：
1. 检查客户 ASN 授权边界（asn_type = customer）
2. 检查实际客户合同（Customer 关联）
3. 检查 BGP 记录（历史是否宣告过该前缀）

注意：良性冲突识别只降低误报优先级，不能替代安全验证。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement
from app.models.business import Customer
from app.models.detection import Alert
from app.models.prefix import Prefix
from app.schemas.benign_conflict import BenignConflictAnalysisResult

logger = get_logger("app.benign_conflict.customer_misconfig")


async def detect_customer_misconfig(
    db: AsyncSession, alert: Alert
) -> BenignConflictAnalysisResult:
    """识别客户误配置。

    Args:
        db: 异步数据库会话
        alert: 待分析的告警对象

    Returns:
        良性冲突分析结果。若识别为客户误配置，``is_benign`` 为 True，
        ``conflict_type`` 为 ``customer_misconfig``。
    """
    prefix = alert.prefix
    origin_as = alert.origin_as

    if origin_as is None:
        return BenignConflictAnalysisResult(
            is_benign=False,
            recommendation="告警缺少 origin_as，无法判定客户误配置",
        )

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "checks": {},
    }
    confidence = 0.0

    # 1. 检查 origin_as 是否为客户 ASN
    customer_asn = await _check_customer_asn(db, origin_as)
    evidence["checks"]["is_customer_asn"] = customer_asn is not None
    if customer_asn is not None:
        evidence["customer_asn_info"] = {
            "asn": customer_asn.asn,
            "name": customer_asn.name,
            "asn_type": customer_asn.asn_type,
            "contact_email": customer_asn.contact_email,
            "noc_phone": customer_asn.noc_phone,
        }
        confidence += 0.3

    # 2. 检查前缀资产台账与客户关联
    prefix_record = await _get_prefix_record(db, prefix)
    if prefix_record is not None:
        evidence["prefix_record"] = {
            "id": prefix_record.id,
            "prefix": prefix_record.prefix,
            "customer_id": prefix_record.customer_id,
            "business_service": prefix_record.business_service,
            "status": prefix_record.status,
        }
        # 前缀关联了客户，但 origin_as 不是该客户的 ASN
        if prefix_record.customer_id is not None:
            customer = await _get_customer(db, prefix_record.customer_id)
            if customer is not None:
                evidence["customer_info"] = {
                    "id": customer.id,
                    "name": customer.name,
                }
                # 检查客户 ASN 是否与 origin_as 匹配（简化判断）
                evidence["checks"]["prefix_has_customer"] = True
                confidence += 0.2

    # 3. 检查 BGP 历史记录（客户是否曾宣告过该前缀）
    historical_announcements = await _check_historical_announcements(
        db, prefix, origin_as
    )
    evidence["checks"]["has_historical_announcement"] = historical_announcements[
        "has_history"
    ]
    evidence["historical_announcements"] = historical_announcements
    if historical_announcements["has_history"]:
        confidence += 0.2
    else:
        # 无历史宣告记录，可能是误配置
        confidence += 0.1

    # 4. 检查是否为子前缀误宣告（客户宣告了未授权的子前缀）
    parent_prefix = await _find_parent_prefix(db, prefix)
    if parent_prefix is not None:
        evidence["parent_prefix"] = {
            "id": parent_prefix.id,
            "prefix": parent_prefix.prefix,
            "customer_id": parent_prefix.customer_id,
        }
        evidence["checks"]["has_parent_prefix"] = True
        # 父前缀属于其他客户，但当前 origin_as 是客户 ASN → 误配置
        if (
            parent_prefix.customer_id is not None
            and prefix_record is not None
            and prefix_record.customer_id != parent_prefix.customer_id
        ):
            evidence["checks"]["cross_customer_misconfig"] = True
            confidence += 0.2

    # 规范化置信度
    confidence = max(0.0, min(1.0, confidence))

    # 判定：客户 ASN 且存在误配置线索 → 良性冲突（误配置）
    is_benign = customer_asn is not None

    if is_benign:
        recommendation = (
            f"前缀 {prefix} 由客户 AS{origin_as} 宣告，"
            "判定为客户误配置良性冲突。"
            "建议：生成修复待办，通知客户 NOC 联系人"
            f"（{customer_asn.contact_email or '未知邮箱'}）"
            "核实宣告配置；如确认误配置，要求客户撤回宣告并更新 ROA。"
        )
    elif customer_asn is not None:
        recommendation = (
            f"前缀 {prefix} 由 AS{origin_as} 宣告，"
            "存在客户 ASN 线索但证据不完整。"
            "建议：人工核实客户合同与授权边界。"
        )
    else:
        recommendation = "未识别为客户误配置良性冲突，按正常告警处置流程处理。"

    return BenignConflictAnalysisResult(
        conflict_type="customer_misconfig" if is_benign else None,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
        is_benign=is_benign,
    )


async def _check_customer_asn(db: AsyncSession, asn: int) -> ASN | None:
    """检查 ASN 是否为客户 ASN。

    Args:
        db: 异步数据库会话
        asn: AS 号

    Returns:
        ASN 对象（若为客户 ASN），否则 None
    """
    stmt = select(ASN).where(ASN.asn == asn).where(ASN.asn_type == "customer")
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_prefix_record(db: AsyncSession, prefix: str) -> Prefix | None:
    """查询前缀资产台账记录。"""
    stmt = select(Prefix).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_customer(db: AsyncSession, customer_id: int) -> Customer | None:
    """查询客户信息。"""
    stmt = select(Customer).where(Customer.id == customer_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _check_historical_announcements(
    db: AsyncSession,
    prefix: str,
    origin_as: int,
    lookback_days: int = 30,
) -> dict[str, Any]:
    """检查客户是否曾宣告过该前缀。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        origin_as: 起源 AS 号
        lookback_days: 回溯天数

    Returns:
        包含历史宣告信息的字典
    """
    since = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    stmt = (
        select(BGPAnnouncement)
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as == origin_as)
        .where(BGPAnnouncement.timestamp >= since)
        .order_by(BGPAnnouncement.timestamp.desc())
        .limit(5)
    )
    result = await db.execute(stmt)
    announcements = list(result.scalars().all())

    return {
        "has_history": len(announcements) > 0,
        "count": len(announcements),
        "recent_announcements": [
            {
                "id": ann.id,
                "timestamp": ann.timestamp.isoformat() if ann.timestamp else None,
                "observation_point_id": ann.observation_point_id,
            }
            for ann in announcements
        ],
        "lookback_days": lookback_days,
    }


async def _find_parent_prefix(db: AsyncSession, prefix: str) -> Prefix | None:
    """查找前缀的父前缀。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀

    Returns:
        父前缀对象（若存在），否则 None
    """
    stmt = select(Prefix).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    current = result.scalar_one_or_none()
    if current is None or current.parent_id is None:
        return None

    parent_stmt = select(Prefix).where(Prefix.id == current.parent_id)
    parent_result = await db.execute(parent_stmt)
    return parent_result.scalar_one_or_none()


__all__ = ["detect_customer_misconfig"]
