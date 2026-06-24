"""RPKI-RTR 服务管理。

负责 RTR 服务实例的全生命周期管理：创建、启动、停止、状态查询、
VRP 数据更新、序列号回滚、一致性检查与客户端会话查询。

运行中的 RTR 服务引擎通过模块级全局字典 ``_running_engines`` 维护，
key 为 RTR 服务 ID，value 为 :class:`RTRServerEngine` 实例。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.rtr_server import RTRServerEngine
from app.models.rpki import VRP
from app.models.rtr import (
    RTRServer,
    RTRSerialHistory,
    RTRSession,
)
from app.schemas.rtr import (
    RTRConsistencyCheckResult,
    RTRConsistencyDifference,
    RTRServerCreate,
    RTRServerStatus,
    RTRServerUpdate,
)

logger = get_logger("app.rtr_service")


# 运行中的 RTR 服务引擎池：server_id -> RTRServerEngine
_running_engines: dict[int, RTRServerEngine] = {}


# ──────────────────────────────────────────────
# RTR 服务 CRUD
# ──────────────────────────────────────────────


async def create_rtr_server(
    db: AsyncSession, server_create: RTRServerCreate
) -> RTRServer:
    """创建 RTR 服务配置。

    Args:
        db: 异步数据库会话
        server_create: RTR 服务创建数据

    Returns:
        创建后的 RTRServer 对象

    Raises:
        ValueError: 同名 RTR 服务已存在
    """
    existing = await get_rtr_server_by_name(db, server_create.name)
    if existing is not None:
        raise ValueError(f"RTR 服务名称 '{server_create.name}' 已存在")

    server = RTRServer(
        name=server_create.name,
        listen_host=server_create.listen_host,
        listen_port=server_create.listen_port,
        session_id=server_create.session_id,
        mtls_enabled=server_create.mtls_enabled,
        whitelist=server_create.whitelist,
        config=server_create.config,
        status="stopped",
        current_serial=0,
        vrps_count=0,
        connected_clients=0,
    )
    db.add(server)
    await db.flush()
    await db.commit()
    await db.refresh(server)

    logger.info(
        "RTR 服务已创建",
        server_id=server.id,
        name=server.name,
        listen=f"{server.listen_host}:{server.listen_port}",
    )
    return server


async def get_rtr_server(db: AsyncSession, server_id: int) -> RTRServer | None:
    """根据 ID 获取 RTR 服务。"""
    stmt = select(RTRServer).where(RTRServer.id == server_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_rtr_server_by_name(
    db: AsyncSession, name: str
) -> RTRServer | None:
    """根据名称获取 RTR 服务。"""
    stmt = select(RTRServer).where(RTRServer.name == name)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_rtr_servers(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    status: str | None = None,
) -> list[RTRServer]:
    """获取 RTR 服务列表。

    Args:
        db: 异步数据库会话
        skip: 跳过记录数
        limit: 返回记录数上限
        status: 按状态过滤

    Returns:
        RTR 服务列表
    """
    stmt = select(RTRServer)
    if status is not None:
        stmt = stmt.where(RTRServer.status == status)
    stmt = stmt.order_by(RTRServer.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_rtr_servers(
    db: AsyncSession, status: str | None = None
) -> int:
    """统计 RTR 服务数量。"""
    stmt = select(func.count(RTRServer.id))
    if status is not None:
        stmt = stmt.where(RTRServer.status == status)
    result = await db.execute(stmt)
    return result.scalar_one()


async def update_rtr_server(
    db: AsyncSession, server_id: int, server_update: RTRServerUpdate
) -> RTRServer | None:
    """更新 RTR 服务配置。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID
        server_update: 更新数据

    Returns:
        更新后的 RTRServer 对象，不存在时返回 None
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        return None

    update_data = server_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(server, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(server)

    # 若服务正在运行且监听地址/端口/session_id 变更，需重启
    if server_id in _running_engines:
        engine = _running_engines[server_id]
        if any(
            k in update_data
            for k in ("listen_host", "listen_port", "session_id", "whitelist", "mtls_enabled")
        ):
            logger.info(
                "RTR 服务配置变更，需重启生效",
                server_id=server_id,
            )

    return server


async def delete_rtr_server(
    db: AsyncSession, server_id: int
) -> bool:
    """删除 RTR 服务。

    若服务正在运行，会先停止。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        是否删除成功
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        return False

    # 先停止运行中的引擎
    if server_id in _running_engines:
        await stop_rtr_server(db, server_id)

    await db.delete(server)
    await db.commit()

    logger.info("RTR 服务已删除", server_id=server_id)
    return True


# ──────────────────────────────────────────────
# RTR 服务生命周期管理
# ──────────────────────────────────────────────


async def start_rtr_server(
    db: AsyncSession, server_id: int
) -> RTRServer:
    """启动 RTR 服务。

    流程：
    1. 检查服务是否已在运行
    2. 从数据库加载当前 VRP 数据
    3. 初始化 RTRServerEngine
    4. 启动 TCP 监听
    5. 更新服务状态为 running

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        更新后的 RTRServer 对象

    Raises:
        ValueError: 服务不存在或已在运行
        RuntimeError: 启动失败（如端口占用）
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        raise ValueError(f"RTR 服务 ID {server_id} 不存在")

    if server_id in _running_engines:
        raise ValueError(f"RTR 服务 {server_id} 已在运行")

    # 加载当前 VRP 数据
    vrps = await _load_vrps_from_db(db)
    vrp_dicts = [_vrp_to_dict(v) for v in vrps]

    # 初始化引擎
    engine = RTRServerEngine(
        host=server.listen_host,
        port=server.listen_port,
        session_id=server.session_id,
        whitelist=server.whitelist or [],
        mtls_enabled=server.mtls_enabled,
    )
    engine.update_vrps(vrp_dicts, serial=server.current_serial)

    try:
        await engine.start()
    except Exception as e:
        server.status = "error"
        server.last_error = str(e)
        await db.commit()
        logger.error(
            "RTR 服务启动失败",
            server_id=server_id,
            error=str(e),
        )
        raise RuntimeError(f"RTR 服务启动失败: {e}") from e

    _running_engines[server_id] = engine

    # 更新数据库状态
    server.status = "running"
    server.vrps_count = len(vrp_dicts)
    server.connected_clients = 0
    server.last_started_at = datetime.now(timezone.utc)
    server.last_error = None
    await db.commit()
    await db.refresh(server)

    logger.info(
        "RTR 服务已启动",
        server_id=server_id,
        listen=f"{server.listen_host}:{server.listen_port}",
        vrps_count=len(vrp_dicts),
    )
    return server


async def stop_rtr_server(
    db: AsyncSession, server_id: int
) -> RTRServer:
    """停止 RTR 服务。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        更新后的 RTRServer 对象

    Raises:
        ValueError: 服务不存在
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        raise ValueError(f"RTR 服务 ID {server_id} 不存在")

    engine = _running_engines.pop(server_id, None)
    if engine is not None:
        await engine.stop()

    server.status = "stopped"
    server.connected_clients = 0
    await db.commit()
    await db.refresh(server)

    logger.info("RTR 服务已停止", server_id=server_id)
    return server


async def get_rtr_server_status(
    db: AsyncSession, server_id: int
) -> RTRServerStatus:
    """获取 RTR 服务运行状态。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        RTR 服务状态对象

    Raises:
        ValueError: 服务不存在
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        raise ValueError(f"RTR 服务 ID {server_id} 不存在")

    engine = _running_engines.get(server_id)
    if engine is not None:
        return RTRServerStatus(
            server_id=server.id,
            status=server.status,
            vrps_count=engine.vrps_count,
            connected_clients=engine.connected_clients_count,
            uptime=engine.uptime,
            current_serial=engine.current_serial,
            session_id=server.session_id,
            last_error=engine.last_error,
        )

    return RTRServerStatus(
        server_id=server.id,
        status=server.status,
        vrps_count=server.vrps_count,
        connected_clients=0,
        uptime=0,
        current_serial=server.current_serial,
        session_id=server.session_id,
        last_error=server.last_error,
    )


# ──────────────────────────────────────────────
# VRP 数据更新与回滚
# ──────────────────────────────────────────────


async def update_vrps(
    db: AsyncSession, server_id: int
) -> RTRServer:
    """更新 RTR 服务的 VRP 数据。

    流程：
    1. 从 VRP 服务获取最新 VRP 列表
    2. 计算差异（新增/移除/修改）
    3. 递增序列号
    4. 更新运行中引擎的 VRP 数据
    5. 通知所有连接的客户端
    6. 记录序列号历史

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        更新后的 RTRServer 对象

    Raises:
        ValueError: 服务不存在
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        raise ValueError(f"RTR 服务 ID {server_id} 不存在")

    # 获取最新 VRP
    vrps = await _load_vrps_from_db(db)
    new_vrp_dicts = [_vrp_to_dict(v) for v in vrps]

    # 计算差异
    engine = _running_engines.get(server_id)
    old_vrps = engine.get_vrps() if engine else []
    added, removed, modified = _compute_vrp_diff(old_vrps, new_vrp_dicts)

    # 递增序列号
    new_serial = server.current_serial + 1

    # 更新引擎数据
    if engine is not None:
        engine.update_vrps(new_vrp_dicts, serial=new_serial)
        # 通知客户端
        await engine.notify_clients(new_serial)

    # 更新数据库
    server.current_serial = new_serial
    server.vrps_count = len(new_vrp_dicts)
    if engine is not None:
        server.connected_clients = engine.connected_clients_count
    await db.commit()
    await db.refresh(server)

    # 记录序列号历史
    await _record_serial_history(
        db,
        server_id=server_id,
        serial_number=new_serial,
        change_type="incremental_update",
        added=added,
        removed=removed,
        modified=modified,
    )

    logger.info(
        "RTR 服务 VRP 数据已更新",
        server_id=server_id,
        serial=new_serial,
        vrps_count=len(new_vrp_dicts),
        added=added,
        removed=removed,
        modified=modified,
    )
    return server


async def rollback_serial(
    db: AsyncSession, server_id: int, target_serial: int
) -> RTRServer:
    """回滚到指定序列号。

    流程：
    1. 查找目标序列号对应的历史记录与快照
    2. 加载快照对应的 VRP 数据（当前实现使用当前 VRP 表）
    3. 更新引擎 VRP 数据
    4. 通知客户端
    5. 记录回滚历史

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID
        target_serial: 目标序列号

    Returns:
        更新后的 RTRServer 对象

    Raises:
        ValueError: 服务不存在或目标序列号不存在
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        raise ValueError(f"RTR 服务 ID {server_id} 不存在")

    # 查找目标序列号历史
    history_stmt = (
        select(RTRSerialHistory)
        .where(
            RTRSerialHistory.server_id == server_id,
            RTRSerialHistory.serial_number == target_serial,
        )
        .order_by(RTRSerialHistory.created_at.desc())
        .limit(1)
    )
    history_result = await db.execute(history_stmt)
    history = history_result.scalar_one_or_none()
    if history is None:
        raise ValueError(
            f"RTR 服务 {server_id} 不存在序列号 {target_serial} 的历史记录"
        )

    # 加载 VRP 数据（当前实现：使用当前 VRP 表）
    # TODO: 实际实现应从快照恢复 VRP 状态
    vrps = await _load_vrps_from_db(db)
    vrp_dicts = [_vrp_to_dict(v) for v in vrps]

    # 计算新序列号（回滚后递增）
    new_serial = server.current_serial + 1

    # 更新引擎
    engine = _running_engines.get(server_id)
    if engine is not None:
        engine.update_vrps(vrp_dicts, serial=new_serial)
        await engine.notify_clients(new_serial)

    # 更新数据库
    server.current_serial = new_serial
    server.vrps_count = len(vrp_dicts)
    if engine is not None:
        server.connected_clients = engine.connected_clients_count
    await db.commit()
    await db.refresh(server)

    # 记录回滚历史
    await _record_serial_history(
        db,
        server_id=server_id,
        serial_number=new_serial,
        change_type="rollback",
        added=0,
        removed=0,
        modified=0,
        note=f"回滚到序列号 {target_serial}",
    )

    logger.info(
        "RTR 服务序列号已回滚",
        server_id=server_id,
        target_serial=target_serial,
        new_serial=new_serial,
    )
    return server


# ──────────────────────────────────────────────
# 一致性检查
# ──────────────────────────────────────────────


async def check_consistency(
    db: AsyncSession, server_id: int
) -> RTRConsistencyCheckResult:
    """检查 RTR 服务端 VRP 与数据库 VRP 的一致性。

    比较运行中引擎内存中的 VRP 集合与数据库 VRP 表，返回差异列表。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        一致性检查结果

    Raises:
        ValueError: 服务不存在
    """
    server = await get_rtr_server(db, server_id)
    if server is None:
        raise ValueError(f"RTR 服务 ID {server_id} 不存在")

    # 获取数据库 VRP
    db_vrps = await _load_vrps_from_db(db)
    db_vrp_dicts = [_vrp_to_dict(v) for v in db_vrps]

    # 获取引擎 VRP
    engine = _running_engines.get(server_id)
    if engine is None:
        # 服务未运行，仅返回数据库统计
        return RTRConsistencyCheckResult(
            server_id=server_id,
            consistent=True,
            server_vrps_count=0,
            db_vrps_count=len(db_vrp_dicts),
            differences=[],
        )

    server_vrps = engine.get_vrps()

    # 构建索引：key = (prefix, prefix_length, origin_as)
    def _key(v: dict[str, Any]) -> tuple[str, int, int]:
        return (v["prefix"], v["prefix_length"], v["origin_as"])

    server_map: dict[tuple[str, int, int], dict[str, Any]] = {
        _key(v): v for v in server_vrps
    }
    db_map: dict[tuple[str, int, int], dict[str, Any]] = {
        _key(v): v for v in db_vrp_dicts
    }

    differences: list[RTRConsistencyDifference] = []

    # 仅服务端有
    for key, vrp in server_map.items():
        if key not in db_map:
            differences.append(
                RTRConsistencyDifference(
                    prefix=vrp["prefix"],
                    origin_as=vrp["origin_as"],
                    difference_type="only_in_server",
                    server_max_length=vrp.get("max_length"),
                    db_max_length=None,
                )
            )

    # 仅数据库有
    for key, vrp in db_map.items():
        if key not in server_map:
            differences.append(
                RTRConsistencyDifference(
                    prefix=vrp["prefix"],
                    origin_as=vrp["origin_as"],
                    difference_type="only_in_db",
                    server_max_length=None,
                    db_max_length=vrp.get("max_length"),
                )
            )

    # maxLength 不一致
    for key, server_vrp in server_map.items():
        db_vrp = db_map.get(key)
        if db_vrp is None:
            continue
        server_ml = server_vrp.get("max_length") or server_vrp["prefix_length"]
        db_ml = db_vrp.get("max_length") or db_vrp["prefix_length"]
        if server_ml != db_ml:
            differences.append(
                RTRConsistencyDifference(
                    prefix=server_vrp["prefix"],
                    origin_as=server_vrp["origin_as"],
                    difference_type="max_length_mismatch",
                    server_max_length=server_ml,
                    db_max_length=db_ml,
                )
            )

    return RTRConsistencyCheckResult(
        server_id=server_id,
        consistent=len(differences) == 0,
        server_vrps_count=len(server_vrps),
        db_vrps_count=len(db_vrp_dicts),
        differences=differences,
    )


# ──────────────────────────────────────────────
# 客户端会话与序列号历史查询
# ──────────────────────────────────────────────


async def get_rtr_sessions(
    db: AsyncSession, server_id: int
) -> list[RTRSession]:
    """获取 RTR 服务的客户端会话列表。

    优先返回运行中引擎的实时会话信息，回退到数据库历史记录。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID

    Returns:
        客户端会话列表
    """
    # 优先从运行中引擎获取实时数据
    engine = _running_engines.get(server_id)
    if engine is not None:
        now = datetime.now(timezone.utc)
        sessions: list[RTRSession] = []
        for client_info in engine.get_client_infos():
            session = RTRSession(
                server_id=server_id,
                client_ip=client_info.client_ip,
                client_port=client_info.client_port,
                client_version=client_info.client_version,
                session_state=client_info.session_state,
                last_serial=client_info.last_serial,
                connected_at=client_info.connected_at,
                last_activity_at=client_info.last_activity_at,
                bytes_sent=client_info.bytes_sent,
                bytes_received=client_info.bytes_received,
                created_at=now,
            )
            sessions.append(session)
        return sessions

    # 回退到数据库
    stmt = (
        select(RTRSession)
        .where(RTRSession.server_id == server_id)
        .order_by(RTRSession.connected_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_serial_history(
    db: AsyncSession, server_id: int, limit: int = 50
) -> list[RTRSerialHistory]:
    """获取 RTR 服务的序列号历史。

    Args:
        db: 异步数据库会话
        server_id: RTR 服务 ID
        limit: 返回记录数上限

    Returns:
        序列号历史列表（按时间倒序）
    """
    stmt = (
        select(RTRSerialHistory)
        .where(RTRSerialHistory.server_id == server_id)
        .order_by(RTRSerialHistory.created_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ──────────────────────────────────────────────
# 内部辅助函数
# ──────────────────────────────────────────────


async def _load_vrps_from_db(db: AsyncSession) -> list[VRP]:
    """从数据库加载所有有效 VRP。"""
    stmt = (
        select(VRP)
        .where(VRP.validation_status == "valid")
        .order_by(VRP.id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _vrp_to_dict(vrp: VRP) -> dict[str, Any]:
    """将 VRP ORM 对象转换为引擎使用的字典格式。"""
    return {
        "prefix": vrp.prefix,
        "prefix_length": vrp.prefix_length,
        "origin_as": vrp.origin_as,
        "max_length": vrp.max_length,
    }


def _compute_vrp_diff(
    old_vrps: list[dict[str, Any]],
    new_vrps: list[dict[str, Any]],
) -> tuple[int, int, int]:
    """计算两组 VRP 的差异。

    Args:
        old_vrps: 旧 VRP 列表
        new_vrps: 新 VRP 列表

    Returns:
        (added, removed, modified) 三元组
    """
    def _key(v: dict[str, Any]) -> tuple[str, int, int]:
        return (v["prefix"], v["prefix_length"], v["origin_as"])

    old_map = {_key(v): v for v in old_vrps}
    new_map = {_key(v): v for v in new_vrps}

    added = sum(1 for k in new_map if k not in old_map)
    removed = sum(1 for k in old_map if k not in new_map)
    modified = 0
    for k in new_map:
        if k in old_map:
            old_ml = old_map[k].get("max_length") or old_map[k]["prefix_length"]
            new_ml = new_map[k].get("max_length") or new_map[k]["prefix_length"]
            if old_ml != new_ml:
                modified += 1
    return added, removed, modified


async def _record_serial_history(
    db: AsyncSession,
    server_id: int,
    serial_number: int,
    change_type: str,
    added: int = 0,
    removed: int = 0,
    modified: int = 0,
    snapshot_id: int | None = None,
    note: str | None = None,
) -> RTRSerialHistory:
    """记录序列号变更历史。"""
    history = RTRSerialHistory(
        server_id=server_id,
        serial_number=serial_number,
        change_type=change_type,
        vrps_added=added,
        vrps_removed=removed,
        vrps_modified=modified,
        snapshot_id=snapshot_id,
        note=note,
    )
    db.add(history)
    await db.flush()
    await db.commit()
    await db.refresh(history)
    return history


# ──────────────────────────────────────────────
# 引擎池管理（供外部调用）
# ──────────────────────────────────────────────


def get_running_engine(server_id: int) -> RTRServerEngine | None:
    """获取运行中的 RTR 引擎实例。"""
    return _running_engines.get(server_id)


def get_all_running_engines() -> dict[int, RTRServerEngine]:
    """获取所有运行中的 RTR 引擎。"""
    return dict(_running_engines)


async def stop_all_engines() -> None:
    """停止所有运行中的 RTR 引擎（应用关闭时调用）。"""
    for server_id in list(_running_engines.keys()):
        engine = _running_engines.pop(server_id, None)
        if engine is not None:
            try:
                await engine.stop()
            except Exception as e:
                logger.warning(
                    "停止 RTR 引擎异常",
                    server_id=server_id,
                    error=str(e),
                )


__all__ = [
    "check_consistency",
    "count_rtr_servers",
    "create_rtr_server",
    "delete_rtr_server",
    "get_all_running_engines",
    "get_rtr_server",
    "get_rtr_server_by_name",
    "get_rtr_server_status",
    "get_rtr_servers",
    "get_rtr_sessions",
    "get_running_engine",
    "get_serial_history",
    "rollback_serial",
    "start_rtr_server",
    "stop_all_engines",
    "stop_rtr_server",
    "update_rtr_server",
    "update_vrps",
]
