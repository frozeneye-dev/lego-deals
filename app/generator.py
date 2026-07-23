"""
Generates static HTML pages from daily result data.

Output layout (written to docs/):
  index.html          → 항상 최신 할인 결과 (GitHub Pages 루트)
  YYYY-MM-DD.html     → 날짜별 아카이브 페이지
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from jinja2 import Environment, FileSystemLoader, select_autoescape

log = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "docs"
RESULTS_DIR = BASE_DIR / "results"
TEMPLATES_DIR = BASE_DIR / "templates"

KST = pytz.timezone("Asia/Seoul")


def _extract_item_numbers(data: dict) -> set[str]:
    nums: set[str] = set()
    for key in ("40_plus", "30_plus", "20_plus"):
        for item in data.get(key, []):
            n = item.get("item_number", "")
            if n:
                nums.add(n)
    return nums


def _load_item_numbers(path: Path) -> set[str] | None:
    """주어진 결과 파일의 할인 카테고리(20%+) 품번 집합. 파일 없으면 None."""
    if not path.exists():
        return None
    try:
        return _extract_item_numbers(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        log.warning("결과 파일 읽기 실패: %s", path)
        return None


def _load_yesterday_item_numbers(run_date: str) -> set[str] | None:
    """어제 할인 카테고리(20%+)에 있던 품번 집합. 파일 없으면 None."""
    yesterday = (datetime.strptime(run_date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    return _load_item_numbers(RESULTS_DIR / f"{yesterday}.json")


def _sort_new_first(items: list[dict], prev: set[str] | None) -> list[dict]:
    if prev is None:
        return items
    return sorted(items, key=lambda x: (0 if x.get("item_number", "") not in prev else 1))


def _jinja_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["comma"] = lambda v: f"{v:,}" if v is not None else "—"
    env.filters["pct"] = lambda v: f"{v * 100:.1f}%" if v is not None else "—"
    return env


def generate(result: dict, settings: dict, run_date: str | None = None) -> tuple[str, int]:
    """
    Write docs/YYYY-MM-DD.html and docs/index.html (= today).
    Returns (run_date, notify_new_count) — notify_new_count is how many items
    are newly discounted since the previous run (same day if this isn't the
    first run of the day, otherwise yesterday). Callers use it to decide
    whether a Discord notification is warranted (하루 여러 번 스크래핑해도
    새 할인이 없으면 알림을 또 보내지 않기 위함).
    """
    OUTPUT_DIR.mkdir(exist_ok=True)
    RESULTS_DIR.mkdir(exist_ok=True)

    if run_date is None:
        run_date = datetime.now(KST).strftime("%Y-%m-%d")

    result_path = RESULTS_DIR / f"{run_date}.json"

    # 알림용 신규 판별 기준: 오늘 이전 실행 결과가 있으면 그것, 없으면 어제 결과
    prev_run_nums = _load_item_numbers(result_path)
    notify_baseline = prev_run_nums if prev_run_nums is not None else _load_yesterday_item_numbers(run_date)

    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if notify_baseline is None:
        notify_new_count = sum(len(result.get(k, [])) for k in ("40_plus", "30_plus", "20_plus"))
    else:
        notify_new_count = len(_extract_item_numbers(result) - notify_baseline)

    yesterday_nums = _load_yesterday_item_numbers(run_date)

    # 신규 진입 상품을 각 카테고리 상단으로 정렬
    sorted_result = {
        "40_plus": _sort_new_first(result.get("40_plus", []), yesterday_nums),
        "30_plus": _sort_new_first(result.get("30_plus", []), yesterday_nums),
        "20_plus": _sort_new_first(result.get("20_plus", []), yesterday_nums),
        "no_price": result.get("no_price", []),
    }

    pages_url = settings.get("github_pages_url", "").rstrip("/")

    env = _jinja_env()
    tmpl = env.get_template("deals.html")

    total_count = sum(
        len(result.get(k, []))
        for k in ("40_plus", "30_plus", "20_plus", "no_price")
    )

    new_count = 0
    if yesterday_nums is not None:
        for key in ("40_plus", "30_plus", "20_plus"):
            for item in result.get(key, []):
                if item.get("item_number", "") not in yesterday_nums:
                    new_count += 1

    html = tmpl.render(
        date=run_date,
        result=sorted_result,
        total_count=total_count,
        new_count=new_count,
        yesterday_nums=yesterday_nums,
        pages_url=pages_url,
        settings=settings,
    )

    daily_path = OUTPUT_DIR / f"{run_date}.html"
    daily_path.write_text(html, encoding="utf-8")

    # index.html = 항상 최신 결과 (GitHub Pages 루트)
    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")
    # today.html = Flask /output/today 폴백 파일도 항상 동기화
    (OUTPUT_DIR / "today.html").write_text(html, encoding="utf-8")

    log.info("Generated docs/%s.html  (index.html, today.html updated, 신규 %d건)", run_date, notify_new_count)
    return run_date, notify_new_count
