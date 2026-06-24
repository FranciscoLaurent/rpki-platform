"""资产管理端点：业务服务、客户、路由器 CRUD，以及一致性检查与关系视图。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.schemas.asset import (
    BusinessServiceCreate,
    BusinessServiceListResponse,
    BusinessServiceResponse,
    BusinessServiceUpdate,
    ConsistencyCheckResult,
    CustomerCreate,
    CustomerListResponse,
    CustomerResponse,
    CustomerUpdate,
    RelationshipView,
    RouterCreate,
    RouterListResponse,
    RouterResponse,
    RouterUpdate,
)
from app.services import asset_service, prefix_service

router = APIRouter()


# ──────────────────────────────────────────────
# 业务服务
# ──────────────────────────────────────────────


@router.post(
    "/business-services",
    response_model=BusinessServiceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_business_service(
    payload: BusinessServiceCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> BusinessServiceResponse:
    """创建业务服务（需要 ``asset:write`` 权限）。"""
    service = await asset_service.create_business_service(db, payload)
    return BusinessServiceResponse.model_validate(service)


@router.get("/business-services", response_model=BusinessServiceListResponse)
async def list_business_services(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    name: str | None = Query(None, description="按名称模糊过滤"),
    importance: str | None = Query(None, description="按重要度过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> BusinessServiceListResponse:
    """获取业务服务列表（需要 ``asset:read`` 权限）。"""
    filters: dict[str, object] = {}
    if name is not None:
        filters["name"] = name
    if importance is not None:
        filters["importance"] = importance

    items = await asset_service.get_business_services(
        db, filters=filters, skip=skip, limit=limit
    )
    total = await asset_service.count_business_services(db, filters=filters)
    return BusinessServiceListResponse(
        items=[BusinessServiceResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get(
    "/business-services/{service_id}",
    response_model=BusinessServiceResponse,
)
async def get_business_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> BusinessServiceResponse:
    """获取业务服务详情（需要 ``asset:read`` 权限）。"""
    service = await asset_service.get_business_service(db, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"业务服务 ID {service_id} 不存在",
        )
    return BusinessServiceResponse.model_validate(service)


@router.put(
    "/business-services/{service_id}",
    response_model=BusinessServiceResponse,
)
async def update_business_service(
    service_id: int,
    payload: BusinessServiceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> BusinessServiceResponse:
    """更新业务服务（需要 ``asset:write`` 权限）。"""
    service = await asset_service.get_business_service(db, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"业务服务 ID {service_id} 不存在",
        )
    updated = await asset_service.update_business_service(db, service, payload)
    return BusinessServiceResponse.model_validate(updated)


@router.delete(
    "/business-services/{service_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_business_service(
    service_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> None:
    """删除业务服务（需要 ``asset:write`` 权限）。"""
    service = await asset_service.get_business_service(db, service_id)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"业务服务 ID {service_id} 不存在",
        )
    await asset_service.delete_business_service(db, service)


# ──────────────────────────────────────────────
# 客户
# ──────────────────────────────────────────────


@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer(
    payload: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> CustomerResponse:
    """创建客户（需要 ``asset:write`` 权限）。"""
    customer = await asset_service.create_customer(db, payload)
    return CustomerResponse.model_validate(customer)


@router.get("/customers", response_model=CustomerListResponse)
async def list_customers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    name: str | None = Query(None, description="按名称模糊过滤"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    service_level: str | None = Query(None, description="按服务等级过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> CustomerListResponse:
    """获取客户列表（需要 ``asset:read`` 权限）。"""
    filters: dict[str, object] = {}
    if name is not None:
        filters["name"] = name
    if status_filter is not None:
        filters["status"] = status_filter
    if service_level is not None:
        filters["service_level"] = service_level

    items = await asset_service.get_customers(
        db, filters=filters, skip=skip, limit=limit
    )
    total = await asset_service.count_customers(db, filters=filters)
    return CustomerListResponse(
        items=[CustomerResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> CustomerResponse:
    """获取客户详情（需要 ``asset:read`` 权限）。"""
    customer = await asset_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"客户 ID {customer_id} 不存在",
        )
    return CustomerResponse.model_validate(customer)


@router.put("/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    payload: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> CustomerResponse:
    """更新客户（需要 ``asset:write`` 权限）。"""
    customer = await asset_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"客户 ID {customer_id} 不存在",
        )
    updated = await asset_service.update_customer(db, customer, payload)
    return CustomerResponse.model_validate(updated)


@router.delete(
    "/customers/{customer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> None:
    """删除客户（需要 ``asset:write`` 权限）。"""
    customer = await asset_service.get_customer(db, customer_id)
    if customer is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"客户 ID {customer_id} 不存在",
        )
    await asset_service.delete_customer(db, customer)


# ──────────────────────────────────────────────
# 路由器
# ──────────────────────────────────────────────


@router.post(
    "/routers",
    response_model=RouterResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_router(
    payload: RouterCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> RouterResponse:
    """创建路由器（需要 ``asset:write`` 权限）。"""
    router = await asset_service.create_router(db, payload)
    return RouterResponse.model_validate(router)


@router.get("/routers", response_model=RouterListResponse)
async def list_routers(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(50, ge=1, le=200, description="返回记录数上限"),
    hostname: str | None = Query(None, description="按主机名模糊过滤"),
    status_filter: str | None = Query(None, alias="status", description="按状态过滤"),
    vendor: str | None = Query(None, description="按厂商过滤"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> RouterListResponse:
    """获取路由器列表（需要 ``asset:read`` 权限）。"""
    filters: dict[str, object] = {}
    if hostname is not None:
        filters["hostname"] = hostname
    if status_filter is not None:
        filters["status"] = status_filter
    if vendor is not None:
        filters["vendor"] = vendor

    items = await asset_service.get_routers(
        db, filters=filters, skip=skip, limit=limit
    )
    total = await asset_service.count_routers(db, filters=filters)
    return RouterListResponse(
        items=[RouterResponse.model_validate(i) for i in items],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/routers/{router_id}", response_model=RouterResponse)
async def get_router(
    router_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> RouterResponse:
    """获取路由器详情（需要 ``asset:read`` 权限）。"""
    router = await asset_service.get_router(db, router_id)
    if router is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"路由器 ID {router_id} 不存在",
        )
    return RouterResponse.model_validate(router)


@router.put("/routers/{router_id}", response_model=RouterResponse)
async def update_router(
    router_id: int,
    payload: RouterUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> RouterResponse:
    """更新路由器（需要 ``asset:write`` 权限）。"""
    router = await asset_service.get_router(db, router_id)
    if router is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"路由器 ID {router_id} 不存在",
        )
    updated = await asset_service.update_router(db, router, payload)
    return RouterResponse.model_validate(updated)


@router.delete(
    "/routers/{router_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_router(
    router_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:write")),
) -> None:
    """删除路由器（需要 ``asset:write`` 权限）。"""
    router = await asset_service.get_router(db, router_id)
    if router is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"路由器 ID {router_id} 不存在",
        )
    await asset_service.delete_router(db, router)


# ──────────────────────────────────────────────
# 一致性检查与关系视图
# ──────────────────────────────────────────────


@router.get("/consistency-check", response_model=ConsistencyCheckResult)
async def consistency_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> ConsistencyCheckResult:
    """执行资产一致性检查（需要 ``asset:read`` 权限）。

    对比 IPAM/CMDB 与 BGP/ROA/IRR 资产，检查未登记前缀、过期信息、状态不一致。
    """
    return await asset_service.check_consistency(db)


@router.get("/relationships/{prefix_id}", response_model=RelationshipView)
async def get_relationships(
    prefix_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions("asset:read")),
) -> RelationshipView:
    """获取前缀的关系视图（需要 ``asset:read`` 权限）。

    返回前缀—ASN—ROA—BGP—业务—事件关联信息。
    """
    prefix = await prefix_service.get_prefix(db, prefix_id)
    if prefix is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    view = await asset_service.get_relationship_view(db, prefix_id)
    if view is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"前缀 ID {prefix_id} 不存在",
        )
    return view
