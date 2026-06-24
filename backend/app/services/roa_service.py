"""ROA 生命周期管理服务。

提供 ROA 查询、详情、缺失检测、冲突检测、maxLength 风险检查、
ROA 创建建议与变更影响评估等功能。

设计要点：
- 查询利用已有索引（ix_roas_prefix_origin_as、ix_roas_origin_as 等）
- maxLength 风险检查分析劫持面（过宽授权可能被利用的前缀范围）
- ROA 创建建议遵循 minimal ROA 原则（maxLength = 实际公告前缀长度）
- 变更影响评估识别高风险变更（核心前缀变 Invalid）
"""

from __future__ import annotations

import ipaddress

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.prefix import Prefix
from app.models.rpki import ROA, VRP
from app.schemas.roa import (
    MaxLengthRiskResult,
    ROAChangeImpact,
    ROAChangeParams,
    ROAConflictCheckResult,
    ROACreationSuggestion,
    ROAMissingCheckResult,
    ROAQueryParams,
    ROAValidationChange,
)
from app.schemas.rpki import ROAResponse

logger = get_logger("app.roa_service")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _parse_network(prefix: str) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    """解析前缀字符串为网络对象，失败返回 None。"""
    try:
        return ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return None


def _get_covering_prefixes(prefix: str) -> list[str]:
    """获取覆盖指定前缀的所有祖先前缀（含自身）。

    用于查找覆盖某前缀的所有 ROA/VRP。
    """
    network = _parse_network(prefix)
    if network is None:
        return []
    covering: list[str] = []
    for length in range(0, network.prefixlen + 1):
        addr_int = int(network.network_address)
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


def _get_more_specific_prefixes(prefix: str, max_length: int) -> list[str]:
    """计算过宽授权的劫持面：从 prefix.prefixlen+1 到 max_length 的所有子前缀。

    例如 prefix=192.168.1.0/24, max_length=26 时，
    返回所有 /25 与 /26 子前缀（共 4 个：1 个 /25 + 2 个 /26 的兄弟节点）。

    注意：当 max_length 远大于 prefixlen 时，子前缀数量呈指数增长，
    此处限制最多返回 1024 个子前缀以避免内存爆炸。
    """
    network = _parse_network(prefix)
    if network is None:
        return []
    if max_length <= network.prefixlen:
        return []

    surface: list[str] = []
    # 逐级展开子前缀
    current_level: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [network]
    for length in range(network.prefixlen + 1, max_length + 1):
        next_level: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for net in current_level:
            for sub in net.subnets(new_prefix=length):
                next_level.append(sub)
                surface.append(str(sub))
                if len(surface) >= 1024:
                    return surface
        current_level = next_level
    return surface


async def _get_prefix_metadata(
    db: AsyncSession, prefix: str
) -> tuple[str | None, str | None, int | None]:
    """查询前缀对应的资产元数据（重要度、业务归属、客户 ID）。

    Returns:
        元组 (importance, business_service, customer_id)，无匹配时均为 None
    """
    stmt = select(Prefix).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    prefix_obj = result.scalar_one_or_none()
    if prefix_obj is None:
        return None, None, None
    return (
        prefix_obj.importance,
        prefix_obj.business_service,
        prefix_obj.customer_id,
    )


# ──────────────────────────────────────────────
# ROA 查询
# ──────────────────────────────────────────────


