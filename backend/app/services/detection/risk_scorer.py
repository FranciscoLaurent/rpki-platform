"""风险评分模型。

按六个维度计算告警的可解释风险评分：
1. 资产重要性评分
2. RPKI 证据评分
3. BGP 传播证据评分
4. 授权与变更证据评分
5. 历史与行为基线评分
6. 外部风险特征评分

每个维度包含加分项与减分项，最终返回总分、置信度与建议动作。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement, BGPWithdraw
from app.models.business import BusinessService, Customer
from app.models.detection import Alert, RiskScore
from app.models.prefix import Prefix
from app.models.rpki import VRP
from app.services.vrp_service import validate_bgp_announcement

logger = get_logger("app.detection.risk_scorer")


# 维度权重（总和为 1.0）
DIMENSION_WEIGHTS = {
    "asset_importance": 0.20,
    "rpki_evidence": 0.25,
    "bgp_propagation": 0.20,
    "authorization": 0.15,
    "historical_baseline": 0.10,
    "external_risk": 0.10,
}


async def calculate_risk_score(
    db: AsyncSession, alert: Alert
) -> RiskScore:
    """计算告警的可解释风险评分。

    Args:
        db: 异步数据库会话
        alert: 告警对象

    Returns:
        风险评分对象（已持久化）
    """
    evidence = alert.evidence or {}
    prefix = alert.prefix
    origin_as = alert.origin_as

    # 1. 资产重要性评分
    asset_score, asset_factors = await _score_asset_importance(db, prefix)

    # 2. RPKI 证据评分
    rpki_score, rpki_factors = await _score_rpki_evidence(
        db, prefix, origin_as, evidence
    )

    # 3. BGP 传播证据评分
    bgp_score, bgp_factors = await _score_bgp_propagation(
        db, prefix, origin_as, evidence
    )

    # 4. 授权与变更证据评分
    auth_score, auth_factors = await _score_authorization(
        db, prefix, origin_as, evidence
    )

    # 5. 历史与行为基线评分
    hist_score, hist_factors = await _score_historical_baseline(
        db, prefix, origin_as
    )

    # 6. 外部风险特征评分
    ext_score, ext_factors = await _score_external_risk(
        db, origin_as, evidence
    )

    # 计算加权总分（0-100）
    total_score = (
        asset_score * DIMENSION_WEIGHTS["asset_importance"]
        + rpki_score * DIMENSION_WEIGHTS["rpki_evidence"]
        + bgp_score * DIMENSION_WEIGHTS["bgp_propagation"]
        + auth_score * DIMENSION_WEIGHTS["authorization"]
        + hist_score * DIMENSION_WEIGHTS["historical_baseline"]
        + ext_score * DIMENSION_WEIGHTS["external_risk"]
    ) * 100

    # 计算置信度（基于证据充分性）
    confidence = _calculate_confidence(
        asset_factors, rpki_factors, bgp_factors, auth_factors,
        hist_factors, ext_factors,
    )

    # 生成建议动作
    recommended_actions = _generate_recommended_actions(
        alert.alert_type, total_score, rpki_factors, bgp_factors
    )

    # 持久化风险评分
    risk_score = RiskScore(
        alert_id=alert.id,
        total_score=round(total_score, 2),
        asset_importance_score=round(asset_score * 100, 2),
        asset_importance_factors=asset_factors,
        rpki_evidence_score=round(rpki_score * 100, 2),
        rpki_evidence_factors=rpki_factors,
        bgp_propagation_score=round(bgp_score * 100, 2),
        bgp_propagation_factors=bgp_factors,
        authorization_score=round(auth_score * 100, 2),
        authorization_factors=auth_factors,
        historical_baseline_score=round(hist_score * 100, 2),
        historical_factors=hist_factors,
        external_risk_score=round(ext_score * 100, 2),
        external_risk_factors=ext_factors,
        confidence=round(confidence, 3),
        recommended_actions=recommended_actions,
    )
    db.add(risk_score)
    await db.flush()

    # 更新告警的风险评分与置信度
    alert.risk_score = round(total_score, 2)
    alert.confidence = round(confidence, 3)

    logger.info(
        "风险评分计算完成",
        alert_id=alert.id,
        total_score=total_score,
        confidence=confidence,
    )
    return risk_score


# ──────────────────────────────────────────────
# 维度 1：资产重要性评分
# ──────────────────────────────────────────────


async def _score_asset_importance(
    db: AsyncSession, prefix: str
) -> tuple[float, dict[str, Any]]:
    """资产重要性评分。

    评估因素：
    - 前缀重要度（critical/important/normal/low）
    - 关联客户的服务等级
    - 关联业务服务的重要度
    """
    score = 0.3  # 基础分
    factors: dict[str, Any] = {
        "importance": None,
        "customer_service_level": None,
        "business_importance": None,
        "additions": [],
        "deductions": [],
    }

    # 查询前缀资产
    stmt = select(Prefix).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    prefix_obj = result.scalar_one_or_none()

    if prefix_obj is None:
        factors["additions"].append("前缀不在资产台账中（+0.0）")
        return score, factors

    factors["importance"] = prefix_obj.importance
    importance_score_map = {
        "critical": 0.7,
        "important": 0.5,
        "normal": 0.3,
        "low": 0.1,
    }
    imp_score = importance_score_map.get(prefix_obj.importance, 0.3)
    score = max(score, imp_score)
    factors["additions"].append(
        f"前缀重要度 {prefix_obj.importance}（+{imp_score:.2f}）"
    )

    # 关联客户服务等级
    if prefix_obj.customer_id is not None:
        cust_stmt = select(Customer).where(Customer.id == prefix_obj.customer_id)
        cust_result = await db.execute(cust_stmt)
        customer = cust_result.scalar_one_or_none()
        if customer:
            factors["customer_service_level"] = customer.service_level
            sl_score_map = {
                "platinum": 0.2,
                "gold": 0.15,
                "silver": 0.1,
                "standard": 0.05,
            }
            sl_bonus = sl_score_map.get(customer.service_level, 0.0)
            score = min(1.0, score + sl_bonus)
            factors["additions"].append(
                f"客户服务等级 {customer.service_level}（+{sl_bonus:.2f}）"
            )

    # 关联业务服务重要度
    if prefix_obj.business_service:
        biz_stmt = select(BusinessService).where(
            BusinessService.name == prefix_obj.business_service
        )
        biz_result = await db.execute(biz_stmt)
        biz = biz_result.scalar_one_or_none()
        if biz:
            factors["business_importance"] = biz.importance
            biz_score_map = {
                "critical": 0.15,
                "important": 0.10,
                "normal": 0.05,
                "low": 0.0,
            }
            biz_bonus = biz_score_map.get(biz.importance, 0.0)
            score = min(1.0, score + biz_bonus)
            factors["additions"].append(
                f"业务服务重要度 {biz.importance}（+{biz_bonus:.2f}）"
            )

    return min(1.0, score), factors


# ──────────────────────────────────────────────
# 维度 2：RPKI 证据评分
# ──────────────────────────────────────────────


async def _score_rpki_evidence(
    db: AsyncSession,
    prefix: str,
    origin_as: int | None,
    evidence: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """RPKI 证据评分。

    评估因素：
    - RPKI 验证状态（Valid/Invalid/NotFound）
    - origin AS 不匹配
    - maxLength 超界
    """
    score = 0.3
    factors: dict[str, Any] = {
        "validation_status": None,
        "invalid_reason": None,
        "additions": [],
        "deductions": [],
    }

    # 优先使用 evidence 中的 RPKI 状态
    rpki_status = evidence.get("rpki_validation_status")
    rpki_invalid_reason = evidence.get("rpki_invalid_reason")

    # 若 evidence 中无，则实时验证
    if rpki_status is None and origin_as is not None:
        validation = await validate_bgp_announcement(db, prefix, origin_as)
        rpki_status = validation.validation_result.validation_status
        rpki_invalid_reason = validation.validation_result.invalid_reason

    factors["validation_status"] = rpki_status
    factors["invalid_reason"] = rpki_invalid_reason

    if rpki_status == "invalid":
        # Invalid 是最强的劫持证据
        score = 0.9
        factors["additions"].append(
            f"RPKI 验证 Invalid（+0.6）"
        )
        if rpki_invalid_reason == "origin_as_mismatch":
            score = 1.0
            factors["additions"].append(
                "origin AS 不匹配（+0.1）"
            )
        elif rpki_invalid_reason == "length_exceeded":
            factors["additions"].append(
                "前缀长度超过 maxLength（+0.0）"
            )
    elif rpki_status == "not_found":
        score = 0.4
        factors["additions"].append(
            "RPKI 验证 NotFound（+0.1）"
        )
    elif rpki_status == "valid":
        score = 0.1
        factors["deductions"].append(
            "RPKI 验证 Valid（-0.2，证据不支持劫持）"
        )

    return min(1.0, max(0.0, score)), factors


# ──────────────────────────────────────────────
# 维度 3：BGP 传播证据评分
# ──────────────────────────────────────────────


async def _score_bgp_propagation(
    db: AsyncSession,
    prefix: str,
    origin_as: int | None,
    evidence: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """BGP 传播证据评分。

    评估因素：
    - 观察点数量
    - 传播速度
    - 撤路规模
    - 异常路径
    """
    score = 0.3
    factors: dict[str, Any] = {
        "propagation_scope": None,
        "withdraw_count": None,
        "abnormal_path": None,
        "additions": [],
        "deductions": [],
    }

    propagation_scope = evidence.get("propagation_scope", 0)
    factors["propagation_scope"] = propagation_scope

    # 传播范围评分
    if propagation_scope >= 10:
        score = 0.9
        factors["additions"].append(
            f"传播范围广（{propagation_scope} 个观察点，+0.6）"
        )
    elif propagation_scope >= 5:
        score = 0.7
        factors["additions"].append(
            f"传播范围中等（{propagation_scope} 个观察点，+0.4）"
        )
    elif propagation_scope >= 3:
        score = 0.5
        factors["additions"].append(
            f"传播范围较小（{propagation_scope} 个观察点，+0.2）"
        )

    # 撤路规模
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    withdraw_stmt = (
        select(func.count(BGPWithdraw.id))
        .where(BGPWithdraw.prefix == prefix)
        .where(BGPWithdraw.timestamp >= since)
    )
    withdraw_result = await db.execute(withdraw_stmt)
    withdraw_count = int(withdraw_result.scalar_one() or 0)
    factors["withdraw_count"] = withdraw_count

    if withdraw_count >= 5:
        score = min(1.0, score + 0.2)
        factors["additions"].append(
            f"近期撤路频繁（{withdraw_count} 次，+0.2）"
        )

    # 异常路径
    if evidence.get("path_mutation", {}).get("is_anomaly"):
        score = min(1.0, score + 0.15)
        factors["abnormal_path"] = True
        factors["additions"].append("AS_PATH 突变（+0.15）")
    elif evidence.get("abnormal_transit", {}).get("is_anomaly"):
        score = min(1.0, score + 0.10)
        factors["abnormal_path"] = True
        factors["additions"].append("异常中转 AS（+0.10）")

    return min(1.0, score), factors


# ──────────────────────────────────────────────
# 维度 4：授权与变更证据评分
# ──────────────────────────────────────────────


async def _score_authorization(
    db: AsyncSession,
    prefix: str,
    origin_as: int | None,
    evidence: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """授权与变更证据评分。

    评估因素：
    - 资产台账匹配
    - 审批记录（占位）
    - 变更窗口（占位）
    """
    score = 0.3
    factors: dict[str, Any] = {
        "in_asset_registry": None,
        "authorized_origin_as": None,
        "in_change_window": None,
        "additions": [],
        "deductions": [],
    }

    # 资产台账匹配
    stmt = select(Prefix).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    prefix_obj = result.scalar_one_or_none()

    if prefix_obj is None:
        score = 0.7
        factors["in_asset_registry"] = False
        factors["additions"].append(
            "前缀不在资产台账中（+0.4，可疑）"
        )
    else:
        factors["in_asset_registry"] = True
        factors["deductions"].append(
            "前缀在资产台账中（-0.1，已知资产）"
        )

    # 授权 origin AS 检查
    authorized_origin = evidence.get("authorized_origin_as")
    factors["authorized_origin_as"] = authorized_origin

    if (
        authorized_origin is not None
        and origin_as is not None
        and origin_as != authorized_origin
    ):
        score = min(1.0, score + 0.4)
        factors["additions"].append(
            f"origin AS 不匹配授权（AS{origin_as} ≠ AS{authorized_origin}，+0.4）"
        )
    elif (
        authorized_origin is not None
        and origin_as == authorized_origin
    ):
        score = max(0.0, score - 0.2)
        factors["deductions"].append(
            "origin AS 匹配授权（-0.2，已授权）"
        )

    # TODO: 接入变更管理系统后实现变更窗口检查
    factors["in_change_window"] = None
    factors["additions"].append("变更窗口检查为占位实现（+0.0）")

    return min(1.0, max(0.0, score)), factors


# ──────────────────────────────────────────────
# 维度 5：历史与行为基线评分
# ──────────────────────────────────────────────


async def _score_historical_baseline(
    db: AsyncSession,
    prefix: str,
    origin_as: int | None,
) -> tuple[float, dict[str, Any]]:
    """历史与行为基线评分。

    评估因素：
    - 历史 MOAS 模式
    - Anycast 模式
    - 正常路径基线
    """
    score = 0.3
    factors: dict[str, Any] = {
        "historical_origin_asns": [],
        "is_new_origin": None,
        "historical_moas": None,
        "additions": [],
        "deductions": [],
    }

    # 查询历史 origin AS
    since = datetime.now(timezone.utc) - timedelta(days=30)
    stmt = (
        select(BGPAnnouncement.origin_as)
        .where(BGPAnnouncement.prefix == prefix)
        .where(BGPAnnouncement.origin_as.is_not(None))
        .where(BGPAnnouncement.timestamp >= since)
        .distinct()
    )
    result = await db.execute(stmt)
    historical_asns = [row[0] for row in result.all() if row[0] is not None]
    factors["historical_origin_asns"] = historical_asns

    if origin_as is not None:
        if origin_as not in historical_asns:
            # 新 origin AS，可疑
            score = 0.7
            factors["is_new_origin"] = True
            factors["additions"].append(
                f"origin AS{origin_as} 历史上未宣告过该前缀（+0.4）"
            )
        else:
            factors["is_new_origin"] = False
            factors["deductions"].append(
                f"origin AS{origin_as} 历史上宣告过该前缀（-0.1）"
            )

    # 历史 MOAS
    if len(historical_asns) >= 2:
        factors["historical_moas"] = True
        factors["deductions"].append(
            "前缀历史上存在 MOAS（-0.05，可能是正常多 origin）"
        )
        score = max(0.0, score - 0.05)

    return min(1.0, max(0.0, score)), factors


# ──────────────────────────────────────────────
# 维度 6：外部风险特征评分
# ──────────────────────────────────────────────


async def _score_external_risk(
    db: AsyncSession,
    origin_as: int | None,
    evidence: dict[str, Any],
) -> tuple[float, dict[str, Any]]:
    """外部风险特征评分。

    评估因素：
    - 异常 ASN 历史
    - 未知中转
    - 异常国家/地区（占位）
    """
    score = 0.2
    factors: dict[str, Any] = {
        "asn_risk_profile": None,
        "abnormal_transit": None,
        "additions": [],
        "deductions": [],
    }

    if origin_as is None:
        return score, factors

    # 查询 ASN 风险画像
    stmt = select(ASN).where(ASN.asn == origin_as)
    result = await db.execute(stmt)
    asn_obj = result.scalar_one_or_none()

    if asn_obj is None:
        # 未知 AS
        score = 0.6
        factors["additions"].append(
            f"origin AS{origin_as} 不在 ASN 台账中（+0.4，未知 AS）"
        )
    else:
        factors["asn_risk_profile"] = asn_obj.risk_profile
        if asn_obj.risk_profile:
            risk = asn_obj.risk_profile.lower()
            if "high_risk" in risk:
                score = 0.8
                factors["additions"].append(
                    f"AS{origin_as} 风险画像标注为高风险（+0.6）"
                )
            elif "medium_risk" in risk:
                score = 0.5
                factors["additions"].append(
                    f"AS{origin_as} 风险画像标注为中等风险（+0.3）"
                )

    # 异常中转
    abnormal_transit = evidence.get("abnormal_transit", {})
    if abnormal_transit.get("is_anomaly"):
        score = min(1.0, score + 0.2)
        factors["abnormal_transit"] = abnormal_transit.get(
            "abnormal_asns", []
        )
        factors["additions"].append(
            f"存在异常中转 AS（+0.2）"
        )

    return min(1.0, score), factors


# ──────────────────────────────────────────────
# 置信度计算
# ──────────────────────────────────────────────


def _calculate_confidence(
    asset_factors: dict[str, Any],
    rpki_factors: dict[str, Any],
    bgp_factors: dict[str, Any],
    auth_factors: dict[str, Any],
    hist_factors: dict[str, Any],
    ext_factors: dict[str, Any],
) -> float:
    """计算置信度。

    基于各维度证据的充分性，证据越充分置信度越高。
    """
    confidence = 0.5  # 基础置信度

    # RPKI 验证状态明确
    if rpki_factors.get("validation_status") is not None:
        confidence += 0.2

    # 资产台账信息明确
    if asset_factors.get("importance") is not None:
        confidence += 0.1

    # 历史基线充分
    if hist_factors.get("historical_origin_asns"):
        confidence += 0.1

    # BGP 传播数据充分
    if bgp_factors.get("propagation_scope") is not None:
        confidence += 0.05

    # 授权信息明确
    if auth_factors.get("authorized_origin_as") is not None:
        confidence += 0.05

    return min(1.0, confidence)


# ──────────────────────────────────────────────
# 建议动作生成
# ──────────────────────────────────────────────


def _generate_recommended_actions(
    alert_type: str,
    total_score: float,
    rpki_factors: dict[str, Any],
    bgp_factors: dict[str, Any],
) -> list[dict[str, Any]]:
    """根据告警类型与评分生成建议动作。"""
    actions: list[dict[str, Any]] = []

    # 高风险：立即处置
    if total_score >= 70:
        actions.append({
            "priority": "immediate",
            "action": "立即联系 origin AS 的 NOC，要求撤回异常公告",
            "reason": "风险评分过高，需立即处置",
        })
        actions.append({
            "priority": "immediate",
            "action": "通知上游提供商过滤该前缀的异常路由",
            "reason": "防止异常路由进一步传播",
        })

    # RPKI Invalid：建议部署 RPKI 过滤
    if rpki_factors.get("validation_status") == "invalid":
        actions.append({
            "priority": "high",
            "action": "在边界路由器部署 RPKI ROV 过滤，拒绝 Invalid 路由",
            "reason": "RPKI 验证失败，应拒绝该路由",
        })

    # 传播范围广：建议联系上游
    if (bgp_factors.get("propagation_scope") or 0) >= 10:
        actions.append({
            "priority": "high",
            "action": "联系主要上游提供商，协调全球范围撤回",
            "reason": "异常路由已大范围传播",
        })

    # 中等风险：调查确认
    if 40 <= total_score < 70:
        actions.append({
            "priority": "medium",
            "action": "调查 origin AS 的公告意图，确认是否为授权变更",
            "reason": "风险评分中等，需进一步调查",
        })

    # 低风险：持续观察
    if total_score < 40:
        actions.append({
            "priority": "low",
            "action": "持续观察，纳入基线监控",
            "reason": "风险评分较低，可能是正常变更",
        })

    # 按告警类型补充建议
    if alert_type == "moas":
        actions.append({
            "priority": "medium",
            "action": "核实 MOAS 是否为授权多 origin 或 Anycast",
            "reason": "MOAS 可能是正常业务场景",
        })
    elif alert_type == "route_leak":
        actions.append({
            "priority": "high",
            "action": "检查 BGP 路由策略，必要时调整 import/export 策略",
            "reason": "路由泄露通常源于策略配置错误",
        })
    elif alert_type == "withdraw_flap":
        actions.append({
            "priority": "medium",
            "action": "检查前缀的稳定性，联系 origin AS 排查",
            "reason": "频繁震荡可能影响业务",
        })

    return actions


__all__ = ["calculate_risk_score"]
