"""前缀树（Patricia Trie）匹配测试。

覆盖前缀树的插入、查找覆盖前缀、精确匹配、最长前缀匹配、
IPv4/IPv6 支持、删除与遍历等核心能力。
"""

from __future__ import annotations

import pytest

from app.core.prefix_tree import PrefixTree, build_vrp_prefix_tree


@pytest.fixture
def v4_tree() -> PrefixTree[str]:
    """构造一棵含若干 IPv4 前缀的树。"""
    tree: PrefixTree[str] = PrefixTree()
    tree.insert("0.0.0.0/0", "default")
    tree.insert("10.0.0.0/8", "ten")
    tree.insert("10.1.0.0/16", "ten-one")
    tree.insert("10.1.1.0/24", "ten-one-one")
    tree.insert("192.168.1.0/24", "cisco-private")
    return tree


@pytest.fixture
def v6_tree() -> PrefixTree[str]:
    """构造一棵含若干 IPv6 前缀的树。"""
    tree: PrefixTree[str] = PrefixTree()
    tree.insert("::/0", "default-v6")
    tree.insert("2001:db8::/32", "doc-prefix")
    tree.insert("2001:db8:1::/48", "doc-subnet")
    tree.insert("2001:db8:1:1::/64", "doc-host")
    return tree


# ──────────────────────────────────────────────
# 插入与基本属性
# ──────────────────────────────────────────────


def test_insert_returns_true_for_valid_prefix() -> None:
    """合法前缀插入应返回 True 并增加 size。"""
    tree: PrefixTree[str] = PrefixTree()
    assert tree.insert("192.168.1.0/24", "data") is True
    assert tree.size == 1


def test_insert_returns_false_for_invalid_prefix() -> None:
    """非法前缀字符串应拒绝插入。"""
    tree: PrefixTree[str] = PrefixTree()
    assert tree.insert("not-a-prefix", "data") is False
    assert tree.size == 0


def test_insert_multiple_data_on_same_prefix() -> None:
    """同一前缀允许多次插入，数据按列表累积。"""
    tree: PrefixTree[str] = PrefixTree()
    tree.insert("10.0.0.0/8", "a")
    tree.insert("10.0.0.0/8", "b")
    assert tree.size == 2
    results = tree.lookup("10.0.0.0/8")
    assert "a" in results
    assert "b" in results


# ──────────────────────────────────────────────
# lookup（祖先链匹配）
# ──────────────────────────────────────────────


def test_lookup_returns_ancestor_chain(v4_tree: PrefixTree[str]) -> None:
    """lookup 应返回覆盖查询前缀的所有祖先节点数据。"""
    results = v4_tree.lookup("10.1.1.0/24")
    # 路径：0.0.0.0/0 -> 10.0.0.0/8 -> 10.1.0.0/16 -> 10.1.1.0/24
    assert "default" in results
    assert "ten" in results
    assert "ten-one" in results
    assert "ten-one-one" in results


def test_lookup_exact_match(v4_tree: PrefixTree[str]) -> None:
    """精确匹配前缀应返回该前缀及其祖先。"""
    results = v4_tree.lookup("192.168.1.0/24")
    assert "cisco-private" in results
    assert "default" in results  # 根节点


def test_lookup_unrelated_prefix_returns_only_default(
    v4_tree: PrefixTree[str],
) -> None:
    """查询无具体匹配的前缀时，仅返回根节点（0.0.0.0/0）。"""
    results = v4_tree.lookup("172.16.0.0/12")
    assert results == ["default"]


def test_lookup_invalid_prefix_returns_empty() -> None:
    """非法前缀查询应返回空列表。"""
    tree: PrefixTree[str] = PrefixTree()
    assert tree.lookup("invalid") == []


def test_lookup_empty_tree_returns_empty() -> None:
    """空树查询应返回空列表。"""
    tree: PrefixTree[str] = PrefixTree()
    assert tree.lookup("10.0.0.0/8") == []


# ──────────────────────────────────────────────
# find_more_specific（后代匹配）
# ──────────────────────────────────────────────


def test_find_more_specific_returns_descendants(
    v4_tree: PrefixTree[str],
) -> None:
    """find_more_specific 应返回查询前缀下的所有更具体前缀数据。"""
    results = v4_tree.find_more_specific("10.0.0.0/8")
    # 10.0.0.0/8 自身不计入，但其子树（10.1.0.0/16、10.1.1.0/24）应返回
    assert "ten-one" in results
    assert "ten-one-one" in results
    assert "ten" not in results  # 自身不包含


def test_find_more_specific_no_descendants(v4_tree: PrefixTree[str]) -> None:
    """无更具体前缀时应返回空列表。"""
    results = v4_tree.find_more_specific("192.168.1.0/24")
    assert results == []


def test_find_more_specific_invalid_prefix_returns_empty() -> None:
    """非法前缀应返回空列表。"""
    tree: PrefixTree[str] = PrefixTree()
    assert tree.find_more_specific("bad") == []


# ──────────────────────────────────────────────
# find_less_specific（祖先链匹配，等价于 lookup）
# ──────────────────────────────────────────────


def test_find_less_specific_equals_lookup(v4_tree: PrefixTree[str]) -> None:
    """find_less_specific 应与 lookup 行为一致。"""
    assert v4_tree.find_less_specific("10.1.1.0/24") == v4_tree.lookup("10.1.1.0/24")


# ──────────────────────────────────────────────
# IPv6 支持
# ──────────────────────────────────────────────


def test_ipv6_insert_and_lookup(v6_tree: PrefixTree[str]) -> None:
    """IPv6 前缀插入与祖先链查询。"""
    results = v6_tree.lookup("2001:db8:1:1::/64")
    assert "default-v6" in results
    assert "doc-prefix" in results
    assert "doc-subnet" in results
    assert "doc-host" in results


def test_ipv6_find_more_specific(v6_tree: PrefixTree[str]) -> None:
    """IPv6 前缀的后代查询。"""
    results = v6_tree.find_more_specific("2001:db8::/32")
    assert "doc-subnet" in results
    assert "doc-host" in results
    assert "doc-prefix" not in results


def test_v4_and_v6_are_isolated() -> None:
    """IPv4 与 IPv6 树应相互隔离。"""
    tree: PrefixTree[str] = PrefixTree()
    tree.insert("10.0.0.0/8", "v4-data")
    tree.insert("2001:db8::/32", "v6-data")
    # IPv4 查询不应返回 IPv6 数据
    v4_results = tree.lookup("10.0.0.0/8")
    assert "v4-data" in v4_results
    assert "v6-data" not in v4_results
    # IPv6 查询不应返回 IPv4 数据
    v6_results = tree.lookup("2001:db8::/32")
    assert "v6-data" in v6_results
    assert "v4-data" not in v6_results


# ──────────────────────────────────────────────
# 删除
# ──────────────────────────────────────────────


def test_remove_existing_data(v4_tree: PrefixTree[str]) -> None:
    """删除已存在的数据应返回 True 并减少 size。"""
    initial_size = v4_tree.size
    assert v4_tree.remove("10.1.0.0/16", "ten-one") is True
    assert v4_tree.size == initial_size - 1
    # 删除后 lookup 不应再包含该数据
    results = v4_tree.lookup("10.1.0.0/16")
    assert "ten-one" not in results


def test_remove_nonexistent_data_returns_false(
    v4_tree: PrefixTree[str],
) -> None:
    """删除不存在的数据应返回 False。"""
    assert v4_tree.remove("10.1.0.0/16", "not-exist") is False


def test_remove_invalid_prefix_returns_false() -> None:
    """非法前缀删除应返回 False。"""
    tree: PrefixTree[str] = PrefixTree()
    assert tree.remove("bad", "data") is False


# ──────────────────────────────────────────────
# 清空
# ──────────────────────────────────────────────


def test_clear_resets_tree(v4_tree: PrefixTree[str]) -> None:
    """clear 应清空所有数据并重置 size。"""
    v4_tree.clear()
    assert v4_tree.size == 0
    assert v4_tree.lookup("10.0.0.0/8") == []


# ──────────────────────────────────────────────
# 工厂函数
# ──────────────────────────────────────────────


def test_build_vrp_prefix_tree() -> None:
    """build_vrp_prefix_tree 应批量构建前缀树。"""
    vrps = [
        ("10.0.0.0/8", {"asn": 65001}),
        ("192.168.1.0/24", {"asn": 65002}),
        ("2001:db8::/32", {"asn": 65003}),
    ]
    tree = build_vrp_prefix_tree(vrps)
    assert tree.size == 3
    # 验证查询
    assert {"asn": 65001} in tree.lookup("10.0.0.0/8")
    assert {"asn": 65002} in tree.lookup("192.168.1.0/24")
    assert {"asn": 65003} in tree.lookup("2001:db8::/32")


# ──────────────────────────────────────────────
# 最长前缀匹配场景
# ──────────────────────────────────────────────


def test_longest_prefix_match_priority() -> None:
    """lookup 结果按从更不具体到更具体的顺序排列。"""
    tree: PrefixTree[str] = PrefixTree()
    tree.insert("0.0.0.0/0", "root")
    tree.insert("10.0.0.0/8", "eight")
    tree.insert("10.1.0.0/16", "sixteen")
    tree.insert("10.1.1.0/24", "twenty-four")

    results = tree.lookup("10.1.1.0/24")
    # 最长前缀（最具体）应在列表末尾
    assert results[-1] == "twenty-four"
    # 根节点应在列表开头
    assert results[0] == "root"
