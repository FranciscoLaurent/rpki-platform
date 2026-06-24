"""RPKI 验证性能测试。

测试 ``validate_bgp_announcement`` 与 ``_validate_against_vrps`` 在大规模
VRP 数据下的验证性能。使用 ``time.perf_counter`` 进行高精度计时。

运行方式：
    pytest tests/perf/test_validation_perf.py -v -s
"""

from __future__ import annotations

import ipaddress
import random
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.rov_simulation_service import _validate_against_vrps
from app.services.vrp_service import (
    _get_covering_prefixes,
    validate_bgp_announcement,
)


# ──────────────────────────────────────────────
# 性能测试常量
# ──────────────────────────────────────────────

VRP_SCALE = 50_000
VALIDATION_COUNT = 1_000
VALIDATION_THRESHOLD_MS = 5.0  # 单次验证 5ms
COVERING_PREFIX_THRESHOLD_MS = 0.5  # 单次祖先链计算 0.5ms


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _generate_vrps(count: int) -> list[MagicMock]:
    """生成指定数量的模拟 VRP 对象。"""
    vrps: list[MagicMock] = []
    for i in range(count):
        vrp = MagicMock()
        # 随机生成 IPv4 前缀
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
        vrp.roa_id = i
        vrps.append(vrp)
    return vrps


def _make_vrp(prefix: str, prefix_length: int, origin_as: int,
              max_length: int | None = None) -> MagicMock:
    """构造单个 VRP mock。"""
    vrp = MagicMock()
    vrp.prefix = prefix
    vrp.prefix_length = prefix_length
    vrp.origin_as = origin_as
    vrp.max_length = max_length or prefix_length
    vrp.validation_status = "valid"
    vrp.tal_id = 1
    vrp.roa_id = 1
    vrp.trust_anchor = "test"
    vrp.id = 1
    vrp.prefix_family = 4
    vrp.created_at = datetime.now(timezone.utc)
    vrp.updated_at = datetime.now(timezone.utc)
    return vrp


def _make_db_mock(vrps: list[Any]) -> AsyncMock:
    """构造返回指定 VRP 列表的 AsyncSession mock。"""
    db = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = vrps
    result.scalars.return_value = scalars
    db.execute.return_value = result
    return db


# ──────────────────────────────────────────────
# _get_covering_prefixes 性能测试
# ──────────────────────────────────────────────


def test_get_covering_prefixes_performance() -> None:
    """祖先链计算性能测试。"""
    # 生成不同前缀长度的查询
    test_prefixes = []
    for _ in range(VALIDATION_COUNT):
        addr_int = random.randint(0, 0xFFFFFFFF)
        prefix_len = random.randint(8, 32)
        mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
        network_addr = addr_int & mask
        network = ipaddress.IPv4Network((network_addr, prefix_len), strict=True)
        test_prefixes.append(str(network))

    start = time.perf_counter()
    for p in test_prefixes:
        _get_covering_prefixes(p)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / VALIDATION_COUNT) * 1000
    print(
        f"\n[祖先链计算] {VALIDATION_COUNT} 次，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )

    assert avg_ms < COVERING_PREFIX_THRESHOLD_MS


# ──────────────────────────────────────────────
# _validate_against_vrps 性能测试
# ──────────────────────────────────────────────


def test_validate_against_vrps_large_scale() -> None:
    """大规模 VRP 数据下的内存验证性能测试。"""
    vrps = _generate_vrps(VRP_SCALE)

    # 生成待验证的公告（部分匹配 VRP，部分不匹配）
    announcements = []
    for _ in range(VALIDATION_COUNT):
        if random.random() < 0.5:
            # 使用现有 VRP 的前缀
            vrp = random.choice(vrps)
            announcements.append((vrp.prefix, vrp.origin_as))
        else:
            # 随机前缀
            addr_int = random.randint(0, 0xFFFFFFFF)
            prefix_len = random.randint(8, 32)
            mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
            network_addr = addr_int & mask
            network = ipaddress.IPv4Network((network_addr, prefix_len), strict=True)
            announcements.append((str(network), random.randint(1, 65535)))

    start = time.perf_counter()
    for prefix, origin_as in announcements:
        _validate_against_vrps(prefix, origin_as, vrps)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / VALIDATION_COUNT) * 1000
    print(
        f"\n[内存验证] {VALIDATION_COUNT} 次验证（VRP 规模 {VRP_SCALE}），"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )

    assert avg_ms < VALIDATION_THRESHOLD_MS


def test_validate_against_vrps_valid_case() -> None:
    """Valid 验证性能测试（匹配 VRP）。"""
    vrps = _generate_vrps(VRP_SCALE)
    # 选取现有 VRP 构造 Valid 公告
    test_cases = [(v.prefix, v.origin_as) for v in random.sample(vrps, min(VALIDATION_COUNT, len(vrps)))]

    start = time.perf_counter()
    for prefix, origin_as in test_cases:
        _validate_against_vrps(prefix, origin_as, vrps)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / len(test_cases)) * 1000
    print(
        f"\n[Valid 验证] {len(test_cases)} 次，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )


def test_validate_against_vrps_not_found_case() -> None:
    """NotFound 验证性能测试（无匹配 VRP）。"""
    vrps = _generate_vrps(VRP_SCALE)
    # 生成不太可能匹配的随机前缀
    test_cases = []
    for _ in range(VALIDATION_COUNT):
        addr_int = random.randint(0, 0xFFFFFFFF)
        prefix_len = random.randint(8, 32)
        mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
        network_addr = addr_int & mask
        network = ipaddress.IPv4Network((network_addr, prefix_len), strict=True)
        test_cases.append((str(network), 99999))

    start = time.perf_counter()
    for prefix, origin_as in test_cases:
        _validate_against_vrps(prefix, origin_as, vrps)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / VALIDATION_COUNT) * 1000
    print(
        f"\n[NotFound 验证] {VALIDATION_COUNT} 次，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )


# ──────────────────────────────────────────────
# validate_bgp_announcement 异步验证性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_bgp_announcement_performance() -> None:
    """validate_bgp_announcement 异步验证性能测试。"""
    # 构造少量 VRP（数据库查询模拟）
    vrps = [_make_vrp("192.168.1.0/24", 24, 65001, max_length=24)]
    db = _make_db_mock(vrps)

    start = time.perf_counter()
    for _ in range(VALIDATION_COUNT):
        await validate_bgp_announcement(db, "192.168.1.0/24", 65001)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / VALIDATION_COUNT) * 1000
    print(
        f"\n[异步验证] {VALIDATION_COUNT} 次，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )


# ──────────────────────────────────────────────
# 批量验证性能测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_validation_performance() -> None:
    """批量验证性能测试。"""
    from app.schemas.rpki import BGPAnnouncementValidationRequest
    from app.services.vrp_service import validate_bgp_announcements

    vrps = [_make_vrp("192.168.1.0/24", 24, 65001, max_length=24)]
    db = _make_db_mock(vrps)

    announcements = [
        BGPAnnouncementValidationRequest(prefix="192.168.1.0/24", origin_as=65001)
        for _ in range(VALIDATION_COUNT)
    ]

    start = time.perf_counter()
    results = await validate_bgp_announcements(db, announcements)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / VALIDATION_COUNT) * 1000
    print(
        f"\n[批量验证] {VALIDATION_COUNT} 条公告，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/条"
    )

    assert len(results) == VALIDATION_COUNT