async def get_roas(db: AsyncSession, query_params: ROAQueryParams) -> tuple[list[ROA], int]:
    """查询 ROA 列表（支持过滤与分页）。

    利用 ix_roas_prefix_origin_as、ix_roas_origin_as、ix_roas_tal_id、
    ix_roas_status 索引实现高性能过滤。

    Args:
        db: 异步数据库会话
        query_params: 查询参数

    Returns:
        元组 (ROA 列表, 总数)
    """
    stmt = select(ROA)
    count_stmt = select(func.count(ROA.id))

    if query_params.prefix is not None:
        stmt = stmt.where(ROA.prefix == query_params.prefix)
        count_stmt = count_stmt.where(ROA.prefix == query_params.prefix)
    if query_params.origin_as is not None:
        stmt = stmt.where(ROA.origin_as == query_params.origin_as)
        count_stmt = count_stmt.where(ROA.origin_as == query_params.origin_as)
    if query_params.max_length is not None:
        stmt = stmt.where(ROA.max_length == query_params.max_length)
        count_stmt = count_stmt.where(ROA.max_length == query_params.max_length)
    if query_params.status is not None:
        stmt = stmt.where(ROA.status == query_params.status)
        count_stmt = count_stmt.where(ROA.status == query_params.status)
    if query_params.tal_id is not None:
        stmt = stmt.where(ROA.tal_id == query_params.tal_id)
        count_stmt = count_stmt.where(ROA.tal_id == query_params.tal_id)

    # 分页
    skip = (query_params.page - 1) * query_params.page_size
    stmt = stmt.order_by(ROA.id).offset(skip).limit(query_params.page_size)

    result = await db.execute(stmt)
    roas = list(result.scalars().all())

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return roas, total


