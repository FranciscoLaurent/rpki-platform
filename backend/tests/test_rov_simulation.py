"""ROV 策略模拟与 ROA 变更影响评估测试。

覆盖 ``app.services.rov_simulation_service`` 的核心功能：
- ROV 策略模拟（drop_invalid / de-preference_invalid / monitor_only）
- ROA 变更影响评估
- 分阶段部署建议生成
- 风险评估
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.rov import (
    AffectedPrefix,
    ROAChangeSimulationRequest,
    ROVSimulationRequest,
    ROVSimulationScope,
)
from app.services.rov_simulation_service import (
    _compute_simulated_status,
    _get_covering_prefixes,
    _get_more_specific_prefixes,
    _validate_against_vrps,
    assess_simulation_risk,
    check_high_risk_block,
    generate_deployment_recommendations,
    simulate_roa_change,
    simulate_rov_policy,
)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _make_vrp(
    prefix: str,
    prefix_length: int,
    origin_as: int,
    max_length: int | None = None,
    validation_status: str = "valid",
    roa_id: int | None = 1,
) -> MagicMock:
    """构造一个模拟的 VRP 对象。"""
    vrp = MagicMock()
    vrp.prefix = prefix
    vrp.prefix_length = prefix_length
    vrp.origin_as = origin_as
    vrp.max_length = max_length
    vrp.validation_status = validation_status
    vrp.roa_id = roa_id
    return vrp


def _make_announcement(
    prefix: str,
    origin_as: int,
    prefix_length: int,
    address_family: int = 4,
    rpki_validation_status: str | None = None,
    rpki_invalid_reason: str | None = None,
    observation_point_id: int | None = 1,
) -> MagicMock:
    """构造一个模拟的 BGPAnnouncement 对象。"""
    ann = MagicMock()
    ann.prefix = prefix
    ann.origin_as = origin_as
    ann.prefix_length = prefix_length
    ann.address_family = address_family
    ann.rpki_validation_status = rpki_validation_status
    ann.rpki_invalid_reason = rpki_invalid_reason
    ann.observation_point_id = observation_point_id
    ann.timestamp = datetime.now(timezone.utc)
    return ann


def _make_roa(
    roa_id: int,
    prefix: str,
    prefix_length: int,
    origin_as: int,
    max_length: int | None = None,
    prefix_family: int = 4,
    status: str = "valid",
) -> MagicMock:
    """构造一个模拟的 ROA 对象。"""
    roa = MagicMock()
    roa.id = roa_id
    roa.prefix = prefix
    roa.prefix_length = prefix_length
    roa.origin_as = origin_as
    roa.max_length = max_length
    roa.prefix_family = prefix_family
    roa.status = status
    roa.tal_id = 1
    return roa


def _make_result_mock(rows: list[Any]) -> MagicMock:
    """构造一个返回指定行列表的查询结果 mock。"""
    result = MagicMock()
    result.all.return_value = rows
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    result.first.return_value = rows[0] if rows else None
    result.scalar_one_or_none.return_value = rows[0] if rows else None
    return result


def _make_db_mock(execute_returns: list[Any] | None = None) -> AsyncMock:
    """构造一个模拟的 AsyncSession。"""
    db = AsyncMock()
    if execute_returns is None:
        db.execute.return_value = _make_result_mock([])
        return db
    side_effects = []
    for ret in execute_returns:
        if isinstance(ret, list):
            side_effects.append(_make_result_mock(ret))
        elif isinstance(ret, MagicMock):
            side_effects.append(ret)
        else:
            side_effects.append(_make_result_mock([ret]))
    db.execute.side_effect = side_effects
    return db


# ──────────────────────────────────────────────
# _compute_simulated_status 单元测试
# ──────────────────────────────────────────────


def test_compute_simulated_status_drop_invalid() -> None:
    """drop_invalid 策略下 Invalid 应变为 rejected。"""
    assert _compute_simulated_status("invalid", "drop_invalid") == "rejected"


def test_compute_simulated_status_de_preference_invalid() -> None:
    """de-preference_invalid 策略下 Invalid 应变为 de-preferenced。"""
    assert (
        _compute_simulated_status("invalid", "de-preference_invalid")
        == "de-preferenced"
    )


def test_compute_simulated_status_monitor_only() -> None:
    """monitor_only 策略下状态应保持不变。"""
    assert _compute_simulated_status("invalid", "monitor_only") == "invalid"


def test_compute_simulated_status_valid_unchanged() -> None:
    """Valid 状态在任何策略下应保持不变。"""
    assert _compute_simulated_status("valid", "drop_invalid") == "valid"


def test_compute_simulated_status_not_found_unchanged() -> None:
    """NotFound 状态在任何策略下应保持不变。"""
    assert _compute_simulated_status("not_found", "drop_invalid") == "not_found"


# ──────────────────────────────────────────────
# _validate_against_vrps 单元测试
# ──────────────────────────────────────────────


def test_validate_against_vrps_valid() -> None:
    """完全匹配的 VRP 应返回 Valid。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    status, reason = _validate_against_vrps("192.168.1.0/24", 65001, [vrp])
    assert status == "valid"
    assert reason is None


