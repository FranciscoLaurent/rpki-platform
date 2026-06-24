"""前缀树性能测试。

测试 PrefixTree 在大规模数据（10 万级前缀）下的插入与查询性能。
使用 ``time.perf_counter`` 进行高精度计时。

运行方式：
    pytest tests/perf/test_prefix_tree_perf.py -v -s
"""

from __future__ import annotations

import ipaddress
import random
import time

from app.core.prefix_tree import PrefixTree, build_vrp_prefix_tree

# ──────────────────────────────────────────────
# 性能测试常量
# ──────────────────────────────────────────────

# 大规模测试的前缀数量
LARGE_SCALE = 100_000
# 中等规模测试的前缀数量
MEDIUM_SCALE = 10_000
# 查询次数
QUERY_COUNT = 1_000
# 性能阈值（秒）：单次操作不应超过此时间
INSERT_THRESHOLD_MS = 0.5  # 单次插入 0.5ms
LOOKUP_THRESHOLD_MS = 1.0  # 单次查询 1ms


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


def _generate_random_ipv4_prefixes(count: int) -> list[str]:
    """生成指定数量的随机 IPv4 前缀。"""
    prefixes: list[str] = []
    for _ in range(count):
        # 随机生成 IPv4 地址
        addr_int = random.randint(0, 0xFFFFFFFF)
        # 随机前缀长度（8-32，避免过多 /0 ~ /7 的超大范围）
        prefix_len = random.randint(8, 32)
        mask = (0xFFFFFFFF << (32 - prefix_len)) & 0xFFFFFFFF
        network_addr = addr_int & mask
        network = ipaddress.IPv4Network((network_addr, prefix_len), strict=True)
        prefixes.append(str(network))
    return prefixes


def _generate_random_ipv6_prefixes(count: int) -> list[str]:
    """生成指定数量的随机 IPv6 前缀。"""
    prefixes: list[str] = []
    for _ in range(count):
        # 随机生成 IPv6 地址
        addr_int = random.randint(0, (1 << 128) - 1)
        # 随机前缀长度（32-64）
        prefix_len = random.randint(32, 64)
        mask = (1 << 128) - (1 << (128 - prefix_len))
        network_addr = addr_int & mask
        network = ipaddress.IPv6Network((network_addr, prefix_len), strict=True)
        prefixes.append(str(network))
    return prefixes


# ──────────────────────────────────────────────
# 插入性能测试
# ──────────────────────────────────────────────


def test_prefix_tree_insert_medium_scale() -> None:
    """中等规模（1 万前缀）插入性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(MEDIUM_SCALE)

    tree: PrefixTree[str] = PrefixTree()
    start = time.perf_counter()
    for p in prefixes:
        tree.insert(p, "data")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / MEDIUM_SCALE) * 1000
    print(f"\n[中等规模插入] {MEDIUM_SCALE} 个前缀，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/条")

    assert tree.size == MEDIUM_SCALE
    assert avg_ms < INSERT_THRESHOLD_MS, f"单次插入 {avg_ms:.4f}ms 超过阈值 {INSERT_THRESHOLD_MS}ms"


def test_prefix_tree_insert_large_scale() -> None:
    """大规模（10 万前缀）插入性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(LARGE_SCALE)

    tree: PrefixTree[str] = PrefixTree()
    start = time.perf_counter()
    for p in prefixes:
        tree.insert(p, "data")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / LARGE_SCALE) * 1000
    print(f"\n[大规模插入] {LARGE_SCALE} 个前缀，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/条")

    assert tree.size == LARGE_SCALE
    assert avg_ms < INSERT_THRESHOLD_MS


def test_prefix_tree_insert_ipv6_large_scale() -> None:
    """大规模 IPv6 前缀插入性能测试。"""
    prefixes = _generate_random_ipv6_prefixes(MEDIUM_SCALE)

    tree: PrefixTree[str] = PrefixTree()
    start = time.perf_counter()
    for p in prefixes:
        tree.insert(p, "data")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / MEDIUM_SCALE) * 1000
    print(
        f"\n[IPv6 大规模插入] {MEDIUM_SCALE} 个前缀，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/条"
    )

    assert tree.size == MEDIUM_SCALE


