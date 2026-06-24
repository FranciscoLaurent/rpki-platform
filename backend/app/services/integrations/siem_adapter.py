"""SIEM/SOC/ITSM 集成适配器。

提供与安全信息事件管理（SIEM）、安全运营中心（SOC）及 IT 服务管理（ITSM）
系统的集成能力，支持转发事件到 SIEM（Splunk/Elastic/QRadar）、创建与更新
ITSM 工单（ServiceNow/Jira）、查询 SIEM 历史事件。
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services.integrations.base import AdapterResult, BaseAdapter

logger: BoundLogger = get_logger("app.integrations.siem")


class SIEMAdapter(BaseAdapter):
    """SIEM/SOC 集成适配器。

    支持的子类型：
    - ``splunk``: Splunk（通过 HEC HTTP Event Collector）
    - ``elastic``: Elasticsearch（通过 _bulk API）
    - ``qradar``: IBM QRadar（通过 HTTP Forwarder）

    连接参数：
    - ``url``: SIEM 基础 URL
    - ``timeout``: 请求超时（秒，默认 15）
    - ``verify_tls``: 是否校验 TLS（默认 True）
    - ``index``: 索引名（Elasticsearch）
    """

    async def test_connection(self) -> AdapterResult:
        """测试 SIEM 连接。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="SIEM URL 未配置")

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                # 根据子类型调用不同的健康检查接口
                subtype = self.connection_params.get("subtype", "splunk")
                if subtype == "splunk":
                    response = await client.get(
                        f"{base_url}/services/collector/health",
                        headers=headers,
                    )
                elif subtype == "elastic":
                    response = await client.get(
                        f"{base_url}/_cluster/health",
                        headers=headers,
                    )
                else:
                    response = await client.get(f"{base_url}/api/help", headers=headers)
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            return AdapterResult(
                success=success,
                data=None,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(success=False, error_message=str(e), latency_ms=latency_ms)

    async def forward_event(self, incident: dict[str, Any]) -> AdapterResult:
        """转发事件到 SIEM。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="SIEM URL 未配置")

        subtype = self.connection_params.get("subtype", "splunk")
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                if subtype == "splunk":
                    # Splunk HEC 格式
                    payload = {
                        "time": time.time(),
                        "host": incident.get("host", "rpki-platform"),
                        "source": "rpki-platform",
                        "sourcetype": "rpki:incident",
                        "event": incident,
                    }
                    response = await client.post(
                        f"{base_url}/services/collector",
                        headers=headers,
                        content=json.dumps(payload, ensure_ascii=False, default=str),
                    )
                elif subtype == "elastic":
                    # Elasticsearch _bulk 格式
                    index = self.connection_params.get("index", "rpki-incidents")
                    action = {"index": {"_index": index}}
                    bulk_lines = [
                        json.dumps(action, ensure_ascii=False, default=str),
                        json.dumps(incident, ensure_ascii=False, default=str),
                    ]
                    response = await client.post(
                        f"{base_url}/_bulk",
                        headers=headers,
                        content="\n".join(bulk_lines) + "\n",
                    )
                else:
                    # QRadar 通用 HTTP Forwarder
                    response = await client.post(
                        f"{base_url}/api/events",
                        headers=headers,
                        content=json.dumps(incident, ensure_ascii=False, default=str),
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
            return AdapterResult(success=False, error_message=str(e), latency_ms=latency_ms)


class ITSMAdapter(BaseAdapter):
    """ITSM 工单系统集成适配器。

    支持的子类型：
    - ``servicenow``: ServiceNow（REST API）
    - ``jira``: Jira（REST API v3）
    - ``freshservice``: Freshservice

    连接参数：
    - ``url``: ITSM 基础 URL
    - ``timeout``: 请求超时（秒，默认 15）
    - ``verify_tls``: 是否校验 TLS（默认 True）
    - ``project``: 默认项目/工作空间
    """

    async def test_connection(self) -> AdapterResult:
        """测试 ITSM 连接。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="ITSM URL 未配置")

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            subtype = self.connection_params.get("subtype", "servicenow")
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                if subtype == "servicenow":
                    response = await client.get(
                        f"{base_url}/api/now/table/incident",
                        headers=headers,
                        params={"sysparm_limit": "1"},
                    )
                elif subtype == "jira":
                    response = await client.get(f"{base_url}/rest/api/3/myself", headers=headers)
                else:
                    response = await client.get(
                        f"{base_url}/api/v2/tickets",
                        headers=headers,
                        params={"per_page": "1"},
                    )
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            return AdapterResult(
                success=success,
                data=None,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(success=False, error_message=str(e), latency_ms=latency_ms)

    async def create_ticket(self, incident: dict[str, Any]) -> AdapterResult:
        """在 ITSM 创建工单。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="ITSM URL 未配置")

        subtype = self.connection_params.get("subtype", "servicenow")
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                if subtype == "servicenow":
                    payload = {
                        "short_description": incident.get("title", "RPKI 事件"),
                        "description": incident.get("description", ""),
                        "urgency": _severity_to_urgency(incident.get("severity", "P3")),
                        "category": "network",
                        "subcategory": "rpki_security",
                    }
                    response = await client.post(
                        f"{base_url}/api/now/table/incident",
                        headers=headers,
                        content=json.dumps(payload, ensure_ascii=False, default=str),
                    )
                elif subtype == "jira":
                    project = self.connection_params.get("project", incident.get("project", "RPKI"))
                    payload = {
                        "fields": {
                            "project": {"key": project},
                            "summary": incident.get("title", "RPKI 事件"),
                            "description": incident.get("description", ""),
                            "issuetype": {"name": "Incident"},
                            "priority": {
                                "name": _severity_to_jira_priority(incident.get("severity", "P3"))
                            },
                            "labels": ["rpki", "security"],
                        }
                    }
                    response = await client.post(
                        f"{base_url}/rest/api/3/issue",
                        headers=headers,
                        content=json.dumps(payload, ensure_ascii=False, default=str),
                    )
                else:
                    # Freshservice
                    payload = {
                        "subject": incident.get("title", "RPKI 事件"),
                        "description": incident.get("description", ""),
                        "priority": _severity_to_freshservice_priority(
                            incident.get("severity", "P3")
                        ),
                        "category": "Network",
                        "sub_category": "Security",
                    }
                    response = await client.post(
                        f"{base_url}/api/v2/tickets",
                        headers=headers,
                        content=json.dumps(payload, ensure_ascii=False, default=str),
                    )
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            data = response.json() if success else None
            return AdapterResult(
                success=success,
                data=data,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(success=False, error_message=str(e), latency_ms=latency_ms)

    async def update_ticket(self, ticket_id: str, update: dict[str, Any]) -> AdapterResult:
        """更新 ITSM 工单。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(success=False, error_message="ITSM URL 未配置")

        subtype = self.connection_params.get("subtype", "servicenow")
        headers = self._get_auth_headers()
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                if subtype == "servicenow":
                    response = await client.patch(
                        f"{base_url}/api/now/table/incident/{ticket_id}",
                        headers=headers,
                        content=json.dumps(update, ensure_ascii=False, default=str),
                    )
                elif subtype == "jira":
                    payload = {"fields": update}
                    response = await client.put(
                        f"{base_url}/rest/api/3/issue/{ticket_id}",
                        headers=headers,
                        content=json.dumps(payload, ensure_ascii=False, default=str),
                    )
                else:
                    response = await client.put(
                        f"{base_url}/api/v2/tickets/{ticket_id}",
                        headers=headers,
                        content=json.dumps(update, ensure_ascii=False, default=str),
                    )
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            return AdapterResult(
                success=success,
                data=None,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(success=False, error_message=str(e), latency_ms=latency_ms)


# ──────────────────────────────────────────────
# 函数式接口
# ──────────────────────────────────────────────


async def forward_to_siem(config: dict[str, Any], incident: dict[str, Any]) -> bool:
    """转发事件到 SIEM（Splunk/Elastic/QRadar）。

    Args:
        config: SIEM 配置，需包含 ``url``、``subtype``，可选 ``token``、
            ``username``、``password``、``index``、``timeout``、``verify_tls``。
        incident: 事件数据。

    Returns:
        是否转发成功。
    """
    adapter = SIEMAdapter(
        connection_params={
            "url": config.get("url"),
            "subtype": config.get("subtype", "splunk"),
            "timeout": config.get("timeout", 15),
            "verify_tls": config.get("verify_tls", True),
            "index": config.get("index"),
        },
        auth_config=(
            {
                "type": "bearer",
                "token": config.get("token", ""),
            }
            if config.get("token")
            else {
                "type": "basic",
                "username": config.get("username", ""),
                "password": config.get("password", ""),
            }
        ),
    )
    result = await adapter.forward_event(incident)
    if not result.success:
        logger.error(
            "转发事件到 SIEM 失败",
            url=config.get("url"),
            error=result.error_message,
        )
    return result.success


async def create_itsm_ticket(config: dict[str, Any], incident: dict[str, Any]) -> dict[str, Any]:
    """在 ITSM 创建工单（ServiceNow/Jira/Freshservice）。

    Args:
        config: ITSM 配置，需包含 ``url``、``subtype``，可选 ``token``、
            ``username``、``password``、``project``、``timeout``。
        incident: 事件数据。

    Returns:
        创建结果，包含 success、ticket_id、message 字段。
    """
    adapter = ITSMAdapter(
        connection_params={
            "url": config.get("url"),
            "subtype": config.get("subtype", "servicenow"),
            "timeout": config.get("timeout", 15),
            "verify_tls": config.get("verify_tls", True),
            "project": config.get("project"),
        },
        auth_config=(
            {
                "type": "bearer",
                "token": config.get("token", ""),
            }
            if config.get("token")
            else {
                "type": "basic",
                "username": config.get("username", ""),
                "password": config.get("password", ""),
            }
        ),
    )
    result = await adapter.create_ticket(incident)
    if not result.success:
        logger.error(
            "创建 ITSM 工单失败",
            url=config.get("url"),
            error=result.error_message,
        )
        return {
            "success": False,
            "ticket_id": None,
            "message": result.error_message or "创建工单失败",
        }

    # 从响应中提取工单 ID
    ticket_id = None
    if result.data:
        subtype = config.get("subtype", "servicenow")
        if subtype == "servicenow":
            ticket_id = result.data.get("result", {}).get("sys_id")
        elif subtype == "jira":
            ticket_id = result.data.get("key")
        else:
            ticket_id = str(result.data.get("id", ""))

    return {
        "success": True,
        "ticket_id": ticket_id,
        "message": "工单创建成功",
        "details": result.data,
    }


async def update_itsm_ticket(
    config: dict[str, Any], ticket_id: str, update: dict[str, Any]
) -> bool:
    """更新 ITSM 工单。

    Args:
        config: ITSM 配置。
        ticket_id: 工单 ID。
        update: 更新内容。

    Returns:
        是否更新成功。
    """
    adapter = ITSMAdapter(
        connection_params={
            "url": config.get("url"),
            "subtype": config.get("subtype", "servicenow"),
            "timeout": config.get("timeout", 15),
            "verify_tls": config.get("verify_tls", True),
        },
        auth_config=(
            {
                "type": "bearer",
                "token": config.get("token", ""),
            }
            if config.get("token")
            else {
                "type": "basic",
                "username": config.get("username", ""),
                "password": config.get("password", ""),
            }
        ),
    )
    result = await adapter.update_ticket(ticket_id, update)
    if not result.success:
        logger.error(
            "更新 ITSM 工单失败",
            ticket_id=ticket_id,
            error=result.error_message,
        )
    return result.success


async def query_siem_events(config: dict[str, Any], query: dict[str, Any]) -> list[dict[str, Any]]:
    """查询 SIEM 历史事件。

    Args:
        config: SIEM 配置。
        query: 查询条件，包含 ``query``（搜索语句）、``start_time``、
            ``end_time``、``limit`` 等字段。

    Returns:
        事件列表。
    """
    base_url = config.get("url", "").rstrip("/")
    if not base_url:
        logger.error("查询 SIEM 事件失败：URL 未配置")
        return []

    subtype = config.get("subtype", "splunk")
    headers: dict[str, str] = {"Accept": "application/json"}
    token = config.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    else:
        import base64

        username = config.get("username", "")
        password = config.get("password", "")
        credentials = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        headers["Authorization"] = f"Basic {credentials}"

    timeout = float(config.get("timeout", 15))
    verify_tls = config.get("verify_tls", True)
    limit = int(query.get("limit", 50))
    search_query = query.get("query", "*")
    start_time = query.get("start_time")
    end_time = query.get("end_time")

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls) as client:
            if subtype == "splunk":
                # Splunk 搜索 API
                params = {
                    "search": f"search {search_query}",
                    "count": limit,
                    "output_mode": "json",
                }
                if start_time:
                    params["earliest_time"] = start_time
                if end_time:
                    params["latest_time"] = end_time
                response = await client.post(
                    f"{base_url}/services/search/jobs/export",
                    headers=headers,
                    data=params,
                )
                if response.status_code < 400:
                    # Splunk export 返回多行 JSON
                    events: list[dict[str, Any]] = []
                    for line in response.text.splitlines():
                        if line.strip():
                            try:
                                events.append(json.loads(line).get("result", {}))
                            except json.JSONDecodeError:
                                continue
                    return events
            elif subtype == "elastic":
                # Elasticsearch _search
                index = config.get("index", "rpki-*")
                body: dict[str, Any] = {
                    "query": {"query_string": {"query": search_query}},
                    "size": limit,
                    "sort": [{"@timestamp": {"order": "desc"}}],
                }
                if start_time or end_time:
                    range_filter: dict[str, Any] = {}
                    if start_time:
                        range_filter["gte"] = start_time
                    if end_time:
                        range_filter["lte"] = end_time
                    body["query"] = {
                        "bool": {
                            "must": [body["query"]],
                            "filter": [{"range": {"@timestamp": range_filter}}],
                        }
                    }
                response = await client.post(
                    f"{base_url}/{index}/_search",
                    headers=headers,
                    content=json.dumps(body, ensure_ascii=False, default=str),
                )
                if response.status_code < 400:
                    hits = response.json().get("hits", {}).get("hits", [])
                    return [hit.get("_source", {}) for hit in hits]
            else:
                # QRadar 通用查询
                params = {"filter": search_query, "range": f"0-{limit}"}
                response = await client.get(
                    f"{base_url}/api/siem/events",
                    headers=headers,
                    params=params,
                )
                if response.status_code < 400:
                    return (
                        response.json() if isinstance(response.json(), list) else [response.json()]
                    )

            logger.error(
                "查询 SIEM 事件失败",
                status_code=response.status_code,
                body=response.text[:500],
            )
            return []
    except Exception as e:
        logger.error("查询 SIEM 事件异常", error=str(e))
        return []


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _severity_to_urgency(severity: str) -> str:
    """将平台严重等级映射为 ServiceNow 紧急度。"""
    mapping = {
        "P0": "1",
        "P1": "1",
        "P2": "2",
        "P3": "3",
        "P4": "3",
    }
    return mapping.get(severity, "3")


def _severity_to_jira_priority(severity: str) -> str:
    """将平台严重等级映射为 Jira 优先级。"""
    mapping = {
        "P0": "Highest",
        "P1": "Highest",
        "P2": "High",
        "P3": "Medium",
        "P4": "Low",
    }
    return mapping.get(severity, "Medium")


def _severity_to_freshservice_priority(severity: str) -> int:
    """将平台严重等级映射为 Freshservice 优先级。"""
    mapping = {
        "P0": 1,
        "P1": 1,
        "P2": 2,
        "P3": 3,
        "P4": 4,
    }
    return mapping.get(severity, 3)


__all__ = [
    "ITSMAdapter",
    "SIEMAdapter",
    "create_itsm_ticket",
    "forward_to_siem",
    "query_siem_events",
    "update_itsm_ticket",
]
