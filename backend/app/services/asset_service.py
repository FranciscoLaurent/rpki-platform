"""资产服务：业务服务/客户/路由器 CRUD、一致性检查与关系视图。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bgp_peer import BGPPeer
from app.models.business import BusinessService, Customer, Router
from app.models.prefix import Prefix
from app.schemas.asset import (
    BusinessServiceCreate,
    BusinessServiceUpdate,
    ConsistencyCheckItem,
    ConsistencyCheckResult,
    CustomerCreate,
    CustomerUpdate,
    RelationshipView,
    RouterCreate,
    RouterUpdate,
)


# ──────────────────────────────────────────────
# 业务服务 CRUD
# ──────────────────────────────────────────────


async def create_business_service(
    db: AsyncSession, data: BusinessServiceCreate
) -> BusinessService:
    """创建业务服务。"""
    service = BusinessService(
        name=data.name,
        description=data.description,
        importance=data.importance,
        owner_contact=data.owner_contact,
    )
    db.add(service)
    await db.flush()
    await db.commit()
    await db.refresh(service)
    return service


async def get_business_service(
    db: AsyncSession, service_id: int
) -> BusinessService | None:
    """根据 ID 获取业务服务。"""
    stmt = select(BusinessService).where(BusinessService.id == service_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_business_services(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[BusinessService]:
    """分页查询业务服务。"""
    stmt = select(BusinessService)
    if filters:
        if filters.get("name"):
            stmt = stmt.where(BusinessService.name.ilike(f"%{filters['name']}%"))
        if filters.get("importance"):
            stmt = stmt.where(BusinessService.importance == filters["importance"])

    stmt = stmt.order_by(BusinessService.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_business_services(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计业务服务数量。"""
    stmt = select(func.count(BusinessService.id))
    if filters:
        if filters.get("name"):
            stmt = stmt.where(BusinessService.name.ilike(f"%{filters['name']}%"))
        if filters.get("importance"):
            stmt = stmt.where(BusinessService.importance == filters["importance"])

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_business_service(
    db: AsyncSession,
    service: BusinessService,
    data: BusinessServiceUpdate,
) -> BusinessService:
    """更新业务服务。"""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(service, field, value)
    await db.flush()
    await db.commit()
    await db.refresh(service)
    return service


async def delete_business_service(
    db: AsyncSession, service: BusinessService
) -> None:
    """删除业务服务。"""
    await db.delete(service)
    await db.commit()


# ──────────────────────────────────────────────
# 客户 CRUD
# ──────────────────────────────────────────────


async def create_customer(
    db: AsyncSession, data: CustomerCreate
) -> Customer:
    """创建客户。"""
    customer = Customer(
        name=data.name,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        contract_id=data.contract_id,
        service_level=data.service_level,
        status=data.status,
    )
    db.add(customer)
    await db.flush()
    await db.commit()
    await db.refresh(customer)
    return customer


