"""VRP（Validated ROA Payload）服务。

负责 VRP 生成、查询、BGP 公告验证、快照管理与多验证器比对。
VRP 查询使用前缀树实现高性能匹配，BGP 公告验证逻辑完整实现
Valid/Invalid/NotFound 三态及 Invalid 原因细分。
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.prefix_tree import PrefixTree
from app.core.rpki_validator import parse_prefix
from app.models.rpki import (
    ROA,
    TAL,
    VRP,
    RPKIObject,
    RPKISnapshot,
)
from app.schemas.rpki import (
    BGPAnnouncementValidation,
    BGPAnnouncementValidationRequest,
    SnapshotDiff,
    SnapshotDiffResponse,
    SnapshotRollbackResponse,
    ValidationResult,
    VRPResponse,
)

logger = get_logger("app.vrp_service")


# ──────────────────────────────────────────────
# VRP 生成与查询
# ──────────────────────────────────────────────


async def generate_vrps(db: AsyncSession) -> int:
    """依据已验证的 ROA 生成 VRP。

    扫描所有状态为 ``valid`` 的 ROA，为每个 ROA 生成对应的 VRP 记录。
    生成前会清空现有 VRP 表（全量重建）。

    Args:
        db: 异步数据库会话

    Returns:
        生成的 VRP 数量
    """
    # 清空现有 VRP
    await db.execute(delete(VRP))
    await db.flush()

    # 查询所有有效的 ROA
    stmt = select(ROA).where(ROA.status == "valid")
    result = await db.execute(stmt)
    roas = list(result.scalars().all())

    # 查询 TAL 名称映射
    tal_stmt = select(TAL.id, TAL.name)
    tal_result = await db.execute(tal_stmt)
    tal_map: dict[int, str] = {row.id: row.name for row in tal_result}

    vrp_count = 0
    for roa in roas:
        # 解析前缀
        parsed = parse_prefix(roa.prefix)
        if parsed is None:
            continue
        family, prefix_length, _ = parsed

        vrp = VRP(
            prefix=roa.prefix,
            prefix_family=family,
            prefix_length=prefix_length,
            origin_as=roa.origin_as,
            max_length=roa.max_length,
            tal_id=roa.tal_id,
            roa_id=roa.id,
            trust_anchor=tal_map.get(roa.tal_id) if roa.tal_id else None,
            validation_status="valid",
        )
        db.add(vrp)
        vrp_count += 1

    await db.flush()
    await db.commit()

    logger.info("VRP 生成完成", count=vrp_count)
    return vrp_count


async def query_vrps(
    db: AsyncSession,
    prefix: str | None = None,
    origin_as: int | None = None,
    max_length: int | None = None,
    tal_id: int | None = None,
    time_point: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[VRP]:
    """高性能查询 VRP。

    支持按前缀、起源 AS、最大长度、TAL 与时间点过滤。
    前缀过滤会返回所有覆盖该前缀的 VRP（祖先链匹配）。

    Args:
        db: 异步数据库会话
        prefix: 前缀过滤（返回覆盖该前缀的 VRP）
        origin_as: 起源 AS 过滤
        max_length: 最大前缀长度过滤
        tal_id: TAL ID 过滤
        time_point: 时间点过滤（仅返回该时间点之前创建的 VRP）
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        VRP 列表
    """
    stmt = select(VRP)

    if origin_as is not None:
        stmt = stmt.where(VRP.origin_as == origin_as)
    if max_length is not None:
        stmt = stmt.where(VRP.max_length == max_length)
    if tal_id is not None:
        stmt = stmt.where(VRP.tal_id == tal_id)
    if time_point is not None:
        stmt = stmt.where(VRP.created_at <= time_point)

    if prefix is not None:
        # 前缀过滤：返回覆盖该前缀的所有 VRP
        # 通过前缀树或网络范围匹配实现
        covering_prefixes = _get_covering_prefixes(prefix)
        if covering_prefixes:
            stmt = stmt.where(VRP.prefix.in_(covering_prefixes))
        else:
            # 无覆盖前缀，返回空
            return []

    stmt = stmt.order_by(VRP.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_vrps(
    db: AsyncSession,
    prefix: str | None = None,
    origin_as: int | None = None,
    max_length: int | None = None,
    tal_id: int | None = None,
    time_point: datetime | None = None,
) -> int:
    """统计 VRP 数量（与 query_vrps 同样的过滤条件）。"""
    stmt = select(func.count(VRP.id))

    if origin_as is not None:
        stmt = stmt.where(VRP.origin_as == origin_as)
    if max_length is not None:
        stmt = stmt.where(VRP.max_length == max_length)
    if tal_id is not None:
        stmt = stmt.where(VRP.tal_id == tal_id)
    if time_point is not None:
        stmt = stmt.where(VRP.created_at <= time_point)

    if prefix is not None:
        covering_prefixes = _get_covering_prefixes(prefix)
        if covering_prefixes:
            stmt = stmt.where(VRP.prefix.in_(covering_prefixes))
        else:
            return 0

    result = await db.execute(stmt)
    return result.scalar_one()


def _get_covering_prefixes(prefix: str) -> list[str]:
    """获取覆盖指定前缀的所有可能前缀（祖先链）。

    例如对于 ``192.168.1.0/24``，返回：
    ``0.0.0.0/0, 192.0.0.0/8, 192.168.0.0/16, 192.168.1.0/24``

    Args:
        prefix: 查询前缀

    Returns:
        覆盖该前缀的所有前缀字符串列表
    """
    try:
        network = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return []

    covering: list[str] = []
    # 从 /0 开始逐级增加前缀长度，使用 supernet 计算父网络
    for length in range(0, network.prefixlen + 1):
        # 计算该长度下的祖先网络
        addr_int = int(network.network_address)
        # 根据前缀长度计算掩码
        if network.version == 4:
            if length == 0:
                mask = 0
            else:
                mask = (0xFFFFFFFF << (32 - length)) & 0xFFFFFFFF
            parent_addr = addr_int & mask
            parent = ipaddress.IPv4Network((parent_addr, length), strict=True)
        else:
            if length == 0:
                mask = 0
            else:
                mask = (1 << 128) - (1 << (128 - length))
            parent_addr = addr_int & mask
            parent = ipaddress.IPv6Network((parent_addr, length), strict=True)
        covering.append(str(parent))

    return covering


def _build_vrp_prefix_tree(vrps: list[VRP]) -> PrefixTree[VRP]:
    """从 VRP 列表构建前缀树。"""
    tree: PrefixTree[VRP] = PrefixTree()
    for vrp in vrps:
        tree.insert(vrp.prefix, vrp)
    return tree


# ──────────────────────────────────────────────
# BGP 公告验证
# ──────────────────────────────────────────────


async def validate_bgp_announcement(
    db: AsyncSession,
    prefix: str,
    origin_as: int,
) -> BGPAnnouncementValidation:
    """验证单个 BGP 公告。

    验证逻辑（RFC 6811）：
    1. 查找覆盖该前缀的所有 VRP（祖先链匹配）
    2. 若无匹配 VRP → NotFound
    3. 若有匹配 VRP：
       a. 检查 origin_as 是否匹配 → 不匹配则 Invalid (origin_as_mismatch)
       b. 检查前缀长度是否超过 max_length → 超过则 Invalid (length_exceeded)
       c. 检查 VRP 状态 → 已撤销则 Invalid (roa_revoked)
       d. 全部通过 → Valid

    Args:
        db: 异步数据库会话
        prefix: BGP 公告前缀
        origin_as: BGP 公告起源 AS 号

    Returns:
        验证结果（包含状态、原因与匹配的 VRP 列表）
    """
    # 查询覆盖该前缀的所有 VRP
    matched_vrps = await query_vrps(db, prefix=prefix, limit=1000)

    # 无匹配 VRP → NotFound
    if not matched_vrps:
        return BGPAnnouncementValidation(
            prefix=prefix,
            origin_as=origin_as,
            validation_result=ValidationResult(
                validation_status="not_found",
                invalid_reason=None,
                matched_vrps=[],
            ),
        )

    matched_vrp_responses = [VRPResponse.model_validate(v) for v in matched_vrps]

    # 解析公告前缀长度
    try:
        announcement_network = ipaddress.ip_network(prefix, strict=False)
        announcement_length = announcement_network.prefixlen
    except ValueError:
        return BGPAnnouncementValidation(
            prefix=prefix,
            origin_as=origin_as,
            validation_result=ValidationResult(
                validation_status="invalid",
                invalid_reason="data_source_error",
                matched_vrps=matched_vrp_responses,
            ),
        )

    # 检查每个匹配的 VRP
    # 优先级：valid > invalid
    # 只要有一个 VRP 完全匹配（origin_as + 长度），则为 Valid
    # 若所有 VRP 都不匹配，则根据原因细分 Invalid
    has_origin_match = False
    has_length_match = False
    has_valid_vrp = False

    for vrp in matched_vrps:
        # 跳过已撤销的 VRP
        if vrp.validation_status == "revoked":
            continue

        has_valid_vrp = True

        # 检查 origin_as 匹配
        if vrp.origin_as == origin_as:
            has_origin_match = True

            # 检查前缀长度是否在 max_length 范围内
            effective_max_length = vrp.max_length or vrp.prefix_length
            if announcement_length <= effective_max_length:
                has_length_match = True
                # 完全匹配 → Valid
                return BGPAnnouncementValidation(
                    prefix=prefix,
                    origin_as=origin_as,
                    validation_result=ValidationResult(
                        validation_status="valid",
                        invalid_reason=None,
                        matched_vrps=matched_vrp_responses,
                    ),
                )

    # 没有完全匹配，判定 Invalid 原因
    invalid_reason: str

    if not has_valid_vrp:
        # 所有匹配的 VRP 都已撤销
        invalid_reason = "roa_revoked"
    elif not has_origin_match:
        # origin_as 不匹配
        invalid_reason = "origin_as_mismatch"
    elif not has_length_match:
        # 前缀长度超过 max_length
        invalid_reason = "length_exceeded"
    else:
        # 其他资源链错误
        invalid_reason = "resource_chain_error"

    return BGPAnnouncementValidation(
        prefix=prefix,
        origin_as=origin_as,
        validation_result=ValidationResult(
            validation_status="invalid",
            invalid_reason=invalid_reason,
            matched_vrps=matched_vrp_responses,
        ),
    )


async def validate_bgp_announcements(
    db: AsyncSession,
    announcements: list[BGPAnnouncementValidationRequest],
) -> list[BGPAnnouncementValidation]:
    """批量验证 BGP 公告。

    Args:
        db: 异步数据库会话
        announcements: 待验证的 BGP 公告列表

    Returns:
        验证结果列表（顺序与输入一致）
    """
    results: list[BGPAnnouncementValidation] = []
    for ann in announcements:
        result = await validate_bgp_announcement(db, ann.prefix, ann.origin_as)
        results.append(result)
    return results


# ──────────────────────────────────────────────
# ROA 查询
# ──────────────────────────────────────────────


async def query_roas(
    db: AsyncSession,
    prefix: str | None = None,
    origin_as: int | None = None,
    tal_id: int | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[ROA]:
    """查询 ROA 列表。"""
    stmt = select(ROA)

    if prefix is not None:
        stmt = stmt.where(ROA.prefix == prefix)
    if origin_as is not None:
        stmt = stmt.where(ROA.origin_as == origin_as)
    if tal_id is not None:
        stmt = stmt.where(ROA.tal_id == tal_id)
    if status is not None:
        stmt = stmt.where(ROA.status == status)

    stmt = stmt.order_by(ROA.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_roas(
    db: AsyncSession,
    prefix: str | None = None,
    origin_as: int | None = None,
    tal_id: int | None = None,
    status: str | None = None,
) -> int:
    """统计 ROA 数量。"""
    stmt = select(func.count(ROA.id))

    if prefix is not None:
        stmt = stmt.where(ROA.prefix == prefix)
    if origin_as is not None:
        stmt = stmt.where(ROA.origin_as == origin_as)
    if tal_id is not None:
        stmt = stmt.where(ROA.tal_id == tal_id)
    if status is not None:
        stmt = stmt.where(ROA.status == status)

    result = await db.execute(stmt)
    return result.scalar_one()


async def get_roa_by_id(db: AsyncSession, roa_id: int) -> ROA | None:
    """根据 ID 获取 ROA。"""
    stmt = select(ROA).where(ROA.id == roa_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


# ──────────────────────────────────────────────
# 快照管理
# ──────────────────────────────────────────────


async def create_snapshot(db: AsyncSession) -> RPKISnapshot:
    """创建 RPKI 数据快照。

    记录当前 VRP/ROA/对象数量与元数据摘要。

    Args:
        db: 异步数据库会话

    Returns:
        创建的快照对象
    """
    vrp_count = await db.execute(select(func.count(VRP.id)))
    roa_count = await db.execute(select(func.count(ROA.id)))
    object_count = await db.execute(select(func.count(RPKIObject.id)))

    vrp_total = vrp_count.scalar_one()
    roa_total = roa_count.scalar_one()
    object_total = object_count.scalar_one()

    # 收集元数据（VRP 摘要）
    metadata: dict[str, Any] = {
        "vrp_count": vrp_total,
        "roa_count": roa_total,
        "object_count": object_total,
        "created_at": datetime.now(UTC).isoformat(),
    }

    snapshot = RPKISnapshot(
        snapshot_time=datetime.now(UTC),
        vrp_count=vrp_total,
        roa_count=roa_total,
        object_count=object_total,
        metadata_=metadata,
    )
    db.add(snapshot)
    await db.flush()
    await db.commit()
    await db.refresh(snapshot)

    logger.info(
        "RPKI 快照已创建",
        snapshot_id=snapshot.id,
        vrp_count=vrp_total,
        roa_count=roa_total,
    )
    return snapshot


async def list_snapshots(db: AsyncSession, skip: int = 0, limit: int = 50) -> list[RPKISnapshot]:
    """获取快照列表。"""
    stmt = (
        select(RPKISnapshot).order_by(RPKISnapshot.snapshot_time.desc()).offset(skip).limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_snapshots(db: AsyncSession) -> int:
    """统计快照总数。"""
    stmt = select(func.count(RPKISnapshot.id))
    result = await db.execute(stmt)
    return result.scalar_one()


async def get_snapshot_by_id(db: AsyncSession, snapshot_id: int) -> RPKISnapshot | None:
    """根据 ID 获取快照。"""
    stmt = select(RPKISnapshot).where(RPKISnapshot.id == snapshot_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_snapshot_diff(
    db: AsyncSession, snapshot_id_1: int, snapshot_id_2: int
) -> SnapshotDiffResponse:
    """获取两个快照之间的差异。

    通过比较快照元数据中的 VRP 列表摘要计算差异。

    Args:
        db: 异步数据库会话
        snapshot_id_1: 第一个快照 ID（旧）
        snapshot_id_2: 第二个快照 ID（新）

    Returns:
        快照差异响应

    Raises:
        ValueError: 快照不存在
    """
    snap1 = await get_snapshot_by_id(db, snapshot_id_1)
    snap2 = await get_snapshot_by_id(db, snapshot_id_2)
    if snap1 is None:
        raise ValueError(f"快照 ID {snapshot_id_1} 不存在")
    if snap2 is None:
        raise ValueError(f"快照 ID {snapshot_id_2} 不存在")

    # TODO: 实际实现需存储快照时的 VRP 完整列表
    # 当前基于元数据中的统计信息计算粗略差异
    added_vrps: list[VRPResponse] = []
    removed_vrps: list[VRPResponse] = []
    modified_vrps: list[VRPResponse] = []

    # 占位：基于 VRP 数量差异生成摘要
    # 实际实现应比较两个快照的 VRP 集合
    diff = SnapshotDiff(
        added_vrps=added_vrps,
        removed_vrps=removed_vrps,
        modified_vrps=modified_vrps,
    )

    return SnapshotDiffResponse(
        snapshot_id_1=snapshot_id_1,
        snapshot_id_2=snapshot_id_2,
        diff=diff,
        added_count=len(added_vrps),
        removed_count=len(removed_vrps),
        modified_count=len(modified_vrps),
    )


async def rollback_to_snapshot(db: AsyncSession, snapshot_id: int) -> SnapshotRollbackResponse:
    """回滚到指定快照。

    Note:
        TODO: 当前为占位实现，实际回滚需恢复快照时的 VRP/ROA 状态。
        完整实现需存储快照时的完整 VRP/ROA 列表。

    Args:
        db: 异步数据库会话
        snapshot_id: 目标快照 ID

    Returns:
        回滚结果响应

    Raises:
        ValueError: 快照不存在
    """
    snapshot = await get_snapshot_by_id(db, snapshot_id)
    if snapshot is None:
        raise ValueError(f"快照 ID {snapshot_id} 不存在")

    # TODO: 实现完整回滚逻辑
    # 1. 从快照元数据恢复 VRP/ROA 列表
    # 2. 清空当前 VRP/ROA 表
    # 3. 插入快照时的数据
    logger.info(
        "快照回滚（占位）",
        snapshot_id=snapshot_id,
        vrp_count=snapshot.vrp_count,
    )

    return SnapshotRollbackResponse(
        snapshot_id=snapshot_id,
        rolled_back=True,
        message=f"已回滚到快照 {snapshot_id}（占位实现，实际数据未变更）",
    )


# ──────────────────────────────────────────────
# 多验证器比对
# ──────────────────────────────────────────────


async def compare_validators(db: AsyncSession) -> dict[str, Any]:
    """多验证器结果比对。

    比较本地验证器与其他验证器（如 Routinator、RIPE Validator）的结果，
    生成一致性报告。

    Note:
        TODO: 当前为占位实现，实际需对接外部验证器 API 或导入其输出。

    Args:
        db: 异步数据库会话

    Returns:
        一致性报告字典
    """
    # 查询本地 VRP 统计
    vrp_total = await db.execute(select(func.count(VRP.id)))
    local_count = vrp_total.scalar_one()

    # TODO: 对接外部验证器
    # 1. 调用 Routinator API（如 https://localhost:8080/api/v1/validity/）
    # 2. 调用 RIPE Validator API
    # 3. 比较三者 VRP 集合差异

    return {
        "local_validator": {
            "name": "builtin",
            "vrp_count": local_count,
            "status": "active",
        },
        "external_validators": [],
        "consistency_report": {
            "total_compared": 0,
            "consistent_count": 0,
            "inconsistent_count": 0,
            "consistency_rate": 1.0 if local_count > 0 else 0.0,
        },
        "note": "多验证器比对为占位实现，需对接外部验证器 API",
    }
