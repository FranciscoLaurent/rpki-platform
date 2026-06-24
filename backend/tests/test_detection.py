"""BGP 路由安全检测引擎测试。

覆盖六类检测器：
- 源 AS 劫持（hijack）与子前缀劫持（subprefix_hijack）
- MOAS（Multiple Origin AS）异常
- 路由泄露（route_leak）
- 路径异常（path_anomaly）
- 撤路与震荡（withdraw_flap）
- RPKI Invalid 传播
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.detection.hijack_detector import (
    detect_origin_as_hijack,
    detect_subprefix_hijack,
)
from app.services.detection.moas_detector import detect_moas
from app.services.detection.path_anomaly_detector import detect_path_anomaly
from app.services.detection.route_leak_detector import detect_route_leak
from app.services.detection.rpki_invalid_detector import (
    detect_rpki_invalid_propagation,
)
from app.services.detection.withdraw_detector import detect_withdraw_flap

# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _make_announcement(
    prefix: str = "192.168.1.0/24",
    origin_as: int | None = 65001,
    as_path: list[int] | None = None,
    observation_point_id: int | None = 1,
    rpki_validation_status: str | None = None,
    rpki_invalid_reason: str | None = None,
) -> MagicMock:
    """构造一个模拟的 BGPAnnouncement 对象。"""
    ann = MagicMock()
    ann.prefix = prefix
    ann.origin_as = origin_as
    ann.as_path = as_path
    ann.observation_point_id = observation_point_id
    ann.rpki_validation_status = rpki_validation_status
    ann.rpki_invalid_reason = rpki_invalid_reason
    ann.timestamp = datetime.now(UTC)
    return ann


def _make_vrp(
    prefix: str,
    prefix_length: int,
    origin_as: int,
    max_length: int | None = None,
    validation_status: str = "valid",
) -> MagicMock:
    """构造一个模拟的 VRP 对象。"""
    vrp = MagicMock()
    vrp.prefix = prefix
    vrp.prefix_length = prefix_length
    vrp.origin_as = origin_as
    vrp.max_length = max_length
    vrp.validation_status = validation_status
    return vrp


def _make_asn(
    asn: int,
    name: str = "",
    asn_type: str = "unknown",
    relationship_tags: list[str] | None = None,
    risk_profile: str | None = None,
) -> MagicMock:
    """构造一个模拟的 ASN 对象。"""
    obj = MagicMock()
    obj.asn = asn
    obj.name = name
    obj.asn_type = asn_type
    obj.relationship_tags = relationship_tags or []
    obj.risk_profile = risk_profile
    return obj


def _make_result_mock(rows: list[Any]) -> MagicMock:
    """构造一个返回指定行列表的查询结果 mock。"""
    result = MagicMock()
    result.all.return_value = rows
    result.scalars.return_value.all.return_value = rows
    result.scalars.return_value = rows
    result.first.return_value = rows[0] if rows else None
    result.one.return_value = rows[0] if rows else None
    result.scalar_one.return_value = rows[0] if rows else 0
    result.scalar_one_or_none.return_value = rows[0] if rows else None
    return result


def _make_db_mock(execute_returns: list[Any] | None = None) -> AsyncMock:
    """构造一个模拟的 AsyncSession。

    Args:
        execute_returns: 每次 execute 调用的返回值列表（按顺序）。
            若元素是 list，则包装为 _make_result_mock。
    """
    db = AsyncMock()
    if execute_returns is None:
        db.execute.return_value = _make_result_mock([])
        return db

    # 使用 side_effect 按顺序返回
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
# 源 AS 劫持检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hijack_no_origin_as_returns_not_detected() -> None:
    """公告缺少 origin_as 应返回未检测到劫持。"""
    ann = _make_announcement(origin_as=None)
    db = _make_db_mock()

    result = await detect_origin_as_hijack(db, ann)

    assert result.is_detected is False
    assert result.alert_type == "hijack"


@pytest.mark.asyncio
async def test_hijack_rpki_invalid_origin_mismatch_detected() -> None:
    """RPKI 验证 Invalid（origin_as_mismatch）应检测为劫持。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=66666)
    # execute 调用顺序：
    # 1. validate_bgp_announcement -> query_vrps -> 返回 VRP 列表
    # 2. _get_authorized_origin_as -> 返回授权 AS
    # 3. _get_historical_origin_asns -> 返回历史 AS 列表
    # 4. _count_propagation_scope -> 返回传播范围
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    db = _make_db_mock([
        [vrp],          # query_vrps
        [(65001, 1)],   # _get_authorized_origin_as
        [],             # _get_historical_origin_asns
        [3],            # _count_propagation_scope
    ])

    result = await detect_origin_as_hijack(db, ann)

    assert result.is_detected is True
    assert result.severity in ("P0", "P1")
    assert result.rpki_validation_status == "invalid"


