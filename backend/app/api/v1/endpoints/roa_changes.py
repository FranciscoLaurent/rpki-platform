"""ROA 变更审批管理 API 端点。

提供 ROA 变更请求的创建、查询、审批、执行、回滚与变更后验证等接口，
以及审批规则的 CRUD 管理接口。

本文件导出两个路由器：
- ``changes_router``：ROA 变更请求路由（前缀 ``/roa-changes``）
- ``rules_router``：ROA 审批规则路由（前缀 ``/roa-approval-rules``）

在 ``router.py`` 中注册示例::

    from app.api.v1.endpoints import roa_changes
    api_router.include_router(
        roa_changes.changes_router,
        prefix="/roa-changes",
        tags=["ROA 变更审批管理"],
    )
    api_router.include_router(
        roa_changes.rules_router,
        prefix="/roa-approval-rules",
        tags=["ROA 审批规则管理"],
    )

权限要求：
- roa:read：查询变更请求与审批规则
- roa:write：创建变更请求、执行变更、回滚变更
- roa:approve：审批变更请求
- roa:admin：管理审批规则（创建/更新/删除）
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.roa_change import (
    ROAApprovalAction,
    ROAApprovalRuleCreate,
    ROAApprovalRuleListResponse,
    ROAApprovalRuleResponse,
    ROAApprovalRuleUpdate,
    ROAChangeExecutionResult,
    ROAChangeRequestCreate,
    ROAChangeRequestListResponse,
    ROAChangeRequestResponse,
    ROAChangeVerificationResult,
    UserInfo,
)
from app.services import roa_approval_service, roa_change_service

# ROA 权限码（使用字符串字面量，避免修改共享的 rbac.py）
ROA_READ = "roa:read"
ROA_WRITE = "roa:write"
ROA_APPROVE = "roa:approve"
ROA_ADMIN = "roa:admin"

# 变更请求路由器（前缀 /roa-changes）
changes_router = APIRouter()

# 审批规则路由器（前缀 /roa-approval-rules）
rules_router = APIRouter()


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _build_change_request_response(
    db: AsyncSession, change_request
) -> ROAChangeRequestResponse:
    """构建变更请求响应（含申请人/审批人信息）。"""
    response = ROAChangeRequestResponse.model_validate(change_request)

    # 嵌入申请人信息
    requester_stmt = select(User).where(User.id == change_request.requested_by)
    requester_result = await db.execute(requester_stmt)
    requester = requester_result.scalar_one_or_none()
    if requester is not None:
        response.requester = UserInfo.model_validate(requester)

    # 嵌入审批人信息
    if change_request.approved_by is not None:
        approver_stmt = select(User).where(User.id == change_request.approved_by)
        approver_result = await db.execute(approver_stmt)
        approver = approver_result.scalar_one_or_none()
        if approver is not None:
            response.approver = UserInfo.model_validate(approver)

    return response


# ──────────────────────────────────────────────
# ROA 变更请求端点（前缀 /roa-changes）
# ──────────────────────────────────────────────


@changes_router.post(
    "",
    response_model=ROAChangeRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_change_request(
    request_create: ROAChangeRequestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_WRITE)),
) -> ROAChangeRequestResponse:
    """创建 ROA 变更请求。

    需要 ``roa:write`` 权限。

    创建流程会自动执行影响评估、设置风险等级、匹配审批规则。
    如果匹配到自动批准规则且非高风险变更，请求将直接进入 approved 状态。
    """
    try:
        change_request = await roa_change_service.create_change_request(
            db, request_create, current_user
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return await _build_change_request_response(db, change_request)


@changes_router.get("", response_model=ROAChangeRequestListResponse)
async def list_change_requests(
    change_type: str | None = Query(None, description="按变更类型过滤：create/modify/revoke"),
    request_status: str | None = Query(
        None,
        alias="status",
        description=(
            "按状态过滤：draft/pending_approval/approved/rejected/executed/failed/rolled_back"
        ),
    ),
    risk_level: str | None = Query(None, description="按风险等级过滤：low/medium/high/critical"),
    requested_by: int | None = Query(None, description="按申请人 ID 过滤"),
    roa_id: int | None = Query(None, description="按 ROA ID 过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_READ)),
) -> ROAChangeRequestListResponse:
    """查询 ROA 变更请求列表。

    需要 ``roa:read`` 权限。支持按变更类型、状态、风险等级、
    申请人、ROA ID 过滤，支持分页。
    """
    filters: dict[str, object] = {}
    if change_type is not None:
        filters["change_type"] = change_type
    if request_status is not None:
        filters["status"] = request_status
    if risk_level is not None:
        filters["risk_level"] = risk_level
    if requested_by is not None:
        filters["requested_by"] = requested_by
    if roa_id is not None:
        filters["roa_id"] = roa_id

    requests, total = await roa_change_service.get_change_requests(
        db, filters=filters or None, skip=skip, limit=limit
    )

    items = [await _build_change_request_response(db, r) for r in requests]

    return ROAChangeRequestListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit,
    )


@changes_router.get("/{request_id}", response_model=ROAChangeRequestResponse)
async def get_change_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_READ)),
) -> ROAChangeRequestResponse:
    """获取 ROA 变更请求详情。

    需要 ``roa:read`` 权限。
    """
    change_request = await roa_change_service.get_change_request(db, request_id)
    if change_request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"变更请求 ID {request_id} 不存在",
        )

    return await _build_change_request_response(db, change_request)


@changes_router.post(
    "/{request_id}/approve",
    response_model=ROAChangeRequestResponse,
)
async def approve_change_request(
    request_id: int,
    approval: ROAApprovalAction,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_APPROVE)),
) -> ROAChangeRequestResponse:
    """审批 ROA 变更请求。

    需要 ``roa:approve`` 权限。

    输入审批动作（approve/reject）与审批意见。
    对于双人审批或委员会审批，需要多人分别批准后请求才会进入 approved 状态。
    """
    try:
        change_request = await roa_change_service.approve_change_request(
            db,
            request_id,
            current_user,
            approval.action,
            approval.comments,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return await _build_change_request_response(db, change_request)


@changes_router.post(
    "/{request_id}/execute",
    response_model=ROAChangeExecutionResult,
)
async def execute_change_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_WRITE)),
) -> ROAChangeExecutionResult:
    """执行 ROA 变更。

    需要 ``roa:write`` 权限。

    仅 approved 状态的变更请求可执行。执行后会自动触发变更后验证。
    """
    try:
        result = await roa_change_service.execute_change_request(db, request_id, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.message,
        )

    return result


@changes_router.post(
    "/{request_id}/rollback",
    response_model=ROAChangeRequestResponse,
)
async def rollback_change(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_WRITE)),
) -> ROAChangeRequestResponse:
    """回滚 ROA 变更。

    需要 ``roa:write`` 权限。

    仅 executed 状态的变更请求可回滚。回滚会恢复 ROA 到变更前状态。
    """
    try:
        change_request = await roa_change_service.rollback_change(db, request_id, current_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return await _build_change_request_response(db, change_request)


@changes_router.get(
    "/{request_id}/verification",
    response_model=ROAChangeVerificationResult,
)
async def get_change_verification(
    request_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_READ)),
) -> ROAChangeVerificationResult:
    """获取变更后验证结果。

    需要 ``roa:read`` 权限。

    验证内容包括：ROA 状态、VRP 更新情况、受影响 BGP 公告的验证状态。
    """
    try:
        return await roa_change_service.verify_change_result(db, request_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# ROA 审批规则端点（前缀 /roa-approval-rules）
# ──────────────────────────────────────────────


@rules_router.post(
    "",
    response_model=ROAApprovalRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_approval_rule(
    rule_create: ROAApprovalRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_ADMIN)),
) -> ROAApprovalRuleResponse:
    """创建 ROA 审批规则。

    需要 ``roa:admin`` 权限。
    """
    rule = await roa_approval_service.create_approval_rule(db, rule_create)
    return ROAApprovalRuleResponse.model_validate(rule)


@rules_router.get("", response_model=ROAApprovalRuleListResponse)
async def list_approval_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_READ)),
) -> ROAApprovalRuleListResponse:
    """获取 ROA 审批规则列表。

    需要 ``roa:read`` 权限。
    """
    rules = await roa_approval_service.get_approval_rules(db)
    return ROAApprovalRuleListResponse(
        items=[ROAApprovalRuleResponse.model_validate(r) for r in rules],
        total=len(rules),
    )


@rules_router.put("/{rule_id}", response_model=ROAApprovalRuleResponse)
async def update_approval_rule(
    rule_id: int,
    rule_update: ROAApprovalRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_ADMIN)),
) -> ROAApprovalRuleResponse:
    """更新 ROA 审批规则。

    需要 ``roa:admin`` 权限。
    """
    rule = await roa_approval_service.get_approval_rule_by_id(db, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"审批规则 ID {rule_id} 不存在",
        )

    updated_rule = await roa_approval_service.update_approval_rule(db, rule, rule_update)
    return ROAApprovalRuleResponse.model_validate(updated_rule)


@rules_router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_approval_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(ROA_ADMIN)),
) -> None:
    """删除 ROA 审批规则。

    需要 ``roa:admin`` 权限。
    """
    rule = await roa_approval_service.get_approval_rule_by_id(db, rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"审批规则 ID {rule_id} 不存在",
        )

    await roa_approval_service.delete_approval_rule(db, rule)
