"""健康检查端点测试。"""

from __future__ import annotations

from httpx import AsyncClient


async def test_health_check(client: AsyncClient) -> None:
    """测试根路径健康检查端点返回 200 与正确状态。"""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


async def test_api_v1_health_check(client: AsyncClient) -> None:
    """测试 v1 API 健康检查端点。"""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
