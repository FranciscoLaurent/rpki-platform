"""检测引擎性能测试。

测试各检测器在大规模数据下的检测性能。
使用 ``time.perf_counter`` 进行高精度计时。

运行方式：
    pytest tests/perf/test_detection_perf.py -v -s
"""

from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.detection.hijack_detector import detect_origin_as_hijack
from app.services.detection.moas_detector import detect_moas
from app.services.detection.path_anomaly_detector import detect_path_anomaly
from app.services.detection.route_leak_detector import detect_route_leak
from app.services.detection.rpki_invalid_detector import (
    detect_rpki_invalid_propagation,
)
from app.services.detection.withdraw_detector import detect_withdraw_flap
from app.services.rov_simulation_service import _validate_against_vrps

# ──────────────────────────────────────────────
# 性能测试常量
# ──────────────────────────────────────────────

DETECTION_COUNT = 500
DETECTION_THRESHOLD_MS = 50.0  # 单次检测 50ms
VRP_SCALE = 10_000


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _make_announcement(
    prefix: str = "192.168.1.0/24",
    origin_as: int | None = 65001,
    as_path: list[int] | None = None,
    observation_point_id: int | None = 1,
) -> MagicMock:
    """构造模拟的 BGPAnnouncement。"""
    ann = MagicMock()
    ann.prefix = prefix
    ann.origin_as = origin_as
    ann.as_path = as_path or [65001, 65002, 65003]
    ann.observation_point_id = observation_point_id
    ann.rpki_validation_status = None
    ann.rpki_invalid_reason = None
    ann.timestamp = datetime.now(UTC)
    return ann


def _make_vrp(
    prefix: str,
    prefix_length: int,
    origin_as: int,
    max_length: int | None = None,
) -> MagicMock:
    """构造模拟的 VRP。"""
    vrp = MagicMock()
    vrp.prefix = prefix
    vrp.prefix_length = prefix_length
    vrp.origin_as = origin_as
    vrp.max_length = max_length or prefix_length
    vrp.validation_status = "valid"
    return vrp


def _make_asn(
    asn: int,
    asn_type: str = "own",
    risk_profile: str | None = None,
) -> MagicMock:
    """构造模拟的 ASN。"""
    obj = MagicMock()
    obj.asn = asn
    obj.name = f"AS{asn}"
    obj.asn_type = asn_type
    obj.relationship_tags = []
    obj.risk_profile = risk_profile
    return obj


def _make_result_mock(rows: list[Any], scalar: Any = None) -> MagicMock:
    """构造查询结果 mock。"""
    result = MagicMock()
    result.all.return_value = rows
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    result.first.return_value = rows[0] if rows else None
    result.one.return_value = rows[0] if rows else None
    if scalar is not None:
        result.scalar_one.return_value = scalar
    else:
        result.scalar_one.return_value = rows[0] if rows else 0
    return result


