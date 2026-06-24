"""ROV 策略模拟与变更影响评估服务。

提供以下核心功能：
- ROV 策略模拟：模拟 drop_invalid / de-preference_invalid / monitor_only 策略
  对 BGP 路由的影响，生成受影响前缀、业务、客户清单与部署建议。
- ROA 变更影响评估：模拟 ROA 创建/修改/撤销对 BGP 公告验证状态的影响，
  分析新增攻击面。
- 分阶段部署建议生成：监控 → 降权 → 拒收三阶段递进方案。
- 风险评估：检查核心前缀与大规模合法路由受影响情况，判定是否需要审批。

设计要点：
- 基于实际的 BGP 公告与 VRP 数据进行模拟
- 批量加载 VRP 并在内存中验证，避免逐条查询数据库
- 支持按路由器、地域、机房、VRF、地址族、业务域、重要度过滤范围
- 支持历史路由表模拟（通过 snapshot_time 过滤）
"""

from __future__ import annotations

import csv
import io
import ipaddress
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.business import Customer
from app.models.prefix import Prefix
from app.models.rpki import ROA, VRP
from app.schemas.rov import (
    AffectedAnnouncement,
    AffectedBusiness,
    AffectedCustomer,
    AffectedPrefix,
    AttackSurfaceItem,
    DeploymentRecommendation,
    RiskAssessment,
    ROAChangeSimulationRequest,
    ROAChangeSimulationResult,
    ROVExportRequest,
    ROVExportResponse,
    ROVSimulationRequest,
    ROVSimulationResult,
    ROVSimulationScope,
    ValidationChange,
)

logger = get_logger("app.rov_simulation_service")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _parse_network(
    prefix: str,
) -> ipaddress.IPv4Network | ipaddress.IPv6Network | None:
    """解析前缀字符串为网络对象，失败返回 None。"""
    try:
        return ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return None


def _get_covering_prefixes(prefix: str) -> list[str]:
    """获取覆盖指定前缀的所有祖先前缀（含自身）。

    用于查找覆盖某前缀的所有 VRP。例如对于 ``192.168.1.0/24``，返回：
    ``0.0.0.0/0, 192.0.0.0/8, 192.168.0.0/16, 192.168.1.0/24``
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

    当 max_length 远大于 prefixlen 时，子前缀数量呈指数增长，
    此处限制最多返回 1024 个子前缀以避免内存爆炸。
    """
    network = _parse_network(prefix)
    if network is None:
        return []
    if max_length <= network.prefixlen:
        return []

    surface: list[str] = []
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


def _validate_against_vrps(
    prefix: str,
    origin_as: int,
    vrps: list[VRP],
) -> tuple[str, str | None]:
    """根据给定的 VRP 列表验证 BGP 公告（RFC 6811）。

    验证逻辑：
    1. 查找覆盖该前缀的所有 VRP（祖先链匹配）
    2. 若无匹配 VRP → NotFound
    3. 若有匹配 VRP：
       a. 检查 origin_as 是否匹配 → 不匹配则 Invalid (origin_as_mismatch)
       b. 检查前缀长度是否超过 max_length → 超过则 Invalid (length_exceeded)
       c. 检查 VRP 状态 → 已撤销则 Invalid (roa_revoked)
       d. 全部通过 → Valid

    Args:
        prefix: BGP 公告前缀
        origin_as: BGP 公告起源 AS 号
        vrps: VRP 列表（在内存中匹配，避免逐条查询数据库）

    Returns:
        元组 (validation_status, invalid_reason)
    """
    # 查找覆盖该前缀的所有 VRP
    covering_prefixes = _get_covering_prefixes(prefix)
    if not covering_prefixes:
        return "not_found", None

    covering_set = set(covering_prefixes)
    matched_vrps = [v for v in vrps if v.prefix in covering_set]

    # 无匹配 VRP → NotFound
    if not matched_vrps:
        return "not_found", None

    # 解析公告前缀长度
    try:
        announcement_network = ipaddress.ip_network(prefix, strict=False)
        announcement_length = announcement_network.prefixlen
    except ValueError:
        return "invalid", "data_source_error"

    # 检查每个匹配的 VRP
    # 优先级：valid > invalid
    # 只要有一个 VRP 完全匹配（origin_as + 长度），则为 Valid
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
                return "valid", None

    # 没有完全匹配，判定 Invalid 原因
    if not has_valid_vrp:
        # 所有匹配的 VRP 都已撤销
        return "invalid", "roa_revoked"
    elif not has_origin_match:
        # origin_as 不匹配
        return "invalid", "origin_as_mismatch"
    elif not has_length_match:
        # 前缀长度超过 max_length
        return "invalid", "length_exceeded"
    else:
        # 其他资源链错误
        return "invalid", "resource_chain_error"