def test_validate_against_vrps_not_found() -> None:
    """无匹配 VRP 应返回 NotFound。"""
    status, reason = _validate_against_vrps("192.168.1.0/24", 65001, [])
    assert status == "not_found"
    assert reason is None


def test_validate_against_vrps_invalid_origin_mismatch() -> None:
    """origin AS 不匹配应返回 Invalid（origin_as_mismatch）。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    status, reason = _validate_against_vrps("192.168.1.0/24", 66666, [vrp])
    assert status == "invalid"
    assert reason == "origin_as_mismatch"


def test_validate_against_vrps_invalid_length_exceeded() -> None:
    """前缀长度超过 maxLength 应返回 Invalid（length_exceeded）。"""
    vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=16)
    status, reason = _validate_against_vrps("10.1.1.0/24", 65001, [vrp])
    assert status == "invalid"
    assert reason == "length_exceeded"


# ──────────────────────────────────────────────
# _get_covering_prefixes 与 _get_more_specific_prefixes
# ──────────────────────────────────────────────


def test_get_covering_prefixes_ipv4() -> None:
    """IPv4 前缀的祖先链应包含 /0 到自身。"""
    covering = _get_covering_prefixes("192.168.1.0/24")
    assert "0.0.0.0/0" in covering
    assert "192.168.1.0/24" in covering


def test_get_more_specific_prefixes() -> None:
    """子前缀计算应返回从 prefixlen+1 到 max_length 的所有子前缀。"""
    surface = _get_more_specific_prefixes("10.0.0.0/8", 9)
    assert len(surface) == 2  # 10.0.0.0/9, 10.128.0.0/9


def test_get_more_specific_prefixes_no_expansion() -> None:
    """max_length <= prefixlen 时应返回空列表。"""
    assert _get_more_specific_prefixes("10.0.0.0/8", 8) == []


# ──────────────────────────────────────────────
# generate_deployment_recommendations 单元测试
# ──────────────────────────────────────────────


def test_deployment_recommendations_three_phases() -> None:
    """部署建议应包含监控、降权、拒收三个阶段。"""
    affected = [
        AffectedPrefix(
            prefix="192.168.1.0/24",
            origin_as=65001,
            current_status="invalid",
            simulated_status="rejected",
            importance="normal",
        ),
    ]
    recommendations = generate_deployment_recommendations(affected)

    phases = [r.phase for r in recommendations]
    assert "monitor" in phases
    assert "de-preference" in phases
    assert "drop" in phases


def test_deployment_recommendations_empty_affected() -> None:
    """无受影响前缀时仍应返回三阶段建议。"""
    recommendations = generate_deployment_recommendations([])
    assert len(recommendations) >= 3


# ──────────────────────────────────────────────
# assess_simulation_risk 单元测试
# ──────────────────────────────────────────────


def test_assess_risk_no_risk() -> None:
    """无受影响前缀应返回 none 风险。"""
    assessment = assess_simulation_risk([], [])
    assert assessment.risk_level == "none"
    assert assessment.requires_approval is False


def test_assess_risk_critical_rejected_high_risk() -> None:
    """核心前缀被拒绝应为 high 风险且需审批。"""
    affected = [
        AffectedPrefix(
            prefix="192.168.1.0/24",
            origin_as=65001,
            current_status="invalid",
            simulated_status="rejected",
            importance="critical",
        ),
    ]
    assessment = assess_simulation_risk(affected, [])
    assert assessment.risk_level == "high"
    assert assessment.requires_approval is True
    assert len(assessment.blocking_issues) > 0


def test_assess_risk_large_scale_triggers_approval() -> None:
    """受影响前缀超过 200 个应触发审批。"""
    affected = [
        AffectedPrefix(
            prefix=f"10.{i}.0.0/24",
            origin_as=65001,
            current_status="invalid",
            simulated_status="rejected",
            importance="normal",
        )
        for i in range(201)
    ]
    assessment = assess_simulation_risk(affected, [])
    assert assessment.requires_approval is True


# ──────────────────────────────────────────────
# check_high_risk_block 单元测试
# ──────────────────────────────────────────────


def test_check_high_risk_block_critical_rejected() -> None:
    """核心前缀被拒绝应返回 True。"""
    affected = [
        AffectedPrefix(
            prefix="192.168.1.0/24",
            origin_as=65001,
            current_status="invalid",
            simulated_status="rejected",
            importance="critical",
        ),
    ]
    assert check_high_risk_block(affected) is True


def test_check_high_risk_block_large_scale() -> None:
    """被拒绝前缀超过 200 个应返回 True。"""
    affected = [
        AffectedPrefix(
            prefix=f"10.{i}.0.0/24",
            origin_as=65001,
            current_status="invalid",
            simulated_status="rejected",
            importance="normal",
        )
        for i in range(201)
    ]
    assert check_high_risk_block(affected) is True


def test_check_high_risk_block_normal_not_blocked() -> None:
    """普通前缀降权不应触发阻断。"""
    affected = [
        AffectedPrefix(
            prefix="192.168.1.0/24",
            origin_as=65001,
            current_status="invalid",
            simulated_status="de-preferenced",
            importance="normal",
        ),
    ]
    assert check_high_risk_block(affected) is False


# ──────────────────────────────────────────────
# simulate_rov_policy 集成测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulate_rov_policy_drop_invalid() -> None:
    """drop_invalid 策略应将 Invalid 路由变为 rejected。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    # 一个 Valid 公告（origin AS 匹配）+ 一个 Invalid 公告（origin AS 不匹配）
    valid_ann = _make_announcement("192.168.1.0/24", 65001, 24)
    invalid_ann = _make_announcement("192.168.1.0/24", 66666, 24)
    # execute 顺序：_fetch_all_vrps, _fetch_bgp_announcements, _build_prefix_metadata_map
    db = _make_db_mock([
        [vrp],                          # _fetch_all_vrps
        [valid_ann, invalid_ann],       # _fetch_bgp_announcements
        [],                             # _build_prefix_metadata_map
    ])

    request = ROVSimulationRequest(policy="drop_invalid")
    result = await simulate_rov_policy(db, request)

    assert result.policy == "drop_invalid"
    assert result.total_announcements == 2
    # invalid_ann 应被拒绝
    rejected = [ap for ap in result.affected_prefixes if ap.simulated_status == "rejected"]
    assert len(rejected) == 1
    assert rejected[0].origin_as == 66666


