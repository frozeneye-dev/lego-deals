import logging
import os

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger(__name__)
KST = pytz.timezone("Asia/Seoul")


def _daily_job():
    """Called by APScheduler. Imports here to avoid circular imports."""
    import config as cfg
    from app.scraper.coordinator import run_pipeline
    from app.generator import generate
    from app.notifier import send_discord

    settings = cfg.load_settings()
    sources = cfg.load_sources()
    prices = cfg.load_prices()

    log.info("Daily job started.")
    result = run_pipeline(sources, prices, settings)
    run_date = generate(result, settings)

    pages_url = settings.get("github_pages_url", "")
    if pages_url:
        send_discord(settings.get("discord_webhook_url", ""), pages_url, run_date)
    log.info("Daily job finished.")


def build_scheduler() -> BackgroundScheduler:
    return BackgroundScheduler(timezone=KST)


def start_scheduler(scheduler: BackgroundScheduler, app) -> None:
    """Schedule the daily job based on current settings."""
    import config as cfg
    settings = cfg.load_settings()
    hour = int(settings.get("schedule_hour", 9))
    minute = int(settings.get("schedule_minute", 0))

    scheduler.add_job(
        _daily_job,
        trigger="cron",
        hour=hour,
        minute=minute,
        id="daily_scrape",
        replace_existing=True,
    )
    if not scheduler.running:
        scheduler.start()
    log.info("Scheduler started — daily job at %02d:%02d KST", hour, minute)