async def _fetch_all_vrps(db: AsyncSession, snapshot_time: datetime | None = None) -> list[VRP]:
    """获取所有 VRP（可选时间点过滤）。"""
    stmt = select(VRP)
    if snapshot_time is not None:
        stmt = stmt.where(VRP.created_at <= snapshot_time)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _fetch_bgp_announcements(
    db: AsyncSession,
    snapshot_time: datetime | None = None,
) -> list[BGPAnnouncement]:
    """获取所有 BGP 公告（可选时间点过滤）。

    仅返回有 origin_as 的公告（无 origin_as 无法进行 RPKI 验证）。
    """
    stmt = select(BGPAnnouncement).where(BGPAnnouncement.origin_as.is_not(None))
    if snapshot_time is not None:
        stmt = stmt.where(BGPAnnouncement.timestamp <= snapshot_time)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _build_prefix_metadata_map(db: AsyncSession, prefixes: list[str]) -> dict[str, Prefix]:
    """批量查询前缀元数据，返回 prefix → Prefix 的映射。"""
    if not prefixes:
        return {}
    stmt = select(Prefix).where(Prefix.prefix.in_(prefixes))
    result = await db.execute(stmt)
    return {p.prefix: p for p in result.scalars().all()}


async def _build_customer_map(db: AsyncSession, customer_ids: list[int]) -> dict[int, Customer]:
    """批量查询客户信息，返回 customer_id → Customer 的映射。"""
    if not customer_ids:
        return {}
    stmt = select(Customer).where(Customer.id.in_(customer_ids))
    result = await db.execute(stmt)
    return {c.id: c for c in result.scalars().all()}


def _filter_by_scope(
    announcements: list[BGPAnnouncement],
    prefix_map: dict[str, Prefix],
    scope: ROVSimulationScope,
) -> list[BGPAnnouncement]:
    """根据模拟范围过滤 BGP 公告。

    过滤维度：
    - router_ids：按观察点 ID 过滤（近似路由器）
    - address_families：按地址族过滤
    - regions / sites / business_domains / importance_levels：按前缀元数据过滤

    Args:
        announcements: 待过滤的 BGP 公告列表
        prefix_map: 前缀元数据映射
        scope: 模拟范围

    Returns:
        过滤后的 BGP 公告列表
    """
    filtered = announcements

    # 路由器过滤（使用 observation_point_id 作为近似）
    if scope.router_ids:
        router_id_set = set(scope.router_ids)
        filtered = [a for a in filtered if a.observation_point_id in router_id_set]

    # 地址族过滤
    if scope.address_families:
        af_set = set(scope.address_families)
        filtered = [a for a in filtered if a.address_family in af_set]

    # 地域过滤
    if scope.regions:
        region_set = set(scope.regions)
        filtered = [
            a
            for a in filtered
            if a.prefix in prefix_map and prefix_map[a.prefix].region in region_set
        ]

    # 机房过滤
    if scope.sites:
        site_set = set(scope.sites)
        filtered = [
            a for a in filtered if a.prefix in prefix_map and prefix_map[a.prefix].site in site_set
        ]

    # 业务域过滤
    if scope.business_domains:
        business_set = set(scope.business_domains)
        filtered = [
            a
            for a in filtered
            if a.prefix in prefix_map and prefix_map[a.prefix].business_service in business_set
        ]

    # 重要度过滤
    if scope.importance_levels:
        importance_set = set(scope.importance_levels)
        filtered = [
            a
            for a in filtered
            if a.prefix in prefix_map and prefix_map[a.prefix].importance in importance_set
        ]

    return filtered


def _compute_simulated_status(current_status: str, policy: str) -> str:
    """根据 ROV 策略计算模拟后的路由状态。

    - drop_invalid：Invalid 路由将被拒绝（rejected）
    - de-preference_invalid：Invalid 路由将降权（de-preferenced）
    - monitor_only：不影响路由（保持原状态）
    """
    if current_status == "invalid":
        if policy == "drop_invalid":
            return "rejected"
        elif policy == "de-preference_invalid":
            return "de-preferenced"
    # monitor_only 或非 Invalid 状态保持不变
    return current_status


def _build_impact_description(
    current_status: str,
    simulated_status: str,
    reason: str | None,
) -> str:
    """构建影响描述文本。"""
    if simulated_status == "rejected":
        return f"Invalid 路由（原因：{reason}）将被拒绝，可能导致前缀不可达"
    elif simulated_status == "de-preferenced":
        return f"Invalid 路由（原因：{reason}）将被降权，优先级降低但仍保持可达"
    return ""


# ──────────────────────────────────────────────
# ROV 策略模拟
# ──────────────────────────────────────────────


