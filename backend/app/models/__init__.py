"""SQLAlchemy 数据模型集合。

所有模型继承自 ``app.models.base.Base``。
导入此包即注册全部模型到 ``Base.metadata``，供 Alembic 迁移使用。
"""

from __future__ import annotations

from app.models.asn import ASN
from app.models.audit import AuditLog
from app.models.base import Base, TenantMixin, TimestampMixin
from app.models.benign_conflict import (
    AnycastNode,
    BenignConflictRecord,
    MaintenanceWindow,
    ScrubberAuthorization,
)
from app.models.bgp import (
    BGPAnnouncement,
    BGPDataSource,
    BGPRibSnapshot,
    BGPWithdraw,
    DeviceAdapter,
    ObservationPoint,
)
from app.models.bgp_peer import BGPPeer
from app.models.business import BusinessService, Customer, Router
from app.models.detection import Alert, DetectionRule, Incident, RiskScore
from app.models.prefix import Prefix
from app.models.roa_change import ROAApprovalRule, ROAChangeRequest
from app.models.rpki import (
    RPKICache,
    RPKIObject,
    RPKIRepository,
    RPKISnapshot,
    ROA,
    TAL,
    VRP,
)
from app.models.rtr import (
    DeviceConfigTemplate,
    RTRServer,
    RTRSession,
    RTRSerialHistory,
)
from app.models.tenant import Tenant, TenantMember
from app.models.user import (
    Permission,
    Role,
    User,
    role_permissions,
    user_roles,
)

__all__ = [
    "ASN",
    "Alert",
    "AnycastNode",
    "AuditLog",
    "BGPAnnouncement",
    "BGPDataSource",
    "BGPPeer",
    "BGPRibSnapshot",
    "BGPWithdraw",
    "Base",
    "BenignConflictRecord",
    "BusinessService",
    "Customer",
    "DetectionRule",
    "DeviceAdapter",
    "DeviceConfigTemplate",
    "Incident",
    "MaintenanceWindow",
    "ObservationPoint",
    "Permission",
    "Prefix",
    "ROA",
    "ROAApprovalRule",
    "ROAChangeRequest",
    "RPKICache",
    "RPKIObject",
    "RPKIRepository",
    "RPKISnapshot",
    "RTRServer",
    "RTRSession",
    "RTRSerialHistory",
    "RiskScore",
    "Role",
    "Router",
    "ScrubberAuthorization",
    "TAL",
    "Tenant",
    "TenantMember",
    "TenantMixin",
    "TimestampMixin",
    "User",
    "VRP",
    "role_permissions",
    "user_roles",
]
