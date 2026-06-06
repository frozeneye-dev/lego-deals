import logging

import requests

log = logging.getLogger(__name__)


def send_discord(webhook_url: str, pages_url: str, run_date: str) -> bool:
    """POST a short deal-link message to a Discord webhook. Returns True on success."""
    if not webhook_url:
        log.warning("Discord webhook URL not configured — skipping notification.")
        return False

    site_url = pages_url.rstrip("/") + "/"
    payload = {
        "content": (
            f"🧱 오늘 할인목록 완성되었습니다\n"
            f"{site_url}"
        )
    }

    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        resp.raise_for_status()
        log.info("Discord notification sent.")
        return True
    except Exception:
        log.exception("Failed to send Discord notification.")
        return False
