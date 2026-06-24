"""外部集成适配器包。

提供 IPAM/CMDB、SIEM/SOC/ITSM、NMS/Prometheus/Grafana、RIR/NIR/IRR/PeeringDB
与企业协作通知等外部系统的集成适配器。
"""

from __future__ import annotations

from app.services.integrations.base import AdapterResult, BaseAdapter
from app.services.integrations.external_info import (
    RIRAdapter,
    enrich_asn,
    enrich_prefix,
    query_irr,
    query_peeringdb,
    query_rir,
)
from app.services.integrations.ipam_adapter import (
    IPAMAdapter,
    check_consistency,
    query_ipam,
    sync_from_netbox,
    sync_to_netbox,
)
from app.services.integrations.nms_adapter import (
    NMSAdapter,
    export_metrics,
    generate_grafana_dashboard,
    push_to_prometheus,
    query_nms_status,
)
from app.services.integrations.notification_adapter import (
    CollaborationAdapter,
    send_dingtalk,
    send_email,
    send_notification,
    send_pagerduty,
    send_slack,
    send_sms,
    send_teams,
    send_voice_call,
    send_wechat_work,
)
from app.services.integrations.siem_adapter import (
    ITSMAdapter,
    SIEMAdapter,
    create_itsm_ticket,
    forward_to_siem,
    query_siem_events,
    update_itsm_ticket,
)

__all__ = [
    "AdapterResult",
    "BaseAdapter",
    "CollaborationAdapter",
    "IPAMAdapter",
    "ITSMAdapter",
    "NMSAdapter",
    "RIRAdapter",
    "SIEMAdapter",
    "check_consistency",
    "create_itsm_ticket",
    "enrich_asn",
    "enrich_prefix",
    "export_metrics",
    "forward_to_siem",
    "generate_grafana_dashboard",
    "push_to_prometheus",
    "query_ipam",
    "query_irr",
    "query_nms_status",
    "query_peeringdb",
    "query_rir",
    "query_siem_events",
    "send_dingtalk",
    "send_email",
    "send_notification",
    "send_pagerduty",
    "send_slack",
    "send_sms",
    "send_teams",
    "send_voice_call",
    "send_wechat_work",
    "sync_from_netbox",
    "sync_to_netbox",
    "update_itsm_ticket",
]
