"""BGP 消息解析工具。

提供 BGP UPDATE 消息的解析功能，包括 AS_PATH、COMMUNITY、Large Community
以及各种 BGP 属性的解析。使用标准库 ``ipaddress`` 处理前缀。
"""

from __future__ import annotations

import ipaddress
import struct
from typing import Any

from app.core.logging import get_logger

logger = get_logger("app.bgp_parser")


# ──────────────────────────────────────────────
# BGP 属性类型常量
# ──────────────────────────────────────────────

# BGP 路径属性类型码（RFC 4271 及相关扩展）
BGP_ATTR_ORIGIN = 1
BGP_ATTR_AS_PATH = 2
BGP_ATTR_NEXT_HOP = 3
BGP_ATTR_MULTI_EXIT_DISC = 4
BGP_ATTR_LOCAL_PREF = 5
BGP_ATTR_ATOMIC_AGGREGATE = 6
BGP_ATTR_AGGREGATOR = 7
BGP_ATTR_COMMUNITIES = 8
BGP_ATTR_ORIGINATOR_ID = 9
BGP_ATTR_CLUSTER_LIST = 10
BGP_ATTR_MP_REACH_NLRI = 14
BGP_ATTR_MP_UNREACH_NLRI = 15
BGP_ATTR_EXTENDED_COMMUNITIES = 16
BGP_ATTR_AS4_PATH = 17
BGP_ATTR_AS4_AGGREGATOR = 18
BGP_ATTR_LARGE_COMMUNITIES = 32

# AS_PATH 段类型
AS_PATH_SEGMENT_AS_SET = 1
AS_PATH_SEGMENT_AS_SEQUENCE = 2
AS_PATH_SEGMENT_CONFED_AS_SET = 3
AS_PATH_SEGMENT_CONFED_AS_SEQUENCE = 4

# 地址族编号
AFI_IPV4 = 1
AFI_IPV6 = 2
SAFI_UNICAST = 1


class BGPParserError(Exception):
    """BGP 解析异常。"""


# ──────────────────────────────────────────────
# 前缀解析
# ──────────────────────────────────────────────


def parse_prefix(prefix_str: str) -> tuple[int, int, int]:
    """解析前缀字符串，返回地址族、前缀长度与网络地址信息。

    使用标准库 ``ipaddress`` 处理前缀。

    Args:
        prefix_str: 前缀字符串，如 ``192.168.1.0/24`` 或 ``2001:db8::/32``

    Returns:
        元组 ``(family, prefix_length, prefix_int)``：
        - family: 4 (IPv4) 或 6 (IPv6)
        - prefix_length: 前缀长度
        - prefix_int: 前缀地址的整数表示

    Raises:
        BGPParserError: 前缀格式无效
    """
    try:
        network = ipaddress.ip_network(prefix_str, strict=False)
    except ValueError as e:
        raise BGPParserError(f"无效的前缀格式: {prefix_str}") from e

    family = 6 if network.version == 6 else 4
    return family, network.prefixlen, int(network.network_address)


def get_prefix_family(prefix_str: str) -> int:
    """获取前缀的地址族。

    Args:
        prefix_str: 前缀字符串

    Returns:
        4 (IPv4) 或 6 (IPv6)
    """
    family, _, _ = parse_prefix(prefix_str)
    return family


def get_prefix_length(prefix_str: str) -> int:
    """获取前缀长度。

    Args:
        prefix_str: 前缀字符串

    Returns:
        前缀长度
    """
    _, length, _ = parse_prefix(prefix_str)
    return length


def normalize_prefix(prefix_str: str) -> str:
    """规范化前缀字符串。

    将前缀转换为网络地址形式，如 ``192.168.1.5/24`` → ``192.168.1.0/24``。

    Args:
        prefix_str: 前缀字符串

    Returns:
        规范化后的前缀字符串
    """
    network = ipaddress.ip_network(prefix_str, strict=False)
    return str(network)


# ──────────────────────────────────────────────
# AS_PATH 解析
# ──────────────────────────────────────────────


def parse_as_path(as_path_data: Any) -> list[int]:
    """解析 AS_PATH 属性。

    支持多种输入格式：
    - 字符串形式：``"123 456 789"`` 或 ``"123,456,789"``
    - 列表形式：``[123, 456, 789]``
    - 二进制形式：BGP AS_PATH 属性原始字节（RFC 4271）

    Args:
        as_path_data: AS_PATH 数据

    Returns:
        AS 号列表（按顺序）
    """
    if as_path_data is None:
        return []

    # 列表形式
    if isinstance(as_path_data, list):
        return [int(asn) for asn in as_path_data]

    # 字符串形式
    if isinstance(as_path_data, str):
        # 去除可能的 AS_PATH 段类型标记
        cleaned = as_path_data.strip()
        if not cleaned:
            return []
        # 支持空格、逗号分隔
        parts = cleaned.replace(",", " ").split()
        result: list[int] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                result.append(int(part))
            except ValueError:
                logger.warning("无法解析 AS 号", asn=part)
        return result

    # 二进制形式（BGP 原始字节）
    if isinstance(as_path_data, (bytes, bytearray)):
        return _parse_as_path_binary(bytes(as_path_data))

    raise BGPParserError(f"不支持的 AS_PATH 数据类型: {type(as_path_data)}")


