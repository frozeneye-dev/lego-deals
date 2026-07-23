"""
One-shot scrape script for GitHub Actions.

Usage:
    python scripts/run_scrape.py

Reads config from config/*.json.
DISCORD_WEBHOOK_URL env var overrides settings.json (set as GitHub Secret).
Exits with code 1 on error so GitHub Actions marks the run as failed.
"""

import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("run_scrape")

import config as cfg
from app.scraper.coordinator import run_pipeline
from app.generator import generate
from app.notifier import send_discord


def main():
    settings = cfg.load_settings()
    sources = cfg.load_sources()
    prices = cfg.load_prices()

    # GitHub Secrets override stored values
    env_webhook = os.environ.get("DISCORD_WEBHOOK", "").strip()
    if env_webhook:
        settings["discord_webhook_url"] = env_webhook

    env_naver_id = os.environ.get("NAVER_CLIENT_ID", "").strip()
    env_naver_secret = os.environ.get("NAVER_CLIENT_SECRET", "").strip()
    if env_naver_id:
        settings["naver_client_id"] = env_naver_id
    if env_naver_secret:
        settings["naver_client_secret"] = env_naver_secret

    if not sources:
        log.warning("No sources registered. Add sources via the web UI and commit config/sources.json.")

    log.info("Running pipeline with %d source(s)…", len(sources))
    result = run_pipeline(sources, prices, settings)
    cfg.save_prices(prices)   # 자동 조회로 갱신된 정가 저장

    total = sum(len(v) for k, v in result.items() if k != "no_price")
    log.info(
        "Results: 40%%+ = %d, 30%%+ = %d, 20%%+ = %d, 정가미등록 = %d",
        len(result["40_plus"]),
        len(result["30_plus"]),
        len(result["20_plus"]),
        len(result["no_price"]),
    )

    run_date, new_count = generate(result, settings)
    log.info("Pages written to docs/  (date: %s)", run_date)

    pages_url = settings.get("github_pages_url", "")
    if not pages_url:
        log.warning("github_pages_url not set — Discord notification skipped.")
    elif new_count == 0:
        log.info("신규 할인 없음 — Discord 알림 생략")
    else:
        send_discord(settings["discord_webhook_url"], pages_url, run_date)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("Fatal error in run_scrape.py")
        sys.exit(1)