async def simulate_rov_policy(
    db: AsyncSession, request: ROVSimulationRequest
) -> ROVSimulationResult:
    """模拟 ROV 策略。

    获取当前/历史路由表中的所有 BGP 公告，对每个公告执行 RPKI 验证，
    根据 policy 计算影响，生成受影响前缀、业务、客户清单，
    生成分阶段部署建议，评估风险。

    Args:
        db: 异步数据库会话
        request: ROV 策略模拟请求

    Returns:
        ROV 策略模拟结果
    """
    # 获取所有 VRP 与 BGP 公告
    vrps = await _fetch_all_vrps(db, request.snapshot_time)
    announcements = await _fetch_bgp_announcements(db, request.snapshot_time)

    # 批量查询前缀元数据（用于范围过滤与影响分析）
    all_prefixes = list({a.prefix for a in announcements})
    prefix_map = await _build_prefix_metadata_map(db, all_prefixes)

    # 按范围过滤
    filtered_announcements = _filter_by_scope(announcements, prefix_map, request.scope)

    # 对每个公告执行 RPKI 验证
    valid_count = 0
    invalid_count = 0
    not_found_count = 0
    affected_prefixes: list[AffectedPrefix] = []

    for ann in filtered_announcements:
        if ann.origin_as is None:
            continue

        # 验证公告（基于当前 VRP 数据）
        status, reason = _validate_against_vrps(ann.prefix, ann.origin_as, vrps)

        # 统计验证状态
        if status == "valid":
            valid_count += 1
        elif status == "invalid":
            invalid_count += 1
        else:
            not_found_count += 1

        # 根据策略计算模拟后状态
        simulated_status = _compute_simulated_status(status, request.policy)

        # 仅记录受影响的公告（模拟后状态与当前状态不同）
        if simulated_status != status:
            prefix_meta = prefix_map.get(ann.prefix)
            importance = prefix_meta.importance if prefix_meta else None
            impact_desc = _build_impact_description(status, simulated_status, reason)

            affected_prefixes.append(
                AffectedPrefix(
                    prefix=ann.prefix,
                    origin_as=ann.origin_as,
                    current_status=status,
                    simulated_status=simulated_status,
                    impact_description=impact_desc,
                    importance=importance,
                )
            )

    # 生成受影响业务与客户清单
    affected_business = _build_affected_business(affected_prefixes, prefix_map)
    affected_customers = await _build_affected_customers(db, affected_prefixes, prefix_map)

    # 生成部署建议
    recommendations = generate_deployment_recommendations(affected_prefixes)

    # 评估风险
    risk_assessment = assess_simulation_risk(affected_prefixes, affected_business)

    logger.info(
        "ROV 策略模拟完成",
        policy=request.policy,
        total_announcements=len(filtered_announcements),
        valid_count=valid_count,
        invalid_count=invalid_count,
        not_found_count=not_found_count,
        affected_prefix_count=len(affected_prefixes),
    )

    return ROVSimulationResult(
        policy=request.policy,
        total_announcements=len(filtered_announcements),
        valid_count=valid_count,
        invalid_count=invalid_count,
        not_found_count=not_found_count,
        affected_prefixes=affected_prefixes,
        affected_business=affected_business,
        affected_customers=affected_customers,
        deployment_recommendations=recommendations,
        risk_assessment=risk_assessment,
    )


def _build_affected_business(
    affected_prefixes: list[AffectedPrefix],
    prefix_map: dict[str, Prefix],
) -> list[AffectedBusiness]:
    """构建受影响业务清单。

    按业务服务分组受影响前缀，根据核心前缀占比判定影响等级。
    """
    business_prefixes: dict[str, list[str]] = {}
    for ap in affected_prefixes:
        prefix_meta = prefix_map.get(ap.prefix)
        if prefix_meta and prefix_meta.business_service:
            business_prefixes.setdefault(prefix_meta.business_service, []).append(ap.prefix)

    result: list[AffectedBusiness] = []
    for business, prefixes in business_prefixes.items():
        # 判断影响等级：含核心/重要前缀为 high，否则按数量判定
        has_critical = any(
            prefix_map.get(p) and prefix_map[p].importance in ("critical", "important")
            for p in prefixes
        )
        if has_critical:
            impact_level = "high"
        elif len(prefixes) > 5:
            impact_level = "medium"
        else:
            impact_level = "low"

        result.append(
            AffectedBusiness(
                business_service=business,
                affected_prefixes=prefixes,
                impact_level=impact_level,
                description=(f"业务 {business} 有 {len(prefixes)} 个前缀受 ROV 策略影响"),
            )
        )
    return result