def _parse_as_path_binary(data: bytes) -> list[int]:
    """解析二进制 AS_PATH 属性。

    AS_PATH 由多个段组成，每段包含段类型、段长度与 AS 号列表。
    AS 号可以是 2 字节（RFC 4271）或 4 字节（RFC 6793）。

    Args:
        data: AS_PATH 属性原始字节

    Returns:
        AS 号列表
    """
    asns: list[int] = []
    offset = 0

    while offset < len(data):
        if offset + 2 > len(data):
            break

        segment_type = data[offset]
        segment_length = data[offset + 1]
        offset += 2

        # 根据剩余数据长度判断是 2 字节还是 4 字节 AS
        # 4 字节 AS：每段数据长度 = segment_length * 4
        # 2 字节 AS：每段数据长度 = segment_length * 2
        remaining = len(data) - offset
        if remaining >= segment_length * 4:
            # 4 字节 AS
            for _ in range(segment_length):
                if offset + 4 > len(data):
                    break
                asn = struct.unpack("!I", data[offset : offset + 4])[0]
                asns.append(asn)
                offset += 4
        else:
            # 2 字节 AS
            for _ in range(segment_length):
                if offset + 2 > len(data):
                    break
                asn = struct.unpack("!H", data[offset : offset + 2])[0]
                asns.append(asn)
                offset += 2

    return asns


def format_as_path(asns: list[int]) -> str:
    """将 AS 号列表格式化为字符串。

    Args:
        asns: AS 号列表

    Returns:
        空格分隔的 AS_PATH 字符串
    """
    return " ".join(str(asn) for asn in asns)


# ──────────────────────────────────────────────
# Community 解析
# ──────────────────────────────────────────────


def parse_communities(communities_data: Any) -> list[str]:
    """解析 COMMUNITY 属性。

    支持多种输入格式：
    - 字符串形式：``"65001:100"`` 或 ``"65001:100 65001:200"``
    - 列表形式：``["65001:100", "65001:200"]``
    - 二进制形式：COMMUNITY 属性原始字节（RFC 1997）

    每个 Community 为 4 字节，高 2 字节为 AS 号，低 2 字节为自定义值。

    Args:
        communities_data: COMMUNITY 数据

    Returns:
        Community 字符串列表（格式 ``AS:VALUE``）
    """
    if communities_data is None:
        return []

    # 列表形式
    if isinstance(communities_data, list):
        return [str(c) for c in communities_data]

    # 字符串形式
    if isinstance(communities_data, str):
        cleaned = communities_data.strip()
        if not cleaned:
            return []
        return [c.strip() for c in cleaned.split() if c.strip()]

    # 二进制形式
    if isinstance(communities_data, (bytes, bytearray)):
        return _parse_communities_binary(bytes(communities_data))

    raise BGPParserError(f"不支持的 COMMUNITY 数据类型: {type(communities_data)}")


def _parse_communities_binary(data: bytes) -> list[str]:
    """解析二进制 COMMUNITY 属性。

    每个 Community 为 4 字节，格式为 ``AS:VALUE``。

    Args:
        data: COMMUNITY 属性原始字节

    Returns:
        Community 字符串列表
    """
    communities: list[str] = []
    offset = 0

    while offset + 4 <= len(data):
        as_num, value = struct.unpack("!HH", data[offset : offset + 4])
        communities.append(f"{as_num}:{value}")
        offset += 4

    return communities


# ──────────────────────────────────────────────
# Large Community 解析
# ──────────────────────────────────────────────


def parse_large_communities(data: Any) -> list[str]:
    """解析 Large Community 属性。

    支持多种输入格式：
    - 字符串形式：``"65001:100:200"``
    - 列表形式：``["65001:100:200"]``
    - 二进制形式：Large Community 属性原始字节（RFC 8092）

    每个 Large Community 为 12 字节：4 字节 Global Administrator、
    4 字节 Local Data Part 1、4 字节 Local Data Part 2。

    Args:
        data: Large Community 数据

    Returns:
        Large Community 字符串列表（格式 ``GLOBAL:LOCAL1:LOCAL2``）
    """
    if data is None:
        return []

    # 列表形式
    if isinstance(data, list):
        return [str(c) for c in data]

    # 字符串形式
    if isinstance(data, str):
        cleaned = data.strip()
        if not cleaned:
            return []
        return [c.strip() for c in cleaned.split() if c.strip()]

    # 二进制形式
    if isinstance(data, (bytes, bytearray)):
        return _parse_large_communities_binary(bytes(data))

    raise BGPParserError(f"不支持的 Large Community 数据类型: {type(data)}")


