"""NMS/Prometheus/Grafana 指标集成适配器。

提供与网络管理系统（NMS）、Prometheus 指标推送与 Grafana 仪表盘生成的
集成能力，支持推送指标到 Pushgateway、生成 Grafana Dashboard JSON、
查询 NMS 设备状态以及导出平台核心指标。
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement
from app.models.detection import Alert, Incident
from app.models.prefix import Prefix
from app.models.rpki import ROA
from app.services.integrations.base import AdapterResult, BaseAdapter

logger: BoundLogger = get_logger("app.integrations.nms")


class NMSAdapter(BaseAdapter):
    """NMS（网络管理系统）集成适配器。

    支持的子类型：
    - ``zabbix``: Zabbix
    - ``librenms``: LibreNMS
    - ``observium``: Observium
    - ``generic``: 通用 NMS（自定义 HTTP 接口）

    连接参数：
    - ``url``: NMS 基础 URL
    - ``timeout``: 请求超时（秒，默认 10）
    - ``verify_tls``: 是否校验 TLS（默认 True）
    """

    async def test_connection(self) -> AdapterResult:
        """测试 NMS 连接。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="NMS URL 未配置")

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                response = await client.get(
                    f"{base_url}/api/v1/status", headers=headers
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            return AdapterResult(
                success=success,
                data=response.json() if success else None,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(
                success=False, error_message=str(e), latency_ms=latency_ms
            )

    async def query_device_status(self, device_name: str) -> AdapterResult:
        """查询单个设备状态。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="NMS URL 未配置")

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                response = await client.get(
                    f"{base_url}/api/v1/devices",
                    headers=headers,
                    params={"name": device_name},
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            return AdapterResult(
                success=success,
                data=response.json() if success else None,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(
                success=False, error_message=str(e), latency_ms=latency_ms
            )


# ──────────────────────────────────────────────
# 函数式接口
# ──────────────────────────────────────────────


async def push_to_prometheus(
    config: dict[str, Any], metrics: list[dict[str, Any]]
) -> bool:
    """推送指标到 Prometheus Pushgateway。

    Args:
        config: Prometheus 配置，需包含 ``pushgateway_url``，可选 ``job_name``、
            ``instance_label``。
        metrics: 指标列表，每项包含 ``name``、``value``、可选 ``labels``、
            ``help``、``type``。

    Returns:
        是否推送成功。
    """
    pushgateway_url = config.get("pushgateway_url")
    if not pushgateway_url:
        logger.error("推送 Prometheus 指标失败：Pushgateway URL 未配置")
        return False

    job_name = config.get("job_name", "rpki-platform")
    instance_label = config.get("instance_label", "")
    url = f"{pushgateway_url.rstrip('/')}/metrics/job/{job_name}"
    if instance_label:
        url += f"/instance/{instance_label}"

    # 构造 Prometheus exposition 格式
    lines: list[str] = []
    for metric in metrics:
        name = metric.get("name")
        value = metric.get("value")
        if name is None or value is None:
            continue
        help_text = metric.get("help")
        metric_type = metric.get("type", "gauge")
        if help_text:
            lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")
        labels = metric.get("labels") or {}
        if labels:
            label_str = ",".join(
                f'{k}="{v}"' for k, v in labels.items()
            )
            lines.append(f"{name}{{{label_str}}} {value}")
        else:
            lines.append(f"{name} {value}")

    body = "\n".join(lines) + "\n"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, content=body.encode("utf-8"))
        success = response.status_code < 400
        if not success:
            logger.error(
                "推送 Prometheus 指标失败",
                status_code=response.status_code,
                body=response.text[:500],
            )
        return success
    except Exception as e:
        logger.error("推送 Prometheus 指标异常", error=str(e))
        return False


async def generate_grafana_dashboard(config: dict[str, Any]) -> dict[str, Any]:
    """生成 Grafana Dashboard JSON。

    生成一个包含 RPKI 平台核心指标的 Grafana Dashboard JSON 配置。

    Args:
        config: Grafana 配置，可选 ``title``、``uid``、``datasource``。

    Returns:
        Grafana Dashboard JSON 配置字典。
    """
    title = config.get("title", "RPKI 路由安全平台")
    uid = config.get("uid", "rpki-platform")
    datasource = config.get("datasource", "Prometheus")

    # 构造面板列表
    panels: list[dict[str, Any]] = []
    panel_definitions = [
        {
            "title": "前缀总数",
            "expr": "rpki_prefixes_total",
            "legend": "{{status}}",
            "y_axis": "数量",
        },
        {
            "title": "ROA 覆盖率",
            "expr": "rpki_roa_coverage_ratio * 100",
            "legend": "覆盖率",
            "y_axis": "百分比",
        },
        {
            "title": "RPKI 验证状态分布",
            "expr": "rpki_validation_total",
            "legend": "{{validation_status}}",
            "y_axis": "数量",
        },
        {
            "title": "活跃告警数",
            "expr": "rpki_alerts_active_total",
            "legend": "{{severity}}",
            "y_axis": "数量",
        },
        {
            "title": "未关闭事件数",
            "expr": "rpki_incidents_open_total",
            "legend": "{{severity}}",
            "y_axis": "数量",
        },
        {
            "title": "ASN 总数",
            "expr": "rpki_asns_total",
            "legend": "ASN",
            "y_axis": "数量",
        },
    ]

    for idx, panel_def in enumerate(panel_definitions):
        panels.append(
            {
                "id": idx + 1,
                "title": panel_def["title"],
                "type": "timeseries",
                "datasource": {"type": "prometheus", "uid": datasource},
                "gridPos": {
                    "h": 8,
                    "w": 12,
                    "x": (idx % 2) * 12,
                    "y": (idx // 2) * 8,
                },
                "targets": [
                    {
                        "expr": panel_def["expr"],
                        "legendFormat": panel_def["legend"],
                        "refId": "A",
                    }
                ],
                "fieldConfig": {
                    "defaults": {
                        "unit": "short",
                        "custom": {"drawStyle": "line", "lineInterpolation": "linear"},
                    },
                },
                "options": {"legend": {"displayMode": "table", "placement": "bottom"}},
            }
        )

    dashboard: dict[str, Any] = {
        "id": None,
        "uid": uid,
        "title": title,
        "tags": ["rpki", "routing-security", "bgp"],
        "timezone": "browser",
        "schemaVersion": 38,
        "version": 1,
        "refresh": "30s",
        "time": {"from": "now-6h", "to": "now"},
        "panels": panels,
        "templating": {
            "list": [
                {
                    "name": "datasource",
                    "type": "datasource",
                    "query": "prometheus",
                    "current": {"text": datasource, "value": datasource},
                }
            ]
        },
    }
    return dashboard


async def query_nms_status(config: dict[str, Any]) -> dict[str, Any]:
    """查询 NMS 设备状态。

    Args:
        config: NMS 配置，需包含 ``url``，可选 ``token``、``username``、
            ``password``、``timeout``、``verify_tls``。

    Returns:
        设备状态汇总，包含 total、up、down、warning 字段。
    """
    base_url = config.get("url", "").rstrip("/")
    if not base_url:
        return {"success": False, "message": "NMS URL 未配置", "devices": []}

    headers: dict[str, str] = {"Accept": "application/json"}
    token = config.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif config.get("username"):
        import base64

        username = config.get("username", "")
        password = config.get("password", "")
        credentials = base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"

    timeout = float(config.get("timeout", 10))
    verify_tls = config.get("verify_tls", True)

    try:
        async with httpx.AsyncClient(
            timeout=timeout, verify=verify_tls
        ) as client:
            response = await client.get(
                f"{base_url}/api/v1/devices", headers=headers
            )
        if response.status_code >= 400:
            return {
                "success": False,
                "message": f"查询失败，状态码 {response.status_code}",
                "devices": [],
            }
        data = response.json()
        devices = data if isinstance(data, list) else data.get("devices", [])
        # 统计设备状态
        status_summary = {"up": 0, "down": 0, "warning": 0}
        for device in devices:
            status = device.get("status", "up").lower()
            if status in status_summary:
                status_summary[status] += 1
        return {
            "success": True,
            "total": len(devices),
            "up": status_summary["up"],
            "down": status_summary["down"],
            "warning": status_summary["warning"],
            "devices": devices,
        }
    except Exception as e:
        logger.error("查询 NMS 设备状态异常", error=str(e))
        return {
            "success": False,
            "message": str(e),
            "devices": [],
        }


async def export_metrics(db: AsyncSession) -> list[dict[str, Any]]:
    """导出平台核心指标。

    从数据库统计前缀数、ROA 覆盖率、Invalid 数、告警数、事件数等核心指标，
    生成 Prometheus 格式的指标列表。

    Args:
        db: 数据库会话。

    Returns:
        指标列表，每项包含 name、value、labels、help、type 字段。
    """
    metrics: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).isoformat()

    # 前缀总数（按状态分组）
    stmt = (
        select(Prefix.status, func.count(Prefix.id))
        .group_by(Prefix.status)
    )
    result = await db.execute(stmt)
    for status, count in result.all():
        metrics.append(
            {
                "name": "rpki_prefixes_total",
                "value": count,
                "labels": {"status": status},
                "help": "前缀总数（按状态分组）",
                "type": "gauge",
            }
        )

    # 前缀总数（合计）
    total_prefixes = await db.scalar(select(func.count(Prefix.id)))
    metrics.append(
        {
            "name": "rpki_prefixes_total",
            "value": total_prefixes or 0,
            "labels": {"status": "all"},
            "help": "前缀总数",
            "type": "gauge",
        }
    )

    # ROA 总数（按状态分组）
    stmt = select(ROA.status, func.count(ROA.id)).group_by(ROA.status)
    result = await db.execute(stmt)
    roa_counts: dict[str, int] = {}
    for status, count in result.all():
        roa_counts[status] = count
        metrics.append(
            {
                "name": "rpki_roas_total",
                "value": count,
                "labels": {"status": status},
                "help": "ROA 总数（按状态分组）",
                "type": "gauge",
            }
        )

    # ROA 覆盖率（有 ROA 的前缀数 / 总前缀数）
    total_roas = sum(roa_counts.values())
    coverage_ratio = 0.0
    if total_prefixes and total_prefixes > 0:
        # 简化估算：ROA 数 / 前缀数（实际应按前缀匹配）
        coverage_ratio = min(total_roas / total_prefixes, 1.0)
    metrics.append(
        {
            "name": "rpki_roa_coverage_ratio",
            "value": coverage_ratio,
            "labels": {},
            "help": "ROA 覆盖率",
            "type": "gauge",
        }
    )

    # ASN 总数（按类型分组）
    stmt = select(ASN.asn_type, func.count(ASN.id)).group_by(ASN.asn_type)
    result = await db.execute(stmt)
    for asn_type, count in result.all():
        metrics.append(
            {
                "name": "rpki_asns_total",
                "value": count,
                "labels": {"type": asn_type},
                "help": "ASN 总数（按类型分组）",
                "type": "gauge",
            }
        )

    # 活跃告警数（按严重等级分组）
    stmt = (
        select(Alert.severity, func.count(Alert.id))
        .where(Alert.status.in_(["new", "confirmed", "assigned"]))
        .group_by(Alert.severity)
    )
    result = await db.execute(stmt)
    for severity, count in result.all():
        metrics.append(
            {
                "name": "rpki_alerts_active_total",
                "value": count,
                "labels": {"severity": severity},
                "help": "活跃告警数（按严重等级分组）",
                "type": "gauge",
            }
        )

    # 未关闭事件数（按严重等级分组）
    stmt = (
        select(Incident.severity, func.count(Incident.id))
        .where(Incident.status.in_(["open", "investigating", "mitigating"]))
        .group_by(Incident.severity)
    )
    result = await db.execute(stmt)
    for severity, count in result.all():
        metrics.append(
            {
                "name": "rpki_incidents_open_total",
                "value": count,
                "labels": {"severity": severity},
                "help": "未关闭事件数（按严重等级分组）",
                "type": "gauge",
            }
        )

    # BGP 公告总数（热数据）
    total_bgp = await db.scalar(select(func.count(BGPAnnouncement.id)))
    metrics.append(
        {
            "name": "rpki_bgp_announcements_total",
            "value": total_bgp or 0,
            "labels": {},
            "help": "BGP 公告总数（热数据）",
            "type": "gauge",
        }
    )

    # 导出时间戳
    metrics.append(
        {
            "name": "rpki_metrics_export_timestamp",
            "value": time.time(),
            "labels": {},
            "help": "指标导出时间戳",
            "type": "gauge",
        }
    )

    logger.info(
        "平台指标导出完成",
        metric_count=len(metrics),
        timestamp=now,
    )
    return metrics


__all__ = [
    "NMSAdapter",
    "export_metrics",
    "generate_grafana_dashboard",
    "push_to_prometheus",
    "query_nms_status",
]