async def _build_affected_customers(
    db: AsyncSession,
    affected_prefixes: list[AffectedPrefix],
    prefix_map: dict[str, Prefix],
) -> list[AffectedCustomer]:
    """构建受影响客户清单。

    按客户分组受影响前缀，批量查询客户名称，根据核心前缀占比判定影响等级。
    """
    customer_prefixes: dict[int, list[str]] = {}
    for ap in affected_prefixes:
        prefix_meta = prefix_map.get(ap.prefix)
        if prefix_meta and prefix_meta.customer_id:
            customer_prefixes.setdefault(prefix_meta.customer_id, []).append(ap.prefix)

    if not customer_prefixes:
        return []

    customer_map = await _build_customer_map(db, list(customer_prefixes.keys()))

    result: list[AffectedCustomer] = []
    for customer_id, prefixes in customer_prefixes.items():
        customer = customer_map.get(customer_id)
        customer_name = customer.name if customer else f"客户 {customer_id}"

        has_critical = any(
            prefix_map.get(p) and prefix_map[p].importance in ("critical", "important")
            for p in prefixes
        )
        if has_critical:
            impact_level = "high"
        elif len(prefixes) > 5:
            impact_level = "medium"
        else:
            impact_level = "low"

        result.append(
            AffectedCustomer(
                customer_id=customer_id,
                customer_name=customer_name,
                affected_prefixes=prefixes,
                impact_level=impact_level,
            )
        )
    return result


# ──────────────────────────────────────────────
# 分阶段部署建议
# ──────────────────────────────────────────────


def generate_deployment_recommendations(
    affected_prefixes: list[AffectedPrefix],
) -> list[DeploymentRecommendation]:
    """生成分阶段部署建议。

    第一阶段：仅监控（记录 Invalid 路由，不影响转发）
    第二阶段：降权 Invalid 路由（de-preference，仍可用但优先级低）
    第三阶段：拒收 Invalid 路由（drop-invalid）
    对 NotFound 和疑似良性 Invalid 提供治理清单。

    Args:
        affected_prefixes: 受影响的前缀列表

    Returns:
        部署建议列表
    """
    recommendations: list[DeploymentRecommendation] = []

    # 收集各类受影响前缀
    invalid_prefixes = [ap.prefix for ap in affected_prefixes if ap.current_status == "invalid"]
    not_found_prefixes = [ap.prefix for ap in affected_prefixes if ap.current_status == "not_found"]
    critical_invalid = [
        ap.prefix
        for ap in affected_prefixes
        if ap.current_status == "invalid" and ap.importance in ("critical", "important")
    ]

    # 第一阶段：仅监控
    recommendations.append(
        DeploymentRecommendation(
            phase="monitor",
            description=(
                "第一阶段：启用 ROV 监控模式（monitor_only）。"
                "记录所有 Invalid 路由但不影响转发，建立基线数据。"
                "建议运行 2-4 周，收集 Invalid 路由的分布、来源与趋势。"
            ),
            prerequisites=[
                "确保 RPKI 验证器正常运行且 VRP 数据已同步",
                "配置日志收集系统记录 Invalid 路由事件",
                "通知相关业务团队关注可能的 Invalid 路由告警",
            ],
            affected_prefixes=invalid_prefixes,
        )
    )

    # 第二阶段：降权（排除核心前缀，核心前缀待根因解决后再处理）
    de_pref_prefixes = [p for p in invalid_prefixes if p not in critical_invalid]
    recommendations.append(
        DeploymentRecommendation(
            phase="de-preference",
            description=(
                "第二阶段：启用 de-preference 模式。"
                "对 Invalid 路由降权处理（如增大 MED、降低 LOCAL_PREF），"
                "使其在有多条路径时不会被优选，但仍保持可达性。"
                "建议先对非核心前缀实施，观察 1-2 周。"
            ),
            prerequisites=[
                "第一阶段监控无异常",
                "确认所有 Invalid 路由均有备用 Valid 路径",
                "核心前缀（critical/important）暂不实施，待根因解决",
            ],
            affected_prefixes=de_pref_prefixes,
        )
    )

    # 第三阶段：拒收
    recommendations.append(
        DeploymentRecommendation(
            phase="drop",
            description=(
                "第三阶段：启用 drop_invalid 模式。"
                "完全拒收 Invalid 路由，实现完整的 ROV 防护。"
                "建议先在边缘路由器实施，逐步推广至核心。"
            ),
            prerequisites=[
                "第二阶段 de-preference 运行稳定",
                "所有 Invalid 路由的根因已排查并修复（ROA 配置错误、路由泄露等）",
                "确认无核心业务依赖 Invalid 路由",
                "制定回滚预案（可快速切换回 de-preference 或 monitor 模式）",
            ],
            affected_prefixes=invalid_prefixes,
        )
    )

    # NotFound 治理清单
    if not_found_prefixes:
        recommendations.append(
            DeploymentRecommendation(
                phase="monitor",
                description=(
                    "NotFound 前缀治理：以下前缀无 ROA 覆盖，"
                    "建议为合法前缀创建 ROA（遵循 minimal ROA 原则），"
                    "对非法前缀加强监控。"
                ),
                prerequisites=[
                    "确认每个 NotFound 前缀的合法性",
                    "为合法前缀申请创建 ROA",
                ],
                affected_prefixes=not_found_prefixes,
            )
        )

    # 核心前缀 Invalid 治理清单
    if critical_invalid:
        recommendations.append(
            DeploymentRecommendation(
                phase="monitor",
                description=(
                    "核心前缀 Invalid 治理：以下核心前缀当前为 Invalid 状态，"
                    "需优先排查 ROA 配置是否正确或是否存在路由劫持。"
                    "在根因解决前，不建议对这些前缀实施 drop 策略。"
                ),
                prerequisites=[
                    "逐一排查每个核心 Invalid 前缀的根因",
                    "联系相关 AS 管理员确认 ROA 配置",
                    "必要时临时创建或修改 ROA 修复验证状态",
                ],
                affected_prefixes=critical_invalid,
            )
        )

    return recommendations


