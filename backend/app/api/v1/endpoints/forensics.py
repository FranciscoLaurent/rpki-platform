"""自动取证与处置闭环 API 端点（Task 20）。

提供事件自动取证、取证结果查询、处置建议生成、事件关闭与复盘、
通知发送等接口，支撑 RPKI/BGP 路由安全事件的自动取证与处置闭环。

权限码使用字符串字面量 ``incident:read`` 与 ``incident:write``，
不修改共享的 rbac.py 权限定义。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.detection import Incident
from app.models.user import User
from app.schemas.forensics import (
    EvidenceCollection,
    IncidentCloseRequest,
    IncidentReview,
    NotificationRequest,
    NotificationResult,
    RemediationSuggestion,
    RemediationSuggestionList,
)
from app.services.forensics_service import collect_evidence
from app.services.notification_service import notify_incident
from app.services.remediation_service import (
    close_incident_with_review,
    generate_remediation_suggestions,
)

router = APIRouter()

# 取证与处置权限码（使用字符串字面量避免修改共享的 rbac.py）
INCIDENT_READ = "incident:read"
INCIDENT_WRITE = "incident:write"


# ──────────────────────────────────────────────
# 自动取证
# ──────────────────────────────────────────────


@router.post(
    "/incidents/{incident_id}/collect-evidence",
    response_model=EvidenceCollection,
)
async def collect_incident_evidence(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INCIDENT_WRITE)),
) -> EvidenceCollection:
    """触发事件自动取证（需要 ``incident:write`` 权限）。

    采集事件关联的 ROA/VRP、BGP 样本、AS_PATH、传播范围、观察点、
    资产关系、变更记录与历史基线等证据，存入事件 evidence 字段。
    """
    # 检查事件存在
    incident = await _get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )

    evidence = await collect_evidence(
        db, incident_id, collected_by=current_user.id
    )
    await db.commit()
    return EvidenceCollection.model_validate(evidence)


@router.get(
    "/incidents/{incident_id}/evidence",
    response_model=EvidenceCollection,
)
async def get_incident_evidence(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INCIDENT_READ)),
) -> EvidenceCollection:
    """获取事件取证结果（需要 ``incident:read`` 权限）。"""
    incident = await _get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )

    if not incident.evidence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 暂无取证结果，请先触发取证",
        )

    return EvidenceCollection.model_validate(incident.evidence)


# ──────────────────────────────────────────────
# 处置建议
# ──────────────────────────────────────────────


@router.get(
    "/incidents/{incident_id}/remediation",
    response_model=RemediationSuggestionList,
)
async def get_incident_remediation(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INCIDENT_READ)),
) -> RemediationSuggestionList:
    """获取事件处置建议（需要 ``incident:read`` 权限）。

    根据事件类型与风险评分生成处置建议，建议类型涵盖：
    联系异常 ASN/上游、修正 ROA、调整策略、发布更具体合法前缀、
    清洗联动、客户通知。
    """
    incident = await _get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )

    # 调用处置建议生成服务
    result = await generate_remediation_suggestions(db, incident_id)
    await db.commit()

    # 将处置动作转换为简化建议格式
    suggestions: list[RemediationSuggestion] = []
    for action in result.suggestions:
        suggestions.append(
            RemediationSuggestion(
                type=_map_action_type(action.action_type),
                priority=action.priority,
                description=action.description or action.title,
                actionable_steps=_build_actionable_steps(action),
                estimated_impact=_estimate_impact(action.priority),
            )
        )

    return RemediationSuggestionList(
        incident_id=incident_id,
        suggestions=suggestions,
        total=len(suggestions),
    )


# ──────────────────────────────────────────────
# 事件关闭与复盘
# ──────────────────────────────────────────────


@router.post(
    "/incidents/{incident_id}/close",
    response_model=IncidentReview,
)
async def close_incident(
    incident_id: int,
    close_request: IncidentCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INCIDENT_WRITE)),
) -> IncidentReview:
    """关闭事件并完成复盘（需要 ``incident:write`` 权限）。

    一次性完成：
    1. 确认恢复（检查当前 BGP 状态）
    2. 记录根因与处置结论
    3. 保留证据与操作链
    4. 沉淀规则和案例库
    """
    incident = await _get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )

    try:
        updated_incident = await close_incident_with_review(
            db,
            incident_id,
            root_cause=close_request.root_cause,
            resolution=close_request.resolution,
            reviewer_id=close_request.reviewer_id,
            lessons_learned=close_request.lessons_learned,
            improvements=close_request.improvements,
            save_to_case_library=close_request.save_to_case_library,
        )
        await db.commit()
        await db.refresh(updated_incident)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e

    # 构建复盘结果响应
    return IncidentReview(
        incident_id=incident_id,
        root_cause=close_request.root_cause,
        resolution=close_request.resolution,
        reviewer_id=close_request.reviewer_id,
        reviewed_at=datetime.now(timezone.utc),
        evidence_preserved=True,
        operation_chain=updated_incident.timeline or [],
        rule_updates=[],
        status=updated_incident.status,
    )


# ──────────────────────────────────────────────
# 通知发送
# ──────────────────────────────────────────────


@router.post(
    "/incidents/{incident_id}/notify",
    response_model=NotificationResult,
)
async def notify_incident_endpoint(
    incident_id: int,
    notify_request: NotificationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INCIDENT_WRITE)),
) -> NotificationResult:
    """发送事件通知（需要 ``incident:write`` 权限）。

    通过指定渠道列表发送事件通知，支持 Webhook、邮件、短信、
    企业协作工具与 ITSM/SOC 集成。
    """
    incident = await _get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )

    # 确保请求体中的 incident_id 与路径一致
    result = await notify_incident(
        db,
        incident_id,
        channels=notify_request.channels or None,
        title=notify_request.title,
        content=notify_request.content,
        triggered_by=current_user.id,
    )
    await db.commit()

    return NotificationResult.model_validate(result)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _get_incident(
    db: AsyncSession, incident_id: int
) -> Incident | None:
    """获取事件。"""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _map_action_type(action_type: str) -> str:
    """将处置动作类型映射为简化建议类型。"""
    mapping = {
        "contact_asn": "contact_asn",
        "contact_upstream": "contact_asn",
        "fix_roa": "fix_roa",
        "adjust_policy": "adjust_policy",
        "announce_legitimate_prefix": "announce_specific",
        "scrubber_coordination": "scrubber",
        "customer_notification": "notify_customer",
        "other": "adjust_policy",
    }
    return mapping.get(action_type, "adjust_policy")


def _build_actionable_steps(action: Any) -> list[str]:
    """根据处置动作构建可执行步骤列表。"""
    steps: list[str] = []
    if action.title:
        steps.append(action.title)
    if action.description:
        steps.append(action.description)
    if action.target:
        steps.append(f"处置目标：{action.target}")
    return steps


def _estimate_impact(priority: str) -> str:
    """根据优先级估算预期影响。"""
    impact_map = {
        "immediate": "需立即处置，影响范围大",
        "high": "影响较大，需尽快处置",
        "medium": "影响中等，建议及时处置",
        "low": "影响较小，可择机处置",
    }
    return impact_map.get(priority, "影响待评估")
