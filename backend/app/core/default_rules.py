"""默认检测规则集。

定义系统内置的 BGP 路由安全检测规则，并提供幂等初始化函数。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import DetectionRule

logger = get_logger("app.default_rules")


# 默认规则列表
DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "源 AS 劫持检测",
        "code": "origin_as_hijack",
        "description": (
            "检测 BGP 公告中非授权 origin AS 的劫持行为，"
            "结合 RPKI 验证、资产台账与历史基线综合判定。"
        ),
        "rule_type": "hijack",
        "enabled": True,
        "priority": 10,
        "conditions": {
            "require_rpki_invalid": True,
            "check_asset_registry": True,
            "check_historical_baseline": True,
        },
        "thresholds": {
            "propagation_scope_critical": 10,
            "propagation_scope_high": 5,
        },
        "whitelist": None,
        "scope": None,
        "severity": "P0",
    },
    {
        "name": "子前缀劫持检测",
        "code": "subprefix_hijack",
        "description": (
            "检测更具体前缀的异常公告，评估流量吸引风险，"
            "检查 ROA/maxLength 漏洞。"
        ),
        "rule_type": "subprefix_hijack",
        "enabled": True,
        "priority": 20,
        "conditions": {
            "check_max_length_violation": True,
            "check_origin_as_mismatch": True,
        },
        "thresholds": {
            "traffic_attraction_high": "high",
            "traffic_attraction_medium": "medium",
        },
        "whitelist": None,
        "scope": None,
        "severity": "P0",
    },
    {
        "name": "MOAS 异常检测",
        "code": "moas_detection",
        "description": (
            "识别前缀被多个 origin AS 宣告的异常情况，"
            "区分授权多 origin、Anycast、客户托管、清洗业务与未知双 origin。"
        ),
        "rule_type": "moas",
        "enabled": True,
        "priority": 30,
        "conditions": {
            "lookback_minutes": 60,
            "check_asn_type": True,
            "check_historical_moas": True,
        },
        "thresholds": {
            "min_origin_asns_for_moas": 2,
        },
        "whitelist": None,
        "scope": None,
        "severity": "P2",
    },
    {
        "name": "路由泄露检测",
        "code": "route_leak_detection",
        "description": (
            "结合上游/下游/对等关系（ASN 的 asn_type）与 AS_PATH 模式，"
            "检测客户向提供商泄露、提供商向客户泄露、对等间泄露等。"
        ),
        "rule_type": "route_leak",
        "enabled": True,
        "priority": 25,
        "conditions": {
            "check_aspa": False,
            "check_asn_type": True,
        },
        "thresholds": None,
        "whitelist": None,
        "scope": None,
        "severity": "P1",
    },
    {
        "name": "路径异常检测",
        "code": "path_anomaly_detection",
        "description": (
            "检测 AS_PATH 突变、异常中转 ASN、异常国家/区域传播、"
            "路径异常拉长与黑洞风险。"
        ),
        "rule_type": "path_anomaly",
        "enabled": True,
        "priority": 40,
        "conditions": {
            "check_path_mutation": True,
            "check_abnormal_transit": True,
            "check_path_elongation": True,
            "check_blackhole_risk": True,
            "check_abnormal_geo": False,
        },
        "thresholds": {
            "baseline_lookback_days": 7,
            "path_elongation_ratio": 2.0,
        },
        "whitelist": None,
        "scope": None,
        "severity": "P2",
    },
    {
        "name": "撤路与震荡检测",
        "code": "withdraw_flap_detection",
        "description": (
            "检测大范围撤路、频繁 announce/withdraw 震荡、"
            "前缀数突变与收敛异常。"
        ),
        "rule_type": "withdraw_flap",
        "enabled": True,
        "priority": 35,
        "conditions": {
            "time_window_minutes": 60,
        },
        "thresholds": {
            "large_scale_withdraw_points": 5,
            "frequent_flap_rate": 0.5,
            "convergence_anomaly_ratio": 3.0,
        },
        "whitelist": None,
        "scope": None,
        "severity": "P1",
    },
    {
        "name": "RPKI Invalid 传播检测",
        "code": "rpki_invalid_propagation",
        "description": (
            "统计 Invalid 路由被哪些观察点接收、传播或拒绝，"
            "反映真实影响面。"
        ),
        "rule_type": "rpki_invalid",
        "enabled": True,
        "priority": 30,
        "conditions": {
            "lookback_hours": 24,
        },
        "thresholds": {
            "propagation_critical": 10,
            "propagation_high": 5,
            "propagation_medium": 1,
        },
        "whitelist": None,
        "scope": None,
        "severity": "P1",
    },
]


async def init_default_rules(db: AsyncSession) -> int:
    """初始化默认规则（幂等）。

    遍历 ``DEFAULT_RULES``，对每个规则按 ``code`` 检查是否已存在，
    不存在则创建。已存在的规则不修改。

    Args:
        db: 异步数据库会话

    Returns:
        新创建的规则数量
    """
    created_count = 0

    for rule_def in DEFAULT_RULES:
        code = rule_def["code"]
        # 检查规则是否已存在
        stmt = select(DetectionRule).where(DetectionRule.code == code)
        result = await db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            continue

        # 创建新规则
        rule = DetectionRule(
            name=rule_def["name"],
            code=code,
            description=rule_def["description"],
            rule_type=rule_def["rule_type"],
            enabled=rule_def["enabled"],
            priority=rule_def["priority"],
            conditions=rule_def["conditions"],
            thresholds=rule_def["thresholds"],
            whitelist=rule_def["whitelist"],
            scope=rule_def["scope"],
            severity=rule_def["severity"],
        )
        db.add(rule)
        created_count += 1

    if created_count > 0:
        await db.flush()
        await db.commit()
        logger.info(
            "默认检测规则初始化完成",
            created_count=created_count,
            total=len(DEFAULT_RULES),
        )

    return created_count


__all__ = [
    "DEFAULT_RULES",
    "init_default_rules",
]
