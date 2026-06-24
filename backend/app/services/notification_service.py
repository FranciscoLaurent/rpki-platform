"""通知集成服务（Task 20）。

提供统一的事件通知能力，支持多种通知渠道：
- Webhook 推送（使用 httpx 实际发送）
- 邮件（SMTP，预留接口）
- 短信（预留接口）
- 企业协作工具（企业微信/钉钉/Slack/Teams，预留接口）
- ITSM/SOC 集成（预留接口）

外部通道的配置从 ``app.core.config.settings`` 读取，实际发送逻辑
仅 Webhook 使用 httpx 实现，其余通道返回占位结果。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.detection import Incident
from app.models.forensics import NotificationChannel, NotificationLog

logger = get_logger("app.notification_service")


# Webhook 请求超时（秒）
WEBHOOK_TIMEOUT = 10.0


async def send_webhook(url: str, payload: dict[str, Any]) -> bool:
    """Webhook 推送。

    使用 httpx 向指定 URL 发送 JSON POST 请求。

    Args:
        url: Webhook 目标 URL
        payload: 推送的 JSON 内容

    Returns:
        发送成功返回 True，失败返回 False
    """
    try:
        async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code < 400:
                logger.info(
                    "Webhook 推送成功",
                    url=url,
                    status_code=response.status_code,
                )
                return True
            logger.warning(
                "Webhook 推送失败",
                url=url,
                status_code=response.status_code,
                response=response.text[:500],
            )
            return False
    except Exception as e:
        logger.exception(
            "Webhook 推送异常",
            url=url,
            error=str(e),
        )
        return False


async def send_email(to: list[str], subject: str, body: str) -> bool:
    """邮件发送（SMTP，预留接口）。

    实际 SMTP 发送逻辑待接入邮件服务后实现，当前返回占位结果。

    Args:
        to: 收件人邮箱列表
        subject: 邮件主题
        body: 邮件正文

    Returns:
        占位返回 True
    """
    logger.info(
        "邮件通知（预留接口）",
        recipients=to,
        subject=subject,
    )
    # TODO: 接入 SMTP 邮件服务后实现实际发送
    # 从 settings 读取 SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASSWORD
    return True


async def send_sms(to: list[str], message: str) -> bool:
    """短信发送（预留接口）。

    实际短信发送逻辑待接入短信服务后实现，当前返回占位结果。

    Args:
        to: 收信人手机号列表
        message: 短信内容

    Returns:
        占位返回 True
    """
    logger.info(
        "短信通知（预留接口）",
        recipients=to,
        message_length=len(message),
    )
    # TODO: 接入短信服务后实现实际发送
    return True


async def send_enterprise_im(channel: str, message: str) -> bool:
    """企业协作工具通知（预留接口）。

    支持企业微信、钉钉、Slack、Teams 等企业协作工具。
    实际发送逻辑待接入对应平台 API 后实现，当前返回占位结果。

    Args:
        channel: 渠道类型（wechat_work/dingtalk/slack/teams）
        message: 消息内容

    Returns:
        占位返回 True
    """
    logger.info(
        "企业 IM 通知（预留接口）",
        channel=channel,
        message_length=len(message),
    )
    # TODO: 接入企业微信/钉钉/Slack/Teams API 后实现实际发送
    return True


async def send_to_itsm(incident: Incident, action: str) -> bool:
    """ITSM/SOC 集成（预留接口）。

    将事件同步到 ITSM/SOC 平台，触发工单或告警流程。
    实际集成逻辑待接入 ITSM/SOC 平台 API 后实现，当前返回占位结果。

    Args:
        incident: 事件对象
        action: 动作类型（create/update/close）

    Returns:
        占位返回 True
    """
    logger.info(
        "ITSM/SOC 集成（预留接口）",
        incident_id=incident.id,
        action=action,
    )
    # TODO: 接入 ITSM/SOC 平台 API 后实现实际同步
    return True


async def notify_incident(
    db: AsyncSession,
    incident_id: int,
    channels: list[str] | None = None,
    title: str | None = None,
    content: str | None = None,
    triggered_by: int | None = None,
) -> dict[str, Any]:
    """统一事件通知入口。

    根据指定渠道列表发送事件通知，记录通知日志。
    若未指定渠道，则查询数据库中所有启用的通知渠道发送。

    Args:
        db: 异步数据库会话
        incident_id: 事件 ID
        channels: 通知渠道列表（为空则查询所有启用渠道）
        title: 通知标题（为空则自动生成）
        content: 通知内容（为空则自动生成）
        triggered_by: 触发人用户 ID（自动触发为空）

    Returns:
        通知结果字典，包含 total_channels/sent_count/failed_count/results/errors
    """
    now = datetime.now(UTC)

    # 查询事件
    incident = await _get_incident(db, incident_id)
    if incident is None:
        return {
            "incident_id": incident_id,
            "total_channels": 0,
            "sent_count": 0,
            "failed_count": 0,
            "results": [],
            "errors": [f"事件 ID {incident_id} 不存在"],
        }

    # 生成通知标题与内容
    notify_title = title or f"[路由安全告警] {incident.title}"
    notify_content = content or _build_incident_content(incident)

    # 确定通知渠道
    channel_list = await _resolve_channels(db, channels)

    if not channel_list:
        logger.warning("无可用的通知渠道", incident_id=incident_id)
        return {
            "incident_id": incident_id,
            "total_channels": 0,
            "sent_count": 0,
            "failed_count": 0,
            "results": [],
            "errors": ["无可用的通知渠道"],
        }

    sent_count = 0
    failed_count = 0
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for channel in channel_list:
        channel_type = channel.channel_type
        channel_config = channel.config or {}

        try:
            success = await _dispatch_to_channel(
                channel_type,
                channel_config,
                notify_title,
                notify_content,
                incident,
            )

            # 记录通知日志
            log = NotificationLog(
                incident_id=incident_id,
                channel_id=channel.id,
                channel_type=channel_type,
                title=notify_title,
                content=notify_content,
                status="sent" if success else "failed",
                error_message=None if success else "渠道发送失败",
                sent_at=now if success else None,
                triggered_by=triggered_by,
            )
            db.add(log)
            await db.flush()

            if success:
                sent_count += 1
                results.append(
                    {
                        "channel_id": channel.id,
                        "channel_type": channel_type,
                        "status": "sent",
                        "log_id": log.id,
                    }
                )
            else:
                failed_count += 1
                results.append(
                    {
                        "channel_id": channel.id,
                        "channel_type": channel_type,
                        "status": "failed",
                        "log_id": log.id,
                    }
                )
        except Exception as e:
            failed_count += 1
            errors.append(f"渠道 {channel_type}（ID={channel.id}）发送异常：{e}")
            logger.exception(
                "通知渠道发送异常",
                incident_id=incident_id,
                channel_type=channel_type,
                error=str(e),
            )

            # 记录失败日志
            log = NotificationLog(
                incident_id=incident_id,
                channel_id=channel.id,
                channel_type=channel_type,
                title=notify_title,
                content=notify_content,
                status="failed",
                error_message=str(e),
                triggered_by=triggered_by,
            )
            db.add(log)
            await db.flush()

    logger.info(
        "事件通知完成",
        incident_id=incident_id,
        total_channels=len(channel_list),
        sent_count=sent_count,
        failed_count=failed_count,
    )

    return {
        "incident_id": incident_id,
        "total_channels": len(channel_list),
        "sent_count": sent_count,
        "failed_count": failed_count,
        "results": results,
        "errors": errors,
    }


# ──────────────────────────────────────────────
# 渠道分发
# ──────────────────────────────────────────────


async def _dispatch_to_channel(
    channel_type: str,
    config: dict[str, Any],
    title: str,
    content: str,
    incident: Incident,
) -> bool:
    """根据渠道类型分发通知。"""
    if channel_type == "webhook":
        url = config.get("url") or config.get("webhook_url")
        if not url:
            logger.warning("Webhook 渠道未配置 URL", channel_type=channel_type)
            return False
        payload = {
            "title": title,
            "content": content,
            "incident_id": incident.id,
            "severity": incident.severity,
            "status": incident.status,
            "affected_prefixes": incident.affected_prefixes,
            "affected_asns": incident.affected_asns,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        return await send_webhook(url, payload)

    if channel_type == "email":
        recipients = config.get("recipients") or config.get("to") or []
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        if not recipients:
            logger.warning("邮件渠道未配置收件人", channel_type=channel_type)
            return False
        return await send_email(recipients, title, content)

    if channel_type == "sms":
        recipients = config.get("recipients") or config.get("to") or []
        if isinstance(recipients, str):
            recipients = [r.strip() for r in recipients.split(",") if r.strip()]
        if not recipients:
            logger.warning("短信渠道未配置收信人", channel_type=channel_type)
            return False
        return await send_sms(recipients, content)

    if channel_type in ("wechat_work", "dingtalk", "slack", "teams"):
        return await send_enterprise_im(channel_type, f"{title}\n{content}")

    if channel_type in ("itsm", "soc"):
        return await send_to_itsm(incident, "notify")

    logger.warning("不支持的通知渠道类型", channel_type=channel_type)
    return False


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _get_incident(db: AsyncSession, incident_id: int) -> Incident | None:
    """获取事件。"""
    stmt = select(Incident).where(Incident.id == incident_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _resolve_channels(
    db: AsyncSession, channels: list[str] | None
) -> list[NotificationChannel]:
    """解析通知渠道列表。

    若指定渠道类型列表，则查询匹配的启用渠道；
    否则查询所有启用的通知渠道。
    """
    stmt = select(NotificationChannel).where(NotificationChannel.enabled.is_(True))
    if channels:
        stmt = stmt.where(NotificationChannel.channel_type.in_(channels))
    result = await db.execute(stmt)
    return list(result.scalars().all())


def _build_incident_content(incident: Incident) -> str:
    """根据事件信息构建通知内容。"""
    parts: list[str] = []
    parts.append(f"事件 ID：{incident.id}")
    parts.append(f"事件标题：{incident.title}")
    parts.append(f"严重等级：{incident.severity}")
    parts.append(f"状态：{incident.status}")
    if incident.description:
        parts.append(f"描述：{incident.description}")
    if incident.affected_prefixes:
        parts.append(f"受影响前缀：{', '.join(incident.affected_prefixes)}")
    if incident.affected_asns:
        parts.append(f"受影响 ASN：{', '.join(f'AS{asn}' for asn in incident.affected_asns)}")
    if incident.first_seen_at:
        parts.append(f"首次发现：{incident.first_seen_at.isoformat()}")
    return "\n".join(parts)


__all__ = [
    "notify_incident",
    "send_email",
    "send_enterprise_im",
    "send_sms",
    "send_to_itsm",
    "send_webhook",
]