def _parse_large_communities_binary(data: bytes) -> list[str]:
    """解析二进制 Large Community 属性。

    每个 Large Community 为 12 字节。

    Args:
        data: Large Community 属性原始字节

    Returns:
        Large Community 字符串列表
    """
    communities: list[str] = []
    offset = 0

    while offset + 12 <= len(data):
        global_admin, local_data1, local_data2 = struct.unpack(
            "!III", data[offset : offset + 12]
        )
        communities.append(f"{global_admin}:{local_data1}:{local_data2}")
        offset += 12

    return communities


# ──────────────────────────────────────────────
# BGP 属性解析
# ──────────────────────────────────────────────


def parse_bgp_attributes(data: dict[str, Any] | bytes) -> dict[str, Any]:
    """解析所有 BGP 属性。

    支持字典形式（已解析的属性）或二进制形式（BGP 路径属性字节）。

    Args:
        data: BGP 属性数据

    Returns:
        包含已解析属性的字典，可能包含以下键：
        - ``origin``: ORIGIN 属性
        - ``as_path``: AS_PATH 列表
        - ``next_hop``: 下一跳地址
        - ``med``: MULTI_EXIT_DISC
        - ``local_pref``: LOCAL_PREF
        - ``communities``: Community 列表
        - ``large_communities``: Large Community 列表
        - ``atomic_aggregate``: 是否原子聚合
        - ``aggregator``: 聚合者
    """
    if isinstance(data, dict):
        return _parse_attributes_from_dict(data)

    if isinstance(data, (bytes, bytearray)):
        return _parse_attributes_from_binary(bytes(data))

    raise BGPParserError(f"不支持的 BGP 属性数据类型: {type(data)}")


def _parse_attributes_from_dict(data: dict[str, Any]) -> dict[str, Any]:
    """从字典解析 BGP 属性。

    Args:
        data: 属性字典

    Returns:
        规范化后的属性字典
    """
    result: dict[str, Any] = {}

    if "origin" in data:
        result["origin"] = data["origin"]

    if "as_path" in data:
        result["as_path"] = parse_as_path(data["as_path"])

    if "next_hop" in data:
        result["next_hop"] = str(data["next_hop"])

    if "med" in data:
        result["med"] = int(data["med"])

    if "local_pref" in data:
        result["local_pref"] = int(data["local_pref"])

    if "communities" in data:
        result["communities"] = parse_communities(data["communities"])

    if "large_communities" in data:
        result["large_communities"] = parse_large_communities(
            data["large_communities"]
        )

    if "atomic_aggregate" in data:
        result["atomic_aggregate"] = bool(data["atomic_aggregate"])

    if "aggregator" in data:
        result["aggregator"] = data["aggregator"]

    return result


def _parse_attributes_from_binary(data: bytes) -> dict[str, Any]:
    """从二进制数据解析 BGP 路径属性。

    每个属性由属性类型、标志与值组成（RFC 4271）。

    Args:
        data: 路径属性原始字节

    Returns:
        属性字典
    """
    result: dict[str, Any] = {}
    offset = 0

    while offset < len(data):
        if offset + 3 > len(data):
            break

        # 属性标志位
        flags = data[offset]
        attr_type = data[offset + 1]
        offset += 2

        # 扩展长度位（flags 第 4 位）
        extended_length = bool(flags & 0x10)

        if extended_length:
            if offset + 2 > len(data):
                break
            attr_length = struct.unpack("!H", data[offset : offset + 2])[0]
            offset += 2
        else:
            attr_length = data[offset]
            offset += 1

        if offset + attr_length > len(data):
            break

        attr_value = data[offset : offset + attr_length]
        offset += attr_length

        # 解析各属性
        try:
            if attr_type == BGP_ATTR_AS_PATH:
                result["as_path"] = _parse_as_path_binary(attr_value)
            elif attr_type == BGP_ATTR_AS4_PATH:
                # AS4_PATH 优先于 AS_PATH（4 字节 AS）
                result["as_path"] = _parse_as_path_binary(attr_value)
            elif attr_type == BGP_ATTR_NEXT_HOP:
                if len(attr_value) == 4:
                    result["next_hop"] = str(ipaddress.IPv4Address(attr_value))
            elif attr_type == BGP_ATTR_MULTI_EXIT_DISC:
                if len(attr_value) == 4:
                    result["med"] = struct.unpack("!I", attr_value)[0]
            elif attr_type == BGP_ATTR_LOCAL_PREF:
                if len(attr_value) == 4:
                    result["local_pref"] = struct.unpack("!I", attr_value)[0]
            elif attr_type == BGP_ATTR_ATOMIC_AGGREGATE:
                result["atomic_aggregate"] = True
            elif attr_type == BGP_ATTR_AGGREGATOR:
                if len(attr_value) == 8:
                    asn, _ = struct.unpack("!II", attr_value)
                    result["aggregator_as"] = asn
            elif attr_type == BGP_ATTR_COMMUNITIES:
                result["communities"] = _parse_communities_binary(attr_value)
            elif attr_type == BGP_ATTR_LARGE_COMMUNITIES:
                result["large_communities"] = _parse_large_communities_binary(
                    attr_value
                )
            elif attr_type == BGP_ATTR_ORIGIN:
                if len(attr_value) == 1:
                    result["origin"] = attr_value[0]
        except Exception as e:
            logger.warning(
                "解析 BGP 属性失败",
                attr_type=attr_type,
                error=str(e),
            )

    return result


