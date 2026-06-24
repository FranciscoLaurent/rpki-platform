"""FastAPI 应用入口。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.clickhouse import close_clickhouse, init_clickhouse
from app.core.config import settings
from app.core.init_data import init_system_data
from app.core.kafka import close_kafka_producer, init_kafka_producer
from app.core.logging import setup_logging
from app.core.redis import close_redis, init_redis
from app.middleware.audit import AuditMiddleware
from app.middleware.ip_whitelist import IPWhitelistMiddleware
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期管理：启动与关闭事件。

    启动时依次初始化 Redis、Kafka、ClickHouse 连接；
    关闭时按逆序清理连接。任一组件初始化失败仅记录警告，
    不阻止应用启动（降级运行）。
    """
    logger = setup_logging()
    logger.info(
        "应用启动",
        app_name=settings.APP_NAME,
        debug=settings.DEBUG,
    )

    # 初始化 Redis（异步）
    try:
        await init_redis()
    except Exception:
        logger.warning("Redis 初始化失败，应用将以降级模式继续启动")

    # 初始化 Kafka 生产者（同步操作放入线程池避免阻塞事件循环）
    try:
        await asyncio.to_thread(init_kafka_producer)
    except Exception:
        logger.warning("Kafka 生产者初始化失败，应用将以降级模式继续启动")

    # 初始化 ClickHouse（同步操作放入线程池）
    try:
        await asyncio.to_thread(init_clickhouse)
    except Exception:
        logger.warning("ClickHouse 初始化失败，应用将以降级模式继续启动")

    # 初始化系统数据（权限、角色、超级管理员）
    try:
        await init_system_data()
    except Exception as e:
        logger.warning("系统数据初始化跳过（数据库可能未就绪）", error=str(e))

    yield

    # 关闭时清理连接（逆序）
    await close_redis()
    await asyncio.to_thread(close_kafka_producer)
    await asyncio.to_thread(close_clickhouse)

    logger.info("应用关闭")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    app = FastAPI(
        title="RPKI 网络安全管理平台 API",
        description="企业级 RPKI 网络安全管理平台后端服务",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # CORS 中间件配置
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # IP 白名单中间件（在限流之前执行，避免被限流前先过滤非法 IP）
    app.add_middleware(IPWhitelistMiddleware)

    # 限流中间件（按客户端 IP 或 API Key 限流）
    app.add_middleware(RateLimitMiddleware)

    # 审计中间件（记录所有 API 请求）
    app.add_middleware(AuditMiddleware)

    # 注册 v1 路由
    app.include_router(api_router, prefix="/api/v1")

    # 根路径健康检查
    @app.get("/health", tags=["健康检查"])
    async def health_check() -> dict[str, str]:
        """健康检查端点。"""
        return {"status": "ok"}

    return app


# 创建应用实例供 uvicorn 使用
app = create_app()
