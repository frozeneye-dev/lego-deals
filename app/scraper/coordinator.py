"""
Orchestrates scraping and deal calculation.

Flow:
  sources → parsers → raw ScrapedItems
  → apply prices & discounts → DealItem list
  → deduplicate by item_number (keep lowest final_price)
  → sort into categories
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.scraper.parsers import ALL_PARSERS
from app.scraper.parsers.base import ScrapedItem

log = logging.getLogger(__name__)


@dataclass
class DealItem:
    item_number: str
    name: str
    official_price: Optional[int]   # None = 정가 미등록
    listed_price: int
    additional_discount: float      # actual value used (global or per-source)
    final_price: Optional[int]      # None if no official_price
    discount_rate: Optional[float]  # 0.36 = 36% off official price
    product_url: str
    source_name: str
    source_url: str
    scraped_at: Optional[str] = None


def _get_parser(url: str):
    for p in ALL_PARSERS:
        if p.can_parse(url):
            return p
    return None


def scrape_sources(sources: list[dict]) -> list[ScrapedItem]:
    """Fetch all enabled sources and return raw ScrapedItems."""
    raw: list[ScrapedItem] = []
    for src in sources:
        if not src.get("enabled", True):
            continue
        url = src["url"]
        parser = _get_parser(url)
        if parser is None:
            log.warning("No parser available for %s – skipping.", url)
            continue
        try:
            items = parser.parse(url, src["name"])
            src_discount = src.get("additional_discount")
            src_trusted = src.get("trusted_price", False)
            for item in items:
                if src_discount is not None:
                    item.additional_discount = src_discount
                item.trusted_price = src_trusted
            raw.extend(items)
            log.info("Source '%s' → %d items", src["name"], len(items))
        except Exception:
            log.exception("Error scraping source '%s' (%s)", src["name"], url)
    return raw


def calculate_deals(
    raw_items: list[ScrapedItem],
    prices: dict,
    settings: dict,
) -> list[DealItem]:
    """
    Convert raw items to DealItems, deduplicate by item_number keeping
    the lowest final_price, and return the list.
    """
    global_discount: float = float(settings.get("global_additional_discount", 0.0))
    best: dict[str, DealItem] = {}

    for item in raw_items:
        price_info = prices.get(item.item_number)
        official_price: Optional[int] = price_info["official_price"] if price_info else None

        add_disc = item.additional_discount if item.additional_discount is not None else global_discount

        if official_price:
            final_price = int(item.listed_price * (1 - add_disc))
            discount_rate = round(1 - final_price / official_price, 4)
        else:
            final_price = None
            discount_rate = None

        name = item.name
        if price_info and price_info.get("name") and not name:
            name = price_info["name"]

        deal = DealItem(
            item_number=item.item_number,
            name=name,
            official_price=official_price,
            listed_price=item.listed_price,
            additional_discount=add_disc,
            final_price=final_price,
            discount_rate=discount_rate,
            product_url=item.product_url,
            source_name=item.source_name,
            source_url=item.source_url,
            scraped_at=item.scraped_at,
        )

        key = item.item_number
        existing = best.get(key)
        if existing is None:
            best[key] = deal
        else:
            # Lower final_price wins; if one has None, prefer the one with a price
            if final_price is not None and (
                existing.final_price is None or final_price < existing.final_price
            ):
                best[key] = deal

    return sorted(best.values(), key=lambda d: (d.discount_rate or 0), reverse=True)


def categorize(deals: list[DealItem]) -> dict[str, list[DealItem]]:
    """Split deals into discount-rate buckets."""
    cat40, cat30, cat20, no_price = [], [], [], []
    for d in deals:
        if d.discount_rate is None:
            no_price.append(d)
        elif d.discount_rate >= 0.40:
            cat40.append(d)
        elif d.discount_rate >= 0.30:
            cat30.append(d)
        elif d.discount_rate >= 0.20:
            cat20.append(d)
        # Below 20% is ignored
    return {
        "40_plus": cat40,
        "30_plus": cat30,
        "20_plus": cat20,
        "no_price": no_price,
    }


def enrich_prices(raw: list[ScrapedItem], prices: dict, settings: dict | None = None) -> int:
    """
    새 품번에 대해 자동 정가 조회를 시도하고 prices dict를 갱신합니다.
    이미 prices에 있는 품번은 건드리지 않습니다.

    조회 순서:
      1. 소스 페이지 취소선 가격 (마트 표시 원가, KRW) — 추가 요청 없음
      2. brickset 공식 API — settings에 brickset_api_key 가 있어야 동작

    Returns: 새로 등록된 항목 수.
    """
    from app.price_lookup import lookup_official_price

    brickset_key = (settings or {}).get("brickset_api_key", "").strip()

    # 처리 대상:
    #   - prices에 없는 새 품번
    #   - prices에 있지만 official_price가 null인 품번 (신뢰 소스에서 채울 기회)
    # 같은 품번이 여러 소스에 있으면 "신뢰+original_price"를 우선 선택
    candidates: dict[str, ScrapedItem] = {}
    for item in raw:
        is_new = item.item_number not in prices
        needs_price = (
            not is_new
            and prices[item.item_number].get("official_price") is None
            and item.trusted_price
            and item.original_price
        )
        if not (is_new or needs_price):
            continue
        existing = candidates.get(item.item_number)
        if existing is None:
            candidates[item.item_number] = item
        elif (not existing.trusted_price or not existing.original_price) and (item.trusted_price and item.original_price):
            candidates[item.item_number] = item
        elif existing.original_price is None and item.original_price is not None:
            candidates[item.item_number] = item

    added = 0
    for item_number, item in candidates.items():
        is_new = item_number not in prices

        # 신뢰 소스 + original_price → 정가 등록 (신규 또는 null 업데이트)
        if item.original_price and item.trusted_price:
            if item.original_price > item.listed_price:
                source_label = f"{item.source_name} 취소선 정가"
            else:
                source_label = f"{item.source_name} 표시가"
            if is_new:
                prices[item_number] = {
                    "name": item.name,
                    "official_price": item.original_price,
                    "auto": True,
                    "source": source_label,
                    "currency": "KRW",
                }
            else:
                prices[item_number]["official_price"] = item.original_price
                prices[item_number]["source"] = source_label
                if not prices[item_number].get("name"):
                    prices[item_number]["name"] = item.name
            log.info("[enrich] [%s] %d원 등록 (%s)", item_number, item.original_price, source_label)
            added += 1
            continue

        # 신규 + 비신뢰 소스: 품번·이름만 등록, 정가는 비워둠
        if is_new and item.original_price and not item.trusted_price:
            prices[item_number] = {
                "name": item.name,
                "official_price": None,
                "auto": True,
                "source": f"{item.source_name} (정가 미인증)",
                "currency": "KRW",
            }
            log.info("[enrich] [%s] 이름만 등록 (비신뢰 소스: %s)", item_number, item.source_name)
            added += 1
            continue

        # 2순위: brickset 공식 API (API 키 없으면 건너뜀)
        if not brickset_key:
            log.debug("[enrich] [%s] brickset API 키 미설정 → 건너뜀", item_number)
            continue

        try:
            result = lookup_official_price(item_number, brickset_key)
        except Exception:
            log.exception("[enrich] [%s] brickset API 오류", item_number)
            result = None

        if result:
            if not result.get("name"):
                result["name"] = item.name
            prices[item_number] = result
            log.info(
                "[enrich] [%s] brickset API %s %s 등록",
                item_number, result["official_price"], result["currency"],
            )
            added += 1
        else:
            log.info("[enrich] [%s] 자동 조회 실패 → 정가 미등록", item_number)

    return added


_MAX_YEAR_LOOKUPS_PER_RUN = 20


def enrich_years(prices: dict, settings: dict | None = None) -> int:
    """
    출시년도(year)가 없는 품번에 대해 brickset API로 연도를 채웁니다.
    정가 출처와 무관하게 동작 (취소선 정가로 이미 official_price가 있어도
    year가 없으면 채움). 매 실행마다 최대 _MAX_YEAR_LOOKUPS_PER_RUN개까지만
    조회해 브릭셋 API 호출을 완만하게 분산시킵니다 — 한 번 채운 연도는
    다시 조회하지 않으므로 몇 번의 실행이면 전체가 채워집니다.

    Returns: 새로 채운 개수.
    """
    from app.price_lookup import lookup_set_year

    brickset_key = (settings or {}).get("brickset_api_key", "").strip()
    if not brickset_key:
        return 0

    added = 0
    for item_number, info in prices.items():
        if added >= _MAX_YEAR_LOOKUPS_PER_RUN:
            break
        if info.get("year"):
            continue
        try:
            year = lookup_set_year(item_number, brickset_key)
        except Exception:
            log.exception("[enrich-year] [%s] brickset API 오류", item_number)
            continue
        if year:
            info["year"] = year
            log.info("[enrich-year] [%s] %d년 등록", item_number, year)
            added += 1

    return added


def run_pipeline(sources: list[dict], prices: dict, settings: dict) -> dict:
    """
    Full pipeline: scrape → enrich prices → enrich years → calculate → categorize.
    prices dict가 갱신되면 호출 측에서 save_prices()로 저장해야 합니다.
    Returns a result dict ready for the HTML generator and JSON storage.
    """
    raw = scrape_sources(sources)
    enrich_prices(raw, prices, settings)   # prices dict 제자리 갱신
    enrich_years(prices, settings)         # prices dict 제자리 갱신 (연도)
    deals = calculate_deals(raw, prices, settings)
    cats = categorize(deals)

    def deal_to_dict(d: DealItem) -> dict:
        return {
            "item_number": d.item_number,
            "name": d.name,
            "official_price": d.official_price,
            "listed_price": d.listed_price,
            "additional_discount": d.additional_discount,
            "final_price": d.final_price,
            "discount_rate": d.discount_rate,
            "product_url": d.product_url,
            "source_name": d.source_name,
            "source_url": d.source_url,
            "scraped_at": d.scraped_at,
        }

    return {
        "40_plus": [deal_to_dict(d) for d in cats["40_plus"]],
        "30_plus": [deal_to_dict(d) for d in cats["30_plus"]],
        "20_plus": [deal_to_dict(d) for d in cats["20_plus"]],
        "no_price": [deal_to_dict(d) for d in cats["no_price"]],
    }
