"""RIPEstat API 客户端。

封装 RIPEstat Data API 的常用查询接口，提供 AS 概览、公告前缀、
前缀概览与 ROA 数据查询能力。

参考文档：
- RIPEstat Data API: https://stat.ripe.net/docs/data_api
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

import httpx
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger

logger: BoundLogger = get_logger("app.ripestat_client")


@dataclass
class ASOverview:
    """AS 概览信息。"""

    asn: int
    holder: str
    announced: bool
    block_resource: str  # 如 "13312-15359"
    block_desc: str
    block_name: str


@dataclass
class AnnouncedPrefix:
    """AS 公告的前缀。"""

    prefix: str
    starttime: str | None
    endtime: str | None


@dataclass
class PrefixOverview:
    """前缀概览（origin AS）。"""

    prefix: str
    announced: bool
    asns: list[tuple[int, str]]  # [(asn, holder), ...]


@dataclass
class ROARecord:
    """ROA 记录。"""

    asn: int
    prefix: str
    max_length: int
    trust_anchor: str  # "ARIN", "RIPE", "APNIC", "LACNIC", "AFRINIC"


class RIPEstatClient:
    """RIPEstat API 客户端。

    封装 RIPEstat Data API 的常用查询，内置速率限制、重试机制与结构化日志。

    Note:
        RIPEstat 建议每秒最多 1 个请求，客户端在请求间自动间隔 1 秒。
    """

    BASE_URL = "https://stat.ripe.net/data"

    def __init__(self, timeout: int = 30, max_retries: int = 3) -> None:
        """初始化 RIPEstat 客户端。

        Args:
            timeout: 单次请求超时（秒）。
            max_retries: 失败重试次数上限（指数退避 1s, 2s, 4s）。
        """
        self._timeout = timeout
        self._max_retries = max_retries
        self._last_request_time: float = 0.0

    async def get_as_overview(self, asn: int) -> ASOverview:
        """获取 AS 概览信息。

        Args:
            asn: AS 号。

        Returns:
            AS 概览数据对象。

        Raises:
            ValueError: 请求失败或响应状态非 ok。
        """
        data = await self._request("as-overview", resource=f"AS{asn}")
        block = data.get("block") or {}
        return ASOverview(
            asn=int(data.get("resource", asn)),
            holder=data.get("holder") or "",
            announced=bool(data.get("announced", False)),
            block_resource=block.get("resource") or "",
            block_desc=block.get("desc") or "",
            block_name=block.get("name") or "",
        )

    async def get_announced_prefixes(self, asn: int) -> list[AnnouncedPrefix]:
        """获取 AS 公告的前缀列表。

        Args:
            asn: AS 号。

        Returns:
            公告前缀列表。

        Raises:
            ValueError: 请求失败或响应状态非 ok。
        """
        data = await self._request("announced-prefixes", resource=f"AS{asn}")
        prefixes: list[AnnouncedPrefix] = []
        for item in data.get("prefixes") or []:
            timelines = item.get("timelines") or []
            starttime: str | None = None
            endtime: str | None = None
            if timelines:
                first = timelines[0]
                starttime = first.get("starttime")
                endtime = first.get("endtime")
            prefixes.append(
                AnnouncedPrefix(
                    prefix=item.get("prefix") or "",
                    starttime=starttime,
                    endtime=endtime,
                )
            )
        return prefixes

    async def get_prefix_overview(self, prefix: str) -> PrefixOverview:
        """获取前缀概览（origin AS）。

        Args:
            prefix: 网络前缀（如 ``8.8.8.0/24``）。

        Returns:
            前缀概览数据对象。

        Raises:
            ValueError: 请求失败或响应状态非 ok。
        """
        data = await self._request("prefix-overview", resource=prefix)
        asns: list[tuple[int, str]] = []
        for entry in data.get("asns") or []:
            asn_value = entry.get("asn")
            if asn_value is None:
                continue
            asns.append((int(asn_value), entry.get("holder") or ""))
        return PrefixOverview(
            prefix=data.get("resource") or prefix,
            announced=bool(data.get("announced", False)),
            asns=asns,
        )

    async def get_roas_for_asn(self, asn: int) -> list[ROARecord]:
        """获取 AS 的 ROA 列表。

        Args:
            asn: AS 号。

        Returns:
            ROA 记录列表。

        Raises:
            ValueError: 请求失败或响应状态非 ok。
        """
        data = await self._request("rpki-roas", resource=f"AS{asn}")
        roas: list[ROARecord] = []
        for item in data.get("roas") or []:
            asn_value = item.get("asn")
            if asn_value is None:
                continue
            roas.append(
                ROARecord(
                    asn=int(asn_value),
                    prefix=item.get("prefix") or "",
                    max_length=int(item.get("maxLength") or 0),
                    trust_anchor=item.get("ta") or "",
                )
            )
        return roas

    async def _request(self, endpoint: str, **params: Any) -> dict[str, Any]:
        """发送 GET 请求并解析响应。

        内置速率限制（请求间间隔 1 秒）与指数退避重试。

        Args:
            endpoint: RIPEstat 数据接口名称（如 ``as-overview``）。
            **params: 查询参数。

        Returns:
            响应中 ``data`` 字段的内容。

        Raises:
            ValueError: HTTP 4xx、JSON 解析失败、响应状态非 ok 或重试耗尽。
        """
        url = f"{self.BASE_URL}/{endpoint}/data.json"
        await self._rate_limit()

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                logger.info(
                    "RIPEstat 请求",
                    endpoint=endpoint,
                    params=params,
                    attempt=attempt + 1,
                )
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as e:
                # 网络超时或传输错误：重试
                last_error = e
                if attempt >= self._max_retries:
                    break
                await self._sleep_backoff(attempt, endpoint, e)
                continue

            # HTTP 4xx：直接抛出，不重试
            if 400 <= response.status_code < 500:
                raise ValueError(
                    f"RIPEstat 请求失败 {endpoint}：HTTP {response.status_code}"
                )

            # HTTP 5xx：重试
            if response.status_code >= 500:
                last_error = RuntimeError(f"HTTP {response.status_code}")
                if attempt >= self._max_retries:
                    break
                await self._sleep_backoff(attempt, endpoint, last_error)
                continue

            # JSON 解析
            try:
                payload = response.json()
            except Exception as e:
                raise ValueError(
                    f"RIPEstat 响应 JSON 解析失败 {endpoint}：{e}"
                ) from e

            # 检查状态
            status = payload.get("status")
            if status != "ok":
                messages = payload.get("messages") or []
                raise ValueError(
                    f"RIPEstat 响应状态非 ok {endpoint}："
                    f"status={status}, messages={messages}"
                )

            data = payload.get("data") or {}
            logger.info(
                "RIPEstat 响应成功",
                endpoint=endpoint,
                status_code=response.status_code,
            )
            return data

        raise ValueError(
            f"RIPEstat 请求失败 {endpoint}："
            f"重试 {self._max_retries} 次后仍失败：{last_error}"
        )

    async def _sleep_backoff(
        self, attempt: int, endpoint: str, error: Exception
    ) -> None:
        """指数退避等待。"""
        backoff = 2 ** attempt  # 1s, 2s, 4s
        logger.warning(
            "RIPEstat 请求失败，准备重试",
            endpoint=endpoint,
            attempt=attempt + 1,
            backoff=backoff,
            error=str(error),
        )
        await asyncio.sleep(backoff)

    async def _rate_limit(self) -> None:
        """速率限制：确保请求间至少间隔 1 秒。"""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if self._last_request_time > 0 and elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        self._last_request_time = time.monotonic()


__all__ = [
    "ASOverview",
    "AnnouncedPrefix",
    "PrefixOverview",
    "ROARecord",
    "RIPEstatClient",
]
