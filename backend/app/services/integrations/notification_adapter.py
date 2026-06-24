"""企业协作与通知系统集成适配器。

提供与邮件（SMTP）、短信、电话语音、企业微信、钉钉、Slack、Microsoft Teams
及 PagerDuty 的集成能力，支持多通道通知发送与统一通知入口。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx
from structlog.stdlib import BoundLogger

from app.core.logging import get_logger
from app.services.integrations.base import AdapterResult, BaseAdapter

logger: BoundLogger = get_logger("app.integrations.notification")


class CollaborationAdapter(BaseAdapter):
    """企业协作平台集成适配器。

    支持的子类型：
    - ``wechat_work``: 企业微信群机器人
    - ``dingtalk``: 钉钉群机器人
    - ``slack``: Slack Incoming Webhook
    - ``teams``: Microsoft Teams Workflows
    - ``pagerduty``: PagerDuty Events API v2

    连接参数：
    - ``webhook_url``: Webhook URL
    - ``timeout``: 请求超时（秒，默认 10）
    """

    async def test_connection(self) -> AdapterResult:
        """测试协作平台连接。"""
        webhook_url = self.connection_params.get("webhook_url")
        if not webhook_url:
            return AdapterResult(success=False, error_message="Webhook URL 未配置")

        start = time.monotonic()
        try:
            async with httpx.AsyncClient(
                timeout=self._get_timeout()
            ) as client:
                # 发送测试消息
                test_payload = {"text": "RPKI 平台连通性测试"}
                response = await client.post(
                    webhook_url,
                    content=json.dumps(test_payload, ensure_ascii=False),
                    headers={"Content-Type": "application/json"},
                )
            latency_ms = int((time.monotonic() - start) * 1000)
            success = response.status_code < 400
            return AdapterResult(
                success=success,
                data=None,
                error_message=None if success else f"状态码 {response.status_code}",
                latency_ms=latency_ms,
            )
        except Exception as e:
            latency_ms = int((time.monotonic() - start) * 1000)
            return AdapterResult(
                success=False, error_message=str(e), latency_ms=latency_ms
            )


# ──────────────────────────────────────────────
# 函数式接口
# ──────────────────────────────────────────────


async def send_email(
    config: dict[str, Any], to: list[str], subject: str, body: str
) -> bool:
    """通过 SMTP 发送邮件。

    Args:
        config: 邮件配置，需包含 ``smtp_host``、``smtp_port``、``mail_from``，
            可选 ``smtp_username``、``smtp_password``、``smtp_use_tls``。
        to: 收件人列表。
        subject: 邮件主题。
        body: 邮件正文。

    Returns:
        是否发送成功。
    """
    smtp_host = config.get("smtp_host")
    if not smtp_host:
        logger.error("发送邮件失败：SMTP 主机未配置")
        return False

    smtp_port = int(config.get("smtp_port", 587))
    smtp_username = config.get("smtp_username")
    smtp_password = config.get("smtp_password")
    smtp_use_tls = config.get("smtp_use_tls", True)
    mail_from = config.get("mail_from", smtp_username or "noreply@rpki.local")

    # 构造邮件内容
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    message = MIMEMultipart("alternative")
    message["From"] = mail_from
    message["To"] = ", ".join(to)
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    try:
        # 使用 smtplib 通过线程池执行同步 SMTP 调用
        import asyncio
        import smtplib

        def _send_smtp() -> None:
            if smtp_use_tls:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            if smtp_username and smtp_password:
                server.login(smtp_username, smtp_password)
            server.sendmail(mail_from, to, message.as_string())
            server.quit()

        await asyncio.to_thread(_send_smtp)
        logger.info("邮件发送成功", to=to, subject=subject)
        return True
    except Exception as e:
        logger.error("邮件发送失败", to=to, subject=subject, error=str(e))
        return False


async def send_sms(
    config: dict[str, Any], to: list[str], message: str
) -> bool:
    """发送短信通知（预留接口）。

    支持的短信服务商：aliyun、tencent、twilio。
    实际生产环境需根据服务商 API 实现具体逻辑。

    Args:
        config: 短信配置，需包含 ``sms_provider``、``sms_api_key``、
            ``sms_api_secret``。
        to: 接收手机号列表。
        message: 短信内容。

    Returns:
        是否发送成功。
    """
    provider = config.get("sms_provider")
    if not provider:
        logger.warning("短信发送失败：短信服务商未配置（预留接口）")
        return False

    api_key = config.get("sms_api_key")
    api_secret = config.get("sms_api_secret")
    if not api_key or not api_secret:
        logger.warning("短信发送失败：API 凭据未配置（预留接口）")
        return False

    # 预留接口：根据服务商调用对应 API
    # 此处仅记录日志，实际实现需对接各服务商 SDK
    logger.info(
        "短信通知（预留接口）",
        provider=provider,
        to=to,
        message=message,
    )
    return True


async def send_voice_call(
    config: dict[str, Any], to: list[str], message: str
) -> bool:
    """发送电话语音通知（预留接口）。

    支持的电话服务商：aliyun、twilio。
    实际生产环境需根据服务商 API 实现具体逻辑。

    Args:
        config: 电话配置，需包含 ``voice_provider``、``api_key``、``api_secret``。
        to: 接收电话号码列表。
        message: 语音内容。

    Returns:
        是否发送成功。
    """
    provider = config.get("voice_provider")
    if not provider:
        logger.warning("电话通知失败：电话服务商未配置（预留接口）")
        return False

    # 预留接口：根据服务商调用对应 API
    logger.info(
        "电话语音通知（预留接口）",
        provider=provider,
        to=to,
        message=message,
    )
    return True


async def send_wechat_work(config: dict[str, Any], message: str) -> bool:
    """发送企业微信群机器人消息。

    Args:
        config: 企业微信配置，需包含 ``wechat_work_webhook``。
        message: 消息内容（文本）。

    Returns:
        是否发送成功。
    """
    webhook_url = config.get("wechat_work_webhook")
    if not webhook_url:
        logger.error("企业微信通知失败：Webhook URL 未配置")
        return False

    payload = {
        "msgtype": "text",
        "text": {"content": message},
    }
    return await _post_webhook(webhook_url, payload, "企业微信")


async def send_dingtalk(config: dict[str, Any], message: str) -> bool:
    """发送钉钉群机器人消息。

    支持加签验证（若配置了 ``dingtalk_secret``）。

    Args:
        config: 钉钉配置，需包含 ``dingtalk_webhook``，可选 ``dingtalk_secret``。
        message: 消息内容（文本）。

    Returns:
        是否发送成功。
    """
    webhook_url = config.get("dingtalk_webhook")
    if not webhook_url:
        logger.error("钉钉通知失败：Webhook URL 未配置")
        return False

    # 加签验证
    secret = config.get("dingtalk_secret")
    if secret:
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{secret}"
        hmac_code = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64_encode(hmac_code))
        webhook_url = f"{webhook_url}&timestamp={timestamp}&sign={sign}"

    payload = {
        "msgtype": "text",
        "text": {"content": message},
    }
    return await _post_webhook(webhook_url, payload, "钉钉")


async def send_slack(config: dict[str, Any], message: str) -> bool:
    """发送 Slack 消息。

    Args:
        config: Slack 配置，需包含 ``slack_webhook``。
        message: 消息内容。

    Returns:
        是否发送成功。
    """
    webhook_url = config.get("slack_webhook")
    if not webhook_url:
        logger.error("Slack 通知失败：Webhook URL 未配置")
        return False

    payload = {"text": message}
    return await _post_webhook(webhook_url, payload, "Slack")


async def send_teams(config: dict[str, Any], message: str) -> bool:
    """发送 Microsoft Teams 消息。

    Args:
        config: Teams 配置，需包含 ``teams_webhook``。
        message: 消息内容。

    Returns:
        是否发送成功。
    """
    webhook_url = config.get("teams_webhook")
    if not webhook_url:
        logger.error("Teams 通知失败：Webhook URL 未配置")
        return False

    payload = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.2",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": message,
                            "wrap": True,
                        }
                    ],
                },
            }
        ],
    }
    return await _post_webhook(webhook_url, payload, "Teams")


async def send_pagerduty(config: dict[str, Any], incident: dict[str, Any]) -> bool:
    """发送 PagerDuty 事件。

    通过 PagerDuty Events API v2 触发事件，支持 trigger、acknowledge、
    resolve 三种事件类型。

    Args:
        config: PagerDuty 配置，需包含 ``pagerduty_integration_key``。
        incident: 事件数据，需包含 ``event_type``（trigger/acknowledge/resolve）、
            ``incident_key``、``description``、``severity``。

    Returns:
        是否发送成功。
    """
    integration_key = config.get("pagerduty_integration_key")
    if not integration_key:
        logger.error("PagerDuty 通知失败：Integration Key 未配置")
        return False

    event_type = incident.get("event_type", "trigger")
    severity = incident.get("severity", "warning")
    # 将平台严重等级映射为 PagerDuty 严重性
    severity_mapping = {
        "P0": "critical",
        "P1": "critical",
        "P2": "error",
        "P3": "warning",
        "P4": "info",
        "critical": "critical",
        "error": "error",
        "warning": "warning",
        "info": "info",
    }
    pagerduty_severity = severity_mapping.get(severity, "warning")

    payload: dict[str, Any] = {
        "routing_key": integration_key,
        "event_action": event_type,
        "dedup_key": incident.get("incident_key", str(incident.get("id", ""))),
    }

    if event_type == "trigger":
        payload["payload"] = {
            "summary": incident.get("description", incident.get("title", "RPKI 事件")),
            "severity": pagerduty_severity,
            "source": "rpki-platform",
            "component": incident.get("component", "rpki"),
            "group": incident.get("group", "network-security"),
            "class": incident.get("class", "incident"),
            "custom_details": incident.get("details", {}),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://events.pagerduty.com/v2/enqueue",
                content=json.dumps(payload, ensure_ascii=False, default=str),
                headers={"Content-Type": "application/json"},
            )
        success = response.status_code < 400
        if not success:
            logger.error(
                "PagerDuty 通知失败",
                status_code=response.status_code,
                body=response.text[:500],
            )
        return success
    except Exception as e:
        logger.error("PagerDuty 通知异常", error=str(e))
        return False


async def send_notification(
    channel: str, config: dict[str, Any], payload: dict[str, Any]
) -> bool:
    """统一通知入口。

    根据通道类型分发到对应的通知发送函数。

    Args:
        channel: 通道类型（email/sms/voice/wechat_work/dingtalk/slack/
            teams/pagerduty）。
        config: 通道配置。
        payload: 通知内容，不同通道所需字段不同：
            - email: to(list)、subject、body
            - sms/voice: to(list)、message
            - wechat_work/dingtalk/slack/teams: message
            - pagerduty: incident(dict)

    Returns:
        是否发送成功。
    """
    channel_handlers = {
        "email": lambda: send_email(
            config,
            payload.get("to", []),
            payload.get("subject", ""),
            payload.get("body", ""),
        ),
        "sms": lambda: send_sms(
            config, payload.get("to", []), payload.get("message", "")
        ),
        "voice": lambda: send_voice_call(
            config, payload.get("to", []), payload.get("message", "")
        ),
        "wechat_work": lambda: send_wechat_work(
            config, payload.get("message", "")
        ),
        "dingtalk": lambda: send_dingtalk(
            config, payload.get("message", "")
        ),
        "slack": lambda: send_slack(
            config, payload.get("message", "")
        ),
        "teams": lambda: send_teams(
            config, payload.get("message", "")
        ),
        "pagerduty": lambda: send_pagerduty(
            config, payload.get("incident", payload)
        ),
    }

    handler = channel_handlers.get(channel)
    if handler is None:
        logger.error("不支持的通知通道", channel=channel)
        return False

    try:
        return await handler()
    except Exception as e:
        logger.error(
            "通知发送异常",
            channel=channel,
            error=str(e),
        )
        return False


# ──────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────


async def _post_webhook(
    url: str, payload: dict[str, Any], channel_name: str
) -> bool:
    """向 Webhook URL 发送 POST 请求。"""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                url,
                content=json.dumps(payload, ensure_ascii=False, default=str),
                headers={"Content-Type": "application/json"},
            )
        success = response.status_code < 400
        if not success:
            logger.error(
                f"{channel_name} 通知失败",
                url=url,
                status_code=response.status_code,
                body=response.text[:500],
            )
        return success
    except Exception as e:
        logger.error(f"{channel_name} 通知异常", url=url, error=str(e))
        return False


def base64_encode(data: bytes) -> str:
    """Base64 编码。"""
    import base64

    return base64.b64encode(data).decode("ascii")


__all__ = [
    "CollaborationAdapter",
    "send_dingtalk",
    "send_email",
    "send_notification",
    "send_pagerduty",
    "send_slack",
    "send_sms",
    "send_teams",
    "send_voice_call",
    "send_wechat_work",
]