# ──────────────────────────────────────────────
# 查询性能测试
# ──────────────────────────────────────────────


def test_prefix_tree_lookup_medium_scale() -> None:
    """中等规模前缀树查询性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(MEDIUM_SCALE)
    tree: PrefixTree[str] = PrefixTree()
    for p in prefixes:
        tree.insert(p, "data")

    # 随机选取查询前缀
    query_prefixes = random.choices(prefixes, k=QUERY_COUNT)

    start = time.perf_counter()
    for q in query_prefixes:
        tree.lookup(q)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / QUERY_COUNT) * 1000
    print(f"\n[中等规模查询] {QUERY_COUNT} 次查询，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert avg_ms < LOOKUP_THRESHOLD_MS


def test_prefix_tree_lookup_large_scale() -> None:
    """大规模前缀树查询性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(LARGE_SCALE)
    tree: PrefixTree[str] = PrefixTree()
    for p in prefixes:
        tree.insert(p, "data")

    query_prefixes = random.choices(prefixes, k=QUERY_COUNT)

    start = time.perf_counter()
    for q in query_prefixes:
        tree.lookup(q)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / QUERY_COUNT) * 1000
    print(
        f"\n[大规模查询] {QUERY_COUNT} 次查询（树规模 {LARGE_SCALE}），"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )

    assert avg_ms < LOOKUP_THRESHOLD_MS


# ──────────────────────────────────────────────
# find_more_specific 性能测试
# ──────────────────────────────────────────────


def test_prefix_tree_find_more_specific_performance() -> None:
    """find_more_specific 性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(MEDIUM_SCALE)
    tree: PrefixTree[str] = PrefixTree()
    for p in prefixes:
        tree.insert(p, "data")

    # 查询较不具体的前缀（/8 或 /16），以找到更多后代
    query_prefixes = [p for p in prefixes if int(p.split("/")[1]) <= 16][:QUERY_COUNT]
    if not query_prefixes:
        query_prefixes = prefixes[:QUERY_COUNT]

    start = time.perf_counter()
    for q in query_prefixes:
        tree.find_more_specific(q)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / len(query_prefixes)) * 1000
    print(
        f"\n[find_more_specific] {len(query_prefixes)} 次查询，"
        f"总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次"
    )


# ──────────────────────────────────────────────
# 工厂函数性能测试
# ──────────────────────────────────────────────


def test_build_vrp_prefix_tree_performance() -> None:
    """build_vrp_prefix_tree 批量构建性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(MEDIUM_SCALE)
    vrps = [(p, {"asn": random.randint(1, 65535)}) for p in prefixes]

    start = time.perf_counter()
    tree = build_vrp_prefix_tree(vrps)
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / MEDIUM_SCALE) * 1000
    print(f"\n[工厂函数构建] {MEDIUM_SCALE} 个 VRP，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/条")

    assert tree.size == MEDIUM_SCALE


# ──────────────────────────────────────────────
# 删除性能测试
# ──────────────────────────────────────────────


def test_prefix_tree_remove_performance() -> None:
    """前缀树删除性能测试。"""
    prefixes = _generate_random_ipv4_prefixes(MEDIUM_SCALE)
    tree: PrefixTree[str] = PrefixTree()
    for p in prefixes:
        tree.insert(p, "data")

    # 随机选取待删除前缀
    to_remove = random.sample(prefixes, QUERY_COUNT)

    start = time.perf_counter()
    for p in to_remove:
        tree.remove(p, "data")
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / QUERY_COUNT) * 1000
    print(f"\n[删除] {QUERY_COUNT} 次删除，总耗时 {elapsed:.3f}s，平均 {avg_ms:.4f}ms/次")

    assert tree.size == MEDIUM_SCALE - QUERY_COUNT