def _make_db_mock(execute_returns: list[Any] | None = None) -> AsyncMock:
    """构造模拟的 AsyncSession。"""
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
# 源 AS 劫持检测性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hijack_detection_performance() -> None:
    """源 AS 劫持检测性能测试。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)

    # 每次检测需要 4 次 execute：query_vrps, authorized, historical, propagation
    execute_returns = [
        [vrp],
        [(65001, 1)],
        [65001],
        [1],
    ]

    # 使用同一个 db mock 重复调用
    db = _make_db_mock(execute_returns * DETECTION_COUNT)

    start = time.perf_counter()
    for _ in range(DETECTION_COUNT):
        await detect_origin_as_hijack(db, ann)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / DETECTION_COUNT) * 1000
    print(f"\n[源 AS 劫持检测] {DETECTION_COUNT} 次，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert avg_ms < DETECTION_THRESHOLD_MS


# ──────────────────────────────────────────────
# MOAS 检测性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_moas_detection_performance() -> None:
    """MOAS 检测性能测试。"""
    ann = _make_announcement(prefix="192.168.1.0/24", origin_as=65001)
    execute_returns = [
        [65001, 65002],  # _get_recent_origin_asns
        [],  # _get_asn_metadata
        [(65001, 5), (65002, 3)],  # _get_historical_moas
    ]

    db = _make_db_mock(execute_returns * DETECTION_COUNT)

    start = time.perf_counter()
    for _ in range(DETECTION_COUNT):
        await detect_moas(db, ann)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / DETECTION_COUNT) * 1000
    print(f"\n[MOAS 检测] {DETECTION_COUNT} 次，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert avg_ms < DETECTION_THRESHOLD_MS


# ──────────────────────────────────────────────
# 路由泄露检测性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_route_leak_detection_performance() -> None:
    """路由泄露检测性能测试。"""
    ann = _make_announcement(as_path=[65001, 65002, 65003, 65004, 65005])
    asn1 = _make_asn(65001, "own")
    asn2 = _make_asn(65002, "provider")
    asn3 = _make_asn(65003, "customer")
    asn4 = _make_asn(65004, "peer")
    asn5 = _make_asn(65005, "own")

    execute_returns = [
        [asn1, asn2, asn3, asn4, asn5],  # _get_asn_metadata
    ]

    db = _make_db_mock(execute_returns * DETECTION_COUNT)

    start = time.perf_counter()
    for _ in range(DETECTION_COUNT):
        await detect_route_leak(db, ann)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / DETECTION_COUNT) * 1000
    print(f"\n[路由泄露检测] {DETECTION_COUNT} 次，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert avg_ms < DETECTION_THRESHOLD_MS


# ──────────────────────────────────────────────
# 路径异常检测性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_path_anomaly_detection_performance() -> None:
    """路径异常检测性能测试。"""
    ann = _make_announcement(as_path=[65001, 65002, 65003, 65004, 65005])
    asns = [_make_asn(asn) for asn in [65001, 65002, 65003, 65004, 65005]]

    execute_returns = [
        [],  # _get_baseline_path
        asns,  # _get_asn_metadata
    ]

    db = _make_db_mock(execute_returns * DETECTION_COUNT)

    start = time.perf_counter()
    for _ in range(DETECTION_COUNT):
        await detect_path_anomaly(db, ann)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / DETECTION_COUNT) * 1000
    print(f"\n[路径异常检测] {DETECTION_COUNT} 次，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert avg_ms < DETECTION_THRESHOLD_MS


# ──────────────────────────────────────────────
# 撤路与震荡检测性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_withdraw_flap_detection_performance() -> None:
    """撤路与震荡检测性能测试。"""
    execute_returns = [
        _make_result_mock([(5, 3)]),  # _count_withdraws
        _make_result_mock([(10, 4)]),  # _count_announcements
    ]

    db = _make_db_mock(execute_returns * DETECTION_COUNT)

    start = time.perf_counter()
    for _ in range(DETECTION_COUNT):
        await detect_withdraw_flap(db, "192.168.1.0/24", time_window=60)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / DETECTION_COUNT) * 1000
    print(f"\n[撤路与震荡检测] {DETECTION_COUNT} 次，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert avg_ms < DETECTION_THRESHOLD_MS


# ──────────────────────────────────────────────
# RPKI Invalid 传播检测性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rpki_invalid_detection_performance() -> None:
    """RPKI Invalid 传播检测性能测试。"""
    # 构造 Invalid 公告行
    rows = []
    for i in range(20):
        row = MagicMock()
        row.origin_as = 66666
        row.observation_point_id = i + 1
        row.rpki_invalid_reason = "origin_as_mismatch"
        row.as_path = [65001, 66666]
        rows.append(row)

    db = _make_db_mock([rows] * DETECTION_COUNT)

    start = time.perf_counter()
    for _ in range(DETECTION_COUNT):
        await detect_rpki_invalid_propagation(db, "192.168.1.0/24")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / DETECTION_COUNT) * 1000
    print(
        f"\n[RPKI Invalid 传播检测] {DETECTION_COUNT} 次，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )

    assert avg_ms < DETECTION_THRESHOLD_MS


# ──────────────────────────────────────────────
# 大规模 VRP 验证性能测试（模拟检测引擎内部验证）
# ──────────────────────────────────────────────


def test_large_scale_vrp_validation_performance() -> None:
    """大规模 VRP 数据下的验证性能测试（检测引擎内部）。"""
    # 生成大规模 VRP
    import ipaddress

    vrps: list[MagicMock] = []
    for _ in range(VRP_SCALE):
        vrp = MagicMock()
        addr_int = random.randint(0, 0xFFFFFFFF)
        prefix_len = random.randint(8, 32)
        mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
        network_addr = addr_int & mask
        network = ipaddress.IPv4Network((network_addr, prefix_len), strict=True)
        vrp.prefix = str(network)
        vrp.prefix_length = prefix_len
        vrp.origin_as = random.randint(1, 65535)
        vrp.max_length = prefix_len
        vrp.validation_status = "valid"
        vrps.append(vrp)

    # 生成待验证公告
    announcements = [
        (v.prefix, v.origin_as) for v in random.sample(vrps, min(DETECTION_COUNT, len(vrps)))
    ]

    start = time.perf_counter()
    for prefix, origin_as in announcements:
        _validate_against_vrps(prefix, origin_as, vrps)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / len(announcements)) * 1000
    print(
        f"\n[大规模 VRP 验证] {len(announcements)} 次验证（VRP 规模 {VRP_SCALE}），"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )

    assert avg_ms < DETECTION_THRESHOLD_MS
