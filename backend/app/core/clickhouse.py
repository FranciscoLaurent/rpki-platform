"""ClickHouse 客户端服务。

提供全局 ClickHouse 客户端管理、查询服务以及建表 SQL 加载功能。
使用 clickhouse-connect 的 HTTP 客户端。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

import clickhouse_connect
from clickhouse_connect.driver.client import Client
from pandas import DataFrame
from structlog.stdlib import BoundLogger

from app.core.config import settings
from app.core.logging import get_logger

logger: BoundLogger = get_logger("app.clickhouse")

# SQL 文件目录
SQL_DIR = Path(__file__).parent / "sql"

# 全局 ClickHouse 客户端单例
_client: Client | None = None


def init_clickhouse() -> None:
    """初始化全局 ClickHouse 连接并测试连通性。

    在应用启动时调用，连接失败会记录日志并抛出异常。
    """
    global _client
    try:
        parsed = urlparse(settings.CLICKHOUSE_URL)
        _client = clickhouse_connect.get_client(
            host=parsed.hostname or "localhost",
            port=parsed.port or 8123,
            username=settings.CLICKHOUSE_USER,
            password=settings.CLICKHOUSE_PASSWORD,
            database=settings.CLICKHOUSE_DATABASE,
        )
        # 测试连接
        result = _client.query("SELECT 1")
        if result.result_rows[0][0] != 1:
            raise RuntimeError("ClickHouse 连接测试返回异常值")
        logger.info("ClickHouse 连接成功", url=settings.CLICKHOUSE_URL)
    except Exception as e:
        logger.error("ClickHouse 连接失败", url=settings.CLICKHOUSE_URL, error=str(e))
        _client = None
        raise


def close_clickhouse() -> None:
    """关闭全局 ClickHouse 连接。

    在应用关闭时调用，释放连接资源。
    """
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("ClickHouse 连接已关闭")


def get_clickhouse_client() -> Client:
    """获取全局 ClickHouse 客户端实例。

    Returns:
        ClickHouse 客户端

    Raises:
        RuntimeError: 客户端未初始化
    """
    if _client is None:
        raise RuntimeError("ClickHouse 客户端未初始化，请先调用 init_clickhouse()")
    return _client


class ClickHouseService:
    """ClickHouse 查询服务，封装常用查询与插入操作。"""

    def __init__(self, client: Client) -> None:
        self._client = client

    def execute(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> None:
        """执行查询（无返回结果），用于 DDL 或 DML 操作。

        Args:
            query: SQL 语句
            parameters: 查询参数（命名占位符）
        """
        self._client.command(query, parameters=parameters)

    def query_df(
        self,
        query: str,
        parameters: dict[str, Any] | None = None,
    ) -> DataFrame:
        """查询并返回 pandas DataFrame。

        Args:
            query: SQL 查询语句
            parameters: 查询参数

        Returns:
            包含查询结果的 DataFrame
        """
        return self._client.query_df(query, parameters=parameters)

    def insert(
        self,
        table: str,
        data: Sequence[Sequence[Any]],
        column_names: Sequence[str],
    ) -> None:
        """批量插入数据。

        Args:
            table: 目标表名
            data: 数据行列表（每行为一个值序列）
            column_names: 列名列表
        """
        self._client.insert(table, data, column_names=list(column_names))


def load_sql(filename: str) -> str:
    """加载 SQL 文件内容。

    Args:
        filename: SQL 文件名（位于 app/core/sql/ 目录下）

    Returns:
        SQL 文件文本内容
    """
    sql_path = SQL_DIR / filename
    return sql_path.read_text(encoding="utf-8")