async def get_roa_detail(db: AsyncSession, roa_id: int) -> ROA | None:
    """获取 ROA 详情（含关联 BGP 公告和 VRP）。

    Args:
        db: 异步数据库会话
        roa_id: ROA ID

    Returns:
        ROA 对象（已预加载 VRP 关系），不存在返回 None
    """
    stmt = select(ROA).options(selectinload(ROA.vrps)).where(ROA.id == roa_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_roa_by_prefix_origin(db: AsyncSession, prefix: str, origin_as: int) -> list[ROA]:
    """按前缀和 origin AS 查询 ROA。

    利用 ix_roas_prefix_origin_as 复合索引实现高性能查询。

    Args:
        db: 异步数据库会话
        prefix: 网络前缀
        origin_as: 起源 AS 号

    Returns:
        匹配的 ROA 列表
    """
    stmt = select(ROA).where(ROA.prefix == prefix, ROA.origin_as == origin_as)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_related_bgp_announcements(db: AsyncSession, roa: ROA) -> list[BGPAnnouncement]:
    """获取与 ROA 关联的 BGP 公告。

    关联规则：
    - 公告前缀等于 ROA 前缀，或
    - 公告前缀是 ROA 前缀的子网（被 ROA 覆盖），且
      公告前缀长度 <= ROA.maxLength（或 ROA.maxLength 为空时 <= ROA.prefix_length）

    Args:
        db: 异步数据库会话
        roa: ROA 对象

    Returns:
        关联的 BGP 公告列表
    """
    effective_max_length = roa.max_length or roa.prefix_length
    roa_network = _parse_network(roa.prefix)
    if roa_network is None:
        return []

    # 查询同族、前缀长度在覆盖范围内的所有公告
    stmt = select(BGPAnnouncement).where(
        BGPAnnouncement.prefix_family == roa.prefix_family,
        BGPAnnouncement.prefix_length >= roa.prefix_length,
        BGPAnnouncement.prefix_length <= effective_max_length,
    )
    result = await db.execute(stmt)
    candidates = list(result.scalars().all())

    # 过滤：公告前缀必须是 ROA 前缀的子网
    related: list[BGPAnnouncement] = []
    for ann in candidates:
        ann_network = _parse_network(ann.prefix)
        if ann_network is None:
            continue
        if ann_network.version != roa_network.version:
            continue
        try:
            if ann_network.subnet_of(roa_network):
                related.append(ann)
        except ValueError:
            continue
    return related


# ──────────────────────────────────────────────
# ROA 缺失检测
# ──────────────────────────────────────────────


async def check_roa_missing(db: AsyncSession) -> list[ROAMissingCheckResult]:
    """ROA 缺失检测。

    扫描所有 BGP 公告（按 prefix + origin_as 去重），检查每个公告：
    1. 是否存在匹配的 ROA（同 prefix + origin_as）
    2. 是否存在匹配的 VRP（覆盖该前缀的 VRP）
    3. BGP 公告的 RPKI 验证状态

    Args:
        db: 异步数据库会话

    Returns:
        缺失检测结果列表（仅返回 has_roa=False 的项）
    """
    # 查询所有 BGP 公告（按 prefix + origin_as 去重）
    stmt = (
        select(
            BGPAnnouncement.prefix,
            BGPAnnouncement.origin_as,
            BGPAnnouncement.rpki_validation_status,
        )
        .where(BGPAnnouncement.origin_as.is_not(None))
        .distinct()
    )
    result = await db.execute(stmt)
    announcement_rows = list(result.all())

    if not announcement_rows:
        return []

    # 批量查询所有 ROA 的 (prefix, origin_as) 集合
    roa_stmt = select(ROA.prefix, ROA.origin_as)
    roa_result = await db.execute(roa_stmt)
    roa_set: set[tuple[str, int]] = {(row.prefix, row.origin_as) for row in roa_result}

    # 批量查询所有 VRP 的 (prefix, origin_as) 集合
    vrp_stmt = select(VRP.prefix, VRP.origin_as)
    vrp_result = await db.execute(vrp_stmt)
    vrp_set: set[tuple[str, int]] = {(row.prefix, row.origin_as) for row in vrp_result}

    missing_results: list[ROAMissingCheckResult] = []
    for row in announcement_rows:
        prefix = row.prefix
        origin_as = row.origin_as
        if origin_as is None:
            continue

        has_roa = (prefix, origin_as) in roa_set
        has_vrp = (prefix, origin_as) in vrp_set
        validation_status = row.rpki_validation_status or "not_found"

        if not has_roa:
            # 查询前缀元数据
            importance, business_service, customer_id = await _get_prefix_metadata(db, prefix)
            missing_results.append(
                ROAMissingCheckResult(
                    prefix=prefix,
                    origin_as=origin_as,
                    has_roa=has_roa,
                    has_vrp=has_vrp,
                    validation_status=validation_status,
                    importance=importance,
                    business_service=business_service,
                    customer_id=customer_id,
                )
            )

    logger.info(
        "ROA 缺失检测完成",
        total_announcements=len(announcement_rows),
        missing_count=len(missing_results),
    )
    return missing_results


# ──────────────────────────────────────────────
# ROA 冲突检测
# ──────────────────────────────────────────────


async def check_roa_conflict(db: AsyncSession) -> list[ROAConflictCheckResult]:
    """ROA 冲突检测。

    检测两类冲突：
    1. 同前缀多 AS 授权（multiple_origin_as）：
       同一前缀被授权给多个不同的 origin AS
    2. ROA 与实际公告不匹配（roa_bgp_mismatch）：
       ROA 授权的 origin AS 与实际公告的 origin AS 不一致

    Args:
        db: 异步数据库会话

    Returns:
        冲突检测结果列表
    """
    conflicts: list[ROAConflictCheckResult] = []

    # 1. 检测同前缀多 AS 授权
    # 按 prefix 分组，统计不同的 origin_as 数量
    stmt = (
        select(
            ROA.prefix,
            func.count(ROA.origin_as.distinct()).label("origin_count"),
        )
        .where(ROA.status == "valid")
        .group_by(ROA.prefix)
        .having(func.count(ROA.origin_as.distinct()) > 1)
    )
    result = await db.execute(stmt)
    multi_origin_rows = list(result.all())

    for row in multi_origin_rows:
        # 查询该前缀下的所有 ROA
        roa_stmt = select(ROA).where(ROA.prefix == row.prefix)
        roa_result = await db.execute(roa_stmt)
        roas = list(roa_result.scalars().all())
        conflicts.append(
            ROAConflictCheckResult(
                prefix=row.prefix,
                origin_as=None,
                conflicting_roas=[ROAResponse.model_validate(r) for r in roas],
                conflict_type="multiple_origin_as",
                description=(f"前缀 {row.prefix} 被授权给 {row.origin_count} 个不同的起源 AS"),
            )
        )

    # 2. 检测 ROA 与实际公告不匹配
    # 查询所有 BGP 公告（按 prefix + origin_as 去重）
    bgp_stmt = (
        select(
            BGPAnnouncement.prefix,
            BGPAnnouncement.origin_as,
        )
        .where(BGPAnnouncement.origin_as.is_not(None))
        .distinct()
    )
    bgp_result = await db.execute(bgp_stmt)
    bgp_announcements = list(bgp_result.all())

    for ann in bgp_announcements:
        if ann.origin_as is None:
            continue
        # 查询覆盖该前缀的所有 ROA（祖先链匹配）
        covering_prefixes = _get_covering_prefixes(ann.prefix)
        if not covering_prefixes:
            continue
        roa_stmt = select(ROA).where(
            ROA.prefix.in_(covering_prefixes),
            ROA.status == "valid",
        )
        roa_result = await db.execute(roa_stmt)
        covering_roas = list(roa_result.scalars().all())

        if not covering_roas:
            continue

        # 检查是否有 origin_as 匹配的 ROA
        has_origin_match = any(r.origin_as == ann.origin_as for r in covering_roas)
        if not has_origin_match:
            # 存在覆盖 ROA 但 origin_as 不匹配 → 冲突
            conflicts.append(
                ROAConflictCheckResult(
                    prefix=ann.prefix,
                    origin_as=ann.origin_as,
                    conflicting_roas=[ROAResponse.model_validate(r) for r in covering_roas],
                    conflict_type="roa_bgp_mismatch",
                    description=(
                        f"前缀 {ann.prefix} 的实际公告 origin AS "
                        f"{ann.origin_as} 与覆盖 ROA 的 origin AS 不匹配"
                    ),
                )
            )

    logger.info(
        "ROA 冲突检测完成",
        total_conflicts=len(conflicts),
        multi_origin_count=len(multi_origin_rows),
    )
    return conflicts


# ──────────────────────────────────────────────
# maxLength 风险检查
# ──────────────────────────────────────────────


async def check_max_length_risk(db: AsyncSession, roa_id: int) -> MaxLengthRiskResult | None:
    """maxLength 风险检查。

    分析 ROA 的 maxLength 设置是否过宽，可能导致被劫持：
    1. 识别过宽授权（maxLength 远大于实际公告长度）
    2. 识别未实际使用的子前缀授权
    3. 分析可能被利用的劫持面
    4. 提出精确化建议

    风险等级判定：
    - high: maxLength - 实际公告长度 >= 8，或存在多个未使用的子前缀
    - medium: maxLength - 实际公告长度 >= 3
    - low: maxLength - 实际公告长度 >= 1
    - none: maxLength = 实际公告长度（minimal ROA）

    Args:
        db: 异步数据库会话
        roa_id: ROA ID

    Returns:
        风险检查结果，ROA 不存在返回 None
    """
    roa = await get_roa_detail(db, roa_id)
    if roa is None:
        return None

    # 获取关联的 BGP 公告
    related_announcements = await get_related_bgp_announcements(db, roa)

    # 计算实际公告的前缀长度
    actual_lengths: list[int] = []
    actual_prefixes: list[str] = []
    for ann in related_announcements:
        actual_lengths.append(ann.prefix_length)
        actual_prefixes.append(ann.prefix)

    # 推荐 maxLength = 实际公告的最大前缀长度（minimal ROA 原则）
    if actual_lengths:
        recommended_max_length = max(actual_lengths)
    else:
        # 无实际公告时，推荐等于 ROA 前缀长度
        recommended_max_length = roa.prefix_length

    current_max_length = roa.max_length or roa.prefix_length

    # 计算风险等级与风险因素
    risk_factors: list[str] = []
    diff = current_max_length - recommended_max_length

    if diff <= 0:
        risk_level = "none"
    elif diff < 3:
        risk_level = "low"
        risk_factors.append(f"maxLength 比实际公告长度大 {diff} 位")
    elif diff < 8:
        risk_level = "medium"
        risk_factors.append(f"maxLength 比实际公告长度大 {diff} 位，存在一定劫持风险")
    else:
        risk_level = "high"
        risk_factors.append(f"maxLength 比实际公告长度大 {diff} 位，存在严重劫持风险")

    # 检查未实际使用的子前缀授权
    if actual_lengths and current_max_length > recommended_max_length:
        risk_factors.append(
            f"maxLength={current_max_length} 授权了未实际使用的子前缀"
            f"（实际公告最大长度为 {recommended_max_length}）"
        )

    # 检查无实际公告但有 maxLength 设置的情况
    if not actual_lengths and roa.max_length is not None:
        risk_factors.append("ROA 设置了 maxLength 但无对应的实际 BGP 公告")
        risk_level = "medium" if risk_level == "none" else risk_level

    # 计算劫持面：从 roa.prefix_length+1 到 current_max_length 的所有子前缀
    hijack_surface: list[str] = []
    if current_max_length > roa.prefix_length:
        hijack_surface = _get_more_specific_prefixes(roa.prefix, current_max_length)
        if hijack_surface:
            risk_factors.append(f"劫持面包含 {len(hijack_surface)} 个可能被利用的子前缀")

    return MaxLengthRiskResult(
        roa_id=roa.id,
        prefix=roa.prefix,
        origin_as=roa.origin_as,
        current_max_length=roa.max_length,
        recommended_max_length=recommended_max_length,
        risk_level=risk_level,
        risk_factors=risk_factors,
        hijack_surface=hijack_surface,
        actual_announcements=actual_prefixes,
    )


# ──────────────────────────────────────────────
# ROA 创建建议
# ──────────────────────────────────────────────


async def generate_roa_creation_suggestions(
    db: AsyncSession,
) -> list[ROACreationSuggestion]:
    """生成 ROA 创建建议。

    对已公告但无 ROA 的前缀提出建议，遵循 minimal ROA 原则：
    maxLength = 实际公告的前缀长度。

    Args:
        db: 异步数据库会话

    Returns:
        ROA 创建建议列表
    """
    # 查询所有 BGP 公告（按 prefix + origin_as 去重）
    bgp_stmt = (
        select(
            BGPAnnouncement.prefix,
            BGPAnnouncement.origin_as,
            BGPAnnouncement.prefix_length,
        )
        .where(BGPAnnouncement.origin_as.is_not(None))
        .distinct()
    )
    bgp_result = await db.execute(bgp_stmt)
    bgp_announcements = list(bgp_result.all())

    if not bgp_announcements:
        return []

    # 批量查询所有现有 ROA 的 (prefix, origin_as) 集合
    roa_stmt = select(ROA.prefix, ROA.origin_as)
    roa_result = await db.execute(roa_stmt)
    roa_set: set[tuple[str, int]] = {(row.prefix, row.origin_as) for row in roa_result}

    suggestions: list[ROACreationSuggestion] = []
    for ann in bgp_announcements:
        if ann.origin_as is None:
            continue
        # 跳过已有 ROA 的前缀
        if (ann.prefix, ann.origin_as) in roa_set:
            continue

        # 查询前缀元数据
        importance, business_service, customer_id = await _get_prefix_metadata(db, ann.prefix)

        # minimal ROA：maxLength = 实际公告前缀长度
        recommended_max_length = ann.prefix_length

        suggestions.append(
            ROACreationSuggestion(
                prefix=ann.prefix,
                origin_as=ann.origin_as,
                recommended_max_length=recommended_max_length,
                reason=(
                    f"前缀 {ann.prefix} 已由 AS{ann.origin_as} 公告但无 ROA 覆盖，"
                    f"建议创建 minimal ROA（maxLength={recommended_max_length}）"
                ),
                minimal_roa=True,
                importance=importance,
                business_service=business_service,
                customer_id=customer_id,
            )
        )

    logger.info(
        "ROA 创建建议生成完成",
        total_suggestions=len(suggestions),
    )
    return suggestions


# ──────────────────────────────────────────────
# ROA 变更影响评估
# ──────────────────────────────────────────────


async def assess_roa_change_impact(
    db: AsyncSession,
    roa_id: int,
    change_params: ROAChangeParams,
) -> ROAChangeImpact | None:
    """ROA 变更影响评估。

    评估修改 ROA 的 prefix、origin AS、maxLength 或撤销 ROA 的影响：
    1. 计算受影响的 BGP 公告
    2. 评估受影响的业务服务与客户
    3. 计算每个受影响公告的验证状态变化
    4. 识别高风险变更（核心前缀变 Invalid）

    Args:
        db: 异步数据库会话
        roa_id: ROA ID
        change_params: 变更参数

    Returns:
        变更影响评估结果，ROA 不存在返回 None
    """
    roa = await get_roa_detail(db, roa_id)
    if roa is None:
        return None

    # 获取当前受 ROA 影响的 BGP 公告
    affected_announcements = await get_related_bgp_announcements(db, roa)

    # 计算变更后的 ROA 参数
    new_prefix = change_params.new_prefix or roa.prefix
    new_origin_as = (
        change_params.new_origin_as if change_params.new_origin_as is not None else roa.origin_as
    )
    if change_params.revoke:
        # 撤销 ROA：所有受影响公告将变为 NotFound
        new_max_length = None
        is_revoked = True
    else:
        new_max_length = (
            change_params.new_max_length
            if change_params.new_max_length is not None
            else (roa.max_length or roa.prefix_length)
        )
        is_revoked = False

    # 计算每个受影响公告的验证状态变化
    validation_changes: list[ROAValidationChange] = []
    affected_business: set[str] = set()
    affected_customers: set[int] = set()
    is_high_risk = False
    risk_description = ""

    for ann in affected_announcements:
        # 变更前的验证状态
        before_status = ann.rpki_validation_status or "not_found"
        before_reason = ann.rpki_invalid_reason

        # 模拟变更后的验证状态
        if is_revoked:
            after_status = "not_found"
            after_reason = None
        else:
            # 检查变更后的 ROA 是否仍覆盖该公告
            new_network = _parse_network(new_prefix)
            ann_network = _parse_network(ann.prefix)
            if (
                new_network is None
                or ann_network is None
                or ann_network.version != new_network.version
            ):
                # 新前缀不覆盖该公告
                after_status = "not_found"
                after_reason = None
            elif not ann_network.subnet_of(new_network):
                after_status = "not_found"
                after_reason = None
            elif ann.prefix_length > (new_max_length or 0):
                # 前缀长度超过新的 maxLength
                after_status = "invalid"
                after_reason = "length_exceeded"
            elif ann.origin_as != new_origin_as:
                # origin AS 不匹配
                after_status = "invalid"
                after_reason = "origin_as_mismatch"
            else:
                after_status = "valid"
                after_reason = None

        # 仅记录有变化的公告
        if before_status != after_status or before_reason != after_reason:
            validation_changes.append(
                ROAValidationChange(
                    prefix=ann.prefix,
                    origin_as=ann.origin_as or 0,
                    before_status=before_status,
                    after_status=after_status,
                    before_reason=before_reason,
                    after_reason=after_reason,
                )
            )

            # 查询该前缀的资产元数据，识别高风险变更
            importance, business_service, customer_id = await _get_prefix_metadata(db, ann.prefix)
            if business_service:
                affected_business.add(business_service)
            if customer_id is not None:
                affected_customers.add(customer_id)

            # 识别高风险变更：核心前缀变 Invalid
            if importance in ("critical", "important") and after_status == "invalid":
                is_high_risk = True
                risk_description = f"核心前缀 {ann.prefix}（{importance}）在变更后将变为 Invalid"

    # 撤销 ROA 时，所有受影响公告变为 NotFound，若涉及核心前缀则为高风险
    if is_revoked and affected_announcements:
        for ann in affected_announcements:
            importance, _, _ = await _get_prefix_metadata(db, ann.prefix)
            if importance in ("critical", "important"):
                is_high_risk = True
                risk_description = (
                    f"撤销 ROA 将导致核心前缀 {ann.prefix}（{importance}）失去 RPKI 保护"
                )
                break

    return ROAChangeImpact(
        roa_id=roa.id,
        change_params=change_params,
        affected_announcements=affected_announcements,
        affected_business=list(affected_business),
        affected_customers=list(affected_customers),
        validation_changes=validation_changes,
        is_high_risk=is_high_risk,
        risk_description=risk_description,
    )


__all__ = [
    "assess_roa_change_impact",
    "check_max_length_risk",
    "check_roa_conflict",
    "check_roa_missing",
    "generate_roa_creation_suggestions",
    "get_related_bgp_announcements",
    "get_roa_by_prefix_origin",
    "get_roa_detail",
    "get_roas",
]
