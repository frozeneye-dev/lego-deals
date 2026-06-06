"""
Flask web UI routes.

Admin pages:
  /                  → dashboard
  /sources           → manage source URLs
  /prices            → manage official LEGO prices
  /settings          → bot configuration
  /run               → manual trigger + log view
  /test-parse        → test a URL with available parsers
  /output/<date>     → 날짜별 할인 결과 HTML (예: /output/2026-06-07)
  /output/today      → 오늘 할인 결과
"""

import json
import logging
import threading
import uuid
from datetime import datetime
from pathlib import Path

import pytz
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import config as cfg

bp = Blueprint("main", __name__)
KST = pytz.timezone("Asia/Seoul")
log = logging.getLogger(__name__)

# Simple in-memory log capture for the /run page
_run_log: list[str] = []
_run_lock = threading.Lock()


def _log(msg: str):
    ts = datetime.now(KST).strftime("%H:%M:%S")
    with _run_lock:
        _run_log.append(f"[{ts}] {msg}")
        if len(_run_log) > 200:
            _run_log.pop(0)


# ── Dashboard ────────────────────────────────────────────────────────────────

@bp.get("/")
def index():
    sources = cfg.load_sources()
    prices = cfg.load_prices()
    settings = cfg.load_settings()
    output_dir = Path(__file__).parent.parent / "docs"
    daily_pages = sorted(output_dir.glob("????-??-??.html"), reverse=True)
    return render_template(
        "admin/index.html",
        sources=sources,
        prices=prices,
        settings=settings,
        daily_pages=[p.stem for p in daily_pages[:10]],
    )


# ── Sources ───────────────────────────────────────────────────────────────────

@bp.get("/sources")
def sources_page():
    return render_template("admin/sources.html", sources=cfg.load_sources())


@bp.post("/sources/add")
def sources_add():
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    add_disc_raw = request.form.get("additional_discount", "").strip()

    if not name or not url:
        flash("이름과 URL을 모두 입력해 주세요.", "error")
        return redirect(url_for("main.sources_page"))

    add_disc = None
    if add_disc_raw:
        try:
            add_disc = float(add_disc_raw)
            if not (0 <= add_disc < 1):
                raise ValueError
        except ValueError:
            flash("추가 할인율은 0 이상 1 미만의 소수로 입력하세요. (예: 0.2)", "error")
            return redirect(url_for("main.sources_page"))

    # Check parser availability
    from app.scraper.parsers import ALL_PARSERS
    parser_found = any(p.can_parse(url) for p in ALL_PARSERS)
    if not parser_found:
        flash(f"이 URL을 처리할 수 있는 파서가 없습니다: {url}", "warning")

    sources = cfg.load_sources()
    sources.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "url": url,
        "additional_discount": add_disc,
        "enabled": True,
        "added_at": datetime.now(KST).strftime("%Y-%m-%d"),
    })
    cfg.save_sources(sources)
    flash(f"소스 '{name}' 이 추가되었습니다.", "success")
    return redirect(url_for("main.sources_page"))


@bp.post("/sources/<source_id>/delete")
def sources_delete(source_id):
    sources = [s for s in cfg.load_sources() if s["id"] != source_id]
    cfg.save_sources(sources)
    flash("소스가 삭제되었습니다.", "success")
    return redirect(url_for("main.sources_page"))


@bp.post("/sources/<source_id>/toggle")
def sources_toggle(source_id):
    sources = cfg.load_sources()
    for s in sources:
        if s["id"] == source_id:
            s["enabled"] = not s.get("enabled", True)
    cfg.save_sources(sources)
    return redirect(url_for("main.sources_page"))


# ── Prices ────────────────────────────────────────────────────────────────────

@bp.get("/prices")
def prices_page():
    return render_template("admin/prices.html", prices=cfg.load_prices())


@bp.post("/prices/save")
def prices_save():
    """Accept a bulk JSON payload from the price editor."""
    raw = request.form.get("prices_json", "")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        flash("JSON 형식이 올바르지 않습니다.", "error")
        return redirect(url_for("main.prices_page"))

    prices = cfg.load_prices()
    for item_number, info in data.items():
        item_number = item_number.strip()
        if not item_number:
            continue
        try:
            official_price = int(str(info.get("official_price", 0)).replace(",", ""))
        except (ValueError, TypeError):
            official_price = 0
        prices[item_number] = {
            "name": str(info.get("name", "")).strip(),
            "official_price": official_price,
        }
    cfg.save_prices(prices)
    flash("정가 정보가 저장되었습니다.", "success")
    return redirect(url_for("main.prices_page"))


@bp.post("/prices/add")
def prices_add():
    item_number = request.form.get("item_number", "").strip()
    name = request.form.get("name", "").strip()
    price_raw = request.form.get("official_price", "").strip().replace(",", "")

    if not item_number or not price_raw:
        flash("품번과 정가를 모두 입력해 주세요.", "error")
        return redirect(url_for("main.prices_page"))

    try:
        official_price = int(price_raw)
    except ValueError:
        flash("정가는 숫자만 입력하세요.", "error")
        return redirect(url_for("main.prices_page"))

    prices = cfg.load_prices()
    prices[item_number] = {
        "name": name,
        "official_price": official_price,
        "auto": False,
        "source": "수동 입력",
        "currency": "KRW",
    }
    cfg.save_prices(prices)
    flash(f"품번 {item_number} 정가가 등록되었습니다.", "success")
    return redirect(url_for("main.prices_page"))


