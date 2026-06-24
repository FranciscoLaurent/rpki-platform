"""ROA 变更管理服务。

提供 ROA 变更请求的创建、审批、执行、回滚与变更后验证功能。

设计要点：
- 创建变更请求时自动执行影响评估并匹配审批规则
- 审批流程支持自动批准、单人审批、双人审批、委员会审批
- 高风险变更（核心前缀、大规模影响）强制审批，不允许自动批准
- 变更执行后自动触发验证（RPKI 仓库状态、VRP 变化、BGP 状态）
- 所有变更操作记录审计日志
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.bgp import BGPAnnouncement
from app.models.prefix import Prefix
from app.models.roa_change import ROAChangeRequest
from app.models.rpki import ROA, VRP, RPKIObject
from app.models.user import User
from app.schemas.roa import ROAChangeParams
from app.schemas.roa_change import (
    ROAChangeExecutionResult,
    ROAChangeRequestCreate,
    ROAChangeVerificationResult,
)
from app.services import audit_service, roa_approval_service, roa_service

logger = get_logger("app.roa_change_service")


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _determine_risk_level(
    is_high_risk: bool,
    affected_count: int,
    prefix_importance: str | None,
) -> str:
    """根据影响评估结果确定风险等级。

    风险等级判定：
    - critical：核心前缀受影响或高风险标记
    - high：重要前缀受影响或受影响公告数 >= 10
    - medium：受影响公告数 >= 3
    - low：其他情况

    Args:
        is_high_risk: 影响评估是否标记为高风险
        affected_count: 受影响的 BGP 公告数
        prefix_importance: 前缀重要度

    Returns:
        风险等级字符串
    """
    if is_high_risk or prefix_importance == "critical":
        return "critical"
    if prefix_importance == "important" or affected_count >= 10:
        return "high"
    if affected_count >= 3:
        return "medium"
    return "low"


async def _get_prefix_importance(db: AsyncSession, prefix: str) -> str | None:
    """查询前缀的重要度。"""
    stmt = select(Prefix.importance).where(Prefix.prefix == prefix)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    return row


async def _get_user_brief(db: AsyncSession, user_id: int) -> dict[str, Any] | None:
    """获取用户简要信息。"""
    stmt = select(User.id, User.username, User.full_name).where(User.id == user_id)
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    return {
        "id": row.id,
        "username": row.username,
        "full_name": row.full_name,
    }


# ──────────────────────────────────────────────
# 变更请求管理
# ──────────────────────────────────────────────


async def create_change_request(
    db: AsyncSession,
    request_create: ROAChangeRequestCreate,
    user: User,
) -> ROAChangeRequest:
    """创建 ROA 变更请求。

    流程：
    1. 校验变更参数（create 不需要 roa_id，modify/revoke 需要）
    2. 记录变更前的值（modify/revoke 时从现有 ROA 获取）
    3. 自动执行影响评估
    4. 根据影响评估结果设置风险等级
    5. 匹配审批规则确定审批流程
    6. 如果是自动批准，直接设置为 approved

    Args:
        db: 异步数据库会话
        request_create: 变更请求创建参数
        user: 申请人

    Returns:
        创建的变更请求对象

    Raises:
        ValueError: 参数校验失败
    """
    # 参数校验
    if request_create.change_type in ("modify", "revoke"):
        if request_create.roa_id is None:
            raise ValueError(f"变更类型 {request_create.change_type} 需要指定 roa_id")
    if request_create.change_type == "create":
        if request_create.prefix is None or request_create.origin_as is None:
            raise ValueError("创建 ROA 需要指定 prefix 和 origin_as")

    # 获取现有 ROA 信息（modify/revoke 时）
    current_roa: ROA | None = None
    if request_create.roa_id is not None:
        current_roa = await roa_service.get_roa_detail(db, request_create.roa_id)
        if current_roa is None:
            raise ValueError(f"ROA ID {request_create.roa_id} 不存在")

    # 记录变更前的值
    current_prefix = current_roa.prefix if current_roa else None
    current_origin_as = current_roa.origin_as if current_roa else None
    current_max_length = current_roa.max_length if current_roa else None

    # 执行影响评估
    impact_summary: dict[str, Any] = {}
    is_high_risk = False
    affected_count = 0
    prefix_importance: str | None = None

    if request_create.change_type in ("modify", "revoke") and current_roa:
        # 使用 assess_roa_change_impact 评估影响
        change_params = ROAChangeParams(
            new_prefix=request_create.prefix,
            new_origin_as=request_create.origin_as,
            new_max_length=request_create.max_length,
            revoke=(request_create.change_type == "revoke"),
        )
        impact = await roa_service.assess_roa_change_impact(db, current_roa.id, change_params)
        if impact is not None:
            is_high_risk = impact.is_high_risk
            affected_count = len(impact.affected_announcements)
            impact_summary = {
                "affected_announcements": affected_count,
                "affected_business": impact.affected_business,
                "affected_customers": impact.affected_customers,
                "validation_changes_count": len(impact.validation_changes),
                "is_high_risk": impact.is_high_risk,
                "risk_description": impact.risk_description,
            }
            # 从受影响公告中提取前缀重要性
            if impact.affected_announcements:
                first_prefix = impact.affected_announcements[0].prefix
                prefix_importance = await _get_prefix_importance(db, first_prefix)
    elif request_create.change_type == "create" and request_create.prefix:
        # 创建场景：检查前缀重要性与现有公告
        prefix_importance = await _get_prefix_importance(db, request_create.prefix)
        # 查询该前缀的现有 BGP 公告数
        bgp_stmt = select(func.count(BGPAnnouncement.id)).where(
            BGPAnnouncement.prefix == request_create.prefix
        )
        bgp_result = await db.execute(bgp_stmt)
        affected_count = bgp_result.scalar_one()
        impact_summary = {
            "affected_announcements": affected_count,
            "prefix_importance": prefix_importance,
            "is_high_risk": prefix_importance == "critical",
        }
        is_high_risk = prefix_importance == "critical"

    if prefix_importance:
        impact_summary["prefix_importance"] = prefix_importance

    # 确定风险等级
    risk_level = _determine_risk_level(is_high_risk, affected_count, prefix_importance)

    # 创建变更请求
    change_request = ROAChangeRequest(
        change_type=request_create.change_type,
        roa_id=request_create.roa_id,
        prefix=request_create.prefix,
        origin_as=request_create.origin_as,
        max_length=request_create.max_length,
        current_prefix=current_prefix,
        current_origin_as=current_origin_as,
        current_max_length=current_max_length,
        reason=request_create.reason,
        impact_summary=impact_summary,
        risk_level=risk_level,
        status="pending_approval",
        requested_by=user.id,
        tenant_id=user.tenant_id if hasattr(user, "tenant_id") else None,
    )

    # 匹配审批规则
    flow_match = await roa_approval_service.match_approval_rule(db, change_request)
    change_request.approval_rule_id = flow_match.rule_id
    change_request.required_approvals = flow_match.required_approvals
    change_request.approvals = []

    # 自动批准：无需审批
    if flow_match.rule_type == "auto_approve" and not flow_match.is_high_risk:
        change_request.status = "approved"
        change_request.approved_by = user.id
        change_request.approval_comments = "自动批准（低风险变更）"

    db.add(change_request)
    await db.flush()
    await db.commit()
    await db.refresh(change_request)

    # 记录审计日志
    await audit_service.log_action(
        db=db,
        user_id=user.id,
        tenant_id=change_request.tenant_id,
        action="roa_change_request.create",
        resource_type="roa_change_request",
        resource_id=str(change_request.id),
        details={
            "change_type": change_request.change_type,
            "roa_id": change_request.roa_id,
            "risk_level": change_request.risk_level,
            "status": change_request.status,
            "approval_rule": flow_match.rule_name,
            "required_approvals": change_request.required_approvals,
        },
    )

    logger.info(
        "创建 ROA 变更请求",
        request_id=change_request.id,
        change_type=change_request.change_type,
        risk_level=change_request.risk_level,
        status=change_request.status,
    )
    return change_request


async def get_change_request(db: AsyncSession, request_id: int) -> ROAChangeRequest | None:
    """获取变更请求详情。"""
    stmt = select(ROAChangeRequest).where(ROAChangeRequest.id == request_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_change_requests(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[ROAChangeRequest], int]:
    """查询变更请求列表。

    Args:
        db: 异步数据库会话
        filters: 过滤条件，支持 change_type、status、risk_level、
                 requested_by、roa_id
        skip: 跳过记录数
        limit: 返回记录数上限

    Returns:
        元组 (变更请求列表, 总数)
    """
    stmt = select(ROAChangeRequest)
    count_stmt = select(func.count(ROAChangeRequest.id))

    if filters:
        if filters.get("change_type"):
            stmt = stmt.where(ROAChangeRequest.change_type == filters["change_type"])
            count_stmt = count_stmt.where(ROAChangeRequest.change_type == filters["change_type"])
        if filters.get("status"):
            stmt = stmt.where(ROAChangeRequest.status == filters["status"])
            count_stmt = count_stmt.where(ROAChangeRequest.status == filters["status"])
        if filters.get("risk_level"):
            stmt = stmt.where(ROAChangeRequest.risk_level == filters["risk_level"])
            count_stmt = count_stmt.where(ROAChangeRequest.risk_level == filters["risk_level"])
        if filters.get("requested_by") is not None:
            stmt = stmt.where(ROAChangeRequest.requested_by == filters["requested_by"])
            count_stmt = count_stmt.where(ROAChangeRequest.requested_by == filters["requested_by"])
        if filters.get("roa_id") is not None:
            stmt = stmt.where(ROAChangeRequest.roa_id == filters["roa_id"])
            count_stmt = count_stmt.where(ROAChangeRequest.roa_id == filters["roa_id"])

    stmt = stmt.order_by(ROAChangeRequest.id.desc()).offset(skip).limit(limit)

    result = await db.execute(stmt)
    requests = list(result.scalars().all())

    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    return requests, total


# ──────────────────────────────────────────────
# 审批
# ──────────────────────────────────────────────


async def approve_change_request(
    db: AsyncSession,
    request_id: int,
    approver: User,
    action: str,
    comments: str | None = None,
) -> ROAChangeRequest:
    """审批变更请求。

    流程：
    1. 检查变更请求状态为 pending_approval
    2. 记录审批动作
    3. 如果是拒绝，直接设置为 rejected
    4. 如果是批准，检查是否达到所需审批人数
    5. 达到所需人数时设置为 approved

    Args:
        db: 异步数据库会话
        request_id: 变更请求 ID
        approver: 审批人
        action: 审批动作（approve/reject）
        comments: 审批意见

    Returns:
        更新后的变更请求对象

    Raises:
        ValueError: 状态不允许审批或参数错误
    """
    change_request = await get_change_request(db, request_id)
    if change_request is None:
        raise ValueError(f"变更请求 ID {request_id} 不存在")

    if change_request.status != "pending_approval":
        raise ValueError(f"变更请求当前状态为 {change_request.status}，无法审批")

    if action not in ("approve", "reject"):
        raise ValueError(f"无效的审批动作：{action}，应为 approve 或 reject")

    # 记录审批动作
    approval_record: dict[str, Any] = {
        "user_id": approver.id,
        "username": approver.username,
        "action": action,
        "comments": comments,
        "timestamp": datetime.now(UTC).isoformat(),
    }

    approvals = change_request.approvals or []
    approvals.append(approval_record)
    change_request.approvals = approvals

    if action == "reject":
        # 拒绝：直接设置为 rejected
        change_request.status = "rejected"
        change_request.approved_by = approver.id
        change_request.approval_comments = comments
    else:
        # 批准：检查是否达到所需审批人数
        approve_count = sum(1 for a in approvals if a.get("action") == "approve")
        if approve_count >= change_request.required_approvals:
            change_request.status = "approved"
            change_request.approved_by = approver.id
            change_request.approval_comments = comments

    await db.flush()
    await db.commit()
    await db.refresh(change_request)

    # 记录审计日志
    await audit_service.log_action(
        db=db,
        user_id=approver.id,
        tenant_id=change_request.tenant_id,
        action=f"roa_change_request.{action}",
        resource_type="roa_change_request",
        resource_id=str(change_request.id),
        details={
            "action": action,
            "comments": comments,
            "new_status": change_request.status,
            "approve_count": sum(1 for a in approvals if a.get("action") == "approve"),
            "required_approvals": change_request.required_approvals,
        },
    )

    logger.info(
        "审批变更请求",
        request_id=change_request.id,
        action=action,
        approver=approver.username,
        new_status=change_request.status,
    )
    return change_request


# ──────────────────────────────────────────────
# 执行变更
# ──────────────────────────────────────────────


async def execute_change_request(
    db: AsyncSession,
    request_id: int,
    user: User,
) -> ROAChangeExecutionResult:
    """执行变更请求。

    流程：
    1. 检查变更请求状态为 approved
    2. 根据变更类型执行 ROA 变更
       - create：创建新 ROA（需创建占位 RPKI 对象）
       - modify：更新 ROA 字段
       - revoke：设置 ROA 状态为 revoked
    3. 更新关联的 VRP
    4. 记录执行结果
    5. 自动触发变更后验证

    Args:
        db: 异步数据库会话
        request_id: 变更请求 ID
        user: 执行人

    Returns:
        变更执行结果

    Raises:
        ValueError: 状态不允许执行或执行失败
    """
    change_request = await get_change_request(db, request_id)
    if change_request is None:
        raise ValueError(f"变更请求 ID {request_id} 不存在")

    if change_request.status != "approved":
        raise ValueError(f"变更请求当前状态为 {change_request.status}，仅 approved 状态可执行")

    execution_result = ROAChangeExecutionResult(
        success=False,
        message="",
        roa_id=change_request.roa_id,
    )

    try:
        if change_request.change_type == "create":
            roa_id = await _execute_create(db, change_request)
            change_request.roa_id = roa_id
            execution_result.roa_id = roa_id
            execution_result.message = f"ROA 创建成功（ID: {roa_id}）"

        elif change_request.change_type == "modify":
            await _execute_modify(db, change_request)
            execution_result.message = f"ROA {change_request.roa_id} 修改成功"

        elif change_request.change_type == "revoke":
            await _execute_revoke(db, change_request)
            execution_result.message = f"ROA {change_request.roa_id} 撤销成功"

        execution_result.success = True
        change_request.status = "executed"
        change_request.executed_at = datetime.now(UTC)

    except Exception as e:
        execution_result.success = False
        execution_result.error = str(e)
        execution_result.message = f"执行失败：{e}"
        change_request.status = "failed"
        logger.error(
            "变更执行失败",
            request_id=change_request.id,
            error=str(e),
            exc_info=True,
        )

    change_request.execution_result = execution_result.model_dump()
    await db.flush()
    await db.commit()
    await db.refresh(change_request)

    # 记录审计日志
    await audit_service.log_action(
        db=db,
        user_id=user.id,
        tenant_id=change_request.tenant_id,
        action="roa_change_request.execute",
        resource_type="roa_change_request",
        resource_id=str(change_request.id),
        details={
            "change_type": change_request.change_type,
            "success": execution_result.success,
            "roa_id": execution_result.roa_id,
            "error": execution_result.error,
        },
    )

    # 执行成功后自动触发变更后验证
    if execution_result.success:
        try:
            verification = await verify_change_result(db, change_request.id)
            execution_result.validation_status = (
                "passed" if verification.bgp_validation_passed else "warning"
            )
            change_request.execution_result = execution_result.model_dump()
            await db.commit()
        except Exception as e:
            logger.warning(
                "变更后验证失败",
                request_id=change_request.id,
                error=str(e),
            )

    return execution_result


async def _execute_create(db: AsyncSession, change_request: ROAChangeRequest) -> int:
    """执行创建 ROA 变更。

    创建流程：
    1. 查找一个可用的 RPKI 仓库（用于关联 RPKI 对象）
    2. 创建占位 RPKI 对象
    3. 创建 ROA
    4. 创建关联的 VRP

    Args:
        db: 异步数据库会话
        change_request: 变更请求

    Returns:
        新创建的 ROA ID

    Raises:
        ValueError: 无可用仓库或参数缺失
    """
    if change_request.prefix is None or change_request.origin_as is None:
        raise ValueError("创建 ROA 需要 prefix 和 origin_as")

    # 解析前缀
    import ipaddress

    network = ipaddress.ip_network(change_request.prefix, strict=False)
    prefix_family = network.version
    prefix_length = network.prefixlen

    # 查找一个可用的 RPKI 仓库
    from app.models.rpki import RPKIRepository

    repo_stmt = select(RPKIRepository).limit(1)
    repo_result = await db.execute(repo_stmt)
    repository = repo_result.scalar_one_or_none()

    if repository is None:
        raise ValueError("无可用 RPKI 仓库，无法创建 ROA")

    # 创建占位 RPKI 对象
    rpki_object = RPKIObject(
        repository_id=repository.id,
        object_type="roa",
        uri=f"local://roa/{change_request.prefix}_{change_request.origin_as}",
        status="valid",
        parsed_data={
            "prefix": change_request.prefix,
            "origin_as": change_request.origin_as,
            "max_length": change_request.max_length,
            "source": "manual_creation",
        },
    )
    db.add(rpki_object)
    await db.flush()

    # 创建 ROA
    roa = ROA(
        object_id=rpki_object.id,
        prefix=change_request.prefix,
        prefix_family=prefix_family,
        prefix_length=prefix_length,
        origin_as=change_request.origin_as,
        max_length=change_request.max_length,
        status="valid",
    )
    db.add(roa)
    await db.flush()

    # 创建关联 VRP
    vrp = VRP(
        prefix=roa.prefix,
        prefix_family=roa.prefix_family,
        prefix_length=roa.prefix_length,
        origin_as=roa.origin_as,
        max_length=roa.max_length,
        roa_id=roa.id,
        validation_status="valid",
    )
    db.add(vrp)
    await db.flush()

    return roa.id


async def _execute_modify(db: AsyncSession, change_request: ROAChangeRequest) -> None:
    """执行修改 ROA 变更。

    修改流程：
    1. 获取现有 ROA
    2. 更新 ROA 字段
    3. 更新关联的 VRP

    Args:
        db: 异步数据库会话
        change_request: 变更请求

    Raises:
        ValueError: ROA 不存在
    """
    if change_request.roa_id is None:
        raise ValueError("修改变更需要 roa_id")

    roa = await roa_service.get_roa_detail(db, change_request.roa_id)
    if roa is None:
        raise ValueError(f"ROA ID {change_request.roa_id} 不存在")

    # 更新 ROA 字段
    if change_request.prefix is not None:
        import ipaddress

        network = ipaddress.ip_network(change_request.prefix, strict=False)
        roa.prefix = change_request.prefix
        roa.prefix_family = network.version
        roa.prefix_length = network.prefixlen

    if change_request.origin_as is not None:
        roa.origin_as = change_request.origin_as

    if change_request.max_length is not None:
        roa.max_length = change_request.max_length

    await db.flush()

    # 更新关联的 VRP
    vrp_stmt = select(VRP).where(VRP.roa_id == roa.id)
    vrp_result = await db.execute(vrp_stmt)
    vrps = list(vrp_result.scalars().all())

    for vrp in vrps:
        if change_request.prefix is not None:
            vrp.prefix = roa.prefix
            vrp.prefix_family = roa.prefix_family
            vrp.prefix_length = roa.prefix_length
        if change_request.origin_as is not None:
            vrp.origin_as = roa.origin_as
        if change_request.max_length is not None:
            vrp.max_length = roa.max_length

    await db.flush()


async def _execute_revoke(db: AsyncSession, change_request: ROAChangeRequest) -> None:
    """执行撤销 ROA 变更。

    撤销流程：
    1. 获取现有 ROA
    2. 设置 ROA 状态为 revoked
    3. 更新关联的 VRP 状态

    Args:
        db: 异步数据库会话
        change_request: 变更请求

    Raises:
        ValueError: ROA 不存在
    """
    if change_request.roa_id is None:
        raise ValueError("撤销变更需要 roa_id")

    roa = await roa_service.get_roa_detail(db, change_request.roa_id)
    if roa is None:
        raise ValueError(f"ROA ID {change_request.roa_id} 不存在")

    # 设置 ROA 状态为 revoked
    roa.status = "revoked"
    await db.flush()

    # 更新关联的 VRP 状态
    vrp_stmt = select(VRP).where(VRP.roa_id == roa.id)
    vrp_result = await db.execute(vrp_stmt)
    vrps = list(vrp_result.scalars().all())

    for vrp in vrps:
        vrp.validation_status = "revoked"

    await db.flush()


# ──────────────────────────────────────────────
# 回滚
# ──────────────────────────────────────────────


async def rollback_change(
    db: AsyncSession,
    request_id: int,
    user: User,
) -> ROAChangeRequest:
    """回滚变更。

    回滚流程：
    1. 检查变更请求状态为 executed
    2. 根据变更类型恢复 ROA 到变更前状态
       - create 回滚：删除创建的 ROA
       - modify 回滚：恢复 ROA 原始字段
       - revoke 回滚：恢复 ROA 状态为 valid
    3. 更新关联的 VRP
    4. 记录回滚信息

    Args:
        db: 异步数据库会话
        request_id: 变更请求 ID
        user: 操作人

    Returns:
        更新后的变更请求对象

    Raises:
        ValueError: 状态不允许回滚
    """
    change_request = await get_change_request(db, request_id)
    if change_request is None:
        raise ValueError(f"变更请求 ID {request_id} 不存在")

    if change_request.status != "executed":
        raise ValueError(f"变更请求当前状态为 {change_request.status}，仅 executed 状态可回滚")

    rollback_info: dict[str, Any] = {
        "rolled_back_by": user.id,
        "rolled_back_at": datetime.now(UTC).isoformat(),
        "change_type": change_request.change_type,
    }

    try:
        if change_request.change_type == "create":
            # 回滚创建：删除 ROA
            if change_request.roa_id is not None:
                roa = await roa_service.get_roa_detail(db, change_request.roa_id)
                if roa is not None:
                    # 删除关联的 VRP
                    vrp_stmt = select(VRP).where(VRP.roa_id == roa.id)
                    vrp_result = await db.execute(vrp_stmt)
                    for vrp in vrp_result.scalars().all():
                        await db.delete(vrp)

                    # 删除 ROA
                    await db.delete(roa)
                    await db.flush()

                    rollback_info["deleted_roa_id"] = change_request.roa_id

        elif change_request.change_type == "modify":
            # 回滚修改：恢复原始字段
            if change_request.roa_id is not None:
                roa = await roa_service.get_roa_detail(db, change_request.roa_id)
                if roa is not None:
                    if change_request.current_prefix is not None:
                        import ipaddress

                        network = ipaddress.ip_network(change_request.current_prefix, strict=False)
                        roa.prefix = change_request.current_prefix
                        roa.prefix_family = network.version
                        roa.prefix_length = network.prefixlen

                    if change_request.current_origin_as is not None:
                        roa.origin_as = change_request.current_origin_as

                    if change_request.current_max_length is not None:
                        roa.max_length = change_request.current_max_length

                    await db.flush()

                    # 恢复 VRP
                    vrp_stmt = select(VRP).where(VRP.roa_id == roa.id)
                    vrp_result = await db.execute(vrp_stmt)
                    for vrp in vrp_result.scalars().all():
                        vrp.prefix = roa.prefix
                        vrp.prefix_family = roa.prefix_family
                        vrp.prefix_length = roa.prefix_length
                        vrp.origin_as = roa.origin_as
                        vrp.max_length = roa.max_length

                    await db.flush()

                    rollback_info["restored_roa_id"] = change_request.roa_id

        elif change_request.change_type == "revoke":
            # 回滚撤销：恢复 ROA 状态
            if change_request.roa_id is not None:
                roa = await roa_service.get_roa_detail(db, change_request.roa_id)
                if roa is not None:
                    roa.status = "valid"
                    await db.flush()

                    # 恢复 VRP 状态
                    vrp_stmt = select(VRP).where(VRP.roa_id == roa.id)
                    vrp_result = await db.execute(vrp_stmt)
                    for vrp in vrp_result.scalars().all():
                        vrp.validation_status = "valid"

                    await db.flush()

                    rollback_info["restored_roa_id"] = change_request.roa_id

        rollback_info["success"] = True
        change_request.status = "rolled_back"
        change_request.rollback_info = rollback_info

    except Exception as e:
        rollback_info["success"] = False
        rollback_info["error"] = str(e)
        change_request.rollback_info = rollback_info
        logger.error(
            "回滚失败",
            request_id=change_request.id,
            error=str(e),
            exc_info=True,
        )
        raise

    await db.flush()
    await db.commit()
    await db.refresh(change_request)

    # 记录审计日志
    await audit_service.log_action(
        db=db,
        user_id=user.id,
        tenant_id=change_request.tenant_id,
        action="roa_change_request.rollback",
        resource_type="roa_change_request",
        resource_id=str(change_request.id),
        details=rollback_info,
    )

    logger.info(
        "回滚变更请求",
        request_id=change_request.id,
        change_type=change_request.change_type,
    )
    return change_request


# ──────────────────────────────────────────────
# 变更后验证
# ──────────────────────────────────────────────


async def verify_change_result(db: AsyncSession, request_id: int) -> ROAChangeVerificationResult:
    """变更后验证。

    验证内容：
    1. 验证 RPKI 仓库状态（ROA 是否存在且状态正确）
    2. 验证 VRP 变化（VRP 是否已更新）
    3. 验证实际 BGP 状态（受影响公告的验证状态）

    Args:
        db: 异步数据库会话
        request_id: 变更请求 ID

    Returns:
        变更后验证结果

    Raises:
        ValueError: 变更请求不存在
    """
    change_request = await get_change_request(db, request_id)
    if change_request is None:
        raise ValueError(f"变更请求 ID {request_id} 不存在")

    result = ROAChangeVerificationResult(
        request_id=request_id,
        roa_id=change_request.roa_id,
    )

    issues: list[str] = []
    validation_details: dict[str, Any] = {}

    # 1. 验证 ROA 状态
    roa: ROA | None = None
    if change_request.roa_id is not None:
        roa = await roa_service.get_roa_detail(db, change_request.roa_id)

    if change_request.change_type == "create":
        if roa is None:
            issues.append("创建的 ROA 不存在")
            result.roa_status = None
        else:
            result.roa_status = roa.status
            if roa.status != "valid":
                issues.append(f"创建的 ROA 状态为 {roa.status}，预期为 valid")
            validation_details["roa_prefix"] = roa.prefix
            validation_details["roa_origin_as"] = roa.origin_as

    elif change_request.change_type == "modify":
        if roa is None:
            issues.append("修改的 ROA 不存在")
        else:
            result.roa_status = roa.status
            # 检查字段是否已更新
            if change_request.prefix is not None and roa.prefix != change_request.prefix:
                issues.append(f"ROA prefix 未更新：期望 {change_request.prefix}，实际 {roa.prefix}")
            if change_request.origin_as is not None and roa.origin_as != change_request.origin_as:
                issues.append(
                    f"ROA origin_as 未更新：期望 {change_request.origin_as}，实际 {roa.origin_as}"
                )
            validation_details["roa_prefix"] = roa.prefix
            validation_details["roa_origin_as"] = roa.origin_as

    elif change_request.change_type == "revoke":
        if roa is None:
            issues.append("撤销的 ROA 不存在")
        else:
            result.roa_status = roa.status
            if roa.status != "revoked":
                issues.append(f"ROA 状态为 {roa.status}，预期为 revoked")

    # 2. 验证 VRP 变化
    if roa is not None:
        vrp_stmt = select(VRP).where(VRP.roa_id == roa.id)
        vrp_result = await db.execute(vrp_stmt)
        vrps = list(vrp_result.scalars().all())
        result.vrp_count = len(vrps)

        if change_request.change_type == "revoke":
            # 撤销后 VRP 状态应为 revoked
            revoked_vrps = [v for v in vrps if v.validation_status == "revoked"]
            result.vrp_updated = len(revoked_vrps) == len(vrps)
            if not result.vrp_updated and vrps:
                issues.append("部分 VRP 状态未更新为 revoked")
        elif change_request.change_type == "create":
            # 创建后应有 VRP
            result.vrp_updated = len(vrps) > 0
            if not result.vrp_updated:
                issues.append("创建 ROA 后未生成关联 VRP")
        elif change_request.change_type == "modify":
            # 修改后 VRP 字段应与 ROA 一致
            result.vrp_updated = True
            for vrp in vrps:
                if vrp.prefix != roa.prefix or vrp.origin_as != roa.origin_as:
                    result.vrp_updated = False
                    issues.append(f"VRP {vrp.id} 字段与 ROA 不一致")
                    break

        validation_details["vrp_count"] = len(vrps)
    else:
        result.vrp_updated = change_request.change_type == "revoke"

    # 3. 验证 BGP 状态
    if roa is not None:
        related_announcements = await roa_service.get_related_bgp_announcements(db, roa)
        result.affected_announcements = len(related_announcements)

        # 验证每个受影响公告的 RPKI 状态
        bgp_valid_count = 0
        bgp_invalid_count = 0
        bgp_not_found_count = 0

        for ann in related_announcements:
            status = ann.rpki_validation_status or "not_found"
            if status == "valid":
                bgp_valid_count += 1
            elif status == "invalid":
                bgp_invalid_count += 1
            else:
                bgp_not_found_count += 1

        validation_details["bgp_validation"] = {
            "valid": bgp_valid_count,
            "invalid": bgp_invalid_count,
            "not_found": bgp_not_found_count,
        }

        # 判定 BGP 验证是否通过
        if change_request.change_type == "revoke":
            # 撤销后受影响公告应为 not_found
            result.bgp_validation_passed = bgp_invalid_count == 0 or bgp_not_found_count > 0
        elif change_request.change_type == "create":
            # 创建后受影响公告应为 valid
            result.bgp_validation_passed = bgp_valid_count > 0
        else:
            # 修改后不应有 invalid 公告（除非是预期行为）
            result.bgp_validation_passed = bgp_invalid_count == 0

        if not result.bgp_validation_passed:
            issues.append(f"BGP 验证未通过：{bgp_invalid_count} 个公告为 invalid")
    else:
        result.bgp_validation_passed = change_request.change_type == "revoke"

    result.validation_details = validation_details
    result.issues = issues

    logger.info(
        "变更后验证完成",
        request_id=request_id,
        vrp_updated=result.vrp_updated,
        bgp_passed=result.bgp_validation_passed,
        issues_count=len(issues),
    )
    return result


# ──────────────────────────────────────────────
# 高风险变更检查
# ──────────────────────────────────────────────


def check_high_risk_change(change_request: ROAChangeRequest) -> bool:
    """检查是否为高风险变更。

    高风险变更判定：
    - 风险等级为 high 或 critical
    - 影响评估标记为高风险
    - 涉及核心前缀（prefix_importance 为 critical）

    高风险变更必须强制审批，不允许自动批准。

    Args:
        change_request: 变更请求

    Returns:
        是否为高风险变更
    """
    # 风险等级判定
    if change_request.risk_level in ("high", "critical"):
        return True

    # 影响评估标记
    if change_request.impact_summary:
        if change_request.impact_summary.get("is_high_risk"):
            return True
        if change_request.impact_summary.get("prefix_importance") == "critical":
            return True

    return False


__all__ = [
    "approve_change_request",
    "check_high_risk_change",
    "create_change_request",
    "execute_change_request",
    "get_change_request",
    "get_change_requests",
    "rollback_change",
    "verify_change_result",
]