@pytest.mark.asyncio
async def test_simulate_rov_policy_monitor_only_no_impact() -> None:
    """monitor_only 策略不应影响任何路由。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    invalid_ann = _make_announcement("192.168.1.0/24", 66666, 24)
    db = _make_db_mock([
        [vrp],
        [invalid_ann],
        [],
    ])

    request = ROVSimulationRequest(policy="monitor_only")
    result = await simulate_rov_policy(db, request)

    assert result.affected_prefixes == []


# ──────────────────────────────────────────────
# simulate_roa_change 集成测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_simulate_roa_change_create() -> None:
    """新建 ROA 模拟应返回验证状态变化与攻击面分析。"""
    # 无现有 VRP，新建 ROA 后前缀从 NotFound 变为 Valid
    existing_ann = _make_announcement("192.168.1.0/24", 65001, 24)
    db = _make_db_mock([
        [],                 # _fetch_all_vrps（无现有 VRP）
        [existing_ann],     # _fetch_bgp_announcements
        [],                 # _build_prefix_metadata_map
    ])

    request = ROAChangeSimulationRequest(
        change_type="create",
        new_prefix="192.168.1.0/24",
        new_origin_as=65001,
        new_max_length=24,
    )
    result = await simulate_roa_change(db, request)

    # 应有验证状态变化（NotFound -> Valid）
    assert len(result.validation_changes) >= 1
    change = result.validation_changes[0]
    assert change.old_status == "not_found"
    assert change.new_status == "valid"


@pytest.mark.asyncio
async def test_simulate_roa_change_revoke() -> None:
    """撤销 ROA 模拟应使前缀从 Valid 变为 NotFound。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24, roa_id=1)
    roa = _make_roa(1, "192.168.1.0/24", 24, 65001, max_length=24)
    existing_ann = _make_announcement("192.168.1.0/24", 65001, 24)

    db = _make_db_mock([
        [vrp],              # _fetch_all_vrps
        [existing_ann],     # _fetch_bgp_announcements
        [roa],              # select ROA by id
        [],                 # _build_affected_announcements -> _build_prefix_metadata_map
    ])

    request = ROAChangeSimulationRequest(
        roa_id=1,
        change_type="revoke",
    )
    result = await simulate_roa_change(db, request)

    # 撤销 ROA 不增加攻击面
    assert result.new_attack_surface == []
    # 应有验证状态变化（Valid -> NotFound）
    assert len(result.validation_changes) >= 1
