"""规则引擎。

加载启用的检测规则，对 BGP 公告执行匹配的检测器，生成告警并计算风险评分，
最后发送 Kafka 事件。

规则执行流程：
接收公告 → 匹配规则类型 → 检查白名单 → 检查范围 → 执行检测器
→ 生成告警 → 计算评分 → 发送 Kafka 事件
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.kafka import KafkaService, Topics
from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.detection import Alert, DetectionRule
from app.schemas.detection import DetectionResult
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
from app.services.detection.withdraw_detector import detect_withdraw_flap

logger = get_logger("app.detection.rule_engine")


# 规则类型 → 检测器函数映射
DETECTOR_MAPPING = {
    "hijack": detect_origin_as_hijack,
    "subprefix_hijack": detect_subprefix_hijack,
    "moas": detect_moas,
    "route_leak": detect_route_leak,
    "path_anomaly": detect_path_anomaly,
}


class RuleEngine:
    """规则引擎。

    加载启用的检测规则，对 BGP 公告执行匹配的检测器，生成告警并计算
    风险评分，最后发送 Kafka 事件。
    """

    def __init__(self, db: AsyncSession) -> None:
        """初始化规则引擎。

        Args:
            db: 异步数据库会话
        """
        self.db = db
        self.rules: list[DetectionRule] = []

    async def load_rules(self) -> None:
        """加载所有启用的检测规则，按优先级排序。"""
        stmt = (
            select(DetectionRule)
            .where(DetectionRule.enabled.is_(True))
            .order_by(DetectionRule.priority.asc())
        )
        result = await self.db.execute(stmt)
        self.rules = list(result.scalars().all())
        logger.info(
            "规则引擎加载规则完成", count=len(self.rules)
        )

    async def evaluate(
        self,
        announcement: BGPAnnouncement,
        kafka: KafkaService | None = None,
    ) -> list[DetectionResult]:
        """评估 BGP 公告，触发匹配的规则。

        Args:
            announcement: BGP 公告对象
            kafka: Kafka 服务（可选，用于发送告警事件）

        Returns:
            检测结果列表
        """
        if not self.rules:
            await self.load_rules()

        results: list[DetectionResult] = []
        for rule in self.rules:
            try:
                result = await self.apply_rule(rule, announcement)
                if result is not None:
                    results.append(result)
                    # 检测到异常时生成告警
                    if result.is_detected:
                        alert = await self._create_alert_from_result(
                            rule, announcement, result
                        )
                        if alert is not None:
                            # 计算风险评分
                            await calculate_risk_score(self.db, alert)
                            await self.db.commit()
                            # 发送 Kafka 事件
                            if kafka is not None:
                                self._send_alert_event(kafka, alert, result)
            except Exception as e:
                logger.error(
                    "规则执行失败",
                    rule_id=rule.id,
                    rule_code=rule.code,
                    error=str(e),
                )
                continue

        return results

    async def apply_rule(
        self,
        rule: DetectionRule,
        announcement: BGPAnnouncement,
    ) -> DetectionResult | None:
        """应用单个规则。

        Args:
            rule: 检测规则
            announcement: BGP 公告对象

        Returns:
            检测结果（规则不适用时返回 None）
        """
        # 1. 检查白名单
        if self.check_whitelist(rule, announcement):
            return None

        # 2. 检查生效范围
        if not self.check_scope(rule, announcement):
            return None

        # 3. 执行对应检测器
        # 标准检测器签名：(db, announcement)
        detector = DETECTOR_MAPPING.get(rule.rule_type)
        if detector is not None:
            result = await detector(self.db, announcement)
        else:
            # 特殊检测器：签名不同，需特殊处理
            result = await self._run_special_detector(rule, announcement)
            if result is None:
                logger.warning(
                    "未找到规则类型对应的检测器",
                    rule_type=rule.rule_type,
                    rule_id=rule.id,
                )
                return None

        # 4. 应用规则阈值（覆盖检测器默认 severity）
        if rule.thresholds:
            result = self._apply_thresholds(rule, result)

        return result

    async def _run_special_detector(
        self,
        rule: DetectionRule,
        announcement: BGPAnnouncement,
    ) -> DetectionResult | None:
        """执行签名特殊的检测器。

        ``withdraw_flap`` 与 ``rpki_invalid`` 检测器的签名不是
        ``(db, announcement)``，需特殊处理。

        Args:
            rule: 检测规则
            announcement: BGP 公告对象

        Returns:
            检测结果，规则类型不支持时返回 None
        """
        # 从规则条件中提取参数，提供默认值
        conditions = rule.conditions or {}

        if rule.rule_type == "withdraw_flap":
            time_window = conditions.get("time_window_minutes", 60)
            return await detect_withdraw_flap(
                self.db, announcement.prefix, time_window
            )

        if rule.rule_type == "rpki_invalid":
            lookback_hours = conditions.get("lookback_hours", 24)
            return await detect_rpki_invalid_propagation(
                self.db, announcement.prefix, lookback_hours
            )

        return None

    def check_whitelist(
        self, rule: DetectionRule, announcement: BGPAnnouncement
    ) -> bool:
        """检查白名单。

        白名单配置示例：
        ```
        {
            "prefixes": ["192.168.1.0/24"],
            "origin_asns": [64512],
            "observation_points": [1, 2]
        }
        ```

        Args:
            rule: 检测规则
            announcement: BGP 公告对象

        Returns:
            True 表示命中白名单（跳过检测），False 表示继续检测
        """
        whitelist = rule.whitelist
        if not whitelist:
            return False

        # 前缀白名单
        whitelist_prefixes = whitelist.get("prefixes", [])
        if whitelist_prefixes and announcement.prefix in whitelist_prefixes:
            return True

        # 前缀包含关系白名单（白名单前缀包含公告前缀）
        if whitelist_prefixes:
            try:
                ann_net = ipaddress.ip_network(
                    announcement.prefix, strict=False
                )
                for wl_prefix in whitelist_prefixes:
                    try:
                        wl_net = ipaddress.ip_network(wl_prefix, strict=False)
                        if (
                            ann_net.version == wl_net.version
                            and ann_net.subnet_of(wl_net)
                        ):
                            return True
                    except ValueError:
                        continue
            except ValueError:
                pass

        # origin AS 白名单
        whitelist_asns = whitelist.get("origin_asns", [])
        if (
            whitelist_asns
            and announcement.origin_as is not None
            and announcement.origin_as in whitelist_asns
        ):
            return True

        # 观察点白名单
        whitelist_points = whitelist.get("observation_points", [])
        if (
            whitelist_points
            and announcement.observation_point_id is not None
            and announcement.observation_point_id in whitelist_points
        ):
            return True

        return False

    def check_scope(
        self, rule: DetectionRule, announcement: BGPAnnouncement
    ) -> bool:
        """检查生效范围。

        生效范围配置示例：
        ```
        {
            "prefixes": ["192.168.0.0/16"],  # 仅对这些前缀生效
            "origin_asns": [64512],          # 仅对这些 origin AS 生效
            "prefix_lengths": {"min": 8, "max": 24}  # 前缀长度范围
        }
        ```

        若 scope 为空或字段为空，表示不限制（全部生效）。

        Args:
            rule: 检测规则
            announcement: BGP 公告对象

        Returns:
            True 表示在生效范围内，False 表示不在
        """
        scope = rule.scope
        if not scope:
            return True

        # 前缀范围
        scope_prefixes = scope.get("prefixes", [])
        if scope_prefixes:
            try:
                ann_net = ipaddress.ip_network(
                    announcement.prefix, strict=False
                )
                in_scope = False
                for sc_prefix in scope_prefixes:
                    try:
                        sc_net = ipaddress.ip_network(sc_prefix, strict=False)
                        if (
                            ann_net.version == sc_net.version
                            and (
                                ann_net.subnet_of(sc_net)
                                or ann_net == sc_net
                            )
                        ):
                            in_scope = True
                            break
                    except ValueError:
                        continue
                if not in_scope:
                    return False
            except ValueError:
                return False

        # origin AS 范围
        scope_asns = scope.get("origin_asns", [])
        if (
            scope_asns
            and (
                announcement.origin_as is None
                or announcement.origin_as not in scope_asns
            )
        ):
            return False

        # 前缀长度范围
        length_range = scope.get("prefix_lengths")
        if length_range:
            min_len = length_range.get("min")
            max_len = length_range.get("max")
            if min_len is not None and announcement.prefix_length < min_len:
                return False
            if max_len is not None and announcement.prefix_length > max_len:
                return False

        return True

    def _apply_thresholds(
        self, rule: DetectionRule, result: DetectionResult
    ) -> DetectionResult:
        """应用规则阈值配置。

        若规则配置了 severity 覆盖，则使用规则的 severity。
        """
        # 规则自身的 severity 优先于检测器默认值
        result.severity = rule.severity
        return result

    async def _create_alert_from_result(
        self,
        rule: DetectionRule,
        announcement: BGPAnnouncement,
        result: DetectionResult,
    ) -> Alert | None:
        """根据检测结果创建告警。

        Args:
            rule: 触发的规则
            announcement: BGP 公告对象
            result: 检测结果

        Returns:
            创建的告警对象（已持久化），失败返回 None
        """
        now = datetime.now(timezone.utc)
        alert = Alert(
            rule_id=rule.id,
            alert_type=result.alert_type,
            severity=result.severity,
            prefix=announcement.prefix,
            origin_as=announcement.origin_as,
            as_path=announcement.as_path,
            observation_point_id=announcement.observation_point_id,
            title=result.description[:500],
            description=result.description,
            evidence=result.evidence,
            risk_score=result.risk_score,
            confidence=result.confidence,
            status="new",
            is_benign_conflict=False,
            first_seen_at=now,
            last_seen_at=now,
            tenant_id=rule.tenant_id,
        )
        self.db.add(alert)
        await self.db.flush()
        logger.info(
            "告警已创建",
            alert_id=alert.id,
            alert_type=alert.alert_type,
            prefix=alert.prefix,
            severity=alert.severity,
        )
        return alert

    def _send_alert_event(
        self,
        kafka: KafkaService,
        alert: Alert,
        result: DetectionResult,
    ) -> None:
        """发送告警事件到 Kafka。"""
        event = {
            "alert_id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "prefix": alert.prefix,
            "origin_as": alert.origin_as,
            "title": alert.title,
            "description": alert.description,
            "risk_score": alert.risk_score,
            "confidence": alert.confidence,
            "evidence": result.evidence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        kafka.send_event(
            topic=Topics.ALERT_EVENTS,
            key=str(alert.id),
            value=event,
        )


async def evaluate_announcement(
    db: AsyncSession,
    announcement: BGPAnnouncement,
    kafka: KafkaService | None = None,
    rule_types: list[str] | None = None,
) -> list[DetectionResult]:
    """评估单条 BGP 公告的便捷函数。

    Args:
        db: 异步数据库会话
        announcement: BGP 公告对象
        kafka: Kafka 服务（可选）
        rule_types: 限定的规则类型列表（为空则全部执行）

    Returns:
        检测结果列表
    """
    engine = RuleEngine(db)
    await engine.load_rules()

    # 按规则类型过滤
    if rule_types:
        engine.rules = [
            r for r in engine.rules if r.rule_type in rule_types
        ]

    return await engine.evaluate(announcement, kafka=kafka)


__all__ = [
    "RuleEngine",
    "evaluate_announcement",
]