# ──────────────────────────────────────────────
# 风险评估
# ──────────────────────────────────────────────


# 大规模受影响前缀的阈值
_LARGE_SCALE_THRESHOLD = 50
# 极大规模受影响前缀的阈值（触发阻断）
_VERY_LARGE_SCALE_THRESHOLD = 200


def assess_simulation_risk(
    affected_prefixes: list[AffectedPrefix],
    affected_business: list[AffectedBusiness],
) -> RiskAssessment:
    """评估模拟风险。

    检查是否有核心前缀受影响，检查是否有大规模合法路由受影响，
    返回风险等级和阻断条件。

    风险等级判定：
    - high：存在阻断问题（核心前缀被拒绝或极大规模受影响）
    - medium：存在多个风险因素但无阻断
    - low：存在少量风险因素
    - none：无风险因素

    Args:
        affected_prefixes: 受影响的前缀列表
        affected_business: 受影响的业务列表

    Returns:
        风险评估结果
    """
    risk_factors: list[str] = []
    blocking_issues: list[str] = []
    requires_approval = False

    # 检查核心前缀受影响
    critical_affected = [
        ap
        for ap in affected_prefixes
        if ap.importance in ("critical", "important")
        and ap.simulated_status in ("rejected", "de-preferenced")
    ]
    if critical_affected:
        risk_factors.append(f"有 {len(critical_affected)} 个核心/重要前缀受策略影响")
        # 核心前缀被拒绝为阻断问题
        critical_rejected = [ap for ap in critical_affected if ap.simulated_status == "rejected"]
        if critical_rejected:
            blocking_issues.append(
                f"有 {len(critical_rejected)} 个核心前缀将被拒绝，可能导致业务中断"
            )
            requires_approval = True

    # 检查大规模合法路由受影响
    if len(affected_prefixes) > _LARGE_SCALE_THRESHOLD:
        risk_factors.append(
            f"受影响前缀数量较大（{len(affected_prefixes)} 个），超过阈值 {_LARGE_SCALE_THRESHOLD}"
        )
        if len(affected_prefixes) > _VERY_LARGE_SCALE_THRESHOLD:
            blocking_issues.append(
                f"受影响前缀数量极大（{len(affected_prefixes)} 个），建议分批实施"
            )
            requires_approval = True

    # 检查高风险业务受影响
    high_impact_business = [b for b in affected_business if b.impact_level == "high"]
    if high_impact_business:
        risk_factors.append(f"有 {len(high_impact_business)} 个业务受高影响")

    # 判定风险等级
    if blocking_issues:
        risk_level = "high"
    elif risk_factors:
        if any("核心" in f for f in risk_factors):
            risk_level = "high"
        elif len(risk_factors) > 2:
            risk_level = "medium"
        else:
            risk_level = "low"
    else:
        risk_level = "none"

    return RiskAssessment(
        risk_level=risk_level,
        risk_factors=risk_factors,
        blocking_issues=blocking_issues,
        requires_approval=requires_approval,
    )


def check_high_risk_block(affected_prefixes: list[AffectedPrefix]) -> bool:
    """检查高风险阻断。

    如果核心前缀或大规模合法路由会变为 Invalid（被拒绝），返回 True
    （表示需要审批后方可实施）。

    阻断条件：
    1. 任意核心/重要前缀被拒绝
    2. 被拒绝的前缀总数超过 200 个

    Args:
        affected_prefixes: 受影响的前缀列表

    Returns:
        是否需要审批（True 表示高风险阻断）
    """
    # 核心前缀被拒绝
    for ap in affected_prefixes:
        if ap.importance in ("critical", "important") and ap.simulated_status == "rejected":
            return True

    # 大规模合法路由被拒绝
    rejected_count = sum(1 for ap in affected_prefixes if ap.simulated_status == "rejected")
    if rejected_count > _VERY_LARGE_SCALE_THRESHOLD:
        return True

    return False


