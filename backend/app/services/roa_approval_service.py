"""ROA 审批规则管理服务。

提供审批规则的 CRUD 操作与规则匹配功能。

设计要点：
- 规则按优先级排序（数值越小优先级越高）
- 匹配条件支持：变更类型、前缀重要性、风险等级
- 高风险变更强制审批（不允许 auto_approve）
- 无匹配规则时默认使用单人审批
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.roa_change import ROAApprovalRule, ROAChangeRequest
from app.schemas.roa_change import (
    ApprovalFlowMatch,
    ROAApprovalRuleCreate,
    ROAApprovalRuleUpdate,
)

logger = get_logger("app.roa_approval_service")


# ──────────────────────────────────────────────
# 审批规则 CRUD
# ──────────────────────────────────────────────


async def create_approval_rule(
    db: AsyncSession, rule_create: ROAApprovalRuleCreate
) -> ROAApprovalRule:
    """创建审批规则。

    Args:
        db: 异步数据库会话
        rule_create: 审批规则创建参数

    Returns:
        创建的审批规则对象
    """
    rule = ROAApprovalRule(
        name=rule_create.name,
        description=rule_create.description,
        rule_type=rule_create.rule_type,
        conditions=rule_create.conditions,
        approvers=rule_create.approvers or [],
        enabled=rule_create.enabled,
        priority=rule_create.priority,
    )
    db.add(rule)
    await db.flush()
    await db.commit()
    await db.refresh(rule)

    logger.info(
        "创建审批规则",
        rule_id=rule.id,
        name=rule.name,
        rule_type=rule.rule_type,
    )
    return rule


async def get_approval_rule_by_id(
    db: AsyncSession, rule_id: int
) -> ROAApprovalRule | None:
    """根据 ID 获取审批规则。"""
    stmt = select(ROAApprovalRule).where(ROAApprovalRule.id == rule_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_approval_rules(db: AsyncSession) -> list[ROAApprovalRule]:
    """获取所有启用的审批规则（按优先级排序）。"""
    stmt = (
        select(ROAApprovalRule)
        .order_by(ROAApprovalRule.priority.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_approval_rule(
    db: AsyncSession,
    rule: ROAApprovalRule,
    rule_update: ROAApprovalRuleUpdate,
) -> ROAApprovalRule:
    """更新审批规则。

    Args:
        db: 异步数据库会话
        rule: 待更新的审批规则对象
        rule_update: 更新参数

    Returns:
        更新后的审批规则对象
    """
    update_data = rule_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(rule)

    logger.info("更新审批规则", rule_id=rule.id, fields=list(update_data.keys()))
    return rule


async def delete_approval_rule(
    db: AsyncSession, rule: ROAApprovalRule
) -> None:
    """删除审批规则。"""
    rule_id = rule.id
    await db.delete(rule)
    await db.commit()

    logger.info("删除审批规则", rule_id=rule_id)


# ──────────────────────────────────────────────
# 审批规则匹配
# ──────────────────────────────────────────────


def _match_condition(
    conditions: dict[str, Any] | None,
    field: str,
    value: str | None,
) -> bool:
    """检查单个条件是否匹配。

    条件格式为 {"field": ["value1", "value2"]}，表示 field 的值
    在指定列表中即匹配。若条件中未包含该 field，则视为不限制（匹配）。

    Args:
        conditions: 规则条件字典
        field: 待检查的字段名
        value: 待检查的值

    Returns:
        是否匹配
    """
    if conditions is None:
        return True
    if field not in conditions:
        return True
    allowed_values = conditions[field]
    if not isinstance(allowed_values, list):
        allowed_values = [allowed_values]
    if value is None:
        return False
    return value in allowed_values


async def match_approval_rule(
    db: AsyncSession, change_request: ROAChangeRequest
) -> ApprovalFlowMatch:
    """为变更请求匹配审批规则。

    匹配逻辑：
    1. 按优先级遍历所有启用的审批规则
    2. 检查规则条件是否匹配变更请求的属性
       （change_type、risk_level、prefix_importance）
    3. 高风险变更不允许 auto_approve，强制至少单人审批
    4. 无匹配规则时默认使用单人审批

    Args:
        db: 异步数据库会话
        change_request: 变更请求对象

    Returns:
        审批流程匹配结果
    """
    rules = await get_approval_rules(db)

    # 从影响评估摘要中提取前缀重要性
    prefix_importance: str | None = None
    if change_request.impact_summary:
        prefix_importance = change_request.impact_summary.get(
            "prefix_importance"
        )

    is_high_risk = change_request.risk_level in ("high", "critical")

    for rule in rules:
        if not rule.enabled:
            continue

        conditions = rule.conditions or {}

        # 检查变更类型
        if not _match_condition(
            conditions, "change_type", change_request.change_type
        ):
            continue

        # 检查风险等级
        if not _match_condition(
            conditions, "risk_level", change_request.risk_level
        ):
            continue

        # 检查前缀重要性
        if not _match_condition(
            conditions, "prefix_importance", prefix_importance
        ):
            continue

        # 高风险变更不允许自动批准
        if is_high_risk and rule.rule_type == "auto_approve":
            continue

        # 匹配成功，确定所需审批人数
        required_approvals = _get_required_approvals(rule.rule_type)

        return ApprovalFlowMatch(
            rule_id=rule.id,
            rule_name=rule.name,
            rule_type=rule.rule_type,
            required_approvals=required_approvals,
            approvers=rule.approvers or [],
            is_high_risk=is_high_risk,
            description=(
                f"匹配审批规则「{rule.name}」"
                f"（类型：{rule.rule_type}，所需审批：{required_approvals}人）"
            ),
        )

    # 无匹配规则：高风险变更强制单人审批，其他默认单人审批
    required_approvals = 1 if is_high_risk else 1
    default_type = "single_approval"

    return ApprovalFlowMatch(
        rule_id=None,
        rule_name=None,
        rule_type=default_type,
        required_approvals=required_approvals,
        approvers=[],
        is_high_risk=is_high_risk,
        description=(
            "无匹配审批规则，使用默认单人审批流程"
            + ("（高风险变更强制审批）" if is_high_risk else "")
        ),
    )


def _get_required_approvals(rule_type: str) -> int:
    """根据审批类型获取所需审批人数。

    Args:
        rule_type: 审批类型

    Returns:
        所需审批人数
    """
    if rule_type == "auto_approve":
        return 0
    elif rule_type == "single_approval":
        return 1
    elif rule_type == "dual_approval":
        return 2
    elif rule_type == "committee":
        return 3  # 委员会至少 3 人
    else:
        return 1


__all__ = [
    "create_approval_rule",
    "delete_approval_rule",
    "get_approval_rule_by_id",
    "get_approval_rules",
    "match_approval_rule",
    "update_approval_rule",
]
