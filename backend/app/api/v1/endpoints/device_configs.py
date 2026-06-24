"""设备配置模板管理与生成 API 端点。

提供设备配置模板的 CRUD、配置生成、厂商列表与默认模板查询等接口。
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.core.device_templates import VENDOR_NAMES
from app.models.user import User
from app.schemas.rtr import (
    DefaultTemplateResponse,
    DeviceConfigRequest,
    DeviceConfigResult,
    DeviceConfigTemplateCreate,
    DeviceConfigTemplateListResponse,
    DeviceConfigTemplateResponse,
    DeviceConfigTemplateUpdate,
    VendorListResponse,
)
from app.services import device_config_service

router = APIRouter()

# 设备配置权限码（与 RTR 共用，使用字符串字面量避免修改共享的 rbac.py）
RTR_READ = "rtr:read"
RTR_WRITE = "rtr:write"


# ──────────────────────────────────────────────
# 模板 CRUD
# ──────────────────────────────────────────────


@router.post(
    "/templates",
    response_model=DeviceConfigTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_template(
    payload: DeviceConfigTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> DeviceConfigTemplateResponse:
    """创建设备配置模板（需要 ``rtr:write`` 权限）。"""
    try:
        template = await device_config_service.create_template(db, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return DeviceConfigTemplateResponse.model_validate(template)


@router.get("/templates", response_model=DeviceConfigTemplateListResponse)
async def list_templates(
    vendor: str | None = Query(None, description="按厂商过滤"),
    template_type: str | None = Query(None, description="按模板类型过滤"),
    enabled: bool | None = Query(None, description="按启用状态过滤"),
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> DeviceConfigTemplateListResponse:
    """获取设备配置模板列表（需要 ``rtr:read`` 权限）。"""
    templates = await device_config_service.get_templates(
        db,
        vendor=vendor,
        template_type=template_type,
        enabled=enabled,
        skip=skip,
        limit=limit,
    )
    total = await device_config_service.count_templates(
        db,
        vendor=vendor,
        template_type=template_type,
        enabled=enabled,
    )
    return DeviceConfigTemplateListResponse(
        items=[DeviceConfigTemplateResponse.model_validate(t) for t in templates],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/templates/{template_id}",
    response_model=DeviceConfigTemplateResponse,
)
async def get_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> DeviceConfigTemplateResponse:
    """获取设备配置模板详情（需要 ``rtr:read`` 权限）。"""
    template = await device_config_service.get_template(db, template_id)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {template_id} 不存在",
        )
    return DeviceConfigTemplateResponse.model_validate(template)


@router.put(
    "/templates/{template_id}",
    response_model=DeviceConfigTemplateResponse,
)
async def update_template(
    template_id: int,
    payload: DeviceConfigTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> DeviceConfigTemplateResponse:
    """更新设备配置模板（需要 ``rtr:write`` 权限）。"""
    template = await device_config_service.update_template(db, template_id, payload)
    if template is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {template_id} 不存在",
        )
    return DeviceConfigTemplateResponse.model_validate(template)


@router.delete(
    "/templates/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_template(
    template_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_WRITE)),
) -> None:
    """删除设备配置模板（需要 ``rtr:write`` 权限）。"""
    deleted = await device_config_service.delete_template(db, template_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"模板 ID {template_id} 不存在",
        )


# ──────────────────────────────────────────────
# 配置生成
# ──────────────────────────────────────────────


@router.post("/generate", response_model=DeviceConfigResult)
async def generate_config(
    request: DeviceConfigRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> DeviceConfigResult:
    """生成设备配置（需要 ``rtr:read`` 权限）。

    根据厂商与模板类型选择模板，填充变量后返回生成的配置文本。
    """
    try:
        return await device_config_service.generate_config_from_request(db, request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        ) from e


# ──────────────────────────────────────────────
# 厂商与默认模板查询
# ──────────────────────────────────────────────


@router.get("/vendors", response_model=VendorListResponse)
async def list_vendors(
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> VendorListResponse:
    """获取支持的厂商列表（需要 ``rtr:read`` 权限）。"""
    return VendorListResponse(vendors=device_config_service.get_vendors())


@router.get(
    "/default-templates/{vendor}",
    response_model=DefaultTemplateResponse,
)
async def get_default_templates(
    vendor: str,
    current_user: User = Depends(require_permissions(RTR_READ)),
) -> DefaultTemplateResponse:
    """获取指定厂商的默认模板列表（需要 ``rtr:read`` 权限）。"""
    if vendor not in VENDOR_NAMES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"不支持的厂商: {vendor}",
        )

    templates_data = device_config_service.get_default_templates_for_vendor(vendor)

    # 将字典列表转换为响应模型
    now = datetime.now(UTC)
    items: list[DeviceConfigTemplateResponse] = []
    for item in templates_data:
        items.append(
            DeviceConfigTemplateResponse(
                id=0,  # 默认模板无 ID
                name=item["name"],
                vendor=item["vendor"],
                template_type=item["template_type"],
                content=item["content"],
                variables=item["variables"],
                description=item["description"],
                enabled=item["enabled"],
                tenant_id=None,
                created_at=now,
                updated_at=now,
            )
        )

    return DefaultTemplateResponse(vendor=vendor, templates=items)


__all__ = ["router"]
