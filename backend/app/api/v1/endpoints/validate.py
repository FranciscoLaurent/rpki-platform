"""统一验证入口 API 端点。

提供一站式路由前缀验证接口，整合 RPKI 验证状态、BGP 公告状态、
ROA/VRP 命中信息与 IRR 信息，返回综合验证结果。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permissions
from app.core.database import get_db
from app.models.user import User
from app.services import vrp_service

router = APIRouter()

# 验证权限码
VALIDATE_READ = "rpki:read"


@router.get("/prefix")
async def validate_prefix(
    prefix: str = Query(..., description="待验证的 IP 前缀（CIDR）"),
    origin_as: int = Query(..., description="起源 AS 号"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(VALIDATE_READ)),
) -> dict:
    """验证指定前缀的 RPKI 状态。

    需要 ``rpki:read`` 权限。返回前缀的 RPKI 验证状态（Valid/Invalid/NotFound）、
    匹配的 VRP/ROA 记录与验证原因。
    """
    result = await vrp_service.validate_bgp_announcement(
        db, prefix=prefix, origin_as=origin_as
    )
    return result.model_dump(mode="json")


@router.post("/batch")
async def validate_batch(
    prefixes: list[dict],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permissions(VALIDATE_READ)),
) -> list[dict]:
    """批量验证前缀的 RPKI 状态。

    需要 ``rpki:read`` 权限。请求体为列表，每项包含 ``prefix`` 与 ``origin_as``。
    """
    results: list[dict] = []
    for item in prefixes:
        prefix = item.get("prefix", "")
        origin_as = item.get("origin_as")
        if not prefix or origin_as is None:
            results.append(
                {"prefix": prefix, "error": "prefix 和 origin_as 不能为空"}
            )
            continue
        try:
            result = await vrp_service.validate_bgp_announcement(
                db, prefix=prefix, origin_as=origin_as
            )
            results.append(result.model_dump(mode="json"))
        except Exception as e:
            results.append({"prefix": prefix, "error": str(e)})
    return results


__all__ = ["router"]
