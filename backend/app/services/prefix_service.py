"""IP 前缀服务：CRUD、批量导入、前缀树与重叠检查。"""

from __future__ import annotations

import ipaddress
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.prefix import Prefix
from app.models.user import User
from app.schemas.prefix import (
    PrefixBatchImportError,
    PrefixBatchImportResult,
    PrefixCreate,
    PrefixUpdate,
)


def _parse_cidr(prefix: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network:
    """解析 CIDR 字符串为网络对象。"""
    return ipaddress.ip_network(prefix, strict=False)


async def create_prefix(
    db: AsyncSession, prefix_create: PrefixCreate, user: User | None = None
) -> Prefix:
    """创建前缀。

    自动从 CIDR 解析 prefix_family 与 prefix_length，
    并通过 ``find_parent_prefix`` 设置 parent_id。

    Args:
        db: 异步数据库会话
        prefix_create: 前缀创建数据
        user: 操作用户（用于多租户隔离）

    Returns:
        创建后的 Prefix 对象

    Raises:
        ValueError: 前缀已存在或与现有前缀重叠
    """
    # 检查唯一性
    existing = await get_prefix_by_cidr(db, prefix_create.prefix)
    if existing is not None:
        raise ValueError(f"前缀 {prefix_create.prefix} 已存在")

    net = _parse_cidr(prefix_create.prefix)
    prefix_family = net.version
    prefix_length = net.prefixlen

    # 查找父前缀
    parent = await find_parent_prefix(db, prefix_create.prefix)
    parent_id = parent.id if parent is not None else None

    # 检查重叠（与同族但非父子关系的前缀）
    overlaps = await check_prefix_overlap(db, prefix_create.prefix)
    if overlaps:
        # 仅在存在非父子关系的重叠时报错
        overlap_desc = ", ".join(p.prefix for p in overlaps)
        raise ValueError(f"前缀与已有前缀重叠: {overlap_desc}")

    prefix = Prefix(
        prefix=str(net),
        prefix_family=prefix_family,
        prefix_length=prefix_length,
        parent_id=parent_id,
        status=prefix_create.status,
        importance=prefix_create.importance,
        business_service=prefix_create.business_service,
        region=prefix_create.region,
        site=prefix_create.site,
        cloud_zone=prefix_create.cloud_zone,
        customer_id=prefix_create.customer_id,
        tags=prefix_create.tags,
        description=prefix_create.description,
        registered_at=prefix_create.registered_at,
        expired_at=prefix_create.expired_at,
        tenant_id=getattr(user, "tenant_id", None) if user else None,
    )
    db.add(prefix)
    await db.flush()
    await db.commit()
    await db.refresh(prefix)
    return prefix


async def get_prefix(db: AsyncSession, prefix_id: int) -> Prefix | None:
    """根据 ID 获取前缀。"""
    stmt = (
        select(Prefix)
        .options(selectinload(Prefix.children))
        .where(Prefix.id == prefix_id)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_prefix_by_cidr(
    db: AsyncSession, cidr: str
) -> Prefix | None:
    """根据 CIDR 字符串获取前缀。"""
    stmt = select(Prefix).where(Prefix.prefix == cidr)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_prefixes(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Prefix]:
    """分页查询前缀，支持按 family/status/importance/region/tags 过滤。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 ``family``、``status``、``importance``、
            ``region``、``site``、``cloud_zone``、``customer_id``、``tag``
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        前缀列表
    """
    stmt = select(Prefix)
    if filters:
        if filters.get("family") is not None:
            stmt = stmt.where(Prefix.prefix_family == filters["family"])
        if filters.get("status"):
            stmt = stmt.where(Prefix.status == filters["status"])
        if filters.get("importance"):
            stmt = stmt.where(Prefix.importance == filters["importance"])
        if filters.get("region"):
            stmt = stmt.where(Prefix.region == filters["region"])
        if filters.get("site"):
            stmt = stmt.where(Prefix.site == filters["site"])
        if filters.get("cloud_zone"):
            stmt = stmt.where(Prefix.cloud_zone == filters["cloud_zone"])
        if filters.get("customer_id") is not None:
            stmt = stmt.where(Prefix.customer_id == filters["customer_id"])
        if filters.get("tag"):
            # JSON 数组包含查询（PostgreSQL）
            stmt = stmt.where(Prefix.tags.contains([filters["tag"]]))
        if filters.get("business_service"):
            stmt = stmt.where(
                Prefix.business_service == filters["business_service"]
            )

    stmt = stmt.order_by(Prefix.prefix).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_prefixes(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计前缀数量。"""
    stmt = select(func.count(Prefix.id))
    if filters:
        if filters.get("family") is not None:
            stmt = stmt.where(Prefix.prefix_family == filters["family"])
        if filters.get("status"):
            stmt = stmt.where(Prefix.status == filters["status"])
        if filters.get("importance"):
            stmt = stmt.where(Prefix.importance == filters["importance"])
        if filters.get("region"):
            stmt = stmt.where(Prefix.region == filters["region"])
        if filters.get("site"):
            stmt = stmt.where(Prefix.site == filters["site"])
        if filters.get("cloud_zone"):
            stmt = stmt.where(Prefix.cloud_zone == filters["cloud_zone"])
        if filters.get("customer_id") is not None:
            stmt = stmt.where(Prefix.customer_id == filters["customer_id"])
        if filters.get("tag"):
            stmt = stmt.where(Prefix.tags.contains([filters["tag"]]))
        if filters.get("business_service"):
            stmt = stmt.where(
                Prefix.business_service == filters["business_service"]
            )

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_prefix(
    db: AsyncSession, prefix: Prefix, prefix_update: PrefixUpdate
) -> Prefix:
    """更新前缀。

    若更新了 prefix 字段，则同步刷新 prefix_family、prefix_length 与 parent_id。

    Args:
        db: 异步数据库会话
        prefix: 待更新的前缀对象
        prefix_update: 更新数据

    Returns:
        更新后的前缀对象

    Raises:
        ValueError: 新前缀与现有前缀重叠
    """
    update_data = prefix_update.model_dump(exclude_unset=True)

    if "prefix" in update_data and update_data["prefix"] is not None:
        new_prefix = update_data["prefix"]
        # 检查唯一性（排除自身）
        existing = await get_prefix_by_cidr(db, new_prefix)
        if existing is not None and existing.id != prefix.id:
            raise ValueError(f"前缀 {new_prefix} 已存在")

        net = _parse_cidr(new_prefix)
        prefix.prefix = str(net)
        prefix.prefix_family = net.version
        prefix.prefix_length = net.prefixlen
        # 重新查找父前缀
        parent = await find_parent_prefix(db, str(net))
        prefix.parent_id = parent.id if parent is not None else None
        update_data.pop("prefix")

    # 处理 parent_id 显式设置
    if "parent_id" in update_data:
        prefix.parent_id = update_data.pop("parent_id")

    # 应用其他字段
    for field, value in update_data.items():
        setattr(prefix, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(prefix)
    return prefix


async def delete_prefix(db: AsyncSession, prefix: Prefix) -> None:
    """删除前缀。

    子前缀的 parent_id 将因外键 ON DELETE SET NULL 自动置空。
    """
    await db.delete(prefix)
    await db.commit()


async def batch_import_prefixes(
    db: AsyncSession,
    prefixes: list[PrefixCreate],
    user: User | None = None,
) -> PrefixBatchImportResult:
    """批量导入前缀。

    逐条创建，单条失败不影响其他项，最终返回成功与失败统计。

    Args:
        db: 异步数据库会话
        prefixes: 待导入的前缀列表
        user: 操作用户

    Returns:
        导入结果统计
    """
    total = len(prefixes)
    errors: list[PrefixBatchImportError] = []
    success = 0

    for idx, item in enumerate(prefixes):
        try:
            await create_prefix(db, item, user)
            success += 1
        except Exception as e:  # noqa: BLE001
            errors.append(
                PrefixBatchImportError(
                    index=idx,
                    prefix=item.prefix,
                    error=str(e),
                )
            )
            # 回滚当前会话以避免污染后续插入
            await db.rollback()

    return PrefixBatchImportResult(
        total=total,
        success=success,
        failed=len(errors),
        errors=errors,
    )


async def get_prefix_tree(
    db: AsyncSession, root_id: int | None = None
) -> list[Prefix]:
    """获取前缀树。

    Args:
        db: 异步数据库会话
        root_id: 指定根节点 ID；为 None 时返回所有顶层前缀（parent_id 为空）

    Returns:
        前缀列表（已预加载 children 关系）
    """
    if root_id is not None:
        stmt = (
            select(Prefix)
            .options(selectinload(Prefix.children))
            .where(Prefix.id == root_id)
        )
        result = await db.execute(stmt)
        root = result.scalar_one_or_none()
        return [root] if root is not None else []

    # 返回所有顶层前缀
    stmt = (
        select(Prefix)
        .options(selectinload(Prefix.children))
        .where(Prefix.parent_id.is_(None))
        .order_by(Prefix.prefix)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def find_parent_prefix(
    db: AsyncSession, prefix: str
) -> Prefix | None:
    """查找给定前缀的父前缀（CIDR 包含关系）。

    在所有已登记前缀中，找到包含给定前缀且前缀长度最大的那个
    （即最接近的祖先）。

    Args:
        db: 异步数据库会话
        prefix: CIDR 字符串

    Returns:
        父前缀对象，无则返回 None
    """
    try:
        target_net = _parse_cidr(prefix)
    except ValueError:
        return None

    stmt = select(Prefix).where(Prefix.prefix_family == target_net.version)
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    best_parent: Prefix | None = None
    best_length = -1
    for cand in candidates:
        try:
            cand_net = _parse_cidr(cand.prefix)
        except ValueError:
            continue
        # 跳过自身
        if cand_net == target_net:
            continue
        # cand 必须严格包含 target
        if (
            cand_net.network_address <= target_net.network_address
            and cand_net.broadcast_address >= target_net.broadcast_address
            and cand_net.prefixlen < target_net.prefixlen
        ):
            if cand_net.prefixlen > best_length:
                best_length = cand_net.prefixlen
                best_parent = cand
    return best_parent


async def check_prefix_overlap(
    db: AsyncSession, prefix: str
) -> list[Prefix]:
    """检查前缀重叠。

    返回与给定前缀存在重叠但非严格父子关系的前缀列表。
    严格父子关系（包含且更具体）不算重叠。

    Args:
        db: 异步数据库会话
        prefix: CIDR 字符串

    Returns:
        重叠前缀列表
    """
    try:
        target_net = _parse_cidr(prefix)
    except ValueError:
        return []

    stmt = select(Prefix).where(Prefix.prefix_family == target_net.version)
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    overlaps: list[Prefix] = []
    for cand in candidates:
        try:
            cand_net = _parse_cidr(cand.prefix)
        except ValueError:
            continue
        # 跳过完全相同
        if cand_net == target_net:
            continue
        # 检查是否重叠（任一包含另一方的部分地址但不构成父子关系）
        if cand_net.overlaps(target_net):
            # 严格父子关系不算重叠
            is_parent_of = (
                cand_net.prefixlen < target_net.prefixlen
                and cand_net.network_address <= target_net.network_address
                and cand_net.broadcast_address >= target_net.broadcast_address
            )
            is_child_of = (
                cand_net.prefixlen > target_net.prefixlen
                and target_net.network_address <= cand_net.network_address
                and target_net.broadcast_address >= cand_net.broadcast_address
            )
            if not (is_parent_of or is_child_of):
                overlaps.append(cand)
    return overlaps


__all__ = [
    "batch_import_prefixes",
    "check_prefix_overlap",
    "count_prefixes",
    "create_prefix",
    "delete_prefix",
    "find_parent_prefix",
    "get_prefix",
    "get_prefix_by_cidr",
    "get_prefix_tree",
    "get_prefixes",
    "update_prefix",
]
