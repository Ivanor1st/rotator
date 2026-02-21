import logging
from typing import Any

import httpx
from plyer import notification

logger = logging.getLogger("rotator.notifier")


def send_notification(title: str, message: str) -> None:
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="API Rotator",
            timeout=5,
        )
    except Exception:
        logger.debug("Desktop notification failed", exc_info=True)


async def send_webhook(event_type: str, message: str, details: dict[str, Any], config: dict[str, Any]) -> None:
    hooks = config.get("webhooks", {}) if config else {}
    discord = hooks.get("discord")
    slack = hooks.get("slack")
    telegram_token = hooks.get("telegram_token")
    telegram_chat_id = hooks.get("telegram_chat_id")

    payload = {
        "event": event_type,
        "message": message,
        "details": details,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        if discord:
            try:
                await client.post(discord, json={"content": f"{message}\n```json\n{payload}\n```"})
            except Exception:
                logger.debug("Discord webhook failed", exc_info=True)
        if slack:
            try:
                await client.post(slack, json={"text": f"{message}\n```{payload}```"})
            except Exception:
                logger.debug("Slack webhook failed", exc_info=True)
        if telegram_token and telegram_chat_id:
            try:
                url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
                await client.post(url, json={"chat_id": telegram_chat_id, "text": f"{message}\n{payload}"})
            except Exception:
                logger.debug("Telegram webhook failed", exc_info=True)