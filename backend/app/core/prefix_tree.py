"""前缀树（Patricia Trie）数据结构，用于高效前缀匹配。

支持 IPv4 与 IPv6 前缀的插入与查询，提供：
- ``lookup``: 查找覆盖查询前缀的所有节点（祖先链）
- ``find_more_specific``: 查找查询前缀下的更具体前缀（后代）
- ``find_less_specific``: 查找覆盖查询前缀的更不具体前缀（祖先）

用于 VRP 与 BGP 公告的高性能匹配。
"""

from __future__ import annotations

import ipaddress
from typing import Generic, TypeVar

from app.core.logging import get_logger

logger = get_logger("app.prefix_tree")

T = TypeVar("T")


class PrefixTreeNode(Generic[T]):
    """前缀树节点。

    每个节点对应一个二进制位，存储该路径上挂载的数据列表。
    """

    __slots__ = ("zero", "one", "data", "prefix")

    def __init__(self, prefix: str | None = None) -> None:
        """初始化节点。

        Args:
            prefix: 该节点对应的前缀字符串（叶子或挂载点）
        """
        # 0 分支与 1 分支
        self.zero: PrefixTreeNode[T] | None = None
        self.one: PrefixTreeNode[T] | None = None
        # 该节点挂载的数据列表
        self.data: list[T] = []
        # 该节点对应的前缀（如有）
        self.prefix: str | None = prefix


class PrefixTree(Generic[T]):
    """前缀树数据结构，支持 IPv4 与 IPv6 前缀的高效匹配。

    内部维护两棵独立的树：IPv4 与 IPv6，根据前缀族自动路由。
    每个前缀按其二进制位串逐位插入。
    """

    def __init__(self) -> None:
        """初始化两棵空树（IPv4 与 IPv6）。"""
        # IPv4 根节点（对应 0.0.0.0/0）
        self._root_v4: PrefixTreeNode[T] = PrefixTreeNode("0.0.0.0/0")
        # IPv6 根节点（对应 ::/0）
        self._root_v6: PrefixTreeNode[T] = PrefixTreeNode("::/0")
        # 节点总数（用于统计）
        self._size: int = 0

    @property
    def size(self) -> int:
        """返回树中挂载的数据条目数。"""
        return self._size

    def _get_bit_string(self, network: ipaddress.IPv4Network | ipaddress.IPv6Network) -> str:
        """获取前缀网络的二进制位串。

        Args:
            network: IP 网络

        Returns:
            二进制位串（长度等于前缀长度）
        """
        addr_int = int(network.network_address)
        prefix_len = network.prefixlen
        if prefix_len == 0:
            return ""
        # 将地址整数转为二进制字符串，取前 prefix_len 位
        # IPv4 地址最多 32 位，IPv6 最多 128 位
        total_bits = 32 if isinstance(network, ipaddress.IPv4Network) else 128
        binary = format(addr_int, f"0{total_bits}b")
        return binary[:prefix_len]

    def _get_root(
        self, network: ipaddress.IPv4Network | ipaddress.IPv6Network
    ) -> PrefixTreeNode[T]:
        """根据网络类型获取对应的根节点。"""
        if isinstance(network, ipaddress.IPv4Network):
            return self._root_v4
        return self._root_v6

    def insert(self, prefix: str, data: T) -> bool:
        """插入前缀与关联数据。

        Args:
            prefix: 前缀字符串，如 ``192.168.1.0/24``
            data: 关联的数据对象

        Returns:
            插入是否成功
        """
        try:
            network = ipaddress.ip_network(prefix, strict=False)
        except ValueError as e:
            logger.warning("无效的前缀，插入失败", prefix=prefix, error=str(e))
            return False

        root = self._get_root(network)
        bits = self._get_bit_string(network)
        node = root

        for bit in bits:
            if bit == "0":
                if node.zero is None:
                    node.zero = PrefixTreeNode()
                node = node.zero
            else:
                if node.one is None:
                    node.one = PrefixTreeNode()
                node = node.one

        # 在终端节点挂载数据与前缀
        if node.prefix is None:
            node.prefix = prefix
        node.data.append(data)
        self._size += 1
        return True

    def lookup(self, prefix: str) -> list[T]:
        """查找覆盖查询前缀的所有节点数据（祖先链）。

        从根节点开始，按查询前缀的二进制位逐位向下遍历，
        收集路径上所有挂载了数据的节点。

        Args:
            prefix: 查询前缀

        Returns:
            匹配的数据列表（按从更不具体到更具体的顺序）
        """
        try:
            network = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            return []

        root = self._get_root(network)
        bits = self._get_bit_string(network)
        node: PrefixTreeNode[T] | None = root
        results: list[T] = []

        # 根节点本身可能挂载数据（::/0 或 0.0.0.0/0）
        if node.data:
            results.extend(node.data)

        for bit in bits:
            if node is None:
                break
            node = node.zero if bit == "0" else node.one
            if node is not None and node.data:
                results.extend(node.data)

        return results

    def find_more_specific(self, prefix: str) -> list[T]:
        """查找查询前缀下的更具体前缀（后代节点）。

        先定位到查询前缀对应的节点，然后递归收集其所有子树的数据。

        Args:
            prefix: 查询前缀

        Returns:
            更具体前缀的数据列表
        """
        try:
            network = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            return []

        root = self._get_root(network)
        bits = self._get_bit_string(network)
        node: PrefixTreeNode[T] | None = root

        # 定位到查询前缀对应的节点
        for bit in bits:
            if node is None:
                return []
            node = node.zero if bit == "0" else node.one

        if node is None:
            return []

        # 递归收集子树所有数据（不包含该节点自身的数据）
        results: list[T] = []
        self._collect_subtree(node, results, include_self=False)
        return results

    def find_less_specific(self, prefix: str) -> list[T]:
        """查找覆盖查询前缀的更不具体前缀（祖先链）。

        与 ``lookup`` 等价，返回从根到查询前缀路径上所有挂载数据的节点。

        Args:
            prefix: 查询前缀

        Returns:
            更不具体前缀的数据列表（按从更不具体到更具体的顺序）
        """
        return self.lookup(prefix)

    def _collect_subtree(
        self,
        node: PrefixTreeNode[T],
        results: list[T],
        include_self: bool = True,
    ) -> None:
        """递归收集子树所有数据。

        Args:
            node: 起始节点
            results: 结果收集列表
            include_self: 是否包含起始节点自身的数据
        """
        if include_self and node.data:
            results.extend(node.data)
        if node.zero is not None:
            self._collect_subtree(node.zero, results, include_self=True)
        if node.one is not None:
            self._collect_subtree(node.one, results, include_self=True)

    def clear(self) -> None:
        """清空前缀树。"""
        self._root_v4 = PrefixTreeNode("0.0.0.0/0")
        self._root_v6 = PrefixTreeNode("::/0")
        self._size = 0

    def remove(self, prefix: str, data: T) -> bool:
        """从前缀树中移除指定前缀上的数据。

        注意：此操作不会立即回收空节点，仅从数据列表中移除。

        Args:
            prefix: 前缀字符串
            data: 待移除的数据对象

        Returns:
            是否成功移除
        """
        try:
            network = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            return False

        root = self._get_root(network)
        bits = self._get_bit_string(network)
        node: PrefixTreeNode[T] | None = root

        for bit in bits:
            if node is None:
                return False
            node = node.zero if bit == "0" else node.one

        if node is None or not node.data:
            return False

        try:
            node.data.remove(data)
            self._size -= 1
            return True
        except ValueError:
            return False


def build_vrp_prefix_tree(vrps: list[tuple[str, object]]) -> PrefixTree[object]:
    """从 VRP 列表构建前缀树。

    Args:
        vrps: VRP 元组列表，每个元组为 (prefix, vrp_data)

    Returns:
        构建好的前缀树
    """
    tree: PrefixTree[object] = PrefixTree()
    for prefix, vrp_data in vrps:
        tree.insert(prefix, vrp_data)
    return tree
