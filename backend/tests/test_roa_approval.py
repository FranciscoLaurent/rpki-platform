"""ROA 变更审批工作流测试。

覆盖 ``app.services.roa_approval_service`` 的审批规则匹配逻辑：
- 规则条件匹配（change_type、risk_level、prefix_importance）
- 高风险变更强制审批（不允许 auto_approve）
- 审批类型与所需审批人数
- 无匹配规则时的默认审批流程
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.roa_change import ApprovalFlowMatch
from app.services.roa_approval_service import (
    _get_required_approvals,
    _match_condition,
    match_approval_rule,
)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _make_rule(
    rule_id: int = 1,
    name: str = "test-rule",
    rule_type: str = "single_approval",
    conditions: dict[str, Any] | None = None,
    approvers: list[int] | None = None,
    enabled: bool = True,
    priority: int = 100,
) -> MagicMock:
    """构造一个模拟的 ROAApprovalRule 对象。"""
    rule = MagicMock()
    rule.id = rule_id
    rule.name = name
    rule.rule_type = rule_type
    rule.conditions = conditions
    rule.approvers = approvers or []
    rule.enabled = enabled
    rule.priority = priority
    return rule


def _make_change_request(
    change_type: str = "create",
    risk_level: str = "low",
    impact_summary: dict[str, Any] | None = None,
) -> MagicMock:
    """构造一个模拟的 ROAChangeRequest 对象。"""
    req = MagicMock()
    req.change_type = change_type
    req.risk_level = risk_level
    req.impact_summary = impact_summary
    return req


def _make_db_mock(rules: list[Any]) -> AsyncMock:
    """构造一个模拟的 AsyncSession，get_approval_rules 返回指定规则列表。"""
    db = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rules
    result.scalars.return_value = scalars
    db.execute.return_value = result
    return db


# ──────────────────────────────────────────────
# _match_condition 单元测试
# ──────────────────────────────────────────────


def test_match_condition_none_conditions_returns_true() -> None:
    """条件为 None 时应视为不限制（匹配）。"""
    assert _match_condition(None, "change_type", "create") is True


def test_match_condition_field_not_in_conditions_returns_true() -> None:
    """条件中未包含该字段时应视为不限制（匹配）。"""
    conditions = {"risk_level": ["high"]}
    assert _match_condition(conditions, "change_type", "create") is True


def test_match_condition_value_in_list_returns_true() -> None:
    """值在允许列表中应返回 True。"""
    conditions = {"change_type": ["create", "modify"]}
    assert _match_condition(conditions, "change_type", "create") is True


def test_match_condition_value_not_in_list_returns_false() -> None:
    """值不在允许列表中应返回 False。"""
    conditions = {"change_type": ["revoke"]}
    assert _match_condition(conditions, "change_type", "create") is False


def test_match_condition_value_none_returns_false() -> None:
    """待检查值为 None 且字段在条件中时应返回 False。"""
    conditions = {"prefix_importance": ["critical"]}
    assert _match_condition(conditions, "prefix_importance", None) is False


def test_match_condition_single_value_wrapped_as_list() -> None:
    """条件值为单个字符串时应自动包装为列表。"""
    conditions = {"change_type": "create"}
    assert _match_condition(conditions, "change_type", "create") is True
    assert _match_condition(conditions, "change_type", "modify") is False


# ──────────────────────────────────────────────
# _get_required_approvals 单元测试
# ──────────────────────────────────────────────


def test_required_approvals_auto_approve() -> None:
    """auto_approve 类型应需要 0 人审批。"""
    assert _get_required_approvals("auto_approve") == 0


def test_required_approvals_single_approval() -> None:
    """single_approval 类型应需要 1 人审批。"""
    assert _get_required_approvals("single_approval") == 1


def test_required_approvals_dual_approval() -> None:
    """dual_approval 类型应需要 2 人审批。"""
    assert _get_required_approvals("dual_approval") == 2


def test_required_approvals_committee() -> None:
    """committee 类型应需要至少 3 人审批。"""
    assert _get_required_approvals("committee") == 3


def test_required_approvals_unknown_type_defaults_to_one() -> None:
    """未知类型应默认需要 1 人审批。"""
    assert _get_required_approvals("unknown_type") == 1


# ──────────────────────────────────────────────
# match_approval_rule 集成测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_match_approval_rule_auto_approve_for_low_risk() -> None:
    """低风险变更匹配 auto_approve 规则时应返回 0 人审批。"""
    rule = _make_rule(
        rule_type="auto_approve",
        conditions={"change_type": ["create"], "risk_level": ["low"]},
    )
    db = _make_db_mock([rule])
    req = _make_change_request(change_type="create", risk_level="low")

    result = await match_approval_rule(db, req)

    assert result.rule_id == rule.id
    assert result.rule_type == "auto_approve"
    assert result.required_approvals == 0
    assert result.is_high_risk is False


@pytest.mark.asyncio
async def test_match_approval_rule_high_risk_blocks_auto_approve() -> None:
    """高风险变更不应匹配 auto_approve 规则，应回退到默认。"""
    rule = _make_rule(
        rule_type="auto_approve",
        conditions={"change_type": ["create"]},
    )
    db = _make_db_mock([rule])
    req = _make_change_request(change_type="create", risk_level="high")

    result = await match_approval_rule(db, req)

    # 高风险变更跳过 auto_approve，无匹配规则，使用默认单人审批
    assert result.rule_id is None
    assert result.is_high_risk is True
    assert result.required_approvals == 1


@pytest.mark.asyncio
async def test_match_approval_rule_dual_approval_for_critical() -> None:
    """核心前缀变更匹配 dual_approval 规则时应返回 2 人审批。"""
    rule = _make_rule(
        rule_type="dual_approval",
        conditions={"prefix_importance": ["critical"]},
        approvers=[1, 2],
    )
    db = _make_db_mock([rule])
    req = _make_change_request(
        change_type="modify",
        risk_level="medium",
        impact_summary={"prefix_importance": "critical"},
    )

    result = await match_approval_rule(db, req)

    assert result.rule_id == rule.id
    assert result.rule_type == "dual_approval"
    assert result.required_approvals == 2
    assert result.approvers == [1, 2]


@pytest.mark.asyncio
async def test_match_approval_rule_no_match_uses_default() -> None:
    """无匹配规则时应使用默认单人审批。"""
    db = _make_db_mock([])
    req = _make_change_request(change_type="create", risk_level="low")

    result = await match_approval_rule(db, req)

    assert result.rule_id is None
    assert result.rule_name is None
    assert result.rule_type == "single_approval"
    assert result.required_approvals == 1


@pytest.mark.asyncio
async def test_match_approval_rule_priority_order() -> None:
    """规则应按优先级顺序匹配（数值越小优先级越高）。"""
    # 两条规则都能匹配，优先级高的应被选中
    low_priority_rule = _make_rule(
        rule_id=2,
        name="low-priority",
        rule_type="dual_approval",
        priority=200,
    )
    high_priority_rule = _make_rule(
        rule_id=1,
        name="high-priority",
        rule_type="single_approval",
        priority=10,
    )
    # 模拟 get_approval_rules 按优先级排序返回
    db = _make_db_mock([high_priority_rule, low_priority_rule])
    req = _make_change_request(change_type="create", risk_level="low")

    result = await match_approval_rule(db, req)

    assert result.rule_id == 1
    assert result.rule_name == "high-priority"


@pytest.mark.asyncio
async def test_match_approval_rule_disabled_rule_skipped() -> None:
    """禁用的规则应被跳过。"""
    disabled_rule = _make_rule(
        rule_id=1,
        rule_type="auto_approve",
        enabled=False,
    )
    db = _make_db_mock([disabled_rule])
    req = _make_change_request(change_type="create", risk_level="low")

    result = await match_approval_rule(db, req)

    # 禁用规则被跳过，无匹配，使用默认
    assert result.rule_id is None


@pytest.mark.asyncio
async def test_match_approval_rule_high_risk_default_forces_approval() -> None:
    """高风险变更无匹配规则时应强制单人审批。"""
    db = _make_db_mock([])
    req = _make_change_request(change_type="revoke", risk_level="critical")

    result = await match_approval_rule(db, req)

    assert result.is_high_risk is True
    assert result.required_approvals == 1
    assert "高风险" in result.description


@pytest.mark.asyncio
async def test_match_approval_rule_committee_type() -> None:
    """committee 类型应需要 3 人审批。"""
    rule = _make_rule(
        rule_type="committee",
        conditions={"risk_level": ["critical"]},
        approvers=[1, 2, 3, 4, 5],
    )
    db = _make_db_mock([rule])
    req = _make_change_request(change_type="modify", risk_level="critical")

    result = await match_approval_rule(db, req)

    assert result.rule_type == "committee"
    assert result.required_approvals == 3
