"""处置建议与执行服务。

根据事件的风险评分、告警类型与证据，生成针对性的处置建议动作，
并支持处置动作的创建、查询、更新与执行记录。

处置动作类型涵盖：
- 联系异常 ASN/上游（contact_asn/contact_upstream）
- 修正 ROA（fix_roa）
- 调整策略（adjust_policy）
- 发布更具体合法前缀（announce_legitimate_prefix）
- 清洗联动（scrubber_coordination）
- 客户通知（customer_notification）
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.detection import Alert, Incident, RiskScore
from app.models.forensics import (
    CaseLibrary,
    ForensicEvidence,
    IncidentReview,
    RemediationAction,
)
from app.schemas.forensics import (
    RemediationActionCreate,
    RemediationExecuteRequest,
    RemediationActionQueryParams,
    RemediationActionUpdate,
    RemediationSuggestionResult,
)
from app.services import incident_service

logger = get_logger("app.remediation_service")


async def generate_remediation_suggestions(
    db: AsyncSession,
    incident_id: int,
) -> RemediationSuggestionResult:
    """为事件生成处置建议动作。

    根据事件的风险评分、告警类型与受影响资产，自动生成针对性的处置建议。
    生成的建议动作标记 ``is_auto_generated=True``，状态为 ``pending``。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID

    Returns:
        处置建议生成结果
    """
    # 查询事件
    incident = await _get_incident(db, incident_id)
    if incident is None:
        return RemediationSuggestionResult(
            incident_id=incident_id,
            suggestions=[],
            summary=f"事件 ID {incident_id} 不存在",
        )

    # 查询事件关联的风险评分
    risk_score = await _get_incident_risk_score(db, incident_id)

    # 查询事件关联的告警
    alerts = await _get_incident_alerts(db, incident_id)

    # 生成建议动作
    suggestions_data = _build_suggestions(
        incident, alerts, risk_score
    )

    # 持久化建议动作
    created_actions: list[RemediationAction] = []
    for suggestion in suggestions_data:
        action = RemediationAction(
            incident_id=incident_id,
            action_type=suggestion["action_type"],
            title=suggestion["title"],
            description=suggestion.get("description"),
            target=suggestion.get("target"),
            priority=suggestion.get("priority", "medium"),
            status="pending",
            is_auto_generated=True,
            tenant_id=incident.tenant_id,
        )
        db.add(action)
        created_actions.append(action)

    if created_actions:
        await db.flush()

    # 构建总结
    summary = _build_summary(incident, created_actions, risk_score)

    logger.info(
        "处置建议已生成",
        incident_id=incident_id,
        suggestion_count=len(created_actions),
    )

    return RemediationSuggestionResult(
        incident_id=incident_id,
        suggestions=created_actions,
        summary=summary,
    )


# ──────────────────────────────────────────────
# 处置动作 CRUD
# ──────────────────────────────────────────────


async def create_action(
    db: AsyncSession, action_data: RemediationActionCreate
) -> RemediationAction:
    """创建处置动作。"""
    action = RemediationAction(
        incident_id=action_data.incident_id,
        action_type=action_data.action_type,
        title=action_data.title,
        description=action_data.description,
        target=action_data.target,
        priority=action_data.priority,
        status=action_data.status,
        is_auto_generated=action_data.is_auto_generated,
        tenant_id=action_data.tenant_id,
    )
    db.add(action)
    await db.flush()
    logger.info(
        "处置动作已创建",
        action_id=action.id,
        action_type=action.action_type,
        incident_id=action.incident_id,
    )
    return action


async def get_action(
    db: AsyncSession, action_id: int
) -> RemediationAction | None:
    """根据 ID 获取处置动作。"""
    stmt = select(RemediationAction).where(RemediationAction.id == action_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_actions(
    db: AsyncSession,
    query_params: RemediationActionQueryParams,
    skip: int = 0,
    limit: int = 50,
) -> list[RemediationAction]:
    """查询处置动作列表。"""
    stmt = select(RemediationAction)

    if query_params.incident_id is not None:
        stmt = stmt.where(
            RemediationAction.incident_id == query_params.incident_id
        )
    if query_params.action_type:
        stmt = stmt.where(
            RemediationAction.action_type == query_params.action_type
        )
    if query_params.status:
        stmt = stmt.where(RemediationAction.status == query_params.status)
    if query_params.priority:
        stmt = stmt.where(
            RemediationAction.priority == query_params.priority
        )
    if query_params.start_time:
        stmt = stmt.where(
            RemediationAction.created_at >= query_params.start_time
        )
    if query_params.end_time:
        stmt = stmt.where(
            RemediationAction.created_at <= query_params.end_time
        )

    stmt = stmt.order_by(
        RemediationAction.created_at.desc()
    ).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_actions(
    db: AsyncSession, query_params: RemediationActionQueryParams
) -> int:
    """统计处置动作数量。"""
    stmt = select(func.count(RemediationAction.id))

    if query_params.incident_id is not None:
        stmt = stmt.where(
            RemediationAction.incident_id == query_params.incident_id
        )
    if query_params.action_type:
        stmt = stmt.where(
            RemediationAction.action_type == query_params.action_type
        )
    if query_params.status:
        stmt = stmt.where(RemediationAction.status == query_params.status)
    if query_params.priority:
        stmt = stmt.where(
            RemediationAction.priority == query_params.priority
        )
    if query_params.start_time:
        stmt = stmt.where(
            RemediationAction.created_at >= query_params.start_time
        )
    if query_params.end_time:
        stmt = stmt.where(
            RemediationAction.created_at <= query_params.end_time
        )

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_action(
    db: AsyncSession,
    action: RemediationAction,
    action_update: RemediationActionUpdate,
) -> RemediationAction:
    """更新处置动作。"""
    update_data = action_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(action, field, value)

    await db.flush()
    logger.info(
        "处置动作已更新",
        action_id=action.id,
        fields=list(update_data.keys()),
    )
    return action


async def execute_action(
    db: AsyncSession,
    action_id: int,
    request: RemediationExecuteRequest,
    executed_by: int | None = None,
) -> RemediationAction | None:
    """执行处置动作（记录执行结果）。

    注意：本方法仅记录执行结果，不实际执行处置操作。
    实际的处置执行（如联系 ASN、修正 ROA 等）需要人工或外部系统完成。

    Args:
        db: 异步数据库会话
        action_id: 处置动作 ID
        request: 执行请求
        executed_by: 执行人用户 ID

    Returns:
        更新后的处置动作对象，动作不存在返回 None
    """
    action = await get_action(db, action_id)
    if action is None:
        return None

    now = datetime.now(timezone.utc)
    action.status = request.status
    action.executed_by = executed_by
    action.executed_at = now
    if request.result is not None:
        action.result = request.result
    if request.result_details is not None:
        action.result_details = request.result_details

    await db.flush()
    logger.info(
        "处置动作已执行",
        action_id=action_id,
        status=request.status,
        executed_by=executed_by,
    )
    return action


async def get_actions_by_incident(
    db: AsyncSession, incident_id: int
) -> list[RemediationAction]:
    """获取事件关联的全部处置动作。"""
    stmt = (
        select(RemediationAction)
        .where(RemediationAction.incident_id == incident_id)
        .order_by(RemediationAction.created_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# 建议动作生成逻辑
# ──────────────────────────────────────────────


def _build_suggestions(
    incident: Incident,
    alerts: list[Alert],
    risk_score: RiskScore | None,
) -> list[dict[str, Any]]:
    """根据事件、告警与风险评分构建处置建议动作列表。"""
    suggestions: list[dict[str, Any]] = []

    # 从风险评分获取建议动作
    if risk_score is not None and risk_score.recommended_actions:
        for rec in risk_score.recommended_actions:
            suggestion = _convert_recommended_action_to_suggestion(
                rec, incident, alerts
            )
            if suggestion is not None:
                suggestions.append(suggestion)

    # 根据告警类型补充建议
    alert_types = {a.alert_type for a in alerts}
    for alert_type in alert_types:
        type_suggestions = _build_type_specific_suggestions(
            alert_type, incident, alerts
        )
        suggestions.extend(type_suggestions)

    # 去重（按 action_type + target 去重）
    seen: set[tuple[str, str | None]] = set()
    unique_suggestions: list[dict[str, Any]] = []
    for s in suggestions:
        key = (s["action_type"], s.get("target"))
        if key in seen:
            continue
        seen.add(key)
        unique_suggestions.append(s)

    return unique_suggestions


def _convert_recommended_action_to_suggestion(
    rec: dict[str, Any],
    incident: Incident,
    alerts: list[Alert],
) -> dict[str, Any] | None:
    """将风险评分的建议动作转换为处置动作建议。"""
    action_text = rec.get("action", "")
    priority = rec.get("priority", "medium")
    reason = rec.get("reason", "")

    # 优先级映射
    priority_map = {
        "immediate": "immediate",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    mapped_priority = priority_map.get(priority, "medium")

    # 根据 action 文本推断动作类型
    if "联系" in action_text and ("origin" in action_text or "AS" in action_text):
        target_asn = _extract_target_asn(incident, alerts)
        return {
            "action_type": "contact_asn",
            "title": action_text,
            "description": reason,
            "target": f"AS{target_asn}" if target_asn else None,
            "priority": mapped_priority,
        }
    if "上游" in action_text or "提供商" in action_text:
        return {
            "action_type": "contact_upstream",
            "title": action_text,
            "description": reason,
            "target": None,
            "priority": mapped_priority,
        }
    if "RPKI" in action_text or "ROV" in action_text or "过滤" in action_text:
        return {
            "action_type": "adjust_policy",
            "title": action_text,
            "description": reason,
            "target": "边界路由器",
            "priority": mapped_priority,
        }
    if "ROA" in action_text and "修正" in action_text:
        return {
            "action_type": "fix_roa",
            "title": action_text,
            "description": reason,
            "target": None,
            "priority": mapped_priority,
        }
    if "调查" in action_text or "确认" in action_text:
        return {
            "action_type": "contact_asn",
            "title": action_text,
            "description": reason,
            "target": None,
            "priority": mapped_priority,
        }
    if "观察" in action_text or "监控" in action_text:
        return {
            "action_type": "customer_notification",
            "title": action_text,
            "description": reason,
            "target": None,
            "priority": mapped_priority,
        }

    # 默认归为 other
    return None


def _build_type_specific_suggestions(
    alert_type: str,
    incident: Incident,
    alerts: list[Alert],
) -> list[dict[str, Any]]:
    """根据告警类型生成特定的处置建议。"""
    suggestions: list[dict[str, Any]] = []
    target_asn = _extract_target_asn(incident, alerts)
    target_str = f"AS{target_asn}" if target_asn else None

    if alert_type in ("hijack", "subprefix_hijack"):
        # 劫持类：联系异常 ASN、联系上游、修正 ROA、发布更具体合法前缀
        suggestions.append({
            "action_type": "contact_asn",
            "title": f"联系异常 ASN {target_str or ''} 的 NOC，要求撤回异常公告",
            "description": "源 AS 劫持/子前缀劫持，需立即联系异常 ASN 撤回",
            "target": target_str,
            "priority": "immediate",
        })
        suggestions.append({
            "action_type": "contact_upstream",
            "title": "通知上游提供商过滤异常前缀路由",
            "description": "防止异常路由进一步传播",
            "target": None,
            "priority": "high",
        })
        suggestions.append({
            "action_type": "fix_roa",
            "title": "检查并修正 ROA 授权",
            "description": "确认 ROA 配置正确，必要时更新授权",
            "target": None,
            "priority": "high",
        })
        suggestions.append({
            "action_type": "announce_legitimate_prefix",
            "title": "发布更具体的合法前缀以吸引流量",
            "description": "通过更具体前缀公告夺回流量控制权",
            "target": None,
            "priority": "high",
        })

    elif alert_type == "moas":
        # MOAS：联系异常 ASN、客户通知
        suggestions.append({
            "action_type": "contact_asn",
            "title": f"核实 MOAS 是否为授权多 origin 或 Anycast",
            "description": "联系相关 ASN 确认多 origin 是否为授权变更",
            "target": target_str,
            "priority": "medium",
        })
        suggestions.append({
            "action_type": "customer_notification",
            "title": "通知客户核实 MOAS 来源",
            "description": "MOAS 可能影响客户业务，需通知客户确认",
            "target": None,
            "priority": "medium",
        })

    elif alert_type == "route_leak":
        # 路由泄露：调整策略、联系上游
        suggestions.append({
            "action_type": "adjust_policy",
            "title": "检查并调整 BGP 路由策略",
            "description": "路由泄露通常源于策略配置错误，需调整 import/export 策略",
            "target": "边界路由器",
            "priority": "high",
        })
        suggestions.append({
            "action_type": "contact_upstream",
            "title": "协调上游撤回泄露的路由",
            "description": "联系上游提供商过滤泄露路由",
            "target": None,
            "priority": "high",
        })

    elif alert_type == "rpki_invalid":
        # RPKI Invalid：调整策略、修正 ROA
        suggestions.append({
            "action_type": "adjust_policy",
            "title": "在边界路由器部署 RPKI ROV 过滤",
            "description": "拒绝 RPKI Invalid 路由",
            "target": "边界路由器",
            "priority": "high",
        })
        suggestions.append({
            "action_type": "fix_roa",
            "title": "检查 ROA 配置是否正确",
            "description": "确认 ROA 授权的 origin AS 与 maxLength 正确",
            "target": None,
            "priority": "medium",
        })

    elif alert_type == "withdraw_flap":
        # 撤路震荡：联系 ASN、客户通知
        suggestions.append({
            "action_type": "contact_asn",
            "title": f"联系 AS{target_asn or ''} 排查前缀稳定性",
            "description": "频繁震荡可能影响业务，需联系 origin AS 排查",
            "target": target_str,
            "priority": "medium",
        })

    elif alert_type == "path_anomaly":
        # 路径异常：调整策略
        suggestions.append({
            "action_type": "adjust_policy",
            "title": "检查 AS_PATH 异常并调整路由策略",
            "description": "路径异常可能源于策略配置或中转 AS 问题",
            "target": "边界路由器",
            "priority": "medium",
        })

    # 高风险事件补充清洗联动建议
    if incident.severity in ("P0", "P1"):
        suggestions.append({
            "action_type": "scrubber_coordination",
            "title": "协调 DDoS 清洗商联动处置",
            "description": "高风险事件，需协调清洗商准备联动",
            "target": None,
            "priority": "high",
        })

    return suggestions


def _extract_target_asn(
    incident: Incident, alerts: list[Alert]
) -> int | None:
    """从事件或告警中提取目标 ASN。"""
    if incident.affected_asns:
        return incident.affected_asns[0]
    for alert in alerts:
        if alert.origin_as is not None:
            return alert.origin_as
    return None


def _build_summary(
    incident: Incident,
    actions: list[RemediationAction],
    risk_score: RiskScore | None,
) -> str:
    """构建处置建议总结。"""
    parts: list[str] = []
    parts.append(f"事件 {incident.id}（{incident.title}）处置建议：")
    parts.append(f"严重等级：{incident.severity}")
    if risk_score is not None:
        parts.append(f"风险评分：{risk_score.total_score}")
        parts.append(f"置信度：{risk_score.confidence}")
    parts.append(f"建议动作数：{len(actions)}")

    # 按优先级分组统计
    priority_counts: dict[str, int] = {}
    for action in actions:
        priority_counts[action.priority] = (
            priority_counts.get(action.priority, 0) + 1
        )
    if priority_counts:
        priority_str = "、".join(
            f"{p}级 {c} 项" for p, c in priority_counts.items()
        )
        parts.append(f"优先级分布：{priority_str}")

    return "\n".join(parts)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _get_incident(
    db: AsyncSession, incident_id: int
) -> Incident | None:
    """获取事件。"""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_incident_risk_score(
    db: AsyncSession, incident_id: int
) -> RiskScore | None:
    """获取事件关联的最新风险评分。"""
    stmt = (
        select(RiskScore)
        .where(RiskScore.incident_id == incident_id)
        .order_by(RiskScore.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _get_incident_alerts(
    db: AsyncSession, incident_id: int
) -> list[Alert]:
    """获取事件关联的告警。"""
    stmt = (
        select(Alert)
        .where(Alert.incident_id == incident_id)
        .order_by(Alert.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# 事件关闭与复盘
# ──────────────────────────────────────────────


async def close_incident_with_review(
    db: AsyncSession,
    incident_id: int,
    root_cause: str,
    resolution: str,
    reviewer_id: int,
    lessons_learned: str | None = None,
    improvements: str | None = None,
    save_to_case_library: bool = False,
) -> Incident:
    """关闭事件并完成复盘。

    一次性完成：
    1. 确认恢复（检查当前 BGP 状态）
    2. 记录根因与处置结论
    3. 保留证据与操作链（timeline）
    4. 沉淀规则和案例库（将事件模式存入知识库 JSON）

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID
        root_cause: 根因分析
        resolution: 处置结论
        reviewer_id: 复盘人用户 ID
        lessons_learned: 经验教训
        improvements: 改进措施
        save_to_case_library: 是否沉淀到案例库

    Returns:
        更新后的事件对象

    Raises:
        ValueError: 事件不存在时抛出
    """
    now = datetime.now(timezone.utc)

    # 查询事件
    incident = await _get_incident(db, incident_id)
    if incident is None:
        raise ValueError(f"事件 ID {incident_id} 不存在")

    # 1. 确认恢复（检查当前 BGP 状态）
    recovery_status = await _check_recovery_status(db, incident)

    # 2. 记录根因与处置结论，关闭事件
    incident = await incident_service.close_incident(
        db, incident_id, resolution
    )
    if incident is None:
        raise ValueError(f"事件 ID {incident_id} 不存在")

    incident.root_cause = root_cause
    incident.resolved_at = now

    # 3. 保留证据与操作链（timeline）
    operation_chain = await _build_operation_chain(db, incident_id)

    # 在 timeline 追加复盘记录
    timeline = incident.timeline or []
    timeline.append(
        {
            "timestamp": now.isoformat(),
            "event_type": "reviewed",
            "description": (
                f"事件复盘完成：根因={root_cause}，"
                f"恢复状态={recovery_status['status']}"
            ),
            "operator": reviewer_id,
        }
    )
    incident.timeline = timeline

    # 4. 沉淀规则和案例库（将事件模式存入复盘记录的知识库 JSON）
    rule_updates = _build_rule_updates(incident, root_cause)

    # 创建复盘记录
    review = IncidentReview(
        incident_id=incident_id,
        root_cause=root_cause,
        lessons_learned=lessons_learned,
        improvements=improvements,
        review_summary=resolution,
        reviewed_by=reviewer_id,
        reviewed_at=now,
        evidence_preserved=True,
        operation_chain=operation_chain,
        rule_updates=rule_updates,
        tenant_id=incident.tenant_id,
    )
    db.add(review)
    await db.flush()

    # 可选：沉淀到案例库
    if save_to_case_library:
        await _create_case_from_incident(
            db, incident, root_cause, resolution, reviewer_id
        )

    await db.flush()

    logger.info(
        "事件关闭与复盘完成",
        incident_id=incident_id,
        review_id=review.id,
        recovery_status=recovery_status["status"],
    )
    return incident


async def _check_recovery_status(
    db: AsyncSession, incident: Incident
) -> dict[str, Any]:
    """检查事件恢复状态（检查当前 BGP 公告状态）。

    查询事件受影响前缀在近期的 BGP 公告，判断是否仍有异常公告。
    """
    prefixes = list(incident.affected_prefixes or [])
    if not prefixes:
        return {"status": "unknown", "reason": "无受影响前缀"}

    # 查询近 1 小时的 BGP 公告
    since = datetime.now(timezone.utc) - timedelta(hours=1)
    stmt = (
        select(func.count(BGPAnnouncement.id))
        .where(BGPAnnouncement.prefix.in_(prefixes))
        .where(BGPAnnouncement.timestamp >= since)
    )
    result = await db.execute(stmt)
    recent_count = int(result.scalar_one() or 0)

    if recent_count == 0:
        return {
            "status": "recovered",
            "reason": "近期无异常 BGP 公告",
            "recent_announcement_count": 0,
        }
    return {
        "status": "monitoring",
        "reason": f"近期仍有 {recent_count} 条 BGP 公告，持续观察",
        "recent_announcement_count": recent_count,
    }


async def _build_operation_chain(
    db: AsyncSession, incident_id: int
) -> list[dict[str, Any]]:
    """构建事件的操作链（处置动作与证据时间线）。"""
    chain: list[dict[str, Any]] = []

    # 处置动作
    action_stmt = (
        select(RemediationAction)
        .where(RemediationAction.incident_id == incident_id)
        .order_by(RemediationAction.created_at.asc())
    )
    action_result = await db.execute(action_stmt)
    actions = list(action_result.scalars().all())
    for action in actions:
        chain.append(
            {
                "action_id": action.id,
                "action_type": action.action_type,
                "title": action.title,
                "status": action.status,
                "executed_by": action.executed_by,
                "executed_at": action.executed_at.isoformat()
                if action.executed_at
                else None,
                "result": action.result,
            }
        )

    # 证据采集节点
    evidence_stmt = (
        select(ForensicEvidence)
        .where(ForensicEvidence.incident_id == incident_id)
        .order_by(ForensicEvidence.collected_at.asc())
    )
    evidence_result = await db.execute(evidence_stmt)
    evidences = list(evidence_result.scalars().all())
    for evidence in evidences:
        chain.append(
            {
                "evidence_id": evidence.id,
                "evidence_type": evidence.evidence_type,
                "title": evidence.title,
                "collected_at": evidence.collected_at.isoformat(),
                "is_auto_collected": evidence.is_auto_collected,
            }
        )

    # 按时间排序
    def _get_time(item: dict[str, Any]) -> str:
        return item.get("executed_at") or item.get("collected_at") or ""

    chain.sort(key=_get_time)
    return chain


def _build_rule_updates(
    incident: Incident, root_cause: str
) -> list[dict[str, Any]]:
    """根据事件模式沉淀规则更新建议。

    将事件的关键特征（告警类型、受影响前缀/ASN、根因）转化为
    规则更新建议，存入复盘记录的 ``rule_updates`` JSON 字段。
    """
    rule_updates: list[dict[str, Any]] = []
    rule_updates.append(
        {
            "type": "case_pattern",
            "incident_id": incident.id,
            "severity": incident.severity,
            "affected_prefixes": list(incident.affected_prefixes or []),
            "affected_asns": list(incident.affected_asns or []),
            "root_cause": root_cause,
            "suggestion": "根据本事件特征优化检测规则阈值与白名单",
        }
    )
    return rule_updates


async def _create_case_from_incident(
    db: AsyncSession,
    incident: Incident,
    root_cause: str,
    resolution: str,
    created_by: int,
) -> CaseLibrary:
    """从事件沉淀案例库记录。"""
    case = CaseLibrary(
        title=f"案例：{incident.title}",
        description=incident.description,
        root_cause=root_cause,
        remediation_plan=resolution,
        tags=[incident.severity],
        severity=incident.severity,
        incident_ids=[incident.id],
        affected_prefixes=incident.affected_prefixes,
        affected_asns=incident.affected_asns,
        is_published=False,
        created_by=created_by,
        tenant_id=incident.tenant_id,
    )
    db.add(case)
    await db.flush()
    logger.info(
        "案例已从事件沉淀",
        case_id=case.id,
        incident_id=incident.id,
    )
    return case


__all__ = [
    "close_incident_with_review",
    "count_actions",
    "create_action",
    "execute_action",
    "generate_remediation_suggestions",
    "get_action",
    "get_actions",
    "get_actions_by_incident",
    "update_action",
]
