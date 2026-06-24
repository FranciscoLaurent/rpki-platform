"""路由泄露检测器。

结合上游/下游/对等关系（ASN 的 asn_type）与 AS_PATH 模式，检测 BGP 路由
泄露事件，包括客户向提供商泄露、提供商向客户泄露、对等间泄露等。
预留 ASPA 关系检查接口。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.asn import ASN
from app.models.bgp import BGPAnnouncement
from app.schemas.detection import RouteLeakDetectionResult

logger = get_logger("app.detection.route_leak")


# AS 关系类型常量
AS_TYPE_PROVIDER = "provider"
AS_TYPE_CUSTOMER = "customer"
AS_TYPE_PEER = "peer"
AS_TYPE_OWN = "own"
AS_TYPE_IXP = "ixp"
AS_TYPE_ROUTE_SERVER = "route_server"
AS_TYPE_SCRUBBER = "scrubber"


async def detect_route_leak(
    db: AsyncSession, announcement: BGPAnnouncement
) -> RouteLeakDetectionResult:
    """路由泄露检测。

    检测流程：
    1. 解析 AS_PATH，提取相邻 AS 对
    2. 查询每个 AS 的 asn_type
    3. 分析 AS_PATH 模式：
       - 客户向提供商泄露（customer → provider）
       - 提供商向客户泄露（provider → customer）
       - 对等间泄露（peer → peer）
    4. 预留 ASPA 关系检查接口

    Args:
        db: 异步数据库会话
        announcement: BGP 公告对象

    Returns:
        路由泄露检测结果
    """
    as_path = announcement.as_path

    if not as_path or len(as_path) < 2:
        return RouteLeakDetectionResult(
            alert_type="route_leak",
            severity="P3",
            description="AS_PATH 过短，无法判定路由泄露",
            is_detected=False,
            confidence=0.5,
        )

    # 查询 AS_PATH 中所有 AS 的元信息
    asn_meta = await _get_asn_metadata(db, as_path)

    # 分析 AS_PATH 模式
    leak_type, severity, description, leak_path = _analyze_path_pattern(as_path, asn_meta)

    is_leak = leak_type is not None

    # ASPA 关系检查（预留接口）
    aspa_result = await _check_aspa_relationship(db, as_path)
    if aspa_result.get("is_leak"):
        is_leak = True
        leak_type = leak_type or "aspa_violation"
        severity = "P1"
        description = f"ASPA 关系检查发现违规：{aspa_result.get('description')}"

    evidence: dict[str, Any] = {
        "prefix": announcement.prefix,
        "as_path": as_path,
        "asn_metadata": asn_meta,
        "leak_type": leak_type,
        "leak_path": leak_path,
        "aspa_check": aspa_result,
    }

    return RouteLeakDetectionResult(
        alert_type="route_leak",
        severity=severity,
        description=description,
        evidence=evidence,
        leak_type=leak_type,
        leak_path=leak_path,
        is_detected=is_leak,
        risk_score=0.0,
        confidence=0.75 if is_leak else 0.5,
    )


async def _get_asn_metadata(db: AsyncSession, asn_list: list[int]) -> dict[int, dict[str, Any]]:
    """查询 ASN 元信息。"""
    if not asn_list:
        return {}
    stmt = select(ASN).where(ASN.asn.in_(asn_list))
    result = await db.execute(stmt)
    asn_objects = list(result.scalars().all())
    return {
        asn.asn: {
            "asn": asn.asn,
            "name": asn.name,
            "asn_type": asn.asn_type,
            "relationship_tags": asn.relationship_tags or [],
        }
        for asn in asn_objects
    }


def _analyze_path_pattern(
    as_path: list[int],
    asn_meta: dict[int, dict[str, Any]],
) -> tuple[str | None, str, str, list[int]]:
    """分析 AS_PATH 模式，识别路由泄露类型。

    AS_PATH 中越靠右越接近 origin（被宣告网络），越靠左越接近观察点。
    泄露判定基于相邻 AS 对的关系类型组合。

    Returns:
        (leak_type, severity, description, leak_path) 四元组
    """
    # 遍历相邻 AS 对，识别异常关系
    for i in range(len(as_path) - 1):
        left_asn = as_path[i]
        right_asn = as_path[i + 1]
        left_meta = asn_meta.get(left_asn, {})
        right_meta = asn_meta.get(right_asn, {})
        left_type = left_meta.get("asn_type", "unknown")
        right_type = right_meta.get("asn_type", "unknown")

        # 客户向提供商泄露：客户 AS 向其提供商传播了不该传播的路由
        # 表现为：客户类型 AS 出现在路径中，且其后跟随 provider 类型 AS
        if left_type == AS_TYPE_CUSTOMER and right_type == AS_TYPE_PROVIDER:
            return (
                "customer_to_provider",
                "P1",
                f"客户 AS{left_asn} 向提供商 AS{right_asn} 泄露路由",
                [left_asn, right_asn],
            )

        # 提供商向客户泄露：路由从提供商流向客户（异常方向）
        if (
            left_type == AS_TYPE_PROVIDER
            and right_type == AS_TYPE_CUSTOMER
            and i < len(as_path) - 2  # 不是路径末端
        ):
            return (
                "provider_to_customer",
                "P1",
                f"提供商 AS{left_asn} 向客户 AS{right_asn} 泄露路由",
                [left_asn, right_asn],
            )

        # 对等间泄露：peer 关系的 AS 间互相传播路由
        if left_type == AS_TYPE_PEER and right_type == AS_TYPE_PEER:
            return (
                "peer_to_peer",
                "P2",
                f"对等 AS{left_asn} 与 AS{right_asn} 间泄露路由",
                [left_asn, right_asn],
            )

    return (
        None,
        "P3",
        "AS_PATH 模式正常，未检测到路由泄露",
        [],
    )


async def _check_aspa_relationship(db: AsyncSession, as_path: list[int]) -> dict[str, Any]:
    """ASPA（Autonomous System Provider Authorization）关系检查。

    ASPA 是 RPKI 中用于验证 AS_PATH 上游/下游关系的扩展。
    当前为预留接口，待 ASPA 数据接入后实现完整检查。

    Args:
        db: 异步数据库会话
        as_path: AS 路径列表

    Returns:
        检查结果字典
    """
    # TODO: 接入 ASPA 数据后实现完整检查
    # 1. 查询每个 AS 的 ASPA 记录（授权的 provider AS 集合）
    # 2. 验证 AS_PATH 中相邻 AS 对是否符合 ASPA 授权关系
    # 3. 识别上游/下游方向违规
    return {
        "is_leak": False,
        "description": "ASPA 检查为预留接口，未实现",
        "checked": False,
    }


__all__ = ["detect_route_leak"]
