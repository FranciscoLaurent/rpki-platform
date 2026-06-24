"""RPKI 相关 Pydantic 模式（请求与响应）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ──────────────────────────────────────────────
# TAL
# ──────────────────────────────────────────────


class TALCreate(BaseModel):
    """创建 TAL 请求。"""

    name: str = Field(..., description="TAL 名称")
    uri: str = Field(..., description="RRDP URI")
    rsync_uri: str = Field(..., description="rsync URI")
    raw_tal: str = Field(..., description="原始 TAL 文件内容")


class TALResponse(BaseModel):
    """TAL 响应。"""

    id: int
    name: str
    uri: str
    rsync_uri: str
    raw_tal: str
    status: str
    last_synced_at: datetime | None
    sync_status: str
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# RPKI Repository
# ──────────────────────────────────────────────


class RPKIRepositoryResponse(BaseModel):
    """RPKI 仓库响应。"""

    id: int
    tal_id: int
    uri: str
    protocol: str
    status: str
    last_synced_at: datetime | None
    sync_status: str
    last_error: str | None
    object_count: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# ROA
# ──────────────────────────────────────────────


class ROAResponse(BaseModel):
    """ROA 响应。"""

    id: int
    object_id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    origin_as: int
    max_length: int | None
    tal_id: int | None
    status: str
    not_before: datetime | None
    not_after: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# VRP
# ──────────────────────────────────────────────


class VRPResponse(BaseModel):
    """VRP 响应。"""

    id: int
    prefix: str
    prefix_family: int
    prefix_length: int
    origin_as: int
    max_length: int | None
    tal_id: int | None
    roa_id: int | None
    trust_anchor: str | None
    validation_status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class VRPQueryParams(BaseModel):
    """VRP 查询参数。"""

    prefix: str | None = Field(None, description="网络前缀过滤")
    origin_as: int | None = Field(None, description="起源 AS 号过滤")
    max_length: int | None = Field(None, description="最大前缀长度过滤")
    tal_id: int | None = Field(None, description="TAL ID 过滤")
    time_point: datetime | None = Field(
        None, description="时间点过滤（仅返回该时间点之前创建的 VRP）"
    )


# ──────────────────────────────────────────────
# BGP 公告验证
# ──────────────────────────────────────────────


class ValidationResult(BaseModel):
    """BGP 公告验证结果。"""

    validation_status: str = Field(..., description="验证状态：valid/invalid/not_found")
    invalid_reason: str | None = Field(
        None,
        description=(
            "无效原因：origin_as_mismatch/length_exceeded/"
            "roa_revoked/resource_chain_error/data_source_error"
        ),
    )
    matched_vrps: list[VRPResponse] = Field(default_factory=list, description="匹配到的 VRP 列表")


class BGPAnnouncementValidation(BaseModel):
    """单个 BGP 公告的验证请求与结果。"""

    prefix: str = Field(..., description="BGP 公告前缀")
    origin_as: int = Field(..., description="BGP 公告起源 AS 号")
    validation_result: ValidationResult | None = Field(None, description="验证结果（响应时填充）")


class BGPAnnouncementValidationRequest(BaseModel):
    """BGP 公告验证请求。"""

    prefix: str = Field(..., description="BGP 公告前缀")
    origin_as: int = Field(..., description="BGP 公告起源 AS 号")


class BatchValidationRequest(BaseModel):
    """批量 BGP 公告验证请求。"""

    announcements: list[BGPAnnouncementValidationRequest] = Field(
        ..., description="待验证的 BGP 公告列表"
    )


class BatchValidationResponse(BaseModel):
    """批量 BGP 公告验证响应。"""

    results: list[BGPAnnouncementValidation] = Field(
        default_factory=list, description="验证结果列表"
    )
    total: int = Field(0, description="总验证数量")
    valid_count: int = Field(0, description="验证通过数量")
    invalid_count: int = Field(0, description="验证失败数量")
    not_found_count: int = Field(0, description="未匹配 VRP 数量")


# ──────────────────────────────────────────────
# 同步状态
# ──────────────────────────────────────────────


class SyncStatusResponse(BaseModel):
    """同步状态响应。"""

    tal_id: int | None = Field(None, description="TAL ID")
    status: str = Field(..., description="同步状态：success/failed/running/pending")
    progress: float = Field(0.0, description="同步进度（0-100）")
    last_synced_at: datetime | None = Field(None, description="最后同步时间")
    error: str | None = Field(None, description="错误信息")


# ──────────────────────────────────────────────
# 快照
# ──────────────────────────────────────────────


class SnapshotResponse(BaseModel):
    """RPKI 快照响应。

    注意：``metadata`` 是 SQLAlchemy 保留字，ORM 属性名为 ``metadata_``，
    此处通过 ``validation_alias`` 从 ORM 读取，通过 ``serialization_alias``
    输出为 ``metadata`` 字段。
    """

    id: int
    snapshot_time: datetime
    vrp_count: int
    roa_count: int
    object_count: int
    metadata: dict[str, Any] | None = Field(
        None,
        validation_alias="metadata_",
        serialization_alias="metadata",
        description="快照元数据",
    )
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SnapshotDiff(BaseModel):
    """快照差异。"""

    added_vrps: list[VRPResponse] = Field(default_factory=list, description="新增的 VRP 列表")
    removed_vrps: list[VRPResponse] = Field(default_factory=list, description="移除的 VRP 列表")
    modified_vrps: list[VRPResponse] = Field(default_factory=list, description="修改的 VRP 列表")


class SnapshotDiffResponse(BaseModel):
    """快照差异响应。"""

    snapshot_id_1: int
    snapshot_id_2: int
    diff: SnapshotDiff
    added_count: int = Field(0, description="新增数量")
    removed_count: int = Field(0, description="移除数量")
    modified_count: int = Field(0, description="修改数量")


class SnapshotRollbackResponse(BaseModel):
    """快照回滚响应。"""

    snapshot_id: int
    rolled_back: bool = Field(..., description="是否回滚成功")
    message: str = Field(..., description="回滚结果消息")


# ──────────────────────────────────────────────
# 健康状态
# ──────────────────────────────────────────────


class RepositoryHealthResponse(BaseModel):
    """仓库健康状态响应。"""

    repository_id: int
    status: str
    sync_status: str
    last_synced_at: datetime | None
    object_count: int
    last_error: str | None
    is_healthy: bool = Field(..., description="是否健康")


class RPKIHealthResponse(BaseModel):
    """RPKI 整体健康状态响应。"""

    overall_healthy: bool = Field(..., description="整体是否健康")
    total_repositories: int = Field(0, description="仓库总数")
    healthy_repositories: int = Field(0, description="健康仓库数")
    failed_repositories: int = Field(0, description="失败仓库数")
    repositories: list[RepositoryHealthResponse] = Field(default_factory=list)
    cache_status: dict[str, Any] | None = Field(None, description="缓存状态")


# ──────────────────────────────────────────────
# 通用列表响应
# ──────────────────────────────────────────────


class PaginatedResponse(BaseModel):
    """通用分页响应基类。"""

    total: int = Field(0, description="总记录数")
    skip: int = Field(0, description="跳过记录数")
    limit: int = Field(50, description="返回记录数上限")


class TALListResponse(PaginatedResponse):
    """TAL 列表响应。"""

    items: list[TALResponse] = Field(default_factory=list)


class RPKIRepositoryListResponse(PaginatedResponse):
    """RPKI 仓库列表响应。"""

    items: list[RPKIRepositoryResponse] = Field(default_factory=list)


class ROAListResponse(PaginatedResponse):
    """ROA 列表响应。"""

    items: list[ROAResponse] = Field(default_factory=list)


class VRPListResponse(PaginatedResponse):
    """VRP 列表响应。"""

    items: list[VRPResponse] = Field(default_factory=list)


class SnapshotListResponse(PaginatedResponse):
    """快照列表响应。"""

    items: list[SnapshotResponse] = Field(default_factory=list)


# ──────────────────────────────────────────────
# 同步触发响应
# ──────────────────────────────────────────────


class SyncTriggerResponse(BaseModel):
    """同步触发响应。"""

    message: str = Field(..., description="操作结果消息")
    tal_id: int | None = Field(None, description="关联 TAL ID")
    status: str = Field(..., description="触发后的同步状态")
