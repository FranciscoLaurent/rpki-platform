"""BGP 路由安全检测引擎。

包含以下检测器与规则引擎：
- hijack_detector: 源 AS 劫持与子前缀劫持检测
- moas_detector: MOAS 异常检测
- route_leak_detector: 路由泄露检测
- path_anomaly_detector: 路径异常检测
- withdraw_detector: 撤路与震荡检测
- rpki_invalid_detector: RPKI Invalid 传播统计
- risk_scorer: 风险评分模型
- rule_engine: 规则引擎
"""

from __future__ import annotations

from app.services.detection.hijack_detector import (
    detect_origin_as_hijack,
    detect_subprefix_hijack,
)
from app.services.detection.moas_detector import detect_moas
from app.services.detection.path_anomaly_detector import detect_path_anomaly
from app.services.detection.risk_scorer import calculate_risk_score
from app.services.detection.route_leak_detector import detect_route_leak
from app.services.detection.rpki_invalid_detector import (
    detect_rpki_invalid_propagation,
)
from app.services.detection.rule_engine import (
    RuleEngine,
    evaluate_announcement,
)
from app.services.detection.withdraw_detector import detect_withdraw_flap

__all__ = [
    "RuleEngine",
    "calculate_risk_score",
    "detect_moas",
    "detect_origin_as_hijack",
    "detect_path_anomaly",
    "detect_route_leak",
    "detect_rpki_invalid_propagation",
    "detect_subprefix_hijack",
    "detect_withdraw_flap",
    "evaluate_announcement",
]
