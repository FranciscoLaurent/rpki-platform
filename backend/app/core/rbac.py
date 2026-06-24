"""RBAC 权限控制：权限定义、权限检查器、系统内置角色。

权限码格式为 ``resource:action``，例如 ``prefix:read``、``roa:approve``。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User


# ──────────────────────────────────────────────
# 权限码常量
# ──────────────────────────────────────────────


class Permissions:
    """系统权限码定义。

    权限码统一使用 ``resource:action`` 格式。
    """

    # 用户管理
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # 角色管理
    ROLE_READ = "role:read"
    ROLE_WRITE = "role:write"
    ROLE_DELETE = "role:delete"

    # 权限管理
    PERMISSION_READ = "permission:read"

    # 租户管理
    TENANT_READ = "tenant:read"
    TENANT_WRITE = "tenant:write"
    TENANT_DELETE = "tenant:delete"

    # 审计日志
    AUDIT_READ = "audit:read"

    # RPKI 前缀管理
    PREFIX_READ = "prefix:read"
    PREFIX_WRITE = "prefix:write"
    PREFIX_DELETE = "prefix:delete"

    # ROA 管理
    ROA_READ = "roa:read"
    ROA_WRITE = "roa:write"
    ROA_APPROVE = "roa:approve"
    ROA_DELETE = "roa:delete"

    # BGP 监测
    BGP_READ = "bgp:read"
    BGP_WRITE = "bgp:write"

    # 系统管理
    SYSTEM_ADMIN = "system:admin"


# 所有权限列表（用于初始化数据）
ALL_PERMISSIONS: list[dict[str, str]] = [
    {"name": "查看用户", "code": Permissions.USER_READ, "resource": "user", "action": "read"},
    {
        "name": "创建/编辑用户",
        "code": Permissions.USER_WRITE,
        "resource": "user",
        "action": "write",
    },
    {"name": "删除用户", "code": Permissions.USER_DELETE, "resource": "user", "action": "delete"},
    {"name": "查看角色", "code": Permissions.ROLE_READ, "resource": "role", "action": "read"},
    {
        "name": "创建/编辑角色",
        "code": Permissions.ROLE_WRITE,
        "resource": "role",
        "action": "write",
    },
    {"name": "删除角色", "code": Permissions.ROLE_DELETE, "resource": "role", "action": "delete"},
    {
        "name": "查看权限",
        "code": Permissions.PERMISSION_READ,
        "resource": "permission",
        "action": "read",
    },
    {"name": "查看租户", "code": Permissions.TENANT_READ, "resource": "tenant", "action": "read"},
    {
        "name": "创建/编辑租户",
        "code": Permissions.TENANT_WRITE,
        "resource": "tenant",
        "action": "write",
    },
    {
        "name": "删除租户",
        "code": Permissions.TENANT_DELETE,
        "resource": "tenant",
        "action": "delete",
    },
    {"name": "查看审计日志", "code": Permissions.AUDIT_READ, "resource": "audit", "action": "read"},
    {"name": "查看前缀", "code": Permissions.PREFIX_READ, "resource": "prefix", "action": "read"},
    {
        "name": "创建/编辑前缀",
        "code": Permissions.PREFIX_WRITE,
        "resource": "prefix",
        "action": "write",
    },
    {
        "name": "删除前缀",
        "code": Permissions.PREFIX_DELETE,
        "resource": "prefix",
        "action": "delete",
    },
    {"name": "查看 ROA", "code": Permissions.ROA_READ, "resource": "roa", "action": "read"},
    {"name": "创建/编辑 ROA", "code": Permissions.ROA_WRITE, "resource": "roa", "action": "write"},
    {"name": "审批 ROA", "code": Permissions.ROA_APPROVE, "resource": "roa", "action": "approve"},
    {"name": "删除 ROA", "code": Permissions.ROA_DELETE, "resource": "roa", "action": "delete"},
    {"name": "查看 BGP 监测", "code": Permissions.BGP_READ, "resource": "bgp", "action": "read"},
    {"name": "编辑 BGP 监测", "code": Permissions.BGP_WRITE, "resource": "bgp", "action": "write"},
    {"name": "系统管理", "code": Permissions.SYSTEM_ADMIN, "resource": "system", "action": "admin"},
]


# ──────────────────────────────────────────────
# 系统内置角色定义
# ──────────────────────────────────────────────

# 每个角色定义包含：name（名称）、description（描述）、permissions（权限码列表，"*" 表示全部）
SYSTEM_ROLES: dict[str, dict[str, object]] = {
    "super_admin": {
        "name": "超级管理员",
        "description": "拥有系统全部权限",
        "permissions": ["*"],
    },
    "network_admin": {
        "name": "网络管理员",
        "description": "管理网络前缀与 ROA",
        "permissions": [
            Permissions.PREFIX_READ,
            Permissions.PREFIX_WRITE,
            Permissions.PREFIX_DELETE,
            Permissions.ROA_READ,
            Permissions.ROA_WRITE,
            Permissions.ROA_APPROVE,
            Permissions.ROA_DELETE,
            Permissions.BGP_READ,
        ],
    },
    "rpki_admin": {
        "name": "RPKI 管理员",
        "description": "管理 RPKI 相关资源",
        "permissions": [
            Permissions.PREFIX_READ,
            Permissions.PREFIX_WRITE,
            Permissions.ROA_READ,
            Permissions.ROA_WRITE,
            Permissions.ROA_APPROVE,
            Permissions.BGP_READ,
        ],
    },
    "noc_operator": {
        "name": "NOC 操作员",
        "description": "网络运营中心操作员，可查看与监测",
        "permissions": [
            Permissions.PREFIX_READ,
            Permissions.ROA_READ,
            Permissions.BGP_READ,
            Permissions.BGP_WRITE,
        ],
    },
    "security_analyst": {
        "name": "安全分析师",
        "description": "安全审计与分析",
        "permissions": [
            Permissions.AUDIT_READ,
            Permissions.BGP_READ,
            Permissions.PREFIX_READ,
            Permissions.ROA_READ,
        ],
    },
    "approver": {
        "name": "审批人",
        "description": "审批 ROA 请求",
        "permissions": [
            Permissions.ROA_READ,
            Permissions.ROA_APPROVE,
            Permissions.PREFIX_READ,
        ],
    },
    "customer": {
        "name": "客户",
        "description": "租户客户，仅查看自身资源",
        "permissions": [
            Permissions.PREFIX_READ,
            Permissions.ROA_READ,
        ],
    },
    "api_service": {
        "name": "API 服务",
        "description": "用于 API 集成的服务账号",
        "permissions": [
            Permissions.PREFIX_READ,
            Permissions.PREFIX_WRITE,
            Permissions.ROA_READ,
            Permissions.ROA_WRITE,
            Permissions.BGP_READ,
        ],
    },
}


# ──────────────────────────────────────────────
# 权限检查器
# ──────────────────────────────────────────────


class PermissionChecker:
    """权限检查器，校验用户是否拥有所需权限。

    超级管理员或拥有 ``"*"`` 通配权限的用户可通过任意检查。
    """

    WILDCARD = "*"

    def __init__(self, required_permissions: list[str]) -> None:
        """初始化检查器。

        Args:
            required_permissions: 所需权限码列表，满足其一即可通过。
        """
        self.required_permissions = required_permissions

    def has_permission(self, user_permissions: set[str]) -> bool:
        """检查用户权限集合是否满足要求。"""
        if self.WILDCARD in user_permissions:
            return True
        return any(p in user_permissions for p in self.required_permissions)

    def has_all_permissions(self, user_permissions: set[str]) -> bool:
        """检查用户是否拥有全部所需权限。"""
        if self.WILDCARD in user_permissions:
            return True
        return all(p in user_permissions for p in self.required_permissions)


def collect_user_permissions(user: User) -> set[str]:
    """从已加载的用户对象中收集权限码集合。

    需确保 ``user.roles`` 及 ``role.permissions`` 已被加载（selectinload）。
    超级管理员返回 ``{"*"}``。
    """
    if user.is_superuser:
        return {PermissionChecker.WILDCARD}

    perms: set[str] = set()
    for role in user.roles:
        for perm in role.permissions:
            perms.add(perm.code)
    return perms


class TenantPermissionChecker:
    """租户感知的权限检查器。

    在常规权限检查的基础上，额外验证租户边界：用户只能访问
    其所属租户的资源，超级管理员可跨租户访问。

    用法::

        checker = TenantPermissionChecker(["tenant:read"])
        if not checker.check(user, target_tenant_id, user_permissions):
            raise HTTPException(403, "无权访问该租户资源")
    """

    WILDCARD = "*"

    def __init__(self, required_permissions: list[str]) -> None:
        """初始化检查器。

        Args:
            required_permissions: 所需权限码列表，满足其一即可通过。
        """
        self.required_permissions = required_permissions

    def has_permission(self, user_permissions: set[str]) -> bool:
        """检查用户权限集合是否满足要求（不含租户边界）。"""
        if self.WILDCARD in user_permissions:
            return True
        return any(p in user_permissions for p in self.required_permissions)

    def check_tenant_boundary(
        self,
        user: User,
        target_tenant_id: int | None,
    ) -> bool:
        """验证用户是否有权访问目标租户的资源。

        规则：
        1. 超级管理员可访问任意租户（含全局资源）
        2. 用户租户 ID 与目标租户 ID 一致时通过
        3. 目标租户为 None（全局资源）时，仅超级管理员可访问
        4. 其他情况拒绝

        Args:
            user: 当前用户
            target_tenant_id: 待访问资源的租户 ID，None 表示全局资源

        Returns:
            是否有权访问
        """
        if user.is_superuser:
            return True

        user_tenant_id = getattr(user, "tenant_id", None)

        # 全局资源（无租户）仅超级管理员可访问
        if target_tenant_id is None:
            return False

        # 用户租户与目标租户一致时通过
        return user_tenant_id is not None and user_tenant_id == target_tenant_id

    def check(
        self,
        user: User,
        target_tenant_id: int | None,
        user_permissions: set[str] | None = None,
    ) -> bool:
        """综合检查权限与租户边界。

        Args:
            user: 当前用户
            target_tenant_id: 待访问资源的租户 ID
            user_permissions: 用户权限集合，未提供时自动收集

        Returns:
            权限与租户边界均通过返回 True
        """
        if user_permissions is None:
            user_permissions = collect_user_permissions(user)

        if not self.has_permission(user_permissions):
            return False

        return self.check_tenant_boundary(user, target_tenant_id)
