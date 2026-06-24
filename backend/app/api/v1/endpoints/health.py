"""健康检查端点。

提供基础健康检查以及各基础设施组件（数据库、Redis、Kafka、ClickHouse）
的连通性检查。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.clickhouse import get_clickhouse_client
from app.core.kafka import Topics, get_kafka_producer
from app.core.redis import get_redis_client

router = APIRouter()


@router.get("")
@router.get("/")
async def health_check() -> dict[str, str]:
    """基础健康检查。"""
    return {"status": "ok"}


@router.get("/db")
async def db_health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """数据库连接健康检查。"""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
        return {"status": "ok", "component": "database"}
    except Exception as e:
        return {"status": "error", "component": "database", "detail": str(e)}


@router.get("/redis")
async def redis_health_check() -> dict[str, str]:
    """Redis 连接健康检查。"""
    try:
        client = get_redis_client()
        pong = await client.ping()
        if pong:
            return {"status": "ok", "component": "redis"}
        return {"status": "error", "component": "redis", "detail": "PING 返回 False"}
    except Exception as e:
        return {"status": "error", "component": "redis", "detail": str(e)}


@router.get("/kafka")
async def kafka_health_check() -> dict[str, str]:
    """Kafka 连接健康检查。

    通过查询主题分区信息验证生产者与 Kafka 集群的连通性。
    """
    try:
        producer = get_kafka_producer()
        # 查询 BGP_EVENTS 主题的分区信息以验证连接
        partitions = producer.partitions_for(Topics.BGP_EVENTS)
        if partitions is not None:
            return {"status": "ok", "component": "kafka"}
        return {
            "status": "error",
            "component": "kafka",
            "detail": "无法获取主题分区信息",
        }
    except Exception as e:
        return {"status": "error", "component": "kafka", "detail": str(e)}


@router.get("/clickhouse")
async def clickhouse_health_check() -> dict[str, str]:
    """ClickHouse 连接健康检查。"""
    try:
        client = get_clickhouse_client()
        result = client.query("SELECT 1")
        if result.result_rows[0][0] == 1:
            return {"status": "ok", "component": "clickhouse"}
        return {
            "status": "error",
            "component": "clickhouse",
            "detail": "查询返回异常值",
        }
    except Exception as e:
        return {"status": "error", "component": "clickhouse", "detail": str(e)}


@router.get("/all")
async def all_health_checks(
    db: AsyncSession = Depends(get_db),
) -> dict[str, dict[str, str]]:
    """汇总健康检查：一次性检查所有基础设施组件。"""
    results: dict[str, dict[str, str]] = {}

    # 数据库
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar_one()
        results["database"] = {"status": "ok"}
    except Exception as e:
        results["database"] = {"status": "error", "detail": str(e)}

    # Redis
    try:
        client = get_redis_client()
        await client.ping()
        results["redis"] = {"status": "ok"}
    except Exception as e:
        results["redis"] = {"status": "error", "detail": str(e)}

    # Kafka
    try:
        producer = get_kafka_producer()
        partitions = producer.partitions_for(Topics.BGP_EVENTS)
        if partitions is not None:
            results["kafka"] = {"status": "ok"}
        else:
            results["kafka"] = {"status": "error", "detail": "无法获取主题分区信息"}
    except Exception as e:
        results["kafka"] = {"status": "error", "detail": str(e)}

    # ClickHouse
    try:
        client = get_clickhouse_client()
        result = client.query("SELECT 1")
        if result.result_rows[0][0] == 1:
            results["clickhouse"] = {"status": "ok"}
        else:
            results["clickhouse"] = {"status": "error", "detail": "查询返回异常值"}
    except Exception as e:
        results["clickhouse"] = {"status": "error", "detail": str(e)}

    return results
