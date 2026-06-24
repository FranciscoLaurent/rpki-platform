"""RIR/NIR/IRR/PeeringDB 外部信息关联。

提供与区域互联网注册管理机构（RIR）、国家互联网注册管理机构（NIR）、
互联网路由注册库（IRR）及 PeeringDB 的集成能力，支持查询前缀分配记录、
路由策略、ASN 信息，并用外部数据丰富本地前缀与 ASN 数据。
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.models.integration import ExternalDataCache
from app.services.integrations.base import AdapterResult, BaseAdapter

logger: BoundLogger = get_logger("app.integrations.external_info")


# RIR 统计数据源 URL
RIR_STAT_SOURCES = {
    "ripe": "https://stat.ripe.net",
    "apnic": "https://stats.apnic.net",
    "arin": "https://stat.arin.net",
    "lacnic": "https://stats.lacnic.net",
    "afrinic": "https://stats.afrinic.net",
}

# IRR 数据库查询源
IRR_SOURCES = {
    "ripe": "whois.ripe.net",
    "radb": "whois.radb.net",
    "nttcom": "whois.ntt.net",
    "level3": "whois.level3.net",
}

# PeeringDB API 基础 URL
PEERINGDB_API_BASE = "https://www.peeringdb.com/api"

# 缓存默认有效期（秒）
DEFAULT_CACHE_TTL = 86400  # 24 小时


class RIRAdapter(BaseAdapter):
    """RIR/NIR 集成适配器。

    支持查询 RIR（RIPE、APNIC、ARIN、LACNIC、AFRINIC）与 NIR（JPNIC、CNNIC 等）
    的前缀分配记录与 ASN 分配记录。

    连接参数：
    - ``url``: RIR 统计 API 基础 URL（可选，默认使用 RIPEstat）
    - ``timeout``: 请求超时（秒，默认 15）
    """

    async def test_connection(self) -> AdapterResult:
        """测试 RIR 数据源连通性。"""
        base_url = self._get_base_url() or RIR_STAT_SOURCES["ripe"]
        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self._get_timeout()
            ) as client:
                response = await client.get(f"{base_url}/data/wholesite/info.json")
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
            return AdapterResult(
                success=False, error_message=str(e), latency_ms=latency_ms
            )


# ──────────────────────────────────────────────
# 函数式接口
# ──────────────────────────────────────────────


async def query_rir(config: dict[str, Any], prefix: str) -> dict[str, Any]:
    """查询 RIR 分配记录。

    通过 RIPEstat Data API 查询前缀的分配信息，包括分配的 RIR、持有者、
    国家与状态。

    Args:
        config: RIR 配置，可选 ``url``、``timeout``、``api_key``。
        prefix: 网络前缀（如 ``1.1.1.0/24``）。

    Returns:
        RIR 分配记录，包含 rir、holder、country、status 等字段。
    """
    base_url = config.get("url", RIR_STAT_SOURCES["ripe"]).rstrip("/")
    timeout = float(config.get("timeout", 15))

    # 查询缓存
    cache_key = f"rir:prefix:{prefix}"
    cached = await _get_cached_data(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            # 使用 RIPEstat prefix-overview API
            response = await client.get(
                f"{base_url}/data/prefix-overview/data.json",
                params={"resource": prefix},
            )
        if response.status_code >= 400:
            logger.error(
                "查询 RIR 分配记录失败",
                prefix=prefix,
                status_code=response.status_code,
            )
            return {
                "success": False,
                "prefix": prefix,
                "message": f"查询失败，状态码 {response.status_code}",
            }
        data = response.json()
        # 解析 RIPEstat 响应
        blocks = data.get("data", {}).get("blocks", [])
        if not blocks:
            return {
                "success": True,
                "prefix": prefix,
                "rir": None,
                "holder": None,
                "country": None,
                "status": "not_found",
                "cached": False,
            }
        # 取第一个 block
        block = blocks[0]
        result = {
            "success": True,
            "prefix": prefix,
            "rir": block.get("rir", "unknown"),
            "holder": block.get("holder", ""),
            "country": block.get("country", ""),
            "status": block.get("status", "allocated"),
            "cached": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        # 写入缓存
        await _set_cached_data(cache_key, result, "rir")
        return result
    except Exception as e:
        logger.error("查询 RIR 分配记录异常", prefix=prefix, error=str(e))
        return {
            "success": False,
            "prefix": prefix,
            "message": str(e),
        }


async def query_irr(config: dict[str, Any], prefix: str) -> dict[str, Any]:
    """查询 IRR 路由策略。

    通过 IRR 数据库（如 RADB、RIPE）查询前缀的路由策略记录，
    包括起源 AS、维护者与描述。

    Args:
        config: IRR 配置，可选 ``source``（如 ripe/radb/nttcom）、``timeout``。
        prefix: 网络前缀。

    Returns:
        IRR 路由记录，包含 routes 列表。
    """
    source = config.get("source", "radb")
    timeout = float(config.get("timeout", 15))

    # 查询缓存
    cache_key = f"irr:prefix:{prefix}:{source}"
    cached = await _get_cached_data(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    # 使用 RIPEstat IRR-records API 作为统一查询入口
    base_url = config.get("url", RIR_STAT_SOURCES["ripe"]).rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                f"{base_url}/data/irr-records/data.json",
                params={"resource": prefix, "source": source},
            )
        if response.status_code >= 400:
            logger.error(
                "查询 IRR 路由记录失败",
                prefix=prefix,
                source=source,
                status_code=response.status_code,
            )
            return {
                "success": False,
                "prefix": prefix,
                "source": source,
                "message": f"查询失败，状态码 {response.status_code}",
            }
        data = response.json()
        records = data.get("data", {}).get("records", [])
        routes: list[dict[str, Any]] = []
        for record in records:
            for line in record.get("record_lines", []):
                routes.append({"raw": line})
        result = {
            "success": True,
            "prefix": prefix,
            "source": source,
            "routes": routes,
            "route_count": len(routes),
            "cached": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        await _set_cached_data(cache_key, result, "irr", source)
        return result
    except Exception as e:
        logger.error("查询 IRR 路由记录异常", prefix=prefix, error=str(e))
        return {
            "success": False,
            "prefix": prefix,
            "source": source,
            "message": str(e),
        }


async def query_peeringdb(asn: int) -> dict[str, Any]:
    """查询 PeeringDB ASN 信息。

    通过 PeeringDB API 查询 ASN 的网络信息，包括名称、网站、前缀数、
    流量级别、覆盖范围与国家。

    Args:
        asn: AS 号。

    Returns:
        PeeringDB 网络信息。
    """
    # 查询缓存
    cache_key = f"peeringdb:asn:{asn}"
    cached = await _get_cached_data(cache_key)
    if cached:
        cached["cached"] = True
        return cached

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                f"{PEERINGDB_API_BASE}/net",
                params={"asn": asn, "depth": 1},
            )
        if response.status_code >= 400:
            logger.error(
                "查询 PeeringDB 失败",
                asn=asn,
                status_code=response.status_code,
            )
            return {
                "success": False,
                "asn": asn,
                "message": f"查询失败，状态码 {response.status_code}",
            }
        data = response.json()
        networks = data.get("data", [])
        if not networks:
            return {
                "success": True,
                "asn": asn,
                "name": None,
                "message": "PeeringDB 中未找到该 ASN",
                "cached": False,
            }
        net = networks[0]
        result = {
            "success": True,
            "asn": asn,
            "name": net.get("name"),
            "aka": net.get("aka"),
            "website": net.get("website"),
            "info_type": net.get("info_type"),
            "info_prefixes4": net.get("info_prefixes4"),
            "info_prefixes6": net.get("info_prefixes6"),
            "info_traffic": net.get("info_traffic"),
            "info_scope": net.get("info_scope"),
            "country": net.get("country"),
            "cached": False,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
        await _set_cached_data(cache_key, result, "peeringdb")
        return result
    except Exception as e:
        logger.error("查询 PeeringDB 异常", asn=asn, error=str(e))
        return {
            "success": False,
            "asn": asn,
            "message": str(e),
        }


async def enrich_prefix(db: AsyncSession, prefix: str) -> dict[str, Any]:
    """用外部信息丰富前缀数据。

    综合查询 RIR 分配记录与 IRR 路由策略，丰富前缀的外部上下文信息。

    Args:
        db: 数据库会话（用于读写缓存）。
        prefix: 网络前缀。

    Returns:
        丰富后的前缀数据，包含 rir_info 与 irr_info 字段。
    """
    enriched: dict[str, Any] = {
        "prefix": prefix,
        "rir_info": None,
        "irr_info": None,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }

    # 并发查询 RIR 与 IRR
    rir_result, irr_result = await _gather(
        query_rir({}, prefix),
        query_irr({}, prefix),
    )

    if rir_result.get("success"):
        enriched["rir_info"] = {
            "rir": rir_result.get("rir"),
            "holder": rir_result.get("holder"),
            "country": rir_result.get("country"),
            "status": rir_result.get("status"),
        }

    if irr_result.get("success"):
        enriched["irr_info"] = {
            "source": irr_result.get("source"),
            "route_count": irr_result.get("route_count"),
            "routes": irr_result.get("routes", []),
        }

    logger.info(
        "前缀信息丰富完成",
        prefix=prefix,
        has_rir=enriched["rir_info"] is not None,
        has_irr=enriched["irr_info"] is not None,
    )
    return enriched


async def enrich_asn(db: AsyncSession, asn: int) -> dict[str, Any]:
    """用外部信息丰富 ASN 数据。

    综合查询 PeeringDB 与 RIR 分配记录，丰富 ASN 的外部上下文信息。

    Args:
        db: 数据库会话（用于读写缓存）。
        asn: AS 号。

    Returns:
        丰富后的 ASN 数据，包含 peeringdb_info 字段。
    """
    enriched: dict[str, Any] = {
        "asn": asn,
        "peeringdb_info": None,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
    }

    # 查询 PeeringDB
    peeringdb_result = await query_peeringdb(asn)
    if peeringdb_result.get("success"):
        enriched["peeringdb_info"] = {
            "name": peeringdb_result.get("name"),
            "aka": peeringdb_result.get("aka"),
            "website": peeringdb_result.get("website"),
            "info_type": peeringdb_result.get("info_type"),
            "info_prefixes4": peeringdb_result.get("info_prefixes4"),
            "info_prefixes6": peeringdb_result.get("info_prefixes6"),
            "info_traffic": peeringdb_result.get("info_traffic"),
            "info_scope": peeringdb_result.get("info_scope"),
            "country": peeringdb_result.get("country"),
        }

    logger.info(
        "ASN 信息丰富完成",
        asn=asn,
        has_peeringdb=enriched["peeringdb_info"] is not None,
    )
    return enriched


# ──────────────────────────────────────────────
# 缓存辅助函数
# ──────────────────────────────────────────────


async def _get_cached_data(cache_key: str) -> dict[str, Any] | None:
    """从数据库缓存中读取外部数据。

    使用 ExternalDataCache 表缓存外部查询结果，避免重复请求。
    """
    try:
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            stmt = select(ExternalDataCache).where(
                ExternalDataCache.cache_key == cache_key,
                ExternalDataCache.expires_at > datetime.now(timezone.utc),
            )
            result = await session.execute(stmt)
            cached = result.scalar_one_or_none()
            if cached and cached.cache_value:
                return dict(cached.cache_value)
    except Exception as e:
        logger.debug("读取缓存失败", cache_key=cache_key, error=str(e))
    return None


async def _set_cached_data(
    cache_key: str,
    data: dict[str, Any],
    source_type: str,
    source_subtype: str | None = None,
) -> None:
    """将外部数据写入数据库缓存。"""
    try:
        from app.core.database import async_session_factory

        async with async_session_factory() as session:
            # 检查是否已存在缓存记录
            stmt = select(ExternalDataCache).where(
                ExternalDataCache.cache_key == cache_key
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=DEFAULT_CACHE_TTL
            )
            if existing:
                existing.cache_value = data
                existing.expires_at = expires_at
                existing.source_type = source_type
                existing.source_subtype = source_subtype
            else:
                cache_entry = ExternalDataCache(
                    source_type=source_type,
                    source_subtype=source_subtype,
                    cache_key=cache_key,
                    cache_value=data,
                    expires_at=expires_at,
                )
                session.add(cache_entry)
            await session.commit()
    except Exception as e:
        logger.debug("写入缓存失败", cache_key=cache_key, error=str(e))


async def _gather(*coroutines: Any) -> tuple[Any, ...]:
    """并发执行多个协程并返回结果。"""
    import asyncio

    return await asyncio.gather(*coroutines, return_exceptions=False)


__all__ = [
    "RIRAdapter",
    "enrich_asn",
    "enrich_prefix",
    "query_irr",
    "query_peeringdb",
    "query_rir",
]
