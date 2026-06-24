"""IPAM/CMDB/NetBox 集成适配器。

提供与 IP 地址管理系统（IPAM）、配置管理数据库（CMDB）及 NetBox 的
集成能力，支持查询 IP 前缀、ASN、设备、VLAN 等资产信息。
"""

from __future__ import annotations

import json
import time
from typing import Any

import httpx
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services.integrations.base import AdapterResult, BaseAdapter

logger: BoundLogger = get_logger("app.integrations.ipam")


class IPAMAdapter(BaseAdapter):
    """IPAM/CMDB/NetBox 集成适配器。

    支持的子类型：
    - ``netbox``: NetBox（REST API v2）
    - ``infoblox``: Infoblox
    - ``phpipam``: phpIPAM
    - ``generic``: 通用 IPAM（自定义 HTTP 接口）

    连接参数：
    - ``url``: 基础 URL（如 ``https://netbox.example.com/api``）
    - ``timeout``: 请求超时（秒，默认 10）
    - ``verify_tls``: 是否校验 TLS（默认 True）
    """

    async def test_connection(self) -> AdapterResult:
        """测试 IPAM 连接（查询状态接口）。"""
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(
                success=False,
                error_message="IPAM URL 未配置",
            )

        start = time.monotonic()
        try:
            # TODO: 实际生产环境应根据子类型调用不同的状态接口
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                response = await client.get(f"{base_url}/status", headers=headers)
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
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def query_prefix(self, prefix: str) -> AdapterResult:
        """查询前缀信息。

        Args:
            prefix: 网络前缀（如 ``1.1.1.0/24``）
        """
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(
                success=False,
                error_message="IPAM URL 未配置",
            )

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            # TODO: 实际生产环境应根据子类型构造不同的查询参数
            params = {"prefix": prefix}
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                response = await client.get(
                    f"{base_url}/ipam/prefixes/",
                    headers=headers,
                    params=params,
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
            return AdapterResult(
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def query_asn(self, asn: int) -> AdapterResult:
        """查询 ASN 信息。

        Args:
            asn: AS 号
        """
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(
                success=False,
                error_message="IPAM URL 未配置",
            )

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            # TODO: 实际生产环境应根据子类型构造不同的查询参数
            params = {"asn": asn}
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                response = await client.get(
                    f"{base_url}/ipam/asns/",
                    headers=headers,
                    params=params,
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
            return AdapterResult(
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def query_device(self, device_name: str) -> AdapterResult:
        """查询设备信息。

        Args:
            device_name: 设备名称
        """
        base_url = self._get_base_url()
        if not base_url:
            return AdapterResult(
                success=False,
                error_message="IPAM URL 未配置",
            )

        start = time.monotonic()
        try:
            headers = self._get_auth_headers()
            headers["Accept"] = "application/json"
            params = {"name": device_name}
            async with httpx.AsyncClient(
                timeout=self._get_timeout(),
                verify=self.connection_params.get("verify_tls", True),
            ) as client:
                response = await client.get(
                    f"{base_url}/dcim/devices/",
                    headers=headers,
                    params=params,
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
            return AdapterResult(
                success=False,
                error_message=str(e),
                latency_ms=latency_ms,
            )

    async def enrich_alert(self, alert_data: dict[str, Any]) -> dict[str, Any]:
        """用 IPAM 数据丰富告警信息。

        根据告警中的前缀与 ASN 查询 IPAM，补充资产归属、设备位置等信息。

        Args:
            alert_data: 告警数据

        Returns:
            丰富后的告警数据
        """
        enriched = dict(alert_data)
        enrichment: dict[str, Any] = {}

        prefix = alert_data.get("prefix")
        if prefix:
            result = await self.query_prefix(prefix)
            if result.success and result.data:
                enrichment["prefix_info"] = result.data

        origin_as = alert_data.get("origin_as")
        if origin_as:
            result = await self.query_asn(int(origin_as))
            if result.success and result.data:
                enrichment["asn_info"] = result.data

        if enrichment:
            enriched["ipam_enrichment"] = enrichment
        return enriched


# ──────────────────────────────────────────────
# 函数式接口
# ──────────────────────────────────────────────


async def sync_from_netbox(config: dict[str, Any]) -> dict[str, Any]:
    """从 NetBox 同步 IP 前缀与 VLAN。

    Args:
        config: NetBox 配置，需包含 ``url``、``token``，可选 ``timeout``、
            ``verify_tls``、``limit``。

    Returns:
        同步结果，包含 prefixes、vlans、synced_count 字段。
    """
    base_url = config.get("url", "").rstrip("/")
    token = config.get("token")
    if not base_url or not token:
        return {
            "success": False,
            "message": "NetBox URL 或 Token 未配置",
            "prefixes": [],
            "vlans": [],
        }

    headers = {
        "Authorization": f"Token {token}",
        "Accept": "application/json",
    }
    timeout = float(config.get("timeout", 30))
    verify_tls = config.get("verify_tls", True)
    limit = int(config.get("limit", 1000))

    prefixes: list[dict[str, Any]] = []
    vlans: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls) as client:
            # 同步前缀
            offset = 0
            while True:
                response = await client.get(
                    f"{base_url}/api/ipam/prefixes/",
                    headers=headers,
                    params={"limit": limit, "offset": offset},
                )
                if response.status_code >= 400:
                    logger.error(
                        "从 NetBox 同步前缀失败",
                        status_code=response.status_code,
                    )
                    break
                data = response.json()
                batch = data.get("results", [])
                prefixes.extend(batch)
                if not data.get("next"):
                    break
                offset += limit

            # 同步 VLAN
            offset = 0
            while True:
                response = await client.get(
                    f"{base_url}/api/ipam/vlans/",
                    headers=headers,
                    params={"limit": limit, "offset": offset},
                )
                if response.status_code >= 400:
                    logger.error(
                        "从 NetBox 同步 VLAN 失败",
                        status_code=response.status_code,
                    )
                    break
                data = response.json()
                batch = data.get("results", [])
                vlans.extend(batch)
                if not data.get("next"):
                    break
                offset += limit

        logger.info(
            "NetBox 同步完成",
            prefix_count=len(prefixes),
            vlan_count=len(vlans),
        )
        return {
            "success": True,
            "prefixes": prefixes,
            "vlans": vlans,
            "synced_count": len(prefixes) + len(vlans),
        }
    except Exception as e:
        logger.error("从 NetBox 同步异常", error=str(e))
        return {
            "success": False,
            "message": str(e),
            "prefixes": [],
            "vlans": [],
        }


async def sync_to_netbox(config: dict[str, Any], prefixes: list[dict[str, Any]]) -> dict[str, Any]:
    """推送前缀到 NetBox。

    Args:
        config: NetBox 配置，需包含 ``url``、``token``。
        prefixes: 要推送的前缀列表，每项需包含 ``prefix`` 字段。

    Returns:
        同步结果，包含 success_count、failure_count、errors 字段。
    """
    base_url = config.get("url", "").rstrip("/")
    token = config.get("token")
    if not base_url or not token:
        return {
            "success": False,
            "message": "NetBox URL 或 Token 未配置",
            "success_count": 0,
            "failure_count": 0,
        }

    headers = {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    timeout = float(config.get("timeout", 30))
    verify_tls = config.get("verify_tls", True)

    success_count = 0
    failure_count = 0
    errors: list[dict[str, Any]] = []

    try:
        async with httpx.AsyncClient(timeout=timeout, verify=verify_tls) as client:
            for prefix_data in prefixes:
                prefix = prefix_data.get("prefix")
                if not prefix:
                    continue
                try:
                    response = await client.post(
                        f"{base_url}/api/ipam/prefixes/",
                        headers=headers,
                        content=json.dumps(prefix_data, ensure_ascii=False, default=str),
                    )
                    if response.status_code < 400:
                        success_count += 1
                    else:
                        failure_count += 1
                        errors.append(
                            {
                                "prefix": prefix,
                                "status_code": response.status_code,
                                "error": response.text[:500],
                            }
                        )
                except Exception as e:
                    failure_count += 1
                    errors.append({"prefix": prefix, "error": str(e)})

        logger.info(
            "推送前缀到 NetBox 完成",
            success_count=success_count,
            failure_count=failure_count,
        )
        return {
            "success": failure_count == 0,
            "success_count": success_count,
            "failure_count": failure_count,
            "errors": errors,
        }
    except Exception as e:
        logger.error("推送到 NetBox 异常", error=str(e))
        return {
            "success": False,
            "message": str(e),
            "success_count": 0,
            "failure_count": len(prefixes),
            "errors": [],
        }


async def query_ipam(config: dict[str, Any], prefix: str) -> dict[str, Any]:
    """查询 IPAM 中前缀信息。

    Args:
        config: IPAM 配置，需包含 ``url``、``token``。
        prefix: 网络前缀。

    Returns:
        前缀信息。
    """
    adapter = IPAMAdapter(
        connection_params={
            "url": config.get("url"),
            "timeout": config.get("timeout", 10),
            "verify_tls": config.get("verify_tls", True),
        },
        auth_config={
            "type": "api_key",
            "header_name": "Authorization",
            "header_value": f"Token {config.get('token', '')}",
        },
    )
    result = await adapter.query_prefix(prefix)
    return {
        "success": result.success,
        "prefix": prefix,
        "data": result.data,
        "error": result.error_message,
    }


async def check_consistency(
    config: dict[str, Any], local_prefixes: list[dict[str, Any]]
) -> dict[str, Any]:
    """一致性检查。

    对比本地前缀与 IPAM 中的前缀，识别差异（仅本地有、仅 IPAM 有、属性不一致）。

    Args:
        config: IPAM 配置。
        local_prefixes: 本地前缀列表，每项需包含 ``prefix`` 字段。

    Returns:
        一致性检查结果，包含 only_local、only_ipam、mismatched 字段。
    """
    # 从 IPAM 同步前缀
    sync_result = await sync_from_netbox(config)
    if not sync_result.get("success"):
        return {
            "success": False,
            "message": sync_result.get("message", "无法从 IPAM 获取前缀"),
            "only_local": [],
            "only_ipam": [],
            "mismatched": [],
        }

    ipam_prefixes = sync_result.get("prefixes", [])
    # 构造 IPAM 前缀映射
    ipam_map: dict[str, dict[str, Any]] = {}
    for p in ipam_prefixes:
        prefix_str = p.get("prefix")
        if prefix_str:
            ipam_map[prefix_str] = p

    # 构造本地前缀映射
    local_map: dict[str, dict[str, Any]] = {}
    for p in local_prefixes:
        prefix_str = p.get("prefix") if isinstance(p, dict) else str(p)
        if prefix_str:
            local_map[prefix_str] = p if isinstance(p, dict) else {"prefix": p}

    # 识别差异
    only_local = [local_map[k] for k in local_map if k not in ipam_map]
    only_ipam = [ipam_map[k] for k in ipam_map if k not in local_map]
    mismatched: list[dict[str, Any]] = []
    for prefix_str in set(local_map) & set(ipam_map):
        local_p = local_map[prefix_str]
        ipam_p = ipam_map[prefix_str]
        # 比较状态字段
        local_status = local_p.get("status")
        ipam_status = ipam_p.get("status")
        if local_status and ipam_status and local_status != ipam_status:
            mismatched.append(
                {
                    "prefix": prefix_str,
                    "local_status": local_status,
                    "ipam_status": ipam_status,
                }
            )

    logger.info(
        "一致性检查完成",
        only_local=len(only_local),
        only_ipam=len(only_ipam),
        mismatched=len(mismatched),
    )
    return {
        "success": True,
        "only_local": only_local,
        "only_ipam": only_ipam,
        "mismatched": mismatched,
        "total_local": len(local_map),
        "total_ipam": len(ipam_map),
    }


__all__ = [
    "IPAMAdapter",
    "check_consistency",
    "query_ipam",
    "sync_from_netbox",
    "sync_to_netbox",
]
