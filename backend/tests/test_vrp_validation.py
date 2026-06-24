"""RPKI 验证测试。

覆盖 ``app.services.vrp_service.validate_bgp_announcement`` 的三态验证逻辑：
- Valid：origin AS 匹配且前缀长度在 maxLength 范围内
- Invalid：origin AS 不匹配、长度超限、ROA 已撤销
- NotFound：无匹配 VRP

同时测试覆盖前缀匹配（祖先链）与批量验证。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.rpki import BGPAnnouncementValidationRequest
from app.services.vrp_service import (
    _get_covering_prefixes,
    validate_bgp_announcement,
    validate_bgp_announcements,
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
    vrp_id: int = 1,
    prefix_family: int = 4,
) -> MagicMock:
    """构造一个模拟的 VRP 对象。"""
    vrp = MagicMock()
    vrp.id = vrp_id
    vrp.prefix = prefix
    vrp.prefix_length = prefix_length
    vrp.prefix_family = prefix_family
    vrp.origin_as = origin_as
    vrp.max_length = max_length
    vrp.tal_id = 1
    vrp.roa_id = 1
    vrp.trust_anchor = "test-tal"
    vrp.validation_status = validation_status
    vrp.created_at = datetime.now(UTC)
    vrp.updated_at = datetime.now(UTC)
    return vrp


def _make_db_mock(vrps: list[Any]) -> AsyncMock:
    """构造一个模拟的 AsyncSession，execute 返回包含给定 VRP 列表的结果。"""
    db = AsyncMock()
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = vrps
    result.scalars.return_value = scalars
    db.execute.return_value = result
    return db


# ──────────────────────────────────────────────
# _get_covering_prefixes 辅助函数测试
# ──────────────────────────────────────────────


def test_get_covering_prefixes_ipv4() -> None:
    """IPv4 前缀的祖先链应包含从 /0 到自身。"""
    covering = _get_covering_prefixes("192.168.1.0/24")
    assert "0.0.0.0/0" in covering
    assert "192.168.0.0/16" in covering
    assert "192.168.1.0/24" in covering


def test_get_covering_prefixes_ipv6() -> None:
    """IPv6 前缀的祖先链应包含从 ::/0 到自身。"""
    covering = _get_covering_prefixes("2001:db8::/32")
    assert "::/0" in covering
    assert "2001:db8::/32" in covering


def test_get_covering_prefixes_invalid_returns_empty() -> None:
    """非法前缀应返回空列表。"""
    assert _get_covering_prefixes("not-a-prefix") == []


# ──────────────────────────────────────────────
# Valid 状态
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_valid_exact_match() -> None:
    """origin AS 与前缀长度完全匹配的 VRP 应返回 Valid。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "192.168.1.0/24", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "valid"
    assert result.validation_result.invalid_reason is None


@pytest.mark.asyncio
async def test_validation_valid_with_max_length() -> None:
    """前缀长度小于 maxLength 时应返回 Valid。"""
    vrp = _make_vrp("10.0.0.0/8", 8, 65002, max_length=24)
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "10.1.0.0/16", 65002)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "valid"


@pytest.mark.asyncio
async def test_validation_valid_with_default_max_length() -> None:
    """VRP 未设置 maxLength 时，前缀长度不超过 prefix_length 应返回 Valid。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=None)
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "192.168.1.0/24", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "valid"


# ──────────────────────────────────────────────
# Invalid 状态
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_invalid_origin_as_mismatch() -> None:
    """origin AS 不匹配应返回 Invalid（origin_as_mismatch）。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "192.168.1.0/24", 66666)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "invalid"
    assert result.validation_result.invalid_reason == "origin_as_mismatch"


@pytest.mark.asyncio
async def test_validation_invalid_length_exceeded() -> None:
    """前缀长度超过 maxLength 应返回 Invalid（length_exceeded）。"""
    vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=16)
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "10.1.1.0/24", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "invalid"
    assert result.validation_result.invalid_reason == "length_exceeded"


@pytest.mark.asyncio
async def test_validation_invalid_roa_revoked() -> None:
    """所有匹配 VRP 都已撤销应返回 Invalid（roa_revoked）。"""
    vrp = _make_vrp(
        "192.168.1.0/24", 24, 65001, max_length=24,
        validation_status="revoked",
    )
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "192.168.1.0/24", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "invalid"
    assert result.validation_result.invalid_reason == "roa_revoked"


# ──────────────────────────────────────────────
# NotFound 状态
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_not_found_no_vrp() -> None:
    """无匹配 VRP 应返回 NotFound。"""
    db = _make_db_mock([])

    result = await validate_bgp_announcement(db, "192.168.1.0/24", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "not_found"
    assert result.validation_result.invalid_reason is None
    assert result.validation_result.matched_vrps == []


# ──────────────────────────────────────────────
# 覆盖前缀匹配（祖先链）
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_validation_covers_ancestor_chain() -> None:
    """父前缀 VRP 应能覆盖子前缀公告（祖先链匹配）。"""
    # 父前缀 /8 授权 AS65001，maxLength=24
    vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=24)
    db = _make_db_mock([vrp])

    # 子前缀 /16 公告，origin AS 匹配，长度在 maxLength 内
    result = await validate_bgp_announcement(db, "10.1.0.0/16", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "valid"


@pytest.mark.asyncio
async def test_validation_multiple_vrps_one_matches() -> None:
    """多个匹配 VRP 中只要有一个完全匹配应返回 Valid。"""
    vrp1 = _make_vrp(
        "192.168.1.0/24", 24, 65001, max_length=24, vrp_id=1
    )
    vrp2 = _make_vrp(
        "192.168.1.0/24", 24, 65002, max_length=24, vrp_id=2
    )
    db = _make_db_mock([vrp1, vrp2])

    # 公告 origin AS 为 65002，应匹配 vrp2
    result = await validate_bgp_announcement(db, "192.168.1.0/24", 65002)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "valid"


@pytest.mark.asyncio
async def test_validation_invalid_prefix_returns_data_source_error() -> None:
    """非法前缀公告应返回 Invalid（data_source_error）。"""
    # 构造一个匹配的 VRP（使流程进入前缀解析阶段）
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    db = _make_db_mock([vrp])

    result = await validate_bgp_announcement(db, "not-a-prefix", 65001)

    assert result.validation_result is not None
    assert result.validation_result.validation_status == "invalid"
    assert result.validation_result.invalid_reason == "data_source_error"


# ──────────────────────────────────────────────
# 批量验证
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_batch_validation_returns_results_in_order() -> None:
    """批量验证应按输入顺序返回结果。"""
    vrp = _make_vrp("192.168.1.0/24", 24, 65001, max_length=24)
    db = _make_db_mock([vrp])

    announcements = [
        BGPAnnouncementValidationRequest(prefix="192.168.1.0/24", origin_as=65001),
        BGPAnnouncementValidationRequest(prefix="10.0.0.0/8", origin_as=99999),
    ]
    results = await validate_bgp_announcements(db, announcements)

    assert len(results) == 2
    assert results[0].prefix == "192.168.1.0/24"
    assert results[1].prefix == "10.0.0.0/8"


@pytest.mark.asyncio
async def test_batch_validation_empty_list() -> None:
    """空列表批量验证应返回空结果。"""
    db = _make_db_mock([])
    results = await validate_bgp_announcements(db, [])
    assert results == []
