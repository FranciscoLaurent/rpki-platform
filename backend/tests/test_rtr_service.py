"""RPKI-RTR 服务管理测试。

覆盖 ``app.services.rtr_service`` 的核心功能：
- RTR 服务 CRUD（创建、查询、更新、删除）
- VRP 数据更新与序列号递增
- 序列号回滚
- 一致性检查（服务端 VRP 与数据库 VRP 比对）
- VRP 差异计算
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.rtr import RTRServerCreate, RTRServerUpdate
from app.services.rtr_service import (
    _compute_vrp_diff,
    _vrp_to_dict,
    check_consistency,
    create_rtr_server,
    delete_rtr_server,
    get_rtr_server,
    get_rtr_servers,
    rollback_serial,
    start_rtr_server,
    stop_rtr_server,
    update_rtr_server,
    update_vrps,
)

# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _make_vrp(
    prefix: str = "192.168.1.0/24",
    prefix_length: int = 24,
    origin_as: int = 65001,
    max_length: int | None = 24,
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


def _make_server(
    server_id: int = 1,
    name: str = "test-rtr",
    listen_host: str = "0.0.0.0",
    listen_port: int = 8282,
    session_id: int = 1,
    status: str = "stopped",
    current_serial: int = 0,
    vrps_count: int = 0,
    connected_clients: int = 0,
    mtls_enabled: bool = False,
    whitelist: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> MagicMock:
    """构造一个模拟的 RTRServer 对象。"""
    server = MagicMock()
    server.id = server_id
    server.name = name
    server.listen_host = listen_host
    server.listen_port = listen_port
    server.session_id = session_id
    server.status = status
    server.current_serial = current_serial
    server.vrps_count = vrps_count
    server.connected_clients = connected_clients
    server.mtls_enabled = mtls_enabled
    server.whitelist = whitelist
    server.config = config
    server.last_started_at = None
    server.last_error = None
    return server


def _make_result_mock(rows: list[Any], scalar: Any = None) -> MagicMock:
    """构造一个返回指定行列表的查询结果 mock。"""
    result = MagicMock()
    result.all.return_value = rows
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    result.first.return_value = rows[0] if rows else None
    result.one.return_value = rows[0] if rows else None
    if scalar is not None:
        result.scalar_one.return_value = scalar
        result.scalar_one_or_none.return_value = scalar
    else:
        result.scalar_one.return_value = rows[0] if rows else None
        result.scalar_one_or_none.return_value = rows[0] if rows else None
    return result


def _make_db_mock(execute_returns: list[Any] | None = None) -> AsyncMock:
    """构造一个模拟的 AsyncSession。"""
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
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
# _vrp_to_dict 单元测试
# ──────────────────────────────────────────────


def test_vrp_to_dict() -> None:
    """VRP 对象应正确转换为字典。"""
    vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=16)
    d = _vrp_to_dict(vrp)
    assert d["prefix"] == "10.0.0.0/8"
    assert d["prefix_length"] == 8
    assert d["origin_as"] == 65001
    assert d["max_length"] == 16


# ──────────────────────────────────────────────
# _compute_vrp_diff 单元测试
# ──────────────────────────────────────────────


def test_compute_vrp_diff_all_added() -> None:
    """旧列表为空时，所有新 VRP 应计为新增。"""
    old: list[dict[str, Any]] = []
    new = [
        {"prefix": "10.0.0.0/8", "prefix_length": 8, "origin_as": 65001, "max_length": 8},
    ]
    added, removed, modified = _compute_vrp_diff(old, new)
    assert added == 1
    assert removed == 0
    assert modified == 0


def test_compute_vrp_diff_all_removed() -> None:
    """新列表为空时，所有旧 VRP 应计为移除。"""
    old = [
        {"prefix": "10.0.0.0/8", "prefix_length": 8, "origin_as": 65001, "max_length": 8},
    ]
    new: list[dict[str, Any]] = []
    added, removed, modified = _compute_vrp_diff(old, new)
    assert added == 0
    assert removed == 1
    assert modified == 0


def test_compute_vrp_diff_max_length_modified() -> None:
    """相同 key 但 maxLength 不同应计为修改。"""
    old = [
        {"prefix": "10.0.0.0/8", "prefix_length": 8, "origin_as": 65001, "max_length": 8},
    ]
    new = [
        {"prefix": "10.0.0.0/8", "prefix_length": 8, "origin_as": 65001, "max_length": 16},
    ]
    added, removed, modified = _compute_vrp_diff(old, new)
    assert added == 0
    assert removed == 0
    assert modified == 1


def test_compute_vrp_diff_no_change() -> None:
    """完全相同的 VRP 列表应无差异。"""
    old = [
        {"prefix": "10.0.0.0/8", "prefix_length": 8, "origin_as": 65001, "max_length": 8},
    ]
    new = [
        {"prefix": "10.0.0.0/8", "prefix_length": 8, "origin_as": 65001, "max_length": 8},
    ]
    added, removed, modified = _compute_vrp_diff(old, new)
    assert added == 0
    assert removed == 0
    assert modified == 0


# ──────────────────────────────────────────────
# create_rtr_server 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_rtr_server_success() -> None:
    """创建 RTR 服务应成功。"""
    # execute 调用：get_rtr_server_by_name（返回 None 表示不存在）
    db = _make_db_mock([_make_result_mock([])])

    server_create = RTRServerCreate(
        name="test-rtr",
        listen_host="0.0.0.0",
        listen_port=8282,
    )

    with patch("app.services.rtr_service.RTRServer") as mock_rtr_class:
        mock_server = _make_server(name="test-rtr")
        mock_rtr_class.return_value = mock_server
        result = await create_rtr_server(db, server_create)

    assert result is not None
    db.add.assert_called_once()
    db.flush.assert_called_once()
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_rtr_server_duplicate_name_raises() -> None:
    """同名 RTR 服务已存在时应抛出 ValueError。"""
    existing = _make_server(name="test-rtr")
    db = _make_db_mock([[existing]])

    server_create = RTRServerCreate(name="test-rtr")

    with pytest.raises(ValueError, match="已存在"):
        await create_rtr_server(db, server_create)


# ──────────────────────────────────────────────
# get_rtr_server / get_rtr_servers 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_rtr_server_found() -> None:
    """根据 ID 查询存在的 RTR 服务应返回对象。"""
    server = _make_server(server_id=5)
    db = _make_db_mock([[server]])

    result = await get_rtr_server(db, 5)

    assert result is not None
    assert result.id == 5


@pytest.mark.asyncio
async def test_get_rtr_server_not_found() -> None:
    """查询不存在的 RTR 服务应返回 None。"""
    db = _make_db_mock([[]])

    result = await get_rtr_server(db, 999)

    assert result is None


@pytest.mark.asyncio
async def test_get_rtr_servers_with_status_filter() -> None:
    """按状态过滤 RTR 服务列表。"""
    running_server = _make_server(server_id=1, status="running")
    db = _make_db_mock([[running_server]])

    result = await get_rtr_servers(db, status="running")

    assert len(result) == 1
    assert result[0].status == "running"


# ──────────────────────────────────────────────
# update_rtr_server 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_rtr_server_success() -> None:
    """更新 RTR 服务配置应成功。"""
    server = _make_server(server_id=1, listen_port=8282)
    db = _make_db_mock([[server]])

    update = RTRServerUpdate(listen_port=9000)

    result = await update_rtr_server(db, 1, update)

    assert result is not None
    assert server.listen_port == 9000
    db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_rtr_server_not_found() -> None:
    """更新不存在的 RTR 服务应返回 None。"""
    db = _make_db_mock([[]])

    result = await update_rtr_server(db, 999, RTRServerUpdate())

    assert result is None


# ──────────────────────────────────────────────
# delete_rtr_server 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_rtr_server_success() -> None:
    """删除存在的 RTR 服务应返回 True。"""
    server = _make_server(server_id=1)
    db = _make_db_mock([[server]])

    result = await delete_rtr_server(db, 1)

    assert result is True
    db.delete.assert_called_once_with(server)


@pytest.mark.asyncio
async def test_delete_rtr_server_not_found() -> None:
    """删除不存在的 RTR 服务应返回 False。"""
    db = _make_db_mock([[]])

    result = await delete_rtr_server(db, 999)

    assert result is False


# ──────────────────────────────────────────────
# start_rtr_server / stop_rtr_server 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_rtr_server_not_found_raises() -> None:
    """启动不存在的 RTR 服务应抛出 ValueError。"""
    db = _make_db_mock([[]])

    with pytest.raises(ValueError, match="不存在"):
        await start_rtr_server(db, 999)


@pytest.mark.asyncio
async def test_stop_rtr_server_not_found_raises() -> None:
    """停止不存在的 RTR 服务应抛出 ValueError。"""
    db = _make_db_mock([[]])

    with pytest.raises(ValueError, match="不存在"):
        await stop_rtr_server(db, 999)


@pytest.mark.asyncio
async def test_stop_rtr_server_stopped_status() -> None:
    """停止运行中的 RTR 服务应将状态置为 stopped。"""
    server = _make_server(server_id=1, status="running")
    db = _make_db_mock([[server]])

    with patch("app.services.rtr_service._running_engines", {}):
        result = await stop_rtr_server(db, 1)

    assert result.status == "stopped"


# ──────────────────────────────────────────────
# update_vrps 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_vrps_not_found_raises() -> None:
    """更新不存在的 RTR 服务 VRP 应抛出 ValueError。"""
    db = _make_db_mock([[]])

    with pytest.raises(ValueError, match="不存在"):
        await update_vrps(db, 999)


@pytest.mark.asyncio
async def test_update_vrps_increments_serial() -> None:
    """更新 VRP 应递增序列号。"""
    server = _make_server(server_id=1, current_serial=5)
    vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=8)
    # execute 顺序：get_rtr_server, _load_vrps_from_db
    db = _make_db_mock(
        [
            [server],  # get_rtr_server
            [vrp],  # _load_vrps_from_db
        ]
    )

    with patch("app.services.rtr_service._running_engines", {}):
        result = await update_vrps(db, 1)

    assert result.current_serial == 6


# ──────────────────────────────────────────────
# rollback_serial 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_rollback_serial_not_found_raises() -> None:
    """回滚不存在的 RTR 服务应抛出 ValueError。"""
    db = _make_db_mock([[]])

    with pytest.raises(ValueError, match="不存在"):
        await rollback_serial(db, 999, target_serial=1)


@pytest.mark.asyncio
async def test_rollback_serial_history_not_found_raises() -> None:
    """目标序列号历史不存在时应抛出 ValueError。"""
    server = _make_server(server_id=1, current_serial=5)
    db = _make_db_mock(
        [
            [server],  # get_rtr_server
            [],  # 历史查询返回空
        ]
    )

    with patch("app.services.rtr_service._running_engines", {}):
        with pytest.raises(ValueError, match="不存在序列号"):
            await rollback_serial(db, 1, target_serial=99)


# ──────────────────────────────────────────────
# check_consistency 测试
# ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_check_consistency_not_found_raises() -> None:
    """检查不存在的 RTR 服务一致性应抛出 ValueError。"""
    db = _make_db_mock([[]])

    with pytest.raises(ValueError, match="不存在"):
        await check_consistency(db, 999)


@pytest.mark.asyncio
async def test_check_consistency_server_not_running() -> None:
    """服务未运行时应返回一致（无差异）。"""
    server = _make_server(server_id=1, status="stopped")
    vrp = _make_vrp("10.0.0.0/8", 8, 65001, max_length=8)
    db = _make_db_mock(
        [
            [server],  # get_rtr_server
            [vrp],  # _load_vrps_from_db
        ]
    )

    with patch("app.services.rtr_service._running_engines", {}):
        result = await check_consistency(db, 1)

    assert result.consistent is True
    assert result.server_vrps_count == 0
    assert result.db_vrps_count == 1
    assert result.differences == []