@pytest.mark.asyncio
async def test_hijack_not_detected_when_authorized() -> None:
    """授权 origin AS 与公告一致时不应检测到劫持。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    db = _make_db_mock([
        [vrp],          # query_vrps
        [(65001, 1)],   # _get_authorized_origin_as
        [65001],        # _get_historical_origin_asns
        [1],            # _count_propagation_scope
    ])

    result = await detect_origin_as_hijack(db, ann)

    assert result.is_detected is False


# ──────────────────────────────────────────────
# 子前缀劫持检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_subprefix_hijack_no_origin_as_returns_not_detected() -> None:
    """公告缺少 origin_as 应返回未检测到子前缀劫持。"""
    ann = _make_announcement(origin_as=None)
    db = _make_db_mock()

    result = await detect_subprefix_hijack(db, ann)

    assert result.is_detected is False
    assert result.alert_type == "subprefix_hijack"


@pytest.mark.asyncio
async def test_subprefix_hijack_origin_mismatch_detected() -> None:
    """子前缀公告 origin AS 与父 VRP 不匹配应检测为子前缀劫持。"""
    ann = _make_announcement(prefix="10.1.1.0/24", origin_as=66666)
    parent_vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=24)
    db = _make_db_mock([[parent_vrp]])

    result = await detect_subprefix_hijack(db, ann)

    assert result.is_detected is True
    assert result.severity == "P0"
    assert result.traffic_attraction_risk == "high"


@pytest.mark.asyncio
async def test_subprefix_hijack_length_exceeded_detected() -> None:
    """子前缀长度超过 maxLength 应检测为子前缀劫持。"""
    ann = _make_announcement(prefix="10.1.1.0/24", origin_as=65001)
    parent_vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=16)
    db = _make_db_mock([[parent_vrp]])

    result = await detect_subprefix_hijack(db, ann)

    assert result.is_detected is True
    assert result.severity == "P1"
    assert result.traffic_attraction_risk == "medium"


@pytest.mark.asyncio
async def test_subprefix_hijack_no_covering_vrp_returns_not_detected() -> None:
    """无覆盖 VRP 时应返回未检测到子前缀劫持。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)
    db = _make_db_mock([[]])

    result = await detect_subprefix_hijack(db, ann)

    assert result.is_detected is False


# ──────────────────────────────────────────────
# MOAS 检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_moas_single_origin_not_detected() -> None:
    """仅一个 origin AS 时不构成 MOAS。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)
    db = _make_db_mock([
        [65001],        # _get_recent_origin_asns
    ])

    result = await detect_moas(db, ann)

    assert result.is_detected is False
    assert result.origin_as_list == [65001]


@pytest.mark.asyncio
async def test_moas_no_origin_as_returns_not_detected() -> None:
    """公告缺少 origin_as 应返回未检测到 MOAS。"""
    ann = _make_announcement(origin_as=None)
    db = _make_db_mock()

    result = await detect_moas(db, ann)

    assert result.is_detected is False


@pytest.mark.asyncio
async def test_moas_unknown_type_detected() -> None:
    """多个未知关系 AS 宣告同一前缀应检测为未知 MOAS。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)
    # execute 顺序：_get_recent_origin_asns, _get_asn_metadata, _get_historical_moas
    db = _make_db_mock([
        [65001, 65002],     # _get_recent_origin_asns
        [],                 # _get_asn_metadata（无 ASN 元信息）
        [],                 # _get_historical_moas（无历史）
    ])

    result = await detect_moas(db, ann)

    assert result.is_detected is True
    assert result.moas_type == "unknown"
    assert result.severity == "P2"


