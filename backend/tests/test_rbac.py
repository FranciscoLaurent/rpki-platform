"""RBAC 权限控制测试。

覆盖 ``app.core.rbac`` 模块：
- 权限检查器（PermissionChecker）
- 通配符权限（*）
- 租户边界检查（TenantPermissionChecker）
- 用户权限收集（collect_user_permissions）
- 系统内置角色权限定义
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from app.core.rbac import (
    ALL_PERMISSIONS,
    SYSTEM_ROLES,
    PermissionChecker,
    TenantPermissionChecker,
    collect_user_permissions,
)
from app.core.rbac import Permissions


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _make_permission(code: str) -> MagicMock:
    """构造一个模拟的 Permission 对象。"""
    perm = MagicMock()
    perm.code = code
    return perm


def _make_role(permissions: list[str]) -> MagicMock:
    """构造一个模拟的 Role 对象，包含给定权限码。"""
    role = MagicMock()
    role.permissions = [_make_permission(code) for code in permissions]
    return role


def _make_user(
    roles: list[Any] | None = None,
    is_superuser: bool = False,
    tenant_id: int | None = None,
) -> MagicMock:
    """构造一个模拟的 User 对象。"""
    user = MagicMock()
    user.roles = roles or []
    user.is_superuser = is_superuser
    user.tenant_id = tenant_id
    return user


# ──────────────────────────────────────────────
# PermissionChecker 测试
# ──────────────────────────────────────────────


def test_permission_checker_has_permission_single() -> None:
    """用户拥有任一所需权限应通过检查。"""
    checker = PermissionChecker([Permissions.PREFIX_READ])
    user_perms = {Permissions.PREFIX_READ}
    assert checker.has_permission(user_perms) is True


def test_permission_checker_has_permission_multiple_required() -> None:
    """多权限要求中满足其一应通过 has_permission。"""
    checker = PermissionChecker([Permissions.PREFIX_READ, Permissions.ROA_READ])
    user_perms = {Permissions.ROA_READ}
    assert checker.has_permission(user_perms) is True


def test_permission_checker_no_permission() -> None:
    """用户无所需权限应不通过。"""
    checker = PermissionChecker([Permissions.PREFIX_WRITE])
    user_perms = {Permissions.PREFIX_READ}
    assert checker.has_permission(user_perms) is False


def test_permission_checker_empty_user_perms() -> None:
    """空权限集应不通过。"""
    checker = PermissionChecker([Permissions.PREFIX_READ])
    assert checker.has_permission(set()) is False


def test_permission_checker_wildcard_passes_any() -> None:
    """通配符权限应通过任意检查。"""
    checker = PermissionChecker([Permissions.SYSTEM_ADMIN])
    user_perms = {PermissionChecker.WILDCARD}
    assert checker.has_permission(user_perms) is True


def test_permission_checker_has_all_permissions() -> None:
    """has_all_permissions 应要求全部权限。"""
    checker = PermissionChecker([Permissions.PREFIX_READ, Permissions.PREFIX_WRITE])
    user_perms = {Permissions.PREFIX_READ, Permissions.PREFIX_WRITE}
    assert checker.has_all_permissions(user_perms) is True


def test_permission_checker_has_all_permissions_partial_fail() -> None:
    """has_all_permissions 仅满足部分应失败。"""
    checker = PermissionChecker([Permissions.PREFIX_READ, Permissions.PREFIX_WRITE])
    user_perms = {Permissions.PREFIX_READ}
    assert checker.has_all_permissions(user_perms) is False


def test_permission_checker_has_all_permissions_wildcard() -> None:
    """通配符应通过 has_all_permissions。"""
    checker = PermissionChecker([Permissions.PREFIX_READ, Permissions.SYSTEM_ADMIN])
    user_perms = {PermissionChecker.WILDCARD}
    assert checker.has_all_permissions(user_perms) is True


# ──────────────────────────────────────────────
# collect_user_permissions 测试
# ──────────────────────────────────────────────


def test_collect_user_permissions_superuser_returns_wildcard() -> None:
    """超级管理员应返回通配符权限。"""
    user = _make_user(is_superuser=True)
    perms = collect_user_permissions(user)
    assert perms == {PermissionChecker.WILDCARD}


def test_collect_user_permissions_normal_user() -> None:
    """普通用户应收集所有角色的权限码。"""
    role1 = _make_role([Permissions.PREFIX_READ, Permissions.ROA_READ])
    role2 = _make_role([Permissions.BGP_READ])
    user = _make_user(roles=[role1, role2], is_superuser=False)

    perms = collect_user_permissions(user)

    assert Permissions.PREFIX_READ in perms
    assert Permissions.ROA_READ in perms
    assert Permissions.BGP_READ in perms
    assert PermissionChecker.WILDCARD not in perms


def test_collect_user_permissions_no_roles() -> None:
    """无角色的用户应返回空权限集。"""
    user = _make_user(roles=[], is_superuser=False)
    perms = collect_user_permissions(user)
    assert perms == set()


def test_collect_user_permissions_deduplicates() -> None:
    """重复权限应被去重。"""
    role1 = _make_role([Permissions.PREFIX_READ])
    role2 = _make_role([Permissions.PREFIX_READ, Permissions.ROA_READ])
    user = _make_user(roles=[role1, role2])

    perms = collect_user_permissions(user)

    assert len(perms) == 2  # PREFIX_READ 与 ROA_READ


# ──────────────────────────────────────────────
# TenantPermissionChecker 测试
# ──────────────────────────────────────────────


def test_tenant_checker_superuser_passes_any_tenant() -> None:
    """超级管理员应通过任意租户边界检查。"""
    checker = TenantPermissionChecker([Permissions.TENANT_READ])
    user = _make_user(is_superuser=True, tenant_id=1)

    assert checker.check_tenant_boundary(user, target_tenant_id=999) is True
    assert checker.check_tenant_boundary(user, target_tenant_id=None) is True


def test_tenant_checker_same_tenant_passes() -> None:
    """用户租户与目标租户一致应通过。"""
    checker = TenantPermissionChecker([Permissions.TENANT_READ])
    user = _make_user(is_superuser=False, tenant_id=5)

    assert checker.check_tenant_boundary(user, target_tenant_id=5) is True


def test_tenant_checker_different_tenant_fails() -> None:
    """用户租户与目标租户不一致应失败。"""
    checker = TenantPermissionChecker([Permissions.TENANT_READ])
    user = _make_user(is_superuser=False, tenant_id=5)

    assert checker.check_tenant_boundary(user, target_tenant_id=6) is False


def test_tenant_checker_global_resource_fails_for_non_superuser() -> None:
    """非超级管理员访问全局资源（target_tenant_id=None）应失败。"""
    checker = TenantPermissionChecker([Permissions.TENANT_READ])
    user = _make_user(is_superuser=False, tenant_id=5)

    assert checker.check_tenant_boundary(user, target_tenant_id=None) is False


def test_tenant_checker_user_without_tenant_fails() -> None:
    """无租户的用户访问任何租户资源应失败。"""
    checker = TenantPermissionChecker([Permissions.TENANT_READ])
    user = _make_user(is_superuser=False, tenant_id=None)

    assert checker.check_tenant_boundary(user, target_tenant_id=5) is False


def test_tenant_checker_check_combines_permission_and_boundary() -> None:
    """check 应综合检查权限与租户边界。"""
    checker = TenantPermissionChecker([Permissions.PREFIX_READ])
    user = _make_user(is_superuser=False, tenant_id=5)
    user_perms = {Permissions.PREFIX_READ}

    # 权限通过且租户边界通过
    assert checker.check(user, target_tenant_id=5, user_permissions=user_perms) is True
    # 权限通过但租户边界失败
    assert checker.check(user, target_tenant_id=6, user_permissions=user_perms) is False


def test_tenant_checker_check_fails_on_permission() -> None:
    """权限不通过时 check 应失败。"""
    checker = TenantPermissionChecker([Permissions.PREFIX_WRITE])
    user = _make_user(is_superuser=False, tenant_id=5)
    user_perms = {Permissions.PREFIX_READ}  # 无 WRITE 权限

    assert checker.check(user, target_tenant_id=5, user_permissions=user_perms) is False


def test_tenant_checker_check_auto_collects_permissions() -> None:
    """未提供 user_permissions 时应自动收集。"""
    checker = TenantPermissionChecker([Permissions.PREFIX_READ])
    role = _make_role([Permissions.PREFIX_READ])
    user = _make_user(roles=[role], is_superuser=False, tenant_id=5)

    assert checker.check(user, target_tenant_id=5) is True


# ──────────────────────────────────────────────
# 系统内置角色定义测试
# ──────────────────────────────────────────────


def test_system_roles_contains_super_admin() -> None:
    """系统角色应包含超级管理员。"""
    assert "super_admin" in SYSTEM_ROLES


def test_super_admin_has_wildcard_permission() -> None:
    """超级管理员应拥有通配符权限。"""
    assert "*" in SYSTEM_ROLES["super_admin"]["permissions"]


def test_system_roles_have_required_fields() -> None:
    """每个系统角色应包含 name、description、permissions 字段。"""
    for role_key, role_def in SYSTEM_ROLES.items():
        assert "name" in role_def, f"角色 {role_key} 缺少 name 字段"
        assert "description" in role_def, f"角色 {role_key} 缺少 description 字段"
        assert "permissions" in role_def, f"角色 {role_key} 缺少 permissions 字段"
        assert isinstance(role_def["permissions"], list)


def test_network_admin_has_prefix_and_roa_permissions() -> None:
    """网络管理员应拥有前缀与 ROA 管理权限。"""
    perms = SYSTEM_ROLES["network_admin"]["permissions"]
    assert Permissions.PREFIX_READ in perms
    assert Permissions.PREFIX_WRITE in perms
    assert Permissions.ROA_READ in perms
    assert Permissions.ROA_APPROVE in perms


def test_noc_operator_has_read_permissions() -> None:
    """NOC 操作员应拥有只读权限。"""
    perms = SYSTEM_ROLES["noc_operator"]["permissions"]
    assert Permissions.PREFIX_READ in perms
    assert Permissions.ROA_READ in perms
    assert Permissions.BGP_READ in perms


def test_approver_has_roa_approve_permission() -> None:
    """审批人应拥有 ROA 审批权限。"""
    perms = SYSTEM_ROLES["approver"]["permissions"]
    assert Permissions.ROA_APPROVE in perms


def test_customer_has_only_read_permissions() -> None:
    """客户角色应仅有只读权限。"""
    perms = SYSTEM_ROLES["customer"]["permissions"]
    for p in perms:
        assert ":read" in p, f"客户角色不应包含非读权限：{p}"


# ──────────────────────────────────────────────
# ALL_PERMISSIONS 测试
# ──────────────────────────────────────────────


def test_all_permissions_contains_user_management() -> None:
    """权限列表应包含用户管理权限。"""
    codes = [p["code"] for p in ALL_PERMISSIONS]
    assert Permissions.USER_READ in codes
    assert Permissions.USER_WRITE in codes
    assert Permissions.USER_DELETE in codes


def test_all_permissions_contains_roa_management() -> None:
    """权限列表应包含 ROA 管理权限。"""
    codes = [p["code"] for p in ALL_PERMISSIONS]
    assert Permissions.ROA_READ in codes
    assert Permissions.ROA_WRITE in codes
    assert Permissions.ROA_APPROVE in codes
    assert Permissions.ROA_DELETE in codes


def test_all_permissions_have_required_fields() -> None:
    """每个权限定义应包含 name、code、resource、action 字段。"""
    for perm in ALL_PERMISSIONS:
        assert "name" in perm
        assert "code" in perm
        assert "resource" in perm
        assert "action" in perm


def test_all_permissions_code_format() -> None:
    """权限码应符合 resource:action 格式。"""
    for perm in ALL_PERMISSIONS:
        code = perm["code"]
        assert ":" in code, f"权限码 {code} 不符合 resource:action 格式"
        parts = code.split(":")
        assert len(parts) == 2
        assert parts[0] == perm["resource"]
        assert parts[1] == perm["action"]
