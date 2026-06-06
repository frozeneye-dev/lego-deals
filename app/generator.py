"""
Generates static HTML pages from daily result data.

Output layout (written to docs/):
  index.html          → 항상 최신 할인 결과 (GitHub Pages 루트)
  YYYY-MM-DD.html     → 날짜별 아카이브 페이지
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pytz
from jinja2 import Environment, FileSystemLoader, select_autoescape

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "docs"
RESULTS_DIR = BASE_DIR / "results"
TEMPLATES_DIR = BASE_DIR / "templates"

KST = pytz.timezone("Asia/Seoul")


def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["comma"] = lambda v: f"{v:,}" if v is not None else "—"
    env.filters["pct"] = lambda v: f"{v * 100:.1f}%" if v is not None else "—"
    return env


def generate(result: dict, settings: dict, run_date: str | None = None) -> str:
    """
    Write docs/YYYY-MM-DD.html and docs/index.html (= today).
    Returns the date string used (YYYY-MM-DD).
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    if run_date is None:
        run_date = datetime.now(KST).strftime("%Y-%m-%d")

    result_path = RESULTS_DIR / f"{run_date}.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    pages_url = settings.get("github_pages_url", "").rstrip("/")

    env = _jinja_env()
    tmpl = env.get_template("deals.html")

    total_count = sum(
        len(result.get(k, []))
        for k in ("40_plus", "30_plus", "20_plus", "no_price")
    )

    html = tmpl.render(
        date=run_date,
        result=result,
        total_count=total_count,
        pages_url=pages_url,
        settings=settings,
    )

    daily_path = OUTPUT_DIR / f"{run_date}.html"
    daily_path.write_text(html, encoding="utf-8")

    # index.html = 항상 오늘 결과 (GitHub Pages 루트 URL로 바로 접근)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")

    log.info("Generated docs/%s.html  (index.html updated)", run_date)
    return run_date
