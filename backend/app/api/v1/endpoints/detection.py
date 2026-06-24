"""BGP 路由安全检测引擎 API 端点。

提供检测规则管理、手动扫描、告警查询与处置、事件管理与风险评分查询接口。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_kafka, require_permissions
from app.core.database import get_db
from app.core.kafka import KafkaService
from app.models.bgp import BGPAnnouncement
from app.models.detection import (
    Alert,
    DetectionRule,
    Incident,
    RiskScore,
)
from app.models.user import User
from app.schemas.detection import (
    AlertAssignRequest,
    AlertQueryParams,
    AlertResponse,
    AlertStatusUpdate,
    DetectionResult,
    DetectionRuleCreate,
    DetectionRuleResponse,
    DetectionRuleUpdate,
    IncidentAssignRequest,
    IncidentCloseRequest,
    IncidentCreate,
    IncidentQueryParams,
    IncidentResponse,
    IncidentUpdate,
    RiskScoreResponse,
    ScanRequest,
    ScanResponse,
    TimelineEvent,
)
from app.services import alert_service, incident_service
from app.services.detection import (
    RuleEngine,
    detect_rpki_invalid_propagation,
    detect_withdraw_flap,
    evaluate_announcement,
)

router = APIRouter()

# 检测引擎权限码（使用字符串字面量避免修改共享的 rbac.py）
DETECTION_READ = "detection:read"
DETECTION_WRITE = "detection:write"


# ──────────────────────────────────────────────
# 检测规则管理
# ──────────────────────────────────────────────


@router.post(
    "/rules",
    response_model=DetectionRuleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_detection_rule(
    rule_create: DetectionRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> DetectionRuleResponse:
    """创建检测规则（需要 ``detection:write`` 权限）。"""
    # 检查 code 唯一性
    stmt = select(DetectionRule).where(DetectionRule.code == rule_create.code)
    result = await db.execute(stmt)
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"规则编码 {rule_create.code} 已存在",
        )

    rule = DetectionRule(
        name=rule_create.name,
        code=rule_create.code,
        description=rule_create.description,
        rule_type=rule_create.rule_type,
        enabled=rule_create.enabled,
        priority=rule_create.priority,
        conditions=rule_create.conditions,
        thresholds=rule_create.thresholds,
        whitelist=rule_create.whitelist,
        scope=rule_create.scope,
        severity=rule_create.severity,
        tenant_id=rule_create.tenant_id,
    )
    db.add(rule)
    await db.flush()
    await db.commit()
    await db.refresh(rule)
    return DetectionRuleResponse.model_validate(rule)


@router.get("/rules", response_model=list[DetectionRuleResponse])
async def list_detection_rules(
    rule_type: str | None = Query(None, description="按规则类型过滤"),
    enabled: bool | None = Query(None, description="按启用状态过滤"),
    severity: str | None = Query(None, description="按严重等级过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=500, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> list[DetectionRuleResponse]:
    """获取检测规则列表（需要 ``detection:read`` 权限）。"""
    stmt = select(DetectionRule)
    if rule_type:
        stmt = stmt.where(DetectionRule.rule_type == rule_type)
    if enabled is not None:
        stmt = stmt.where(DetectionRule.enabled.is_(enabled))
    if severity:
        stmt = stmt.where(DetectionRule.severity == severity)

    stmt = stmt.order_by(DetectionRule.priority.asc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    rules = list(result.scalars().all())
    return [DetectionRuleResponse.model_validate(r) for r in rules]


@router.get(
    "/rules/{rule_id}", response_model=DetectionRuleResponse
)
async def get_detection_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> DetectionRuleResponse:
    """获取检测规则详情（需要 ``detection:read`` 权限）。"""
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"规则 ID {rule_id} 不存在",
        )
    return DetectionRuleResponse.model_validate(rule)


@router.put(
    "/rules/{rule_id}", response_model=DetectionRuleResponse
)
async def update_detection_rule(
    rule_id: int,
    rule_update: DetectionRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> DetectionRuleResponse:
    """更新检测规则（需要 ``detection:write`` 权限）。"""
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"规则 ID {rule_id} 不存在",
        )

    update_data = rule_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(rule, field, value)

    await db.flush()
    await db.commit()
    await db.refresh(rule)
    return DetectionRuleResponse.model_validate(rule)


@router.delete(
    "/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_detection_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> None:
    """删除检测规则（需要 ``detection:write`` 权限）。"""
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"规则 ID {rule_id} 不存在",
        )
    await db.delete(rule)
    await db.commit()


@router.post(
    "/rules/{rule_id}/enable", response_model=DetectionRuleResponse
)
async def enable_detection_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> DetectionRuleResponse:
    """启用检测规则（需要 ``detection:write`` 权限）。"""
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"规则 ID {rule_id} 不存在",
        )
    rule.enabled = True
    await db.flush()
    await db.commit()
    await db.refresh(rule)
    return DetectionRuleResponse.model_validate(rule)


@router.post(
    "/rules/{rule_id}/disable", response_model=DetectionRuleResponse
)
async def disable_detection_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> DetectionRuleResponse:
    """禁用检测规则（需要 ``detection:write`` 权限）。"""
    stmt = select(DetectionRule).where(DetectionRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"规则 ID {rule_id} 不存在",
        )
    rule.enabled = False
    await db.flush()
    await db.commit()
    await db.refresh(rule)
    return DetectionRuleResponse.model_validate(rule)


# ──────────────────────────────────────────────
# 手动扫描
# ──────────────────────────────────────────────


@router.post("/scan", response_model=ScanResponse)
async def scan(
    scan_request: ScanRequest,
    db: AsyncSession = Depends(get_db),
    kafka: KafkaService = Depends(get_kafka),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> ScanResponse:
    """手动触发检测扫描（需要 ``detection:write`` 权限）。

    输入前缀或公告，执行检测规则并返回结果。
    """
    if not scan_request.prefix:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="必须提供 prefix 参数",
        )

    # 构造 BGPAnnouncement 对象（不持久化）
    announcement = BGPAnnouncement(
        prefix=scan_request.prefix,
        prefix_family=4 if ":" not in scan_request.prefix else 6,
        prefix_length=int(scan_request.prefix.split("/")[-1])
        if "/" in scan_request.prefix
        else 32,
        origin_as=scan_request.origin_as,
        as_path=scan_request.as_path,
        observation_point_id=scan_request.observation_point_id,
        timestamp=datetime.now(timezone.utc),
        address_family=4 if ":" not in scan_request.prefix else 6,
    )

    # 执行规则引擎评估
    results = await evaluate_announcement(
        db,
        announcement,
        kafka=kafka,
        rule_types=scan_request.rule_types,
    )

    alerts_created = sum(1 for r in results if r.is_detected)

    return ScanResponse(
        total_rules_executed=len(results),
        results=results,
        alerts_created=alerts_created,
    )


# ──────────────────────────────────────────────
# 告警查询与处置
# ──────────────────────────────────────────────


@router.get("/alerts", response_model=list[AlertResponse])
async def list_alerts(
    prefix: str | None = Query(None, description="按前缀过滤"),
    origin_as: int | None = Query(None, description="按起源 AS 过滤"),
    severity: str | None = Query(None, description="按严重等级过滤"),
    status_filter: str | None = Query(
        None, alias="status", description="按处置状态过滤"
    ),
    alert_type: str | None = Query(None, description="按告警类型过滤"),
    incident_id: int | None = Query(None, description="按关联事件过滤"),
    start_time: datetime | None = Query(None, description="起始时间"),
    end_time: datetime | None = Query(None, description="截止时间"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> list[AlertResponse]:
    """查询告警列表（需要 ``detection:read`` 权限）。"""
    query_params = AlertQueryParams(
        prefix=prefix,
        origin_as=origin_as,
        severity=severity,
        status=status_filter,
        alert_type=alert_type,
        incident_id=incident_id,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )
    alerts = await alert_service.get_alerts(db, query_params, skip, limit)
    return [AlertResponse.model_validate(a) for a in alerts]


@router.get(
    "/alerts/{alert_id}", response_model=AlertResponse
)
async def get_alert(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> AlertResponse:
    """获取告警详情（需要 ``detection:read`` 权限）。"""
    alert = await alert_service.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"告警 ID {alert_id} 不存在",
        )
    return AlertResponse.model_validate(alert)


@router.put(
    "/alerts/{alert_id}/status", response_model=AlertResponse
)
async def update_alert_status(
    alert_id: int,
    status_update: AlertStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> AlertResponse:
    """更新告警状态（需要 ``detection:write`` 权限）。"""
    alert = await alert_service.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"告警 ID {alert_id} 不存在",
        )
    alert = await alert_service.update_alert_status(
        db,
        alert,
        status_update.status,
        is_benign_conflict=status_update.is_benign_conflict,
        benign_conflict_type=status_update.benign_conflict_type,
    )
    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.post(
    "/alerts/{alert_id}/assign", response_model=AlertResponse
)
async def assign_alert(
    alert_id: int,
    assign_request: AlertAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> AlertResponse:
    """关联告警到事件（需要 ``detection:write`` 权限）。"""
    alert = await alert_service.assign_alert_to_incident(
        db, alert_id, assign_request.incident_id
    )
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"告警 ID {alert_id} 不存在",
        )
    await db.commit()
    await db.refresh(alert)
    return AlertResponse.model_validate(alert)


@router.get(
    "/alerts/{alert_id}/risk-score", response_model=RiskScoreResponse
)
async def get_alert_risk_score(
    alert_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> RiskScoreResponse:
    """获取告警风险评分（需要 ``detection:read`` 权限）。"""
    # 检查告警存在
    alert = await alert_service.get_alert(db, alert_id)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"告警 ID {alert_id} 不存在",
        )

    # 查询最新风险评分
    stmt = (
        select(RiskScore)
        .where(RiskScore.alert_id == alert_id)
        .order_by(RiskScore.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    risk_score = result.scalar_one_or_none()
    if risk_score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"告警 ID {alert_id} 暂无风险评分",
        )
    return RiskScoreResponse.model_validate(risk_score)


# ──────────────────────────────────────────────
# 事件管理
# ──────────────────────────────────────────────


@router.get(
    "/incidents", response_model=list[IncidentResponse]
)
async def list_incidents(
    status_filter: str | None = Query(
        None, alias="status", description="按状态过滤"
    ),
    severity: str | None = Query(None, description="按严重等级过滤"),
    assigned_to: int | None = Query(None, description="按分派用户过滤"),
    prefix: str | None = Query(None, description="按受影响前缀过滤"),
    asn: int | None = Query(None, description="按受影响 ASN 过滤"),
    start_time: datetime | None = Query(None, description="起始时间"),
    end_time: datetime | None = Query(None, description="截止时间"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=500, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> list[IncidentResponse]:
    """查询事件列表（需要 ``detection:read`` 权限）。"""
    query_params = IncidentQueryParams(
        status=status_filter,
        severity=severity,
        assigned_to=assigned_to,
        prefix=prefix,
        asn=asn,
        start_time=start_time,
        end_time=end_time,
        skip=skip,
        limit=limit,
    )
    incidents = await incident_service.get_incidents(
        db, query_params, skip, limit
    )
    return [IncidentResponse.model_validate(i) for i in incidents]


@router.get(
    "/incidents/{incident_id}", response_model=IncidentResponse
)
async def get_incident(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_READ)),
) -> IncidentResponse:
    """获取事件详情（需要 ``detection:read`` 权限）。"""
    incident = await incident_service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )
    return IncidentResponse.model_validate(incident)


@router.post(
    "/incidents",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_incident(
    incident_create: IncidentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> IncidentResponse:
    """创建事件（需要 ``detection:write`` 权限）。"""
    incident = await incident_service.create_incident(db, incident_create)
    await db.commit()
    await db.refresh(incident)
    return IncidentResponse.model_validate(incident)


@router.put(
    "/incidents/{incident_id}", response_model=IncidentResponse
)
async def update_incident(
    incident_id: int,
    incident_update: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> IncidentResponse:
    """更新事件（需要 ``detection:write`` 权限）。"""
    incident = await incident_service.get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )
    incident = await incident_service.update_incident(
        db, incident, incident_update
    )
    await db.commit()
    await db.refresh(incident)
    return IncidentResponse.model_validate(incident)


@router.post(
    "/incidents/{incident_id}/assign", response_model=IncidentResponse
)
async def assign_incident(
    incident_id: int,
    assign_request: IncidentAssignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> IncidentResponse:
    """分派事件（需要 ``detection:write`` 权限）。"""
    incident = await incident_service.assign_incident(
        db, incident_id, assign_request.user_id
    )
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )
    await db.commit()
    await db.refresh(incident)
    return IncidentResponse.model_validate(incident)


@router.post(
    "/incidents/{incident_id}/close", response_model=IncidentResponse
)
async def close_incident(
    incident_id: int,
    close_request: IncidentCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(DETECTION_WRITE)),
) -> IncidentResponse:
    """关闭事件（需要 ``detection:write`` 权限）。"""
    incident = await incident_service.close_incident(
        db, incident_id, close_request.resolution
    )
    if incident is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"事件 ID {incident_id} 不存在",
        )
    await db.commit()
    await db.refresh(incident)
    return IncidentResponse.model_validate(incident)