async def get_customer(db: AsyncSession, customer_id: int) -> Customer | None:
    """根据 ID 获取客户。"""
    stmt = select(Customer).where(Customer.id == customer_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_customers(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Customer]:
    """分页查询客户。"""
    stmt = select(Customer)
    if filters:
        if filters.get("name"):
            stmt = stmt.where(Customer.name.ilike(f"%{filters['name']}%"))
        if filters.get("status"):
            stmt = stmt.where(Customer.status == filters["status"])
        if filters.get("service_level"):
            stmt = stmt.where(Customer.service_level == filters["service_level"])

    stmt = stmt.order_by(Customer.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_customers(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计客户数量。"""
    stmt = select(func.count(Customer.id))
    if filters:
        if filters.get("name"):
            stmt = stmt.where(Customer.name.ilike(f"%{filters['name']}%"))
        if filters.get("status"):
            stmt = stmt.where(Customer.status == filters["status"])
        if filters.get("service_level"):
            stmt = stmt.where(Customer.service_level == filters["service_level"])

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_customer(
    db: AsyncSession, customer: Customer, data: CustomerUpdate
) -> Customer:
    """更新客户。"""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(customer, field, value)
    await db.flush()
    await db.commit()
    await db.refresh(customer)
    return customer


async def delete_customer(db: AsyncSession, customer: Customer) -> None:
    """删除客户。"""
    await db.delete(customer)
    await db.commit()


# ──────────────────────────────────────────────
# 路由器 CRUD
# ──────────────────────────────────────────────


async def create_router(db: AsyncSession, data: RouterCreate) -> Router:
    """创建路由器。"""
    router = Router(
        hostname=data.hostname,
        vendor=data.vendor,
        model=data.model,
        management_ip=data.management_ip,
        location=data.location,
        snmp_community=data.snmp_community,
        status=data.status,
    )
    db.add(router)
    await db.flush()
    await db.commit()
    await db.refresh(router)
    return router


async def get_router(db: AsyncSession, router_id: int) -> Router | None:
    """根据 ID 获取路由器。"""
    stmt = select(Router).where(Router.id == router_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_routers(
    db: AsyncSession,
    filters: dict[str, Any] | None = None,
    skip: int = 0,
    limit: int = 50,
) -> list[Router]:
    """分页查询路由器。"""
    stmt = select(Router)
    if filters:
        if filters.get("hostname"):
            stmt = stmt.where(Router.hostname.ilike(f"%{filters['hostname']}%"))
        if filters.get("status"):
            stmt = stmt.where(Router.status == filters["status"])
        if filters.get("vendor"):
            stmt = stmt.where(Router.vendor == filters["vendor"])

    stmt = stmt.order_by(Router.id).offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def count_routers(
    db: AsyncSession, filters: dict[str, Any] | None = None
) -> int:
    """统计路由器数量。"""
    stmt = select(func.count(Router.id))
    if filters:
        if filters.get("hostname"):
            stmt = stmt.where(Router.hostname.ilike(f"%{filters['hostname']}%"))
        if filters.get("status"):
            stmt = stmt.where(Router.status == filters["status"])
        if filters.get("vendor"):
            stmt = stmt.where(Router.vendor == filters["vendor"])

    result = await db.execute(stmt)
    return result.scalar_one()


async def update_router(
    db: AsyncSession, router: Router, data: RouterUpdate
) -> Router:
    """更新路由器。"""
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(router, field, value)
    await db.flush()
    await db.commit()
    await db.refresh(router)
    return router


async def delete_router(db: AsyncSession, router: Router) -> None:
    """删除路由器。"""
    await db.delete(router)
    await db.commit()


# ──────────────────────────────────────────────
# 资产一致性检查
# ──────────────────────────────────────────────


async def check_consistency(db: AsyncSession) -> ConsistencyCheckResult:
    """资产一致性检查（基础版）。

    检查项：
    1. 未登记前缀：状态为 active 但缺少业务归属或地域信息
    2. 过期信息：前缀 expired_at 早于当前时间但状态仍为 active
    3. 状态不一致：前缀关联的客户状态为 inactive 但前缀状态为 active

    Args:
        db: 异步数据库会话

    Returns:
        一致性检查结果
    """
    items: list[ConsistencyCheckItem] = []
    now = datetime.now(timezone.utc)

    # 加载所有前缀（含关联客户）
    stmt = select(Prefix)
    result = await db.execute(stmt)
    prefixes = list(result.scalars().all())

    # 加载所有客户用于状态对比
    cust_stmt = select(Customer)
    cust_result = await db.execute(cust_stmt)
    customers_map: dict[int, Customer] = {
        c.id: c for c in cust_result.scalars().all()
    }

    for p in prefixes:
        # 1. 未登记前缀：active 但缺少业务归属与地域
        if p.status == "active" and not p.business_service and not p.region:
            items.append(
                ConsistencyCheckItem(
                    type="unregistered_prefix",
                    prefix=p.prefix,
                    description=(
                        f"前缀 {p.prefix} 处于 active 状态但缺少业务归属与地域信息"
                    ),
                    severity="warning",
                )
            )

        # 2. 过期信息：expired_at 早于当前时间但状态仍为 active
        if (
            p.expired_at is not None
            and p.expired_at < now
            and p.status == "active"
        ):
            items.append(
                ConsistencyCheckItem(
                    type="expired",
                    prefix=p.prefix,
                    description=(
                        f"前缀 {p.prefix} 已过期（{p.expired_at.isoformat()}）"
                        "但状态仍为 active"
                    ),
                    severity="critical",
                )
            )

        # 3. 状态不一致：关联客户 inactive 但前缀 active
        if p.customer_id is not None and p.status == "active":
            cust = customers_map.get(p.customer_id)
            if cust is not None and cust.status == "inactive":
                items.append(
                    ConsistencyCheckItem(
                        type="status_mismatch",
                        prefix=p.prefix,
                        description=(
                            f"前缀 {p.prefix} 状态为 active，"
                            f"但关联客户 {cust.name} 状态为 inactive"
                        ),
                        severity="warning",
                    )
                )

    critical_count = sum(1 for i in items if i.severity == "critical")
    warning_count = sum(1 for i in items if i.severity == "warning")
    info_count = sum(1 for i in items if i.severity == "info")

    return ConsistencyCheckResult(
        items=items,
        total=len(items),
        critical_count=critical_count,
        warning_count=warning_count,
        info_count=info_count,
        checked_at=now,
    )


# ──────────────────────────────────────────────
# 关系视图
# ──────────────────────────────────────────────


async def get_relationship_view(
    db: AsyncSession, prefix_id: int
) -> RelationshipView | None:
    """获取前缀的关系视图（前缀—ASN—ROA—BGP—业务—事件）。

    目前为基础版实现：
    - 返回前缀本身、父前缀、子前缀
    - 返回关联客户与业务服务信息
    - 返回与该前缀所在网段相关的 BGP 邻居（按 remote_asn 关联 ASN）

    Args:
        db: 异步数据库会话
        prefix_id: 前缀 ID

    Returns:
        关系视图对象；前缀不存在时返回 None
    """
    stmt = (
        select(Prefix)
        .options(selectinload(Prefix.children))
        .where(Prefix.id == prefix_id)
    )
    result = await db.execute(stmt)
    prefix = result.scalar_one_or_none()
    if prefix is None:
        return None

    # 父前缀
    parent_dict: dict[str, Any] | None = None
    if prefix.parent_id is not None:
        parent_stmt = select(Prefix).where(Prefix.id == prefix.parent_id)
        parent_result = await db.execute(parent_stmt)
        parent = parent_result.scalar_one_or_none()
        if parent is not None:
            parent_dict = parent.to_dict()

    # 子前缀
    children_dict = [c.to_dict() for c in prefix.children]

    # 关联客户
    customer_dict: dict[str, Any] | None = None
    if prefix.customer_id is not None:
        cust_stmt = select(Customer).where(Customer.id == prefix.customer_id)
        cust_result = await db.execute(cust_stmt)
        customer = cust_result.scalar_one_or_none()
        if customer is not None:
            customer_dict = customer.to_dict()

    # 关联业务服务（按名称匹配）
    business_dict: dict[str, Any] | None = None
    if prefix.business_service:
        biz_stmt = select(BusinessService).where(
            BusinessService.name == prefix.business_service
        )
        biz_result = await db.execute(biz_stmt)
        biz = biz_result.scalar_one_or_none()
        if biz is not None:
            business_dict = biz.to_dict()

    # 关联 BGP 邻居：当前实现为返回所有 BGP 邻居（基础版）
    # 实际生产中应根据前缀所在网段与邻居 IP 进行匹配
    peer_stmt = select(BGPPeer)
    peer_result = await db.execute(peer_stmt)
    peers = list(peer_result.scalars().all())
    peers_dict = [p.to_dict() for p in peers]

    # 关联 ASN：从 BGP 邻居的 remote_asn 反查
    remote_asns = {p.remote_asn for p in peers}
    related_asns_dict: list[dict[str, Any]] = []
    if remote_asns:
        from app.models.asn import ASN

        asn_stmt = select(ASN).where(ASN.asn.in_(remote_asns))
        asn_result = await db.execute(asn_stmt)
        for asn in asn_result.scalars().all():
            related_asns_dict.append(asn.to_dict())

    return RelationshipView(
        prefix=prefix.to_dict(),
        parent=parent_dict,
        children=children_dict,
        customer=customer_dict,
        business_service=business_dict,
        bgp_peers=peers_dict,
        related_asns=related_asns_dict,
    )


__all__ = [
    "check_consistency",
    "count_business_services",
    "count_customers",
    "count_routers",
    "create_business_service",
    "create_customer",
    "create_router",
    "delete_business_service",
    "delete_customer",
    "delete_router",
    "get_business_service",
    "get_business_services",
    "get_customer",
    "get_customers",
    "get_relationship_view",
    "get_router",
    "get_routers",
    "update_business_service",
    "update_customer",
    "update_router",
]
