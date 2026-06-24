"""异常登录检测服务。

基于多维特征检测异常登录行为，包括：
1. 异常时间登录（非工作时间）
2. 异地登录（基于 IP 历史记录）
3. 频繁失败登录（暴力破解迹象）
4. 新设备/浏览器登录（基于 User-Agent 差异）

本服务提供独立的检测能力，可被认证流程调用以触发二次认证或
记录审计告警。检测结果不阻塞登录流程，由调用方决定后续处理。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("app.services.anomaly_detection_service")

# 用户最近登录 IP 记录（内存实现，生产环境应替换为 Redis）
# 结构：{user_id: [(ip, timestamp), ...]}
_recent_login_ips: dict[int | str, list[tuple[str, float]]] = {}

# 用户最近登录 User-Agent 记录（内存实现）
# 结构：{user_id: [(user_agent_hash, timestamp), ...]}
_recent_user_agents: dict[int | str, list[tuple[str, float]]] = {}

# 登录失败计数（内存实现，按 IP + 用户名聚合）
# 结构：{(ip, username): [(timestamp), ...]}
_login_failures: dict[tuple[str, str], list[float]] = defaultdict(list)

# 时间窗口配置
_RECENT_IP_WINDOW_SECONDS = 7 * 24 * 3600  # 7 天
_RECENT_UA_WINDOW_SECONDS = 30 * 24 * 3600  # 30 天
_FAILURE_WINDOW_SECONDS = 3600  # 1 小时
_FREQUENT_FAILURE_THRESHOLD = 10  # 1 小时内失败次数阈值


def _get_client_ip(headers: dict[str, str], client_host: str | None) -> str:
    """从请求头与客户端信息中获取真实 IP。

    优先解析 ``X-Forwarded-For`` 请求头，其次使用 ``client_host``。

    Args:
        headers: 请求头字典
        client_host: 客户端主机地址

    Returns:
        客户端 IP 地址，无法获取时返回 ``"unknown"``
    """
    forwarded = headers.get("X-Forwarded-For", "") or headers.get(
        "x-forwarded-for", ""
    )
    if forwarded:
        return forwarded.split(",")[0].strip()
    return client_host or "unknown"


def _hash_user_agent(user_agent: str) -> str:
    """对 User-Agent 进行简单哈希以减少存储占用。"""
    import hashlib

    return hashlib.sha256(user_agent.encode("utf-8")).hexdigest()[:16]


def _record_login_ip(user_id: int | str, ip: str) -> None:
    """记录用户登录 IP（用于后续异地登录检测）。"""
    now = datetime.now(timezone.utc).timestamp()
    records = _recent_login_ips.setdefault(user_id, [])
    # 清理过期记录
    cutoff = now - _RECENT_IP_WINDOW_SECONDS
    _recent_login_ips[user_id] = [
        (existing_ip, ts) for existing_ip, ts in records if ts > cutoff
    ]
    # 追加本次记录
    _recent_login_ips[user_id].append((ip, now))


def _is_new_ip_for_user(user_id: int | str, ip: str) -> bool:
    """检查给定 IP 是否为用户最近未使用过的新 IP。"""
    records = _recent_login_ips.get(user_id, [])
    return not any(existing_ip == ip for existing_ip, _ in records)


def _record_user_agent(user_id: int | str, user_agent: str) -> None:
    """记录用户登录 User-Agent。"""
    now = datetime.now(timezone.utc).timestamp()
    ua_hash = _hash_user_agent(user_agent)
    records = _recent_user_agents.setdefault(user_id, [])
    # 清理过期记录
    cutoff = now - _RECENT_UA_WINDOW_SECONDS
    _recent_user_agents[user_id] = [
        (existing_ua, ts) for existing_ua, ts in records if ts > cutoff
    ]
    # 追加本次记录
    _recent_user_agents[user_id].append((ua_hash, now))


def _is_new_user_agent_for_user(
    user_id: int | str, user_agent: str
) -> bool:
    """检查给定 User-Agent 是否为用户最近未使用过的新设备。"""
    ua_hash = _hash_user_agent(user_agent)
    records = _recent_user_agents.get(user_id, [])
    return not any(existing_ua == ua_hash for existing_ua, _ in records)


def record_login_failure(ip: str, username: str) -> int:
    """记录登录失败事件。

    用于频繁失败登录检测。返回当前时间窗口内的失败次数。

    Args:
        ip: 客户端 IP
        username: 登录用户名

    Returns:
        当前时间窗口内的失败次数
    """
    now = datetime.now(timezone.utc).timestamp()
    key = (ip, username)
    records = _login_failures[key]
    # 清理过期记录
    cutoff = now - _FAILURE_WINDOW_SECONDS
    _login_failures[key] = [ts for ts in records if ts > cutoff]
    # 追加本次失败
    _login_failures[key].append(now)
    return len(_login_failures[key])


def clear_login_failures(ip: str, username: str) -> None:
    """清除指定 IP + 用户名的登录失败记录（登录成功后调用）。"""
    key = (ip, username)
    if key in _login_failures:
        del _login_failures[key]


def detect_off_hours_login(login_hour: int) -> bool:
    """检测是否在非工作时间登录。

    Args:
        login_hour: 登录小时（0-23，UTC）

    Returns:
        是否为非工作时间登录
    """
    office_start = settings.ANOMALOUS_LOGIN_OFFICE_HOURS_START
    office_end = settings.ANOMALOUS_LOGIN_OFFICE_HOURS_END
    if office_start <= office_end:
        # 同日工作时间区间（如 8-18）
        return login_hour < office_start or login_hour >= office_end
    # 跨日工作时间区间（如 22-6）
    return office_end <= login_hour < office_start


def detect_frequent_failures(ip: str, username: str) -> bool:
    """检测是否存在频繁登录失败（暴力破解迹象）。

    Args:
        ip: 客户端 IP
        username: 登录用户名

    Returns:
        是否达到频繁失败阈值
    """
    key = (ip, username)
    now = datetime.now(timezone.utc).timestamp()
    cutoff = now - _FAILURE_WINDOW_SECONDS
    records = _login_failures.get(key, [])
    recent_count = sum(1 for ts in records if ts > cutoff)
    return recent_count >= _FREQUENT_FAILURE_THRESHOLD


def detect_anomalous_login(
    user_id: int | str,
    username: str,
    headers: dict[str, str],
    client_host: str | None = None,
) -> dict[str, Any]:
    """异常登录检测主入口。

    基于多维特征检测异常登录行为，返回检测结果供调用方记录审计日志
    或触发二次认证。本函数不阻塞登录流程。

    检测维度：
    1. **异常时间登录**：在非工作时间（默认 18:00 - 次日 08:00）登录
    2. **异地登录**：用户从最近未使用过的新 IP 登录
    3. **新设备/浏览器**：基于 User-Agent 与历史记录的差异
    4. **频繁失败**：登录前存在大量失败尝试（暴力破解迹象）

    Args:
        user_id: 用户 ID
        username: 用户名
        headers: 请求头字典
        client_host: 客户端主机地址

    Returns:
        检测结果字典，包含以下字段：
        - ``is_anomalous``: 是否检测到异常
        - ``reasons``: 异常原因列表
        - ``client_ip``: 客户端 IP
        - ``user_agent``: User-Agent 摘要
        - ``login_hour``: 登录小时（UTC）
        - ``risk_level``: 风险等级（low/medium/high）
    """
    reasons: list[str] = []
    client_ip = _get_client_ip(headers, client_host)
    user_agent = headers.get("User-Agent", "") or headers.get(
        "user-agent", ""
    )[:200]

    now = datetime.now(timezone.utc)
    login_hour = now.hour

    # 1. 异常时间登录检测
    if detect_off_hours_login(login_hour):
        reasons.append(f"非工作时间登录（{login_hour}:00 UTC）")

    # 2. 异地登录检测（基于 IP 历史）
    if client_ip != "unknown" and _is_new_ip_for_user(user_id, client_ip):
        reasons.append(f"异地/新 IP 登录（{client_ip}）")

    # 3. 新设备/浏览器检测
    if user_agent and _is_new_user_agent_for_user(user_id, user_agent):
        reasons.append("新设备/浏览器登录")

    # 4. 频繁失败检测
    if detect_frequent_failures(client_ip, username):
        reasons.append("频繁登录失败（疑似暴力破解）")

    # 记录本次登录 IP 与 User-Agent，便于后续检测
    if client_ip != "unknown":
        _record_login_ip(user_id, client_ip)
    if user_agent:
        _record_user_agent(user_id, user_agent)

    # 评估风险等级
    if len(reasons) >= 3:
        risk_level = "high"
    elif len(reasons) >= 2:
        risk_level = "medium"
    elif len(reasons) >= 1:
        risk_level = "low"
    else:
        risk_level = "low"

    result: dict[str, Any] = {
        "is_anomalous": len(reasons) > 0,
        "reasons": reasons,
        "client_ip": client_ip,
        "user_agent": user_agent,
        "login_hour": login_hour,
        "risk_level": risk_level,
    }

    if result["is_anomalous"]:
        logger.warning(
            "检测到异常登录",
            user_id=user_id,
            username=username,
            reasons=reasons,
            client_ip=client_ip,
            login_hour=login_hour,
            risk_level=risk_level,
        )

    return result


def get_login_history_summary(
    user_id: int | str,
) -> dict[str, Any]:
    """获取用户登录历史摘要（用于异常检测上下文展示）。

    Args:
        user_id: 用户 ID

    Returns:
        登录历史摘要字典，包含最近 IP 数量与 User-Agent 数量
    """
    ip_records = _recent_login_ips.get(user_id, [])
    ua_records = _recent_user_agents.get(user_id, [])
    now = datetime.now(timezone.utc).timestamp()

    ip_cutoff = now - _RECENT_IP_WINDOW_SECONDS
    ua_cutoff = now - _RECENT_UA_WINDOW_SECONDS

    recent_ips = {
        ip for ip, ts in ip_records if ts > ip_cutoff
    }
    recent_uas = {
        ua for ua, ts in ua_records if ts > ua_cutoff
    }

    return {
        "user_id": user_id,
        "recent_ip_count": len(recent_ips),
        "recent_user_agent_count": len(recent_uas),
        "ip_history_window_days": _RECENT_IP_WINDOW_SECONDS // 86400,
        "ua_history_window_days": _RECENT_UA_WINDOW_SECONDS // 86400,
    }


__all__ = [
    "clear_login_failures",
    "detect_anomalous_login",
    "detect_frequent_failures",
    "detect_off_hours_login",
    "get_login_history_summary",
    "record_login_failure",
]