@bp.post("/prices/<item_number>/edit")
def prices_edit(item_number):
    """인라인 수정 — 가격만 변경, 이름 유지, auto 플래그 해제."""
    price_raw = request.form.get("official_price", "").strip().replace(",", "")
    name = request.form.get("name", "").strip()

    try:
        official_price = int(price_raw)
    except ValueError:
        flash("정가는 숫자만 입력하세요.", "error")
        return redirect(url_for("main.prices_page"))

    prices = cfg.load_prices()
    existing = prices.get(item_number, {})
    prices[item_number] = {
        "name": name or existing.get("name", ""),
        "official_price": official_price,
        "auto": False,          # 직접 수정했으므로 auto 플래그 해제
        "source": "수동 수정",
        "currency": "KRW",
    }
    cfg.save_prices(prices)
    flash(f"품번 {item_number} 정가가 수정되었습니다.", "success")
    return redirect(url_for("main.prices_page"))


@bp.post("/prices/<item_number>/delete")
def prices_delete(item_number):
    prices = cfg.load_prices()
    prices.pop(item_number, None)
    cfg.save_prices(prices)
    flash(f"품번 {item_number} 이 삭제되었습니다.", "success")
    return redirect(url_for("main.prices_page"))


# ── Settings ──────────────────────────────────────────────────────────────────

@bp.get("/settings")
def settings_page():
    return render_template("admin/settings.html", settings=cfg.load_settings())


@bp.post("/settings/save")
def settings_save():
    f = request.form
    settings = cfg.load_settings()

    settings["discord_webhook_url"] = f.get("discord_webhook_url", "").strip()
    settings["github_pages_url"] = f.get("github_pages_url", "").strip()
    settings["github_username"] = f.get("github_username", "").strip()
    settings["github_repo"] = f.get("github_repo", "lego-deals").strip()
    settings["brickset_api_key"] = f.get("brickset_api_key", "").strip()

    try:
        settings["schedule_hour"] = int(f.get("schedule_hour", 9))
        settings["schedule_minute"] = int(f.get("schedule_minute", 0))
    except ValueError:
        flash("실행 시각은 정수로 입력해 주세요.", "error")
        return redirect(url_for("main.settings_page"))

    try:
        disc = float(f.get("global_additional_discount", 0))
        if not (0 <= disc < 1):
            raise ValueError
        settings["global_additional_discount"] = disc
    except ValueError:
        flash("전역 추가 할인율은 0 이상 1 미만의 소수로 입력하세요.", "error")
        return redirect(url_for("main.settings_page"))

    cfg.save_settings(settings)
    flash("설정이 저장되었습니다.", "success")
    return redirect(url_for("main.settings_page"))


# ── Manual run ────────────────────────────────────────────────────────────────

@bp.get("/run")
def run_page():
    with _run_lock:
        logs = list(_run_log)
    return render_template("admin/run.html", logs=logs)


@bp.post("/run/start")
def run_start():
    def _task():
        from app.scraper.coordinator import run_pipeline
        from app.generator import generate
        from app.notifier import send_discord

        settings = cfg.load_settings()
        sources = cfg.load_sources()
        prices = cfg.load_prices()

        _log("스크래핑 시작...")
        try:
            result = run_pipeline(sources, prices, settings)
            cfg.save_prices(prices)   # 자동 조회 결과 저장
            total = sum(len(v) for v in result.values())
            _log(f"스크래핑 완료: 총 {total}개 상품")
            run_date = generate(result, settings)
            _log(f"HTML 생성 완료: output/{run_date}.html")
            pages_url = settings.get("github_pages_url", "")
            if pages_url:
                ok = send_discord(settings.get("discord_webhook_url", ""), pages_url, run_date)
                _log("Discord 알림 전송 완료" if ok else "Discord 알림 실패 (로그 확인)")
            else:
                _log("GitHub Pages URL 미설정 — Discord 알림 생략")
        except Exception as e:
            _log(f"오류 발생: {e}")

    threading.Thread(target=_task, daemon=True).start()
    flash("실행이 시작되었습니다. 잠시 후 로그를 확인하세요.", "info")
    return redirect(url_for("main.run_page"))


# ── Output viewer ────────────────────────────────────────────────────────────

@bp.get("/output/today")
def output_today():
    output_dir = Path(__file__).parent.parent / "docs"
    today = datetime.now(KST).strftime("%Y-%m-%d")
    f = output_dir / f"{today}.html"
    if not f.exists():
        f = output_dir / "today.html"
    if not f.exists():
        abort(404)
    return send_file(f)


@bp.get("/output/<date>")
def output_date(date):
    output_dir = Path(__file__).parent.parent / "docs"
    f = output_dir / f"{date}.html"
    if not f.exists():
        abort(404)
    return send_file(f)


# ── Parse test ───────────────────────────────────────────────────────────────

@bp.get("/test-parse")
def test_parse_page():
    return render_template("admin/test_parse.html", result=None, url="")


@bp.post("/test-parse")
def test_parse_run():
    url = request.form.get("url", "").strip()
    if not url:
        flash("URL을 입력해 주세요.", "error")
        return redirect(url_for("main.test_parse_page"))

    from app.scraper.parsers import ALL_PARSERS
    parser = next((p for p in ALL_PARSERS if p.can_parse(url)), None)
    if parser is None:
        flash(f"파서를 찾을 수 없습니다: {url}", "error")
        return render_template("admin/test_parse.html", result=None, url=url)

    error = None
    items = []
    try:
        items = parser.parse(url, "테스트")
    except Exception as e:
        error = str(e)

    return render_template(
        "admin/test_parse.html",
        result=items,
        url=url,
        error=error,
        parser_name=type(parser).__name__,
    )