@pytest.mark.asyncio
async def test_moas_authorized_multi_origin_not_detected() -> None:
    """全部 AS 在历史基线中应判定为授权多 origin。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)
    db = _make_db_mock([
        [65001, 65002],                 # _get_recent_origin_asns
        [],                             # _get_asn_metadata
        [(65001, 5), (65002, 3)],       # _get_historical_moas（含历史）
    ])

    result = await detect_moas(db, ann)

    assert result.is_detected is False
    assert result.moas_type == "authorized_multi_origin"


# ──────────────────────────────────────────────
# 路由泄露检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_leak_short_path_not_detected() -> None:
    """AS_PATH 过短应返回未检测到路由泄露。"""
    ann = _make_announcement(as_path=[65001])
    db = _make_db_mock()

    result = await detect_route_leak(db, ann)

    assert result.is_detected is False
    assert result.alert_type == "route_leak"


@pytest.mark.asyncio
async def test_route_leak_customer_to_provider_detected() -> None:
    """客户向提供商泄露应被检测。"""
    ann = _make_announcement(as_path=[65001, 65002, 65003])
    asn_customer = _make_asn(65001, asn_type="customer")
    asn_provider = _make_asn(65002, asn_type="provider")
    asn_origin = _make_asn(65003, asn_type="own")
    db = _make_db_mock([
        [asn_customer, asn_provider, asn_origin],  # _get_asn_metadata
    ])

    result = await detect_route_leak(db, ann)

    assert result.is_detected is True
    assert result.leak_type == "customer_to_provider"


@pytest.mark.asyncio
async def test_route_leak_peer_to_peer_detected() -> None:
    """对等间泄露应被检测。"""
    ann = _make_announcement(as_path=[65001, 65002, 65003])
    asn_peer1 = _make_asn(65001, asn_type="peer")
    asn_peer2 = _make_asn(65002, asn_type="peer")
    asn_origin = _make_asn(65003, asn_type="own")
    db = _make_db_mock([
        [asn_peer1, asn_peer2, asn_origin],
    ])

    result = await detect_route_leak(db, ann)

    assert result.is_detected is True
    assert result.leak_type == "peer_to_peer"


@pytest.mark.asyncio
async def test_route_leak_normal_path_not_detected() -> None:
    """正常 AS_PATH 不应检测到路由泄露。"""
    ann = _make_announcement(as_path=[65001, 65002, 65003])
    asn1 = _make_asn(65001, asn_type="own")
    asn2 = _make_asn(65002, asn_type="own")
    asn3 = _make_asn(65003, asn_type="own")
    db = _make_db_mock([
        [asn1, asn2, asn3],
    ])

    result = await detect_route_leak(db, ann)

    assert result.is_detected is False


# ──────────────────────────────────────────────
# 路径异常检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_path_anomaly_empty_path_not_detected() -> None:
    """公告缺少 AS_PATH 应返回未检测到路径异常。"""
    ann = _make_announcement(as_path=None)
    db = _make_db_mock()

    result = await detect_path_anomaly(db, ann)

    assert result.is_detected is False
    assert result.alert_type == "path_anomaly"


@pytest.mark.asyncio
async def test_path_anomaly_blackhole_risk_detected() -> None:
    """路径仅 1 跳且 origin AS 风险画像异常应检测到黑洞风险。"""
    ann = _make_announcement(as_path=[65001])
    asn = _make_asn(65001, risk_profile="blackhole_high_risk")
    db = _make_db_mock([
        [],             # _get_baseline_path（无基线）
        [asn],          # _get_asn_metadata
    ])

    result = await detect_path_anomaly(db, ann)

    assert result.is_detected is True
    assert result.anomaly_type == "blackhole_risk"


@pytest.mark.asyncio
async def test_path_anomaly_abnormal_transit_detected() -> None:
    """路径中出现 IXP 作为中转应检测到异常中转。"""
    ann = _make_announcement(as_path=[65001, 65002, 65003])
    asn1 = _make_asn(65001, asn_type="own")
    asn2 = _make_asn(65002, asn_type="ixp")
    asn3 = _make_asn(65003, asn_type="own")
    db = _make_db_mock([
        [],                                 # _get_baseline_path
        [asn1, asn2, asn3],                 # _get_asn_metadata
    ])

    result = await detect_path_anomaly(db, ann)

    assert result.is_detected is True
    assert result.anomaly_type == "abnormal_transit"


# ──────────────────────────────────────────────
# 撤路与震荡检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_withdraw_flap_no_anomaly() -> None:
    """无撤路与公告时应返回未检测到异常。"""
    db = _make_db_mock([
        _make_result_mock([(0, 0)]),    # _count_withdraws
        _make_result_mock([(0, 0)]),    # _count_announcements
    ])

    result = await detect_withdraw_flap(db, "192.168.1.0/24", time_window=60)

    assert result.is_detected is False
    assert result.withdraw_count == 0
    assert result.announce_count == 0


@pytest.mark.asyncio
async def test_withdraw_flap_large_scale_withdraw_detected() -> None:
    """大范围撤路（>=5 观察点）应被检测。"""
    db = _make_db_mock([
        _make_result_mock([(10, 7)]),   # _count_withdraws: 10 次, 7 个观察点
        _make_result_mock([(2, 2)]),    # _count_announcements
    ])

    result = await detect_withdraw_flap(db, "192.168.1.0/24", time_window=60)

    assert result.is_detected is True
    assert result.severity == "P1"
    assert result.withdraw_count == 10


@pytest.mark.asyncio
async def test_withdraw_flap_frequent_flap_detected() -> None:
    """频繁震荡（频率 >= 0.5 次/分钟）应被检测。"""
    # 60 分钟内 40 次事件 -> 频率 0.67 次/分钟
    db = _make_db_mock([
        _make_result_mock([(20, 3)]),   # _count_withdraws
        _make_result_mock([(20, 3)]),   # _count_announcements
    ])

    result = await detect_withdraw_flap(db, "192.168.1.0/24", time_window=60)

    assert result.is_detected is True
    assert result.flap_rate >= 0.5


# ──────────────────────────────────────────────
# RPKI Invalid 传播检测
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rpki_invalid_no_invalid_announcements() -> None:
    """无 Invalid 公告应返回未检测到。"""
    db = _make_db_mock([[]])  # 无 Invalid 公告

    result = await detect_rpki_invalid_propagation(db, "192.168.1.0/24")

    assert result.is_detected is False
    assert result.alert_type == "rpki_invalid"


@pytest.mark.asyncio
async def test_rpki_invalid_propagation_detected() -> None:
    """有 Invalid 公告被多个观察点接收应被检测。"""
    # 构造 Invalid 公告行
    row1 = MagicMock()
    row1.origin_as = 66666
    row1.observation_point_id = 1
    row1.rpki_invalid_reason = "origin_as_mismatch"
    row1.as_path = [65001, 66666]

    row2 = MagicMock()
    row2.origin_as = 66666
    row2.observation_point_id = 2
    row2.rpki_invalid_reason = "origin_as_mismatch"
    row2.as_path = [65001, 66666]

    db = _make_db_mock([[row1, row2]])

    result = await detect_rpki_invalid_propagation(db, "192.168.1.0/24")

    assert result.is_detected is True
    assert result.propagation_count == 2
    assert result.invalid_reason == "origin_as_mismatch"


@pytest.mark.asyncio
async def test_rpki_invalid_high_propagation_severity_p0() -> None:
    """传播范围 >= 10 个观察点应为 P0 严重等级。"""
    rows = []
    for i in range(12):
        row = MagicMock()
        row.origin_as = 66666
        row.observation_point_id = i + 1
        row.rpki_invalid_reason = "origin_as_mismatch"
        row.as_path = [65001, 66666]
        rows.append(row)

    db = _make_db_mock([rows])

    result = await detect_rpki_invalid_propagation(db, "192.168.1.0/24")

    assert result.is_detected is True
    assert result.severity == "P0"
    assert result.propagation_count == 12
