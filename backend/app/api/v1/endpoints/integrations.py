"""事件推送与外部集成 API 端点。

提供集成配置 CRUD、连通性测试、事件推送、外部信息丰富、
指标导出与 Grafana Dashboard 生成等接口。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.integration import (
    ChannelTestRequest,
    ChannelTestResult,
    EnrichASNRequest,
    EnrichPrefixRequest,
    EnrichResult,
    EventPublishRequest,
    EventPublishResult,
    ExternalInfoQuery,
    ExternalInfoResult,
    GrafanaDashboard,
    GrafanaDashboardRequest,
    IntegrationConfigCreate,
    IntegrationConfigListResponse,
    IntegrationConfigResponse,
    IntegrationConfigUpdate,
    IntegrationTestResult,
    MetricExport,
    MetricExportResponse,
    PushChannelInfo,
    PushChannelListResponse,
)
from app.services import integration_config_service
from app.services.event_publisher import (
    list_push_channels,
    publish_event,
    test_channel,
)
from app.services.integrations.external_info import (
    enrich_asn,
    enrich_prefix,
    query_irr,
    query_peeringdb,
    query_rir,
)
from app.services.integrations.nms_adapter import (
    export_metrics,
    generate_grafana_dashboard,
)

router = APIRouter()

# 集成权限码（使用字符串字面量避免修改共享的 rbac.py）
INTEGRATION_READ = "integration:read"
INTEGRATION_WRITE = "integration:write"


# ──────────────────────────────────────────────
# 集成配置 CRUD
# ──────────────────────────────────────────────


@router.post(
    "",
    response_model=IntegrationConfigResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_integration(
    integration_create: IntegrationConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_WRITE)),
) -> IntegrationConfigResponse:
    """创建集成配置（需要 ``integration:write`` 权限）。"""
    try:
        result = await integration_config_service.create_integration(
            db, integration_create.model_dump()
        )
        return IntegrationConfigResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )


@router.get("", response_model=IntegrationConfigListResponse)
async def list_integrations(
    integration_type: str | None = Query(
        None, description="按集成类型过滤"
    ),
    enabled: bool | None = Query(None, description="按启用状态过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> IntegrationConfigListResponse:
    """列出所有集成配置（需要 ``integration:read`` 权限）。"""
    items = await integration_config_service.list_integrations(db)
    # 应用过滤
    if integration_type:
        items = [
            i for i in items if i["integration_type"] == integration_type
        ]
    if enabled is not None:
        items = [i for i in items if i["enabled"] == enabled]
    return IntegrationConfigListResponse(
        items=[IntegrationConfigResponse(**i) for i in items],
        total=len(items),
    )


@router.get("/{integration_id}", response_model=IntegrationConfigResponse)
async def get_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> IntegrationConfigResponse:
    """获取集成配置详情（需要 ``integration:read`` 权限）。"""
    result = await integration_config_service.get_integration(db, integration_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"集成配置 {integration_id} 不存在",
        )
    return IntegrationConfigResponse(**result)


@router.put("/{integration_id}", response_model=IntegrationConfigResponse)
async def update_integration(
    integration_id: int,
    integration_update: IntegrationConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_WRITE)),
) -> IntegrationConfigResponse:
    """更新集成配置（需要 ``integration:write`` 权限）。"""
    # 仅传入已设置的字段
    update_data = integration_update.model_dump(exclude_unset=True)
    result = await integration_config_service.update_integration(
        db, integration_id, update_data
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"集成配置 {integration_id} 不存在",
        )
    return IntegrationConfigResponse(**result)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_WRITE)),
) -> None:
    """删除集成配置（需要 ``integration:write`` 权限）。"""
    deleted = await integration_config_service.delete_integration(
        db, integration_id
    )
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"集成配置 {integration_id} 不存在",
        )


@router.post(
    "/{integration_id}/test",
    response_model=IntegrationTestResult,
)
async def test_integration(
    integration_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_WRITE)),
) -> IntegrationTestResult:
    """测试集成连通性（需要 ``integration:write`` 权限）。"""
    result = await integration_config_service.test_integration(
        db, integration_id
    )
    return IntegrationTestResult(
        success=result["success"],
        message=result["message"],
        latency_ms=result.get("latency_ms"),
    )


# ──────────────────────────────────────────────
# 事件推送
# ──────────────────────────────────────────────


@router.post(
    "/event-publisher/publish",
    response_model=EventPublishResult,
)
async def publish_event_endpoint(
    request: EventPublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_WRITE)),
) -> EventPublishResult:
    """发布事件到指定通道（需要 ``integration:write`` 权限）。"""
    result = await publish_event(
        db=db,
        event_type=request.event_type,
        event_data=request.event_data,
        channels=request.channels,
    )
    return EventPublishResult(**result)


@router.get(
    "/event-publisher/channels",
    response_model=PushChannelListResponse,
)
async def list_push_channels_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> PushChannelListResponse:
    """列出已配置的推送通道（需要 ``integration:read`` 权限）。"""
    channels = await list_push_channels(db)
    return PushChannelListResponse(
        items=[PushChannelInfo(**c) for c in channels],
        total=len(channels),
    )


@router.post(
    "/event-publisher/test-channel",
    response_model=ChannelTestResult,
)
async def test_channel_endpoint(
    request: ChannelTestRequest,
    current_user: User = Depends(require_permissions(INTEGRATION_WRITE)),
) -> ChannelTestResult:
    """测试通道连通性（需要 ``integration:write`` 权限）。"""
    result = await test_channel(request.channel_type, request.config)
    return ChannelTestResult(**result)


# ──────────────────────────────────────────────
# 外部信息查询与丰富
# ──────────────────────────────────────────────


@router.post("/external-info/query", response_model=ExternalInfoResult)
async def query_external_info(
    query: ExternalInfoQuery,
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> ExternalInfoResult:
    """查询外部信息（需要 ``integration:read`` 权限）。

    支持 RIR、IRR、PeeringDB 三种数据源。
    """
    source = query.source.lower()
    config = query.config or {}
    result: dict[str, Any]

    if source == "rir":
        result = await query_rir(config, query.query)
    elif source == "irr":
        result = await query_irr(config, query.query)
    elif source == "peeringdb":
        # PeeringDB 查询参数为 ASN（整数）
        try:
            asn = int(query.query)
        except ValueError:
            return ExternalInfoResult(
                source=source,
                query=query.query,
                success=False,
                message="PeeringDB 查询需要提供有效的 ASN",
            )
        result = await query_peeringdb(asn)
    else:
        return ExternalInfoResult(
            source=source,
            query=query.query,
            success=False,
            message=f"不支持的数据源: {source}",
        )

    return ExternalInfoResult(
        source=source,
        query=query.query,
        success=result.get("success", False),
        data=result,
        cached=result.get("cached", False),
        message=result.get("message"),
    )


@router.post("/external-info/enrich-prefix", response_model=EnrichResult)
async def enrich_prefix_endpoint(
    request: EnrichPrefixRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> EnrichResult:
    """用外部信息丰富前缀数据（需要 ``integration:read`` 权限）。"""
    result = await enrich_prefix(db, request.prefix)
    return EnrichResult(success=True, data=result)


@router.post("/external-info/enrich-asn", response_model=EnrichResult)
async def enrich_asn_endpoint(
    request: EnrichASNRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> EnrichResult:
    """用外部信息丰富 ASN 数据（需要 ``integration:read`` 权限）。"""
    result = await enrich_asn(db, request.asn)
    return EnrichResult(success=True, data=result)


# ──────────────────────────────────────────────
# NMS 指标导出与 Grafana
# ──────────────────────────────────────────────


@router.get("/nms/export-metrics", response_model=MetricExportResponse)
async def export_metrics_endpoint(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> MetricExportResponse:
    """导出平台核心指标（需要 ``integration:read`` 权限）。

    返回前缀数、ROA 覆盖率、Invalid 数、告警数、事件数等核心指标。
    """
    metrics = await export_metrics(db)
    return MetricExportResponse(
        metrics=[MetricExport(**m) for m in metrics],
        total=len(metrics),
        exported_at=datetime.now(timezone.utc),
    )


@router.get("/nms/grafana-dashboard", response_model=GrafanaDashboard)
async def generate_grafana_dashboard_endpoint(
    title: str | None = Query(None, description="仪表盘标题"),
    uid: str | None = Query(None, description="仪表盘 UID"),
    datasource: str | None = Query(None, description="数据源"),
    current_user: User = Depends(require_permissions(INTEGRATION_READ)),
) -> GrafanaDashboard:
    """生成 Grafana Dashboard JSON（需要 ``integration:read`` 权限）。"""
    config: dict[str, Any] = {}
    if title:
        config["title"] = title
    if uid:
        config["uid"] = uid
    if datasource:
        config["datasource"] = datasource
    result = await generate_grafana_dashboard(config)
    return GrafanaDashboard(**result)


__all__ = ["router"]
