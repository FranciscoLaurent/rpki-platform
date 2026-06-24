"""系统配置数据初始化模块。

提供工厂函数用于生成系统配置示例数据，包括：
- 租户与用户
- 角色与权限
- 检测规则
- RTR 服务
- 业务服务、客户与路由器

外部数据（TAL、ROA、VRP、BGP 公告、ASN、前缀）由
``app.services.real_data_collector.RealDataCollector`` 从权威数据源采集，
不在本模块生成。

所有工厂函数返回 ORM 对象列表，由调用方负责写入数据库。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_password_hash
from app.models.business import BusinessService, Customer, Router
from app.models.detection import DetectionRule
from app.models.rtr import RTRServer
from app.models.tenant import Tenant
from app.models.user import Permission, Role, User

# ──────────────────────────────────────────────
# 租户与用户
# ──────────────────────────────────────────────


def make_tenants() -> list[Tenant]:
    """创建示例租户。"""
    return [
        Tenant(
            name="默认租户",
            slug="default",
            status="active",
            settings={"theme": "light", "language": "zh-CN"},
            max_users=100,
        ),
        Tenant(
            name="演示租户",
            slug="demo",
            status="active",
            settings={"theme": "dark", "language": "zh-CN"},
            max_users=50,
        ),
    ]


def make_users() -> list[User]:
    """创建示例用户（密码均为 ``password123``）。"""
    hashed = get_password_hash("password123")
    return [
        User(
            email="admin@rpki.local",
            username="admin",
            full_name="超级管理员",
            hashed_password=hashed,
            is_active=True,
            is_superuser=True,
        ),
        User(
            email="noc@rpki.local",
            username="noc_operator",
            full_name="NOC 操作员",
            hashed_password=hashed,
            is_active=True,
            is_superuser=False,
        ),
        User(
            email="approver@rpki.local",
            username="approver",
            full_name="ROA 审批人",
            hashed_password=hashed,
            is_active=True,
            is_superuser=False,
        ),
        User(
            email="analyst@rpki.local",
            username="analyst",
            full_name="安全分析师",
            hashed_password=hashed,
            is_active=True,
            is_superuser=False,
        ),
    ]


def make_roles() -> list[Role]:
    """创建示例角色。"""
    return [
        Role(name="超级管理员", code="super_admin", description="拥有系统全部权限", is_system=True),
        Role(
            name="网络管理员",
            code="network_admin",
            description="管理网络前缀与 ROA",
            is_system=True,
        ),
        Role(
            name="NOC 操作员", code="noc_operator", description="网络运营中心操作员", is_system=True
        ),
        Role(
            name="安全分析师", code="security_analyst", description="安全审计与分析", is_system=True
        ),
        Role(name="ROA 审批人", code="roa_approver", description="审批 ROA 请求", is_system=True),
    ]


def make_permissions() -> list[Permission]:
    """创建示例权限（与 ``app.core.rbac.ALL_PERMISSIONS`` 对应）。"""
    from app.core.rbac import ALL_PERMISSIONS

    perms: list[Permission] = []
    for p in ALL_PERMISSIONS:
        perms.append(
            Permission(
                name=p["name"],
                code=p["code"],
                resource=p["resource"],
                action=p["action"],
            )
        )
    return perms


# ──────────────────────────────────────────────
# 检测规则
# ──────────────────────────────────────────────


def make_detection_rules() -> list[DetectionRule]:
    """创建示例检测规则。"""
    return [
        DetectionRule(
            name="源 AS 劫持检测",
            code="hijack_origin_as",
            description="检测非授权 origin AS 宣告已授权前缀",
            rule_type="hijack",
            enabled=True,
            priority=10,
            severity="P0",
            conditions={"min_propagation_scope": 1},
            thresholds={"rpki_invalid_confidence": 0.9},
        ),
        DetectionRule(
            name="子前缀劫持检测",
            code="hijack_subprefix",
            description="检测更具体前缀的异常公告",
            rule_type="subprefix_hijack",
            enabled=True,
            priority=20,
            severity="P0",
        ),
        DetectionRule(
            name="MOAS 异常检测",
            code="moas_unknown",
            description="检测多个未知关系 AS 宣告同一前缀",
            rule_type="moas",
            enabled=True,
            priority=30,
            severity="P2",
            thresholds={"min_origin_as_count": 2},
        ),
        DetectionRule(
            name="路由泄露检测",
            code="route_leak",
            description="检测客户-提供商-对等间的路由泄露",
            rule_type="route_leak",
            enabled=True,
            priority=40,
            severity="P1",
        ),
        DetectionRule(
            name="路径异常检测",
            code="path_anomaly",
            description="检测 AS_PATH 突变、异常中转与黑洞风险",
            rule_type="path_anomaly",
            enabled=True,
            priority=50,
            severity="P2",
        ),
        DetectionRule(
            name="撤路与震荡检测",
            code="withdraw_flap",
            description="检测大范围撤路与频繁震荡",
            rule_type="withdraw_flap",
            enabled=True,
            priority=60,
            severity="P1",
            thresholds={"min_withdraw_points": 5, "min_flap_rate": 0.5},
        ),
        DetectionRule(
            name="RPKI Invalid 传播检测",
            code="rpki_invalid_propagation",
            description="统计 Invalid 路由的传播范围",
            rule_type="rpki_invalid",
            enabled=True,
            priority=70,
            severity="P2",
            thresholds={"min_propagation_count": 1},
        ),
    ]


# ──────────────────────────────────────────────
# RTR 服务
# ──────────────────────────────────────────────


def make_rtr_servers() -> list[RTRServer]:
    """创建示例 RTR 服务配置。"""
    return [
        RTRServer(
            name="主 RTR 服务",
            listen_host="0.0.0.0",
            listen_port=8282,
            session_id=1,
            mtls_enabled=False,
            whitelist=["10.0.0.0/8"],
            config={"refresh_interval": 3600, "timeout": 60},
            status="stopped",
            current_serial=0,
            vrps_count=0,
            connected_clients=0,
        ),
        RTRServer(
            name="备用 RTR 服务",
            listen_host="0.0.0.0",
            listen_port=8283,
            session_id=2,
            mtls_enabled=True,
            whitelist=["192.168.0.0/16"],
            config={"refresh_interval": 1800, "timeout": 30},
            status="stopped",
            current_serial=0,
            vrps_count=0,
            connected_clients=0,
        ),
    ]


# ──────────────────────────────────────────────
# 业务与客户
# ──────────────────────────────────────────────


def make_customers() -> list[Customer]:
    """创建示例客户。"""
    return [
        Customer(
            name="客户 A",
            contact_name="张三",
            contact_email="zhangsan@customer-a.local",
            status="active",
        ),
        Customer(
            name="客户 B",
            contact_name="李四",
            contact_email="lisi@customer-b.local",
            status="active",
        ),
    ]


def make_business_services() -> list[BusinessService]:
    """创建示例业务服务。"""
    return [
        BusinessService(
            name="核心业务",
            description="核心生产业务",
            importance="critical",
            owner_contact="noc@rpki.local",
        ),
        BusinessService(
            name="办公网络",
            description="内部办公网络",
            importance="important",
            owner_contact="it@rpki.local",
        ),
        BusinessService(
            name="测试环境",
            description="测试与开发环境",
            importance="normal",
            owner_contact="dev@rpki.local",
        ),
    ]


def make_routers() -> list[Router]:
    """创建示例路由器。"""
    return [
        Router(
            hostname="core-router-1",
            vendor="cisco_ios_xr",
            model="ASR 9000",
            management_ip="10.0.0.1",
            location="上海机房",
            status="active",
        ),
        Router(
            hostname="edge-router-1",
            vendor="juniper_junos",
            model="MX240",
            management_ip="10.0.0.2",
            location="北京机房",
            status="active",
        ),
    ]


# ──────────────────────────────────────────────
# 系统配置数据初始化
# ──────────────────────────────────────────────


async def init_system_config_data(db: AsyncSession) -> dict:
    """初始化系统配置数据（不含外部数据）。

    外部数据（TAL、ROA、VRP、BGP、ASN、前缀）由 ``RealDataCollector`` 采集。

    Args:
        db: 异步数据库会话

    Returns:
        包含各表记录数和默认租户 ID 的字典
    """
    # 租户（先创建并 flush，以获取默认租户 ID）
    tenants = make_tenants()
    db.add_all(tenants)
    await db.flush()
    default_tenant_id = tenants[0].id if tenants else None

    # 用户、角色、权限
    users = make_users()
    roles = make_roles()
    permissions = make_permissions()
    db.add_all(users)
    db.add_all(roles)
    db.add_all(permissions)

    # 检测规则
    detection_rules = make_detection_rules()
    db.add_all(detection_rules)

    # RTR 服务
    rtr_servers = make_rtr_servers()
    db.add_all(rtr_servers)

    # 业务服务、客户、路由器
    business_services = make_business_services()
    customers = make_customers()
    routers = make_routers()
    db.add_all(business_services)
    db.add_all(customers)
    db.add_all(routers)

    await db.commit()

    return {
        "tenants_count": len(tenants),
        "users_count": len(users),
        "roles_count": len(roles),
        "permissions_count": len(permissions),
        "detection_rules_count": len(detection_rules),
        "rtr_servers_count": len(rtr_servers),
        "business_services_count": len(business_services),
        "customers_count": len(customers),
        "routers_count": len(routers),
        "default_tenant_id": default_tenant_id,
    }


__all__ = [
    "init_system_config_data",
    "make_business_services",
    "make_customers",
    "make_detection_rules",
    "make_permissions",
    "make_roles",
    "make_routers",
    "make_rtr_servers",
    "make_tenants",
    "make_users",
]
