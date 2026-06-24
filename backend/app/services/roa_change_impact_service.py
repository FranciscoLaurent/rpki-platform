"""ROA 变更影响模拟服务。

提供针对 ROA 创建/修改/撤销三种场景的细粒度影响模拟接口，
在已有 ``simulate_roa_change`` 通用能力之上补充以下内容：
- 按变更类型拆分的便捷入口（``simulate_roa_creation`` /
  ``simulate_roa_modification`` / ``simulate_roa_revocation``）
- 增强版攻击面分析（``analyze_attack_surface``），覆盖：
  * 子前缀劫持风险（maxLength 扩大引入的可被劫持子前缀）
  * 未授权 origin 风险（ROA 变更后可能被未授权 AS 利用）
  * 过宽授权风险（maxLength 远大于实际公告长度）
  * 覆盖范围扩大风险（前缀变更后覆盖更多未使用地址空间）
- 受影响 BGP 公告清单构建（含前缀元数据，便于业务关联）

设计要点：
- 复用 ``rov_simulation_service`` 中的 VRP 验证与变更应用逻辑，
  避免重复实现 RFC 6811 验证流程
- 攻击面分析在内存中计算，不写入数据库
- 所有方法均为 async，遵循现有代码风格
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.prefix import Prefix
from app.models.rpki import ROA
from app.schemas.rov import (
    AffectedAnnouncement,
    AttackSurfaceItem,
    ROAChangeSimulationRequest,
    ROAChangeSimulationResult,
    ValidationChange,
)
from app.services.rov_simulation_service import (
    _apply_roa_change,
    _fetch_all_vrps,
    _fetch_bgp_announcements,
    _filter_affected_announcements,
    _get_affected_prefix_ranges,
    _get_more_specific_prefixes,
    _parse_network,
    _validate_against_vrps,
    assess_simulation_risk,
)

logger = get_logger("app.roa_change_impact_service")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _build_affected_announcements(
    db: AsyncSession,
    announcements: list[BGPAnnouncement],
) -> list[AffectedAnnouncement]:
    """构建受影响 BGP 公告清单（含前缀元数据）。

    批量查询前缀元数据，关联重要度与业务服务信息，
    便于业务侧评估变更影响范围。

    Args:
        db: 异步数据库会话
        announcements: 受影响的 BGP 公告列表

    Returns:
        受影响公告清单（含元数据）
    """
    if not announcements:
        return []

    # 批量查询前缀元数据
    prefix_strs = list({a.prefix for a in announcements})
    prefix_map: dict[str, Prefix] = {}
    if prefix_strs:
        stmt = select(Prefix).where(Prefix.prefix.in_(prefix_strs))
        result = await db.execute(stmt)
        prefix_map = {p.prefix: p for p in result.scalars().all()}

    affected: list[AffectedAnnouncement] = []
    for ann in announcements:
        if ann.origin_as is None:
            continue
        prefix_meta = prefix_map.get(ann.prefix)
        affected.append(
            AffectedAnnouncement(
                prefix=ann.prefix,
                origin_as=ann.origin_as,
                prefix_length=ann.prefix_length,
                address_family=ann.address_family,
                current_validation_status=(
                    ann.rpki_validation_status or "not_found"
                ),
                rpki_invalid_reason=ann.rpki_invalid_reason,
                importance=prefix_meta.importance if prefix_meta else None,
                business_service=(
                    prefix_meta.business_service if prefix_meta else None
                ),
            )
        )
    return affected


async def _get_original_roa(
    db: AsyncSession, roa_id: int
) -> ROA:
    """根据 ROA ID 获取原始 ROA，不存在则抛出 ValueError。"""
    stmt = select(ROA).where(ROA.id == roa_id)
    result = await db.execute(stmt)
    roa = result.scalar_one_or_none()
    if roa is None:
        raise ValueError(f"ROA ID {roa_id} 不存在")
    return roa


def _build_change_reason(
    old_status: str,
    new_status: str,
    new_reason: str | None,
    change_type: str,
) -> str:
    """构建验证状态变化的原因描述。"""
    type_desc = {
        "create": "新建 ROA",
        "modify": "修改 ROA",
        "revoke": "撤销 ROA",
    }.get(change_type, "ROA 变更")

    if old_status == "not_found" and new_status == "valid":
        return f"{type_desc}，前缀获得 ROA 覆盖，验证状态从 NotFound 变为 Valid"
    if old_status == "valid" and new_status == "invalid":
        return (
            f"{type_desc}，前缀验证状态从 Valid 变为 Invalid"
            f"（原因：{new_reason}）"
        )
    if old_status == "valid" and new_status == "not_found":
        return f"{type_desc}，ROA 撤销后前缀失去覆盖，验证状态从 Valid 变为 NotFound"
    if old_status == "invalid" and new_status == "valid":
        return f"{type_desc}，前缀验证状态从 Invalid 变为 Valid"
    if old_status == "not_found" and new_status == "invalid":
        return (
            f"{type_desc}，新建 ROA 后前缀验证状态从 NotFound 变为 Invalid"
            f"（原因：{new_reason}）"
        )
    if old_status == "invalid" and new_status == "not_found":
        return f"{type_desc}，ROA 撤销后前缀验证状态从 Invalid 变为 NotFound"
    return f"{type_desc}，验证状态从 {old_status} 变为 {new_status}"


async def _run_simulation(
    db: AsyncSession,
    request: ROAChangeSimulationRequest,
    original_roa: ROA | None,
) -> ROAChangeSimulationResult:
    """执行 ROA 变更模拟的核心流程。

    包含：获取 VRP/BGP 数据 → 应用变更 → 过滤受影响公告 →
    重新验证 → 构建状态变化清单 → 构建受影响公告清单 →
    分析攻击面 → 评估风险。

    Args:
        db: 异步数据库会话
        request: ROA 变更模拟请求
        original_roa: 原始 ROA（create 时为 None）

    Returns:
        ROA 变更模拟结果
    """
    # 获取所有 VRP 与 BGP 公告
    vrps = await _fetch_all_vrps(db)
    announcements = await _fetch_bgp_announcements(db)

    # 模拟变更后的 VRP 列表
    simulated_vrps = _apply_roa_change(vrps, original_roa, request)

    # 确定受影响的前缀范围
    affected_prefix_ranges = _get_affected_prefix_ranges(original_roa, request)

    # 过滤出可能受影响的公告
    affected_announcements = _filter_affected_announcements(
        announcements, affected_prefix_ranges
    )

    # 重新验证并计算状态变化
    validation_changes: list[ValidationChange] = []
    for ann in affected_announcements:
        if ann.origin_as is None:
            continue

        # 变更前状态
        old_status, _ = _validate_against_vrps(
            ann.prefix, ann.origin_as, vrps
        )
        # 变更后状态
        new_status, new_reason = _validate_against_vrps(
            ann.prefix, ann.origin_as, simulated_vrps
        )

        if old_status != new_status:
            change_reason = _build_change_reason(
                old_status, new_status, new_reason, request.change_type
            )
            validation_changes.append(
                ValidationChange(
                    prefix=ann.prefix,
                    origin_as=ann.origin_as,
                    old_status=old_status,
                    new_status=new_status,
                    change_reason=change_reason,
                )
            )

    # 构建受影响 BGP 公告清单
    affected_announcement_list = await _build_affected_announcements(
        db, affected_announcements
    )

    # 分析新增攻击面（增强版）
    new_attack_surface = analyze_attack_surface(
        original_roa, request, affected_announcements
    )

    # 评估风险（复用 ROV 模拟的风险评估逻辑）
    from app.schemas.rov import AffectedPrefix

    affected_prefixes_for_risk = [
        AffectedPrefix(
            prefix=vc.prefix,
            origin_as=vc.origin_as,
            current_status=vc.old_status,
            simulated_status=vc.new_status,
            impact_description=vc.change_reason,
            importance=None,
        )
        for vc in validation_changes
    ]
    risk_assessment = assess_simulation_risk(affected_prefixes_for_risk, [])

    logger.info(
        "ROA 变更影响模拟完成",
        change_type=request.change_type,
        roa_id=request.roa_id,
        validation_change_count=len(validation_changes),
        affected_announcement_count=len(affected_announcement_list),
        attack_surface_count=len(new_attack_surface),
        risk_level=risk_assessment.risk_level,
    )

    return ROAChangeSimulationResult(
        validation_changes=validation_changes,
        affected_announcements=affected_announcement_list,
        new_attack_surface=new_attack_surface,
        risk_assessment=risk_assessment,
    )


# ──────────────────────────────────────────────
# 公共 API：按变更类型拆分的便捷入口
# ──────────────────────────────────────────────


async def simulate_roa_creation(
    db: AsyncSession,
    prefix: str,
    origin_as: int,
    max_length: int | None = None,
) -> ROAChangeSimulationResult:
    """模拟创建 ROA 后的验证状态变化。

    Args:
        db: 异步数据库会话
        prefix: 新 ROA 的网络前缀（含前缀长度，如 ``192.168.1.0/24``）
        origin_as: 新 ROA 授权的起源 AS 号
        max_length: 新 ROA 的最大前缀长度，为空时采用 minimal ROA 原则
            （等于前缀长度）

    Returns:
        ROA 变更模拟结果，包含验证状态变化、受影响公告、攻击面与风险评估

    Raises:
        ValueError: 前缀格式无效
    """
    network = _parse_network(prefix)
    if network is None:
        raise ValueError(f"无效的前缀格式：{prefix}")

    # 默认 minimal ROA：maxLength = 前缀长度
    effective_max_length = (
        max_length if max_length is not None else network.prefixlen
    )

    request = ROAChangeSimulationRequest(
        change_type="create",
        new_prefix=prefix,
        new_origin_as=origin_as,
        new_max_length=effective_max_length,
    )
    return await _run_simulation(db, request, original_roa=None)


async def simulate_roa_modification(
    db: AsyncSession,
    roa_id: int,
    new_prefix: str | None = None,
    new_origin_as: int | None = None,
    new_max_length: int | None = None,
) -> ROAChangeSimulationResult:
    """模拟修改 ROA（含调整 maxLength）后的验证状态变化。

    任意字段为 None 时表示保持原值不变。

    Args:
        db: 异步数据库会话
        roa_id: 待修改的 ROA ID
        new_prefix: 新前缀（如变更前缀），为空表示不变
        new_origin_as: 新起源 AS（如变更 origin），为空表示不变
        new_max_length: 新最大前缀长度（如调整 maxLength），为空表示不变

    Returns:
        ROA 变更模拟结果

    Raises:
        ValueError: ROA ID 不存在，或新前缀格式无效
    """
    original_roa = await _get_original_roa(db, roa_id)

    if new_prefix is not None:
        network = _parse_network(new_prefix)
        if network is None:
            raise ValueError(f"无效的新前缀格式：{new_prefix}")

    request = ROAChangeSimulationRequest(
        roa_id=roa_id,
        change_type="modify",
        new_prefix=new_prefix,
        new_origin_as=new_origin_as,
        new_max_length=new_max_length,
    )
    return await _run_simulation(db, request, original_roa=original_roa)


async def simulate_roa_revocation(
    db: AsyncSession, roa_id: int
) -> ROAChangeSimulationResult:
    """模拟撤销 ROA 后的验证状态变化。

    撤销后所有原本由该 ROA 覆盖的公告将失去 RPKI 保护，
    验证状态可能从 Valid/Invalid 变为 NotFound。

    Args:
        db: 异步数据库会话
        roa_id: 待撤销的 ROA ID

    Returns:
        ROA 变更模拟结果

    Raises:
        ValueError: ROA ID 不存在
    """
    original_roa = await _get_original_roa(db, roa_id)

    request = ROAChangeSimulationRequest(
        roa_id=roa_id,
        change_type="revoke",
    )
    return await _run_simulation(db, request, original_roa=original_roa)


# ──────────────────────────────────────────────
# 增强版攻击面分析
# ──────────────────────────────────────────────


def analyze_attack_surface(
    original_roa: ROA | None,
    request: ROAChangeSimulationRequest,
    affected_announcements: list[BGPAnnouncement] | None = None,
) -> list[AttackSurfaceItem]:
    """分析 ROA 变更后的新增攻击面。

    覆盖以下四类攻击面：
    1. **子前缀劫持风险**（sub_prefix_hijack）：maxLength 扩大后，
       新增的子前缀范围可能被攻击者劫持并宣告，由于 ROA 授权了
       该长度范围内的子前缀，攻击者的路由会被验证为 Valid。
    2. **未授权 origin 风险**（unauthorized_origin）：当 ROA 变更
       扩大了授权范围（如新增 maxLength 或前缀扩大），原本未授权
       的 AS 可能利用扩大的授权范围宣告前缀。
    3. **过宽授权风险**（over_authorization）：maxLength 远大于
       实际公告长度，授权了未实际使用的子前缀空间。
    4. **覆盖范围扩大风险**（coverage_expansion）：ROA 前缀从较小
       范围扩大到更大范围，覆盖了未实际使用的地址空间。

    Args:
        original_roa: 原始 ROA（create 时为 None）
        request: 变更请求
        affected_announcements: 受影响的 BGP 公告列表（用于判断
            实际公告长度，识别过宽授权）

    Returns:
        新增攻击面条目列表
    """
    attack_surface: list[AttackSurfaceItem] = []

    # 撤销 ROA 不增加攻击面（反而减少授权范围）
    if request.change_type == "revoke":
        return []

    # 确定新 ROA 的参数
    if original_roa is not None:
        new_prefix = (
            request.new_prefix
            if request.new_prefix is not None
            else original_roa.prefix
        )
        if request.new_max_length is not None:
            new_max_length = request.new_max_length
        elif original_roa.max_length is not None:
            new_max_length = original_roa.max_length
        else:
            new_max_length = original_roa.prefix_length
        old_max_length = (
            original_roa.max_length
            if original_roa.max_length is not None
            else original_roa.prefix_length
        )
        origin_as = (
            request.new_origin_as
            if request.new_origin_as is not None
            else original_roa.origin_as
        )
        old_prefix = original_roa.prefix
    else:
        if request.new_prefix is None or request.new_origin_as is None:
            return []
        new_prefix = request.new_prefix
        network = _parse_network(new_prefix)
        if network is None:
            return []
        new_max_length = (
            request.new_max_length
            if request.new_max_length is not None
            else network.prefixlen
        )
        old_max_length = 0
        origin_as = request.new_origin_as
        old_prefix = None

    # 解析新前缀
    new_network = _parse_network(new_prefix)
    if new_network is None:
        return []

    # 确保 max_length 不小于前缀长度
    if new_max_length < new_network.prefixlen:
        new_max_length = new_network.prefixlen

    # ── 1. 子前缀劫持风险（maxLength 扩大） ──
    if new_max_length > old_max_length:
        surface_prefixes = _get_more_specific_prefixes(
            new_prefix, new_max_length
        )
        # 排除旧攻击面已覆盖的范围
        old_surface: set[str] = set()
        if original_roa is not None and old_max_length > 0:
            old_surface = set(
                _get_more_specific_prefixes(old_prefix or new_prefix, old_max_length)
            )
        new_surface = [p for p in surface_prefixes if p not in old_surface]

        if new_surface:
            diff = new_max_length - old_max_length
            if diff >= 8:
                risk_level = "high"
            elif diff >= 3:
                risk_level = "medium"
            else:
                risk_level = "low"

            attack_surface.append(
                AttackSurfaceItem(
                    prefix=new_prefix,
                    origin_as=origin_as,
                    description=(
                        f"ROA 变更后 maxLength 从 {old_max_length} "
                        f"扩大到 {new_max_length}，"
                        f"新增 {len(new_surface)} 个可被劫持的子前缀"
                        f"（攻击者可宣告这些子前缀并通过 RPKI 验证）"
                    ),
                    risk_level=risk_level,
                    attack_type="sub_prefix_hijack",
                    affected_subprefixes=new_surface[:50],  # 限制返回数量
                )
            )

    # ── 2. 未授权 origin 风险 ──
    # 当 ROA 变更扩大了授权范围，原本未授权的 AS 可能利用扩大的授权
    # 主要场景：新建 ROA 或修改 ROA 时，授权了一个新的 origin AS
    if request.change_type == "create":
        # 新建 ROA 时，如果该前缀原本无 ROA 覆盖，新建后该 origin AS
        # 获得授权，需检查是否有其他 AS 也在宣告该前缀（潜在冲突）
        attack_surface.append(
            AttackSurfaceItem(
                prefix=new_prefix,
                origin_as=origin_as,
                description=(
                    f"新建 ROA 为 AS{origin_as} 授权前缀 {new_prefix}，"
                    f"需确认该 AS 为前缀的合法持有者，"
                    f"否则可能造成未授权 origin 风险"
                ),
                risk_level="medium",
                attack_type="unauthorized_origin",
            )
        )
    elif (
        request.change_type == "modify"
        and original_roa is not None
        and request.new_origin_as is not None
        and request.new_origin_as != original_roa.origin_as
    ):
        # 修改 origin AS：新 AS 获得授权，需确认合法性
        attack_surface.append(
            AttackSurfaceItem(
                prefix=new_prefix,
                origin_as=origin_as,
                description=(
                    f"ROA 修改后将 origin AS 从 AS{original_roa.origin_as} "
                    f"变更为 AS{origin_as}，"
                    f"需确认新 AS 为前缀的合法持有者"
                ),
                risk_level="medium",
                attack_type="unauthorized_origin",
            )
        )

    # ── 3. 过宽授权风险 ──
    # maxLength 远大于实际公告长度，授权了未实际使用的子前缀空间
    if affected_announcements:
        # 计算实际公告的最大前缀长度
        actual_lengths = [
            a.prefix_length
            for a in affected_announcements
            if a.origin_as == origin_as
        ]
        if actual_lengths:
            max_actual_length = max(actual_lengths)
            if new_max_length > max_actual_length + 3:
                diff = new_max_length - max_actual_length
                if diff >= 8:
                    risk_level = "high"
                elif diff >= 5:
                    risk_level = "medium"
                else:
                    risk_level = "low"

                attack_surface.append(
                    AttackSurfaceItem(
                        prefix=new_prefix,
                        origin_as=origin_as,
                        description=(
                            f"maxLength={new_max_length} 远大于实际公告"
                            f"最大长度 {max_actual_length}，"
                            f"授权了 {diff} 位未实际使用的子前缀空间，"
                            f"建议遵循 minimal ROA 原则收紧 maxLength"
                        ),
                        risk_level=risk_level,
                        attack_type="over_authorization",
                    )
                )

    # ── 4. 覆盖范围扩大风险 ──
    # ROA 前缀从较小范围扩大到更大范围
    if (
        original_roa is not None
        and request.new_prefix is not None
        and old_prefix is not None
    ):
        old_network = _parse_network(old_prefix)
        if (
            old_network is not None
            and new_network != old_network
            and new_network.version == old_network.version
        ):
            try:
                if old_network.subnet_of(new_network):
                    # 旧前缀是新前缀的子网 → 覆盖范围扩大
                    attack_surface.append(
                        AttackSurfaceItem(
                            prefix=new_prefix,
                            origin_as=origin_as,
                            description=(
                                f"ROA 前缀从 {old_prefix} 扩大到 {new_prefix}，"
                                f"覆盖范围增大，可能授权了未实际使用的地址空间"
                            ),
                            risk_level="medium",
                            attack_type="coverage_expansion",
                        )
                    )
            except ValueError:
                pass

    return attack_surface


__all__ = [
    "analyze_attack_surface",
    "simulate_roa_creation",
    "simulate_roa_modification",
    "simulate_roa_revocation",
]
