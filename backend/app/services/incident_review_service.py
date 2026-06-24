"""事件复盘服务。

提供事件关闭与复盘能力，包括：
- 创建复盘记录（根因分析、经验教训、改进措施）
- 关闭事件并联动复盘
- 保留证据与操作链
- 沉淀规则与案例库
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import Incident
from app.models.forensics import (
    CaseLibrary,
    ForensicEvidence,
    IncidentReview,
    RemediationAction,
)
from app.schemas.forensics import (
    CaseLibraryCreate,
    IncidentCloseAndReviewRequest,
    IncidentReviewCreate,
    IncidentReviewUpdate,
)
from app.services import incident_service

logger = get_logger("app.incident_review_service")


async def create_review(
    db: AsyncSession, review_data: IncidentReviewCreate
) -> IncidentReview:
    """创建事件复盘记录。

    Args:
        db: 异步数据库会话
        review_data: 复盘创建数据

    Returns:
        创建的复盘记录对象
    """
    # 若未提供操作链，自动构建
    operation_chain = review_data.operation_chain
    if operation_chain is None:
        operation_chain = await _build_operation_chain(
            db, review_data.incident_id
        )

    review = IncidentReview(
        incident_id=review_data.incident_id,
        root_cause=review_data.root_cause,
        lessons_learned=review_data.lessons_learned,
        improvements=review_data.improvements,
        prevention_measures=review_data.prevention_measures,
        review_summary=review_data.review_summary,
        reviewed_by=review_data.reviewed_by,
        reviewed_at=review_data.reviewed_at,
        evidence_preserved=review_data.evidence_preserved,
        operation_chain=operation_chain,
        rule_updates=review_data.rule_updates,
        tenant_id=review_data.tenant_id,
    )
    db.add(review)
    await db.flush()

    logger.info(
        "事件复盘记录已创建",
        review_id=review.id,
        incident_id=review.incident_id,
    )
    return review


async def get_review(
    db: AsyncSession, review_id: int
) -> IncidentReview | None:
    """根据 ID 获取复盘记录。"""
    stmt = select(IncidentReview).where(IncidentReview.id == review_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_review_by_incident(
    db: AsyncSession, incident_id: int
) -> IncidentReview | None:
    """根据事件 ID 获取复盘记录。"""
    stmt = (
        select(IncidentReview)
        .where(IncidentReview.incident_id == incident_id)
        .order_by(IncidentReview.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_reviews(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[IncidentReview]:
    """查询复盘记录列表。"""
    stmt = (
        select(IncidentReview)
        .order_by(IncidentReview.reviewed_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_reviews(db: AsyncSession) -> int:
    """统计复盘记录数量。"""
    stmt = select(func.count(IncidentReview.id))
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_review(
    db: AsyncSession,
    review: IncidentReview,
    review_update: IncidentReviewUpdate,
) -> IncidentReview:
    """更新复盘记录。"""
    update_data = review_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(review, field, value)

    await db.flush()
    logger.info(
        "复盘记录已更新",
        review_id=review.id,
        fields=list(update_data.keys()),
    )
    return review


async def close_and_review(
    db: AsyncSession,
    request: IncidentCloseAndReviewRequest,
    reviewed_by: int | None = None,
) -> dict[str, Any]:
    """事件关闭与复盘一体化操作。

    一次性完成：
    1. 关闭事件（记录处置结论）
    2. 创建复盘记录（根因、经验教训、改进措施）
    3. 保留证据与操作链
    4. 可选：沉淀到案例库

    Args:
        db: 异步数据库会话
        request: 关闭与复盘请求
        reviewed_by: 复盘人用户 ID

    Returns:
        包含 incident、review、case（可选）的字典
    """
    now = datetime.now(timezone.utc)

    # 1. 关闭事件
    incident = await incident_service.close_incident(
        db, request.incident_id, request.resolution
    )
    if incident is None:
        return {
            "incident": None,
            "review": None,
            "case": None,
            "error": f"事件 ID {request.incident_id} 不存在",
        }

    # 2. 构建操作链
    operation_chain = await _build_operation_chain(db, request.incident_id)

    # 3. 创建复盘记录
    review = IncidentReview(
        incident_id=request.incident_id,
        root_cause=request.root_cause,
        lessons_learned=request.lessons_learned,
        improvements=request.improvements,
        prevention_measures=request.prevention_measures,
        review_summary=request.resolution,
        reviewed_by=reviewed_by,
        reviewed_at=now,
        evidence_preserved=request.preserve_evidence,
        operation_chain=operation_chain,
        tenant_id=incident.tenant_id,
    )
    db.add(review)
    await db.flush()

    # 4. 可选：沉淀到案例库
    case: CaseLibrary | None = None
    if request.save_to_case_library:
        case = await _create_case_from_incident(
            db,
            incident,
            review,
            request.case_title,
            request.case_tags,
            reviewed_by,
        )

    logger.info(
        "事件关闭与复盘完成",
        incident_id=request.incident_id,
        review_id=review.id,
        case_id=case.id if case else None,
    )

    return {
        "incident": incident,
        "review": review,
        "case": case,
        "error": None,
    }


# ──────────────────────────────────────────────
# 案例库管理
# ──────────────────────────────────────────────


async def create_case(
    db: AsyncSession, case_data: CaseLibraryCreate
) -> CaseLibrary:
    """创建案例库记录。"""
    case = CaseLibrary(
        title=case_data.title,
        description=case_data.description,
        root_cause=case_data.root_cause,
        remediation_plan=case_data.remediation_plan,
        tags=case_data.tags,
        severity=case_data.severity,
        incident_ids=case_data.incident_ids,
        alert_type=case_data.alert_type,
        affected_prefixes=case_data.affected_prefixes,
        affected_asns=case_data.affected_asns,
        is_published=case_data.is_published,
        created_by=case_data.created_by,
        tenant_id=case_data.tenant_id,
    )
    db.add(case)
    await db.flush()
    logger.info(
        "案例已创建",
        case_id=case.id,
        title=case.title,
    )
    return case


async def get_case(db: AsyncSession, case_id: int) -> CaseLibrary | None:
    """根据 ID 获取案例。"""
    stmt = select(CaseLibrary).where(CaseLibrary.id == case_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_cases(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 50,
    severity: str | None = None,
    alert_type: str | None = None,
    tag: str | None = None,
    is_published: bool | None = None,
    keyword: str | None = None,
) -> list[CaseLibrary]:
    """查询案例列表。"""
    stmt = select(CaseLibrary)

    if severity:
        stmt = stmt.where(CaseLibrary.severity == severity)
    if alert_type:
        stmt = stmt.where(CaseLibrary.alert_type == alert_type)
    if is_published is not None:
        stmt = stmt.where(CaseLibrary.is_published.is_(is_published))
    if keyword:
        # 关键词搜索（标题与描述）
        like_pattern = f"%{keyword}%"
        stmt = stmt.where(
            (CaseLibrary.title.ilike(like_pattern))
            | (CaseLibrary.description.ilike(like_pattern))
        )

    stmt = stmt.order_by(CaseLibrary.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    cases = list(result.scalars().all())

    # 标签过滤（内存过滤，JSON 包含查询）
    if tag:
        cases = [
            c for c in cases if c.tags and tag in c.tags
        ]

    return cases


async def count_cases(
    db: AsyncSession,
    severity: str | None = None,
    alert_type: str | None = None,
    is_published: bool | None = None,
    keyword: str | None = None,
) -> int:
    """统计案例数量。"""
    stmt = select(func.count(CaseLibrary.id))

    if severity:
        stmt = stmt.where(CaseLibrary.severity == severity)
    if alert_type:
        stmt = stmt.where(CaseLibrary.alert_type == alert_type)
    if is_published is not None:
        stmt = stmt.where(CaseLibrary.is_published.is_(is_published))
    if keyword:
        like_pattern = f"%{keyword}%"
        stmt = stmt.where(
            (CaseLibrary.title.ilike(like_pattern))
            | (CaseLibrary.description.ilike(like_pattern))
        )

    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def update_case(
    db: AsyncSession,
    case: CaseLibrary,
    case_update: Any,
) -> CaseLibrary:
    """更新案例。"""
    update_data = case_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(case, field, value)

    await db.flush()
    logger.info(
        "案例已更新",
        case_id=case.id,
        fields=list(update_data.keys()),
    )
    return case


async def delete_case(db: AsyncSession, case: CaseLibrary) -> None:
    """删除案例。"""
    await db.delete(case)
    await db.flush()
    logger.info("案例已删除", case_id=case.id)


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _build_operation_chain(
    db: AsyncSession, incident_id: int
) -> list[dict[str, Any]]:
    """构建事件的操作链（处置动作时间线）。

    汇总事件关联的处置动作，按时间排序形成操作链。
    """
    stmt = (
        select(RemediationAction)
        .where(RemediationAction.incident_id == incident_id)
        .order_by(RemediationAction.created_at.asc())
    )
    result = await db.execute(stmt)
    actions = list(result.scalars().all())

    chain: list[dict[str, Any]] = []
    for action in actions:
        chain.append(
            {
                "action_id": action.id,
                "action_type": action.action_type,
                "title": action.title,
                "status": action.status,
                "executed_by": action.executed_by,
                "executed_at": action.executed_at.isoformat()
                if action.executed_at
                else None,
                "result": action.result,
            }
        )

    # 补充证据采集节点
    evidence_stmt = (
        select(ForensicEvidence)
        .where(ForensicEvidence.incident_id == incident_id)
        .order_by(ForensicEvidence.collected_at.asc())
    )
    evidence_result = await db.execute(evidence_stmt)
    evidences = list(evidence_result.scalars().all())
    for evidence in evidences:
        chain.append(
            {
                "evidence_id": evidence.id,
                "evidence_type": evidence.evidence_type,
                "title": evidence.title,
                "collected_at": evidence.collected_at.isoformat(),
                "is_auto_collected": evidence.is_auto_collected,
            }
        )

    # 按时间排序（executed_at 或 collected_at）
    def _get_time(item: dict[str, Any]) -> str:
        return item.get("executed_at") or item.get("collected_at") or ""

    chain.sort(key=_get_time)

    return chain


async def _create_case_from_incident(
    db: AsyncSession,
    incident: Incident,
    review: IncidentReview,
    case_title: str | None,
    case_tags: list[str] | None,
    created_by: int | None,
) -> CaseLibrary:
    """从事件与复盘记录创建案例库记录。"""
    title = case_title or f"案例：{incident.title}"
    case = CaseLibrary(
        title=title,
        description=incident.description,
        root_cause=review.root_cause,
        remediation_plan=review.improvements,
        tags=case_tags or [],
        severity=incident.severity,
        incident_ids=[incident.id],
        affected_prefixes=incident.affected_prefixes,
        affected_asns=incident.affected_asns,
        is_published=False,
        created_by=created_by,
        tenant_id=incident.tenant_id,
    )
    db.add(case)
    await db.flush()
    logger.info(
        "案例已从事件沉淀",
        case_id=case.id,
        incident_id=incident.id,
    )
    return case


__all__ = [
    "close_and_review",
    "count_cases",
    "count_reviews",
    "create_case",
    "create_review",
    "delete_case",
    "get_case",
    "get_cases",
    "get_review",
    "get_review_by_incident",
    "get_reviews",
    "update_case",
    "update_review",
]