# ──────────────────────────────────────────────
# ROA 变更模拟
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
    prefix_map = await _build_prefix_metadata_map(db, prefix_strs)

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
                current_validation_status=(ann.rpki_validation_status or "not_found"),
                rpki_invalid_reason=ann.rpki_invalid_reason,
                importance=prefix_meta.importance if prefix_meta else None,
                business_service=(prefix_meta.business_service if prefix_meta else None),
            )
        )
    return affected


async def simulate_roa_change(
    db: AsyncSession, request: ROAChangeSimulationRequest
) -> ROAChangeSimulationResult:
    """模拟 ROA 变更影响。

    获取当前所有 BGP 公告，模拟 ROA 变更后的 VRP 状态，
    重新验证所有受影响公告，计算验证状态变化，
    分析新增攻击面（变更后可能被利用的前缀范围）。

    Args:
        db: 异步数据库会话
        request: ROA 变更模拟请求

    Returns:
        ROA 变更模拟结果

    Raises:
        ValueError: ROA ID 不存在
    """
    # 获取所有 VRP 与 BGP 公告
    vrps = await _fetch_all_vrps(db)
    announcements = await _fetch_bgp_announcements(db)

    # 获取原始 ROA（修改/撤销时）
    original_roa: ROA | None = None
    if request.roa_id is not None:
        stmt = select(ROA).where(ROA.id == request.roa_id)
        result = await db.execute(stmt)
        original_roa = result.scalar_one_or_none()
        if original_roa is None:
            raise ValueError(f"ROA ID {request.roa_id} 不存在")

    # 模拟变更后的 VRP 列表
    simulated_vrps = _apply_roa_change(vrps, original_roa, request)

    # 确定受影响的前缀范围（旧 ROA 与新 ROA 覆盖的前缀）
    affected_prefix_ranges = _get_affected_prefix_ranges(original_roa, request)

    # 过滤出可能受影响的公告
    affected_announcements = _filter_affected_announcements(announcements, affected_prefix_ranges)

    # 重新验证并计算状态变化
    validation_changes: list[ValidationChange] = []
    for ann in affected_announcements:
        if ann.origin_as is None:
            continue

        # 变更前状态（使用当前 VRP 验证）
        old_status, old_reason = _validate_against_vrps(ann.prefix, ann.origin_as, vrps)

        # 变更后状态（使用模拟 VRP 验证）
        new_status, new_reason = _validate_against_vrps(ann.prefix, ann.origin_as, simulated_vrps)

        # 仅记录有变化的公告
        if old_status != new_status:
            change_reason = _build_change_reason(
                old_status, new_status, old_reason, new_reason, request
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

    # 分析新增攻击面（传入受影响公告以便识别过宽授权）
    new_attack_surface = _analyze_attack_surface(original_roa, request, affected_announcements)

    # 构建受影响 BGP 公告清单（含前缀元数据）
    affected_announcement_list = await _build_affected_announcements(db, affected_announcements)

    # 评估风险（将验证变化转为受影响前缀格式以复用风险评估逻辑）
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
        "ROA 变更模拟完成",
        change_type=request.change_type,
        roa_id=request.roa_id,
        validation_change_count=len(validation_changes),
        affected_announcement_count=len(affected_announcement_list),
        attack_surface_count=len(new_attack_surface),
    )

    return ROAChangeSimulationResult(
        validation_changes=validation_changes,
        affected_announcements=affected_announcement_list,
        new_attack_surface=new_attack_surface,
        risk_assessment=risk_assessment,
    )


def _apply_roa_change(
    vrps: list[VRP],
    original_roa: ROA | None,
    request: ROAChangeSimulationRequest,
) -> list[VRP]:
    """应用 ROA 变更，返回模拟后的 VRP 列表。

    - revoke：移除关联的 VRP
    - modify：移除旧 VRP，添加新 VRP
    - create：添加新 VRP
    """
    simulated = list(vrps)

    if request.change_type == "revoke" and original_roa is not None:
        # 撤销：移除关联的 VRP
        simulated = [v for v in simulated if v.roa_id != original_roa.id]
    elif request.change_type == "modify" and original_roa is not None:
        # 修改：移除旧 VRP，添加新 VRP
        simulated = [v for v in simulated if v.roa_id != original_roa.id]
        new_vrp = _create_simulated_vrp(original_roa, request)
        if new_vrp is not None:
            simulated.append(new_vrp)
    elif request.change_type == "create":
        # 创建：添加新 VRP
        new_vrp = _create_simulated_vrp(None, request)
        if new_vrp is not None:
            simulated.append(new_vrp)

    return simulated


