"""DDoS 清洗识别检测器。

识别 DDoS 清洗商临时宣告前缀导致的 ROA/BGP 良性冲突。

检测流程：
1. 检查 origin_as 是否为已登记的清洗商 ASN（asn_type = scrubber）
2. 检查是否有有效的清洗授权记录（ScrubberAuthorization）
3. 检查是否在授权时间窗内
4. 检查 AS_PATH 模式是否符合清洗特征

注意：良性冲突识别只降低误报优先级，不能替代安全验证。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.benign_conflict import ScrubberAuthorization
from app.models.detection import Alert
from app.schemas.benign_conflict import BenignConflictAnalysisResult

logger = get_logger("app.benign_conflict.ddos_scrubbing")


async def detect_ddos_scrubbing(db: AsyncSession, alert: Alert) -> BenignConflictAnalysisResult:
    """识别 DDoS 清洗临时宣告。

    Args:
        db: 异步数据库会话
        alert: 待分析的告警对象

    Returns:
        良性冲突分析结果。若识别为 DDoS 清洗，``is_benign`` 为 True，
        ``conflict_type`` 为 ``ddos_scrubbing``。
    """
    prefix = alert.prefix
    origin_as = alert.origin_as

    # 缺少 origin_as 无法判定
    if origin_as is None:
        return BenignConflictAnalysisResult(
            is_benign=False,
            recommendation="告警缺少 origin_as，无法判定 DDoS 清洗",
        )

    evidence: dict[str, Any] = {
        "prefix": prefix,
        "origin_as": origin_as,
        "checks": {},
    }
    confidence = 0.0

    # 1. 检查 origin_as 是否为已登记的清洗商 ASN
    scrubber_asn = await _check_scrubber_asn(db, origin_as)
    evidence["checks"]["is_scrubber_asn"] = scrubber_asn is not None
    if scrubber_asn is not None:
        evidence["scrubber_asn_info"] = {
            "asn": scrubber_asn.asn,
            "name": scrubber_asn.name,
            "asn_type": scrubber_asn.asn_type,
        }
        confidence += 0.3

    # 2. 检查是否有有效的清洗授权记录
    authorization = await _check_scrubber_authorization(db, origin_as, prefix)
    evidence["checks"]["has_authorization"] = authorization is not None
    if authorization is not None:
        evidence["authorization"] = {
            "id": authorization.id,
            "scrubber_asn": authorization.scrubber_asn,
            "customer_prefix": authorization.customer_prefix,
            "customer_asn": authorization.customer_asn,
            "authorized_at": (
                authorization.authorized_at.isoformat() if authorization.authorized_at else None
            ),
            "expires_at": (
                authorization.expires_at.isoformat() if authorization.expires_at else None
            ),
            "status": authorization.status,
            "work_order_id": authorization.work_order_id,
        }
        confidence += 0.4

        # 3. 检查是否在授权时间窗内
        now = datetime.now(UTC)
        in_window = authorization.authorized_at <= now <= authorization.expires_at
        evidence["checks"]["in_authorization_window"] = in_window
        if in_window:
            confidence += 0.2
        else:
            # 不在授权窗口内，降低置信度
            confidence -= 0.1

    # 4. 检查 AS_PATH 模式是否符合清洗特征
    as_path_pattern = _check_as_path_pattern(alert.as_path, origin_as)
    evidence["checks"]["as_path_pattern"] = as_path_pattern
    if as_path_pattern == "scrubber_like":
        confidence += 0.1

    # 规范化置信度到 [0, 1]
    confidence = max(0.0, min(1.0, confidence))

    # 判定：清洗商 ASN 且有授权 → 良性冲突
    is_benign = (
        scrubber_asn is not None
        and authorization is not None
        and evidence["checks"].get("in_authorization_window", False)
    )

    if is_benign:
        recommendation = (
            f"前缀 {prefix} 由清洗商 AS{origin_as} 临时宣告，"
            "存在有效授权记录且在授权时间窗内，判定为 DDoS 清洗良性冲突。"
            "建议：降低告警优先级，跟踪授权到期后是否撤销宣告；"
            "如需长期宣告，建议补齐临时 ROA 或纳入授权治理流程。"
        )
    elif scrubber_asn is not None or authorization is not None:
        recommendation = (
            f"前缀 {prefix} 由 AS{origin_as} 宣告，存在清洗商相关线索"
            "但证据不完整（缺少授权或不在授权窗口）。"
            "建议：人工核实清洗授权状态，确认是否为计划内清洗作业。"
        )
    else:
        recommendation = "未识别为 DDoS 清洗良性冲突，按正常告警处置流程处理。"

    return BenignConflictAnalysisResult(
        conflict_type="ddos_scrubbing" if is_benign else None,
        confidence=confidence,
        evidence=evidence,
        recommendation=recommendation,
        is_benign=is_benign,
    )


async def _check_scrubber_asn(db: AsyncSession, asn: int) -> ASN | None:
    """检查 ASN 是否为已登记的清洗商。

    Args:
        db: 异步数据库会话
        asn: 待检查的 AS 号

    Returns:
        ASN 对象（若为清洗商），否则 None
    """
    stmt = select(ASN).where(ASN.asn == asn).where(ASN.asn_type == "scrubber")
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _check_scrubber_authorization(
    db: AsyncSession, scrubber_asn: int, prefix: str
) -> ScrubberAuthorization | None:
    """检查是否存在有效的清洗授权记录。

    Args:
        db: 异步数据库会话
        scrubber_asn: 清洗商 AS 号
        prefix: 客户前缀

    Returns:
        清洗授权对象（若存在且状态为 active），否则 None
    """
    stmt = (
        select(ScrubberAuthorization)
        .where(ScrubberAuthorization.scrubber_asn == scrubber_asn)
        .where(ScrubberAuthorization.customer_prefix == prefix)
        .where(ScrubberAuthorization.status == "active")
        .order_by(ScrubberAuthorization.expires_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _check_as_path_pattern(as_path: list[int] | None, origin_as: int) -> str:
    """检查 AS_PATH 模式是否符合清洗特征。

    清洗特征：
    - AS_PATH 较短（通常 <= 4 跳）
    - origin_as 出现在路径末尾
    - 路径中可能包含客户 ASN

    Args:
        as_path: AS 路径列表
        origin_as: 起源 AS 号

    Returns:
        模式标识：``scrubber_like`` / ``normal`` / ``unknown``
    """
    if as_path is None or len(as_path) == 0:
        return "unknown"

    # 路径较短且 origin_as 在末尾
    if len(as_path) <= 4 and as_path[-1] == origin_as:
        return "scrubber_like"

    return "normal"


__all__ = ["detect_ddos_scrubbing"]
