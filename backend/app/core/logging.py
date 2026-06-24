"""日志配置，基于 structlog 提供结构化日志。"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def setup_logging() -> structlog.stdlib.BoundLogger:
    """配置 structlog 结构化日志。

    开发环境使用人类可读格式，生产环境使用 JSON 格式。
    """
    # 共享的日志处理器配置
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.DEBUG:
        # 开发环境：彩色控制台输出
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        # 生产环境：JSON 格式
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 配置标准库 logging，使其与 structlog 协同
    logging.basicConfig(
        level=logging.DEBUG if settings.DEBUG else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )

    return structlog.get_logger("app")


def get_logger(name: str = "app") -> structlog.stdlib.BoundLogger:
    """获取结构化日志记录器。"""
    return structlog.get_logger(name)