def _create_simulated_vrp(
    original_roa: ROA | None,
    request: ROAChangeSimulationRequest,
) -> VRP | None:
    """创建模拟的 VRP 对象（不写入数据库）。

    根据原始 ROA 与变更请求计算新 VRP 的参数。
    """
    # 确定新 VRP 的参数
    if original_roa is not None:
        # 修改场景：使用新值或回退到原值
        prefix = request.new_prefix if request.new_prefix is not None else original_roa.prefix
        origin_as = (
            request.new_origin_as if request.new_origin_as is not None else original_roa.origin_as
        )
        prefix_family = original_roa.prefix_family
        prefix_length = original_roa.prefix_length
        roa_id = original_roa.id
        tal_id = original_roa.tal_id

        # max_length：新值或原值或前缀长度
        if request.new_max_length is not None:
            max_length = request.new_max_length
        elif original_roa.max_length is not None:
            max_length = original_roa.max_length
        else:
            max_length = original_roa.prefix_length
    else:
        # 创建场景：必须提供 new_prefix 和 new_origin_as
        if request.new_prefix is None or request.new_origin_as is None:
            return None
        prefix = request.new_prefix
        origin_as = request.new_origin_as
        parsed = _parse_network(prefix)
        if parsed is None:
            return None
        prefix_family = 6 if parsed.version == 6 else 4
        prefix_length = parsed.prefixlen
        roa_id = None
        tal_id = None
        # max_length：新值或前缀长度（minimal ROA）
        max_length = request.new_max_length if request.new_max_length is not None else prefix_length

    # 确保 max_length 不小于 prefix_length
    if max_length < prefix_length:
        max_length = prefix_length

    # 创建 VRP 对象（不写入数据库，仅用于内存验证）
    vrp = VRP(
        prefix=prefix,
        prefix_family=prefix_family,
        prefix_length=prefix_length,
        origin_as=origin_as,
        max_length=max_length,
        tal_id=tal_id,
        roa_id=roa_id,
        trust_anchor=None,
        validation_status="valid",
    )
    return vrp


def _get_affected_prefix_ranges(
    original_roa: ROA | None,
    request: ROAChangeSimulationRequest,
) -> list[str]:
    """获取受 ROA 变更影响的前缀范围。

    包含旧 ROA 前缀与新 ROA 前缀（如有不同）。
    """
    ranges: list[str] = []

    # 旧 ROA 的前缀
    if original_roa is not None:
        ranges.append(original_roa.prefix)

    # 新前缀
    if request.new_prefix is not None:
        ranges.append(request.new_prefix)

    return list(set(ranges))


def _filter_affected_announcements(
    announcements: list[BGPAnnouncement],
    prefix_ranges: list[str],
) -> list[BGPAnnouncement]:
    """过滤出可能受 ROA 变更影响的公告。

    返回前缀是任一受影响范围的子网（或相等）的公告。
    """
    if not prefix_ranges:
        return announcements

    # 将前缀范围转为网络对象
    range_networks = [_parse_network(p) for p in prefix_ranges]
    range_networks = [n for n in range_networks if n is not None]

    if not range_networks:
        return announcements

    affected: list[BGPAnnouncement] = []
    for ann in announcements:
        ann_network = _parse_network(ann.prefix)
        if ann_network is None:
            continue
        # 检查公告前缀是否在任一受影响范围内（是子网或相等）
        for range_net in range_networks:
            if ann_network.version != range_net.version:
                continue
            try:
                if ann_network.subnet_of(range_net):
                    affected.append(ann)
                    break
            except ValueError:
                continue

    return affected


def _build_change_reason(
    old_status: str,
    new_status: str,
    old_reason: str | None,
    new_reason: str | None,
    request: ROAChangeSimulationRequest,
) -> str:
    """构建验证状态变化的原因描述。"""
    reason_parts: list[str] = []

    # 变更类型描述
    if request.change_type == "create":
        reason_parts.append("新建 ROA")
    elif request.change_type == "modify":
        reason_parts.append("修改 ROA")
    elif request.change_type == "revoke":
        reason_parts.append("撤销 ROA")

    # 状态变化描述
    if old_status == "not_found" and new_status == "valid":
        reason_parts.append("前缀获得 ROA 覆盖，验证状态从 NotFound 变为 Valid")
    elif old_status == "valid" and new_status == "invalid":
        reason_parts.append(f"前缀验证状态从 Valid 变为 Invalid（原因：{new_reason}）")
    elif old_status == "valid" and new_status == "not_found":
        reason_parts.append("ROA 撤销后前缀失去覆盖，验证状态从 Valid 变为 NotFound")
    elif old_status == "invalid" and new_status == "valid":
        reason_parts.append("ROA 变更后前缀验证状态从 Invalid 变为 Valid")
    elif old_status == "not_found" and new_status == "invalid":
        reason_parts.append(
            f"新建 ROA 后前缀验证状态从 NotFound 变为 Invalid（原因：{new_reason}）"
        )
    elif old_status == "invalid" and new_status == "not_found":
        reason_parts.append("ROA 撤销后前缀验证状态从 Invalid 变为 NotFound")
    else:
        reason_parts.append(f"验证状态从 {old_status} 变为 {new_status}")

    return "，".join(reason_parts)


