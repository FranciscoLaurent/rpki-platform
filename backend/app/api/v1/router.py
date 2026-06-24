"""API v1 路由聚合。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    anycast_nodes,
    api_keys,
    asns,
    assets,
    audit,
    auth,
    benign_conflicts,
    bgp,
    bgp_peers,
    dashboard,
    detection,
    device_configs,
    forensics,
    health,
    integrations,
    maintenance_windows,
    prefixes,
    roa_changes,
    roas,
    rov,
    rpki,
    rtr,
    scrubber_authorizations,
    tenants,
    users,
    validate,
)

api_router = APIRouter()

# 注册各业务模块路由
api_router.include_router(health.router, prefix="/health", tags=["健康检查"])
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["租户管理"])
api_router.include_router(audit.router, prefix="/audit-logs", tags=["审计日志"])
api_router.include_router(prefixes.router, prefix="/prefixes", tags=["IP 前缀管理"])
api_router.include_router(asns.router, prefix="/asns", tags=["ASN 管理"])
api_router.include_router(bgp_peers.router, prefix="/bgp-peers", tags=["BGP 邻居管理"])
api_router.include_router(assets.router, prefix="/assets", tags=["资产管理"])
api_router.include_router(rpki.router, prefix="/rpki", tags=["RPKI 管理"])
api_router.include_router(roas.router, prefix="/roas", tags=["ROA 生命周期管理"])
api_router.include_router(roa_changes.changes_router, prefix="/roa-changes", tags=["ROA 变更管理"])
api_router.include_router(roa_changes.rules_router, prefix="/roa-approval-rules", tags=["ROA 审批规则"])
api_router.include_router(bgp.router, prefix="/bgp", tags=["BGP 监测"])
api_router.include_router(detection.router, prefix="/detection", tags=["路由安全检测"])
api_router.include_router(benign_conflicts.router, prefix="/benign-conflicts", tags=["良性冲突识别"])
api_router.include_router(maintenance_windows.router, prefix="/maintenance-windows", tags=["维护窗口"])
api_router.include_router(scrubber_authorizations.router, prefix="/scrubber-authorizations", tags=["清洗授权"])
api_router.include_router(anycast_nodes.router, prefix="/anycast-nodes", tags=["Anycast 节点"])
api_router.include_router(rov.router, prefix="/rov", tags=["ROV 策略模拟"])
api_router.include_router(rtr.router, prefix="/rtr", tags=["RPKI-RTR 服务"])
api_router.include_router(device_configs.router, prefix="/device-configs", tags=["设备配置模板"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["驾驶舱与详情"])
api_router.include_router(forensics.router, prefix="/forensics", tags=["取证与处置"])
api_router.include_router(integrations.router, prefix="/integrations", tags=["外部集成与事件推送"])
api_router.include_router(api_keys.router, prefix="/api-keys", tags=["API Key 管理"])
api_router.include_router(validate.router, prefix="/validate", tags=["统一验证入口"])