# ──────────────────────────────────────────────
# BGP UPDATE 消息解析
# ──────────────────────────────────────────────


def parse_bgp_update(data: dict[str, Any]) -> dict[str, Any]:
    """解析 BGP UPDATE 消息。

    输入为字典形式的 BGP UPDATE 消息，包含撤销路由与公告路由。
    返回解析后的公告与撤路信息。

    输入字典可能包含以下键：
    - ``withdrawn_routes``: 撤销的路由列表
    - ``nlri``: 公告的网络层可达性信息
    - ``attributes`` / ``path_attributes``: BGP 路径属性
    - ``prefix``: 单个前缀（简化格式）

    Args:
        data: BGP UPDATE 消息字典

    Returns:
        包含 ``announcements`` 与 ``withdraws`` 列表的字典：
        - ``announcements``: 公告列表，每项包含 prefix、origin_as、as_path 等
        - ``withdraws``: 撤路列表，每项包含 prefix
    """
    result: dict[str, Any] = {"announcements": [], "withdraws": []}

    # 解析路径属性
    raw_attributes = data.get("attributes") or data.get("path_attributes") or {}
    attributes = parse_bgp_attributes(raw_attributes)

    # 解析撤销路由
    withdrawn_routes = data.get("withdrawn_routes", [])
    if isinstance(withdrawn_routes, list):
        for route in withdrawn_routes:
            prefix = _extract_prefix(route)
            if prefix:
                family, length, _ = parse_prefix(prefix)
                result["withdraws"].append(
                    {
                        "prefix": normalize_prefix(prefix),
                        "prefix_family": family,
                        "prefix_length": length,
                    }
                )

    # 解析公告路由（NLRI）
    nlri_list = data.get("nlri", [])
    if isinstance(nlri_list, list):
        for nlri in nlri_list:
            prefix = _extract_prefix(nlri)
            if prefix:
                announcement = _build_announcement(prefix, attributes, data)
                result["announcements"].append(announcement)

    # 处理简化格式（单个 prefix）
    if not result["announcements"] and not result["withdraws"]:
        prefix = data.get("prefix")
        if prefix:
            family, length, _ = parse_prefix(prefix)
            announcement = _build_announcement(prefix, attributes, data)
            result["announcements"].append(announcement)

    return result


def _extract_prefix(route: Any) -> str | None:
    """从路由数据中提取前缀字符串。

    Args:
        route: 路由数据（字符串或字典）

    Returns:
        前缀字符串，无法提取时返回 None
    """
    if isinstance(route, str):
        return route
    if isinstance(route, dict):
        return route.get("prefix") or route.get("nlri")
    return None


def _build_announcement(
    prefix: str,
    attributes: dict[str, Any],
    raw_data: dict[str, Any],
) -> dict[str, Any]:
    """构建公告字典。

    Args:
        prefix: 前缀字符串
        attributes: 已解析的 BGP 属性
        raw_data: 原始消息数据

    Returns:
        公告字典
    """
    family, length, _ = parse_prefix(prefix)

    # 提取 origin_as（AS_PATH 的最后一个 AS）
    as_path = attributes.get("as_path", [])
    origin_as = as_path[-1] if as_path else raw_data.get("origin_as")

    return {
        "prefix": normalize_prefix(prefix),
        "prefix_family": family,
        "prefix_length": length,
        "origin_as": int(origin_as) if origin_as is not None else None,
        "as_path": as_path,
        "next_hop": attributes.get("next_hop"),
        "communities": attributes.get("communities", []),
        "large_communities": attributes.get("large_communities", []),
        "med": attributes.get("med"),
        "local_pref": attributes.get("local_pref"),
        "address_family": family,
    }