def _analyze_attack_surface(
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
        new_prefix = request.new_prefix if request.new_prefix is not None else original_roa.prefix
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
            request.new_origin_as if request.new_origin_as is not None else original_roa.origin_as
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
            request.new_max_length if request.new_max_length is not None else network.prefixlen
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
        # 新增的子前缀范围
        surface_prefixes = _get_more_specific_prefixes(new_prefix, new_max_length)
        # 排除旧攻击面已覆盖的范围
        old_surface: set[str] = set()
        if original_roa is not None and old_max_length > 0:
            old_surface = set(_get_more_specific_prefixes(old_prefix or new_prefix, old_max_length))
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
        # 计算实际公告的最大前缀长度（仅统计同 origin AS 的公告）
        actual_lengths = [
            a.prefix_length for a in affected_announcements if a.origin_as == origin_as
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
    if original_roa is not None and request.new_prefix is not None and old_prefix is not None:
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


# ──────────────────────────────────────────────
# 导出
# ──────────────────────────────────────────────


async def export_simulation_results(
    db: AsyncSession, request: ROVExportRequest
) -> ROVExportResponse:
    """导出模拟结果为 JSON 或 CSV。

    运行 ROV 策略模拟并将结果导出为指定格式。

    Args:
        db: 异步数据库会话
        request: 导出请求（包含模拟参数与格式）

    Returns:
        导出响应（包含格式、内容与建议文件名）
    """
    # 运行模拟
    result = await simulate_rov_policy(db, request.simulation_request)

    # 生成时间戳用于文件名
    timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    if request.format == "json":
        content = result.model_dump_json(indent=2)
        filename = f"rov_simulation_{timestamp_str}.json"
    else:  # csv
        content = _result_to_csv(result)
        filename = f"rov_simulation_{timestamp_str}.csv"

    return ROVExportResponse(
        format=request.format,
        content=content,
        filename=filename,
    )


def _result_to_csv(result: ROVSimulationResult) -> str:
    """将模拟结果转为 CSV 格式字符串。"""
    output = io.StringIO()
    writer = csv.writer(output)

    # 写入摘要
    writer.writerow(["# 模拟摘要"])
    writer.writerow(["策略", result.policy])
    writer.writerow(["公告总数", result.total_announcements])
    writer.writerow(["Valid 数", result.valid_count])
    writer.writerow(["Invalid 数", result.invalid_count])
    writer.writerow(["NotFound 数", result.not_found_count])
    writer.writerow(["风险等级", result.risk_assessment.risk_level])
    writer.writerow(["需要审批", result.risk_assessment.requires_approval])
    writer.writerow([])

    # 写入受影响前缀
    writer.writerow(["# 受影响前缀"])
    writer.writerow(["前缀", "起源 AS", "当前状态", "模拟状态", "影响描述", "重要度"])
    for ap in result.affected_prefixes:
        writer.writerow(
            [
                ap.prefix,
                ap.origin_as,
                ap.current_status,
                ap.simulated_status,
                ap.impact_description,
                ap.importance or "",
            ]
        )
    writer.writerow([])

    # 写入受影响业务
    writer.writerow(["# 受影响业务"])
    writer.writerow(["业务服务", "受影响前缀数", "影响等级", "描述"])
    for ab in result.affected_business:
        writer.writerow(
            [
                ab.business_service,
                len(ab.affected_prefixes),
                ab.impact_level,
                ab.description,
            ]
        )
    writer.writerow([])

    # 写入受影响客户
    writer.writerow(["# 受影响客户"])
    writer.writerow(["客户 ID", "客户名称", "受影响前缀数", "影响等级"])
    for ac in result.affected_customers:
        writer.writerow(
            [
                ac.customer_id,
                ac.customer_name,
                len(ac.affected_prefixes),
                ac.impact_level,
            ]
        )
    writer.writerow([])

    # 写入部署建议
    writer.writerow(["# 部署建议"])
    writer.writerow(["阶段", "描述", "前置条件", "受影响前缀数"])
    for rec in result.deployment_recommendations:
        writer.writerow(
            [
                rec.phase,
                rec.description,
                "; ".join(rec.prerequisites),
                len(rec.affected_prefixes),
            ]
        )

    return output.getvalue()


__all__ = [
    "assess_simulation_risk",
    "check_high_risk_block",
    "export_simulation_results",
    "generate_deployment_recommendations",
    "simulate_roa_change",
    "simulate_rov_policy",
]
