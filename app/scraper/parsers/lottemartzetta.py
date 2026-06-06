"""
Parser for 롯데마트 제타 (lottemartzetta.com).

robots.txt status (checked 2026-06-06):
  Allow: /   Disallow: /api/, /events/
  → Product pages are permitted.

Verified HTML structure (2026-06-07, /offers/<uuid> pages):
  Card       : div.product-card-container
  Set number : \((\d{4,6})\) pattern inside h3 product name text
  Listed price: span[class*="_display--promotion_"]  (e.g. "33,675원")
  Strikethrough: span[class*="_text--strikethrough_"] (retailer original, NOT used)
  Product link: a[data-test="fop-product-link"]
  Add'l disc  : span.promotion-description texts → find "(\d+)%.*?추가" pattern

Source URL format: https://lottemartzetta.com/offers/<uuid>
(Find active deals via site search or the /promotions page.)
"""

import logging
import re
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from app.scraper.parsers.base import BaseParser, ScrapedItem

log = logging.getLogger(__name__)

# Set number must appear in parentheses inside product name: "(43239)"
_SET_NO_IN_PARENS = re.compile(r"\((\d{4,6})\)")
# Fallback: any 4–6 digit number not preceded/followed by another digit
_SET_NO_FALLBACK = re.compile(r"(?<!\d)(\d{4,6})(?!\d)")
# Additional discount text pattern: "카드 20% 추가 할인" → 20
_ADD_DISC_RE = re.compile(r"(\d+)\s*%.*?추가")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
}


class LotteMartZettaParser(BaseParser):
    def can_parse(self, url: str) -> bool:
        return "lottemartzetta.com" in url

    def parse(self, url: str, source_name: str) -> list[ScrapedItem]:
        resp = requests.get(url, headers=_HEADERS, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        items = self._extract_items(soup, url, source_name)
        log.info("[LotteMartZetta] %s → %d items found", url, len(items))
        return items

    # ------------------------------------------------------------------

    def _extract_items(
        self, soup: BeautifulSoup, base_url: str, source_name: str
    ) -> list[ScrapedItem]:
        results: list[ScrapedItem] = []
        seen: set[str] = set()

        # Strategy 1 – /offers/<uuid> page structure (verified 2026-06-07)
        cards = soup.select("div.product-card-container")
        if cards:
            log.debug("[LotteMartZetta] offers-page layout: %d cards", len(cards))
            for card in cards:
                item = self._parse_offers_card(card, base_url, source_name)
                if item and item.item_number not in seen:
                    seen.add(item.item_number)
                    results.append(item)
            return results

        # Strategy 2 – generic product list selectors (future page types)
        generic_selectors = [
            "li.prd_item", "li.product_item",
            "div.prd_item", "div.product_item",
            "li[class*='prd']", "div[class*='prd_info']",
            "ul.prd_list > li", "ul.product_list > li",
        ]
        cards_generic: list[Tag] = []
        for sel in generic_selectors:
            cards_generic = soup.select(sel)
            if cards_generic:
                log.debug("[LotteMartZetta] generic selector %r: %d cards", sel, len(cards_generic))
                break

        if cards_generic:
            for card in cards_generic:
                item = self._parse_generic_card(card, base_url, source_name)
                if item and item.item_number not in seen:
                    seen.add(item.item_number)
                    results.append(item)
            return results

        # Strategy 3 – full-page regex fallback
        log.warning(
            "[LotteMartZetta] No product cards matched — falling back to page-wide regex scan."
        )
        return self._regex_fallback(soup, base_url, source_name)

    # ------------------------------------------------------------------
    # /offers/<uuid> page parser (primary)
    # ------------------------------------------------------------------

    def _parse_offers_card(
        self, card: Tag, base_url: str, source_name: str
    ) -> Optional[ScrapedItem]:
        # Product name (h3 contains set number in parentheses)
        name_el = card.select_one("h3")
        if name_el is None:
            return None
        name = name_el.get_text(strip=True)

        # Set number: prefer parenthesised form "(43239)"
        m = _SET_NO_IN_PARENS.search(name)
        if not m:
            m = _SET_NO_FALLBACK.search(name)
        if not m:
            return None
        item_number = m.group(1)

        # Sale price: span whose class contains "_display--promotion_"
        price_el = card.select_one('span[class*="_display--promotion_"]')
        if price_el is None:
            # Fallback: price-pack-size-container → first numeric text
            container = card.select_one("div.price-pack-size-container")
            if container:
                price_el = container.select_one("span")
        if price_el is None:
            return None

        listed_price = self._price_int(price_el.get_text())
        if not listed_price:
            return None

        # Additional discount: read all promotion-description spans, find "N% 추가"
        additional_discount = self._extract_additional_discount(card)

        # Strikethrough price = retailer's "original" pre-sale price (often LEGO official KRW)
        strike_el = card.select_one('span[class*="_text--strikethrough_"]')
        original_price = self._price_int(strike_el.get_text()) if strike_el else None

        # Product link
        link_el = card.select_one('a[data-test="fop-product-link"]')
        if link_el is None:
            link_el = card.select_one("a[href*='/products/']")
        product_url = (
            self._absolute_url(link_el["href"], base_url) if link_el else base_url
        )

        return ScrapedItem(
            item_number=item_number,
            name=name,
            listed_price=listed_price,
            additional_discount=additional_discount,
            original_price=original_price,
            product_url=product_url,
            source_name=source_name,
            source_url=base_url,
        )

    @staticmethod
    def _extract_additional_discount(card: Tag) -> Optional[float]:
        """
        Look for promotion texts like "카드 20% 추가 할인" inside the card
        and return the rate as a float (e.g. 0.20). Returns None if not found.
        """
        for span in card.select("span.promotion-description"):
            text = span.get_text(strip=True)
            m = _ADD_DISC_RE.search(text)
            if m:
                pct = int(m.group(1))
                if 1 <= pct <= 99:
                    return pct / 100
        return None

    # ------------------------------------------------------------------
    # Generic card parser (fallback for other page types)
    # ------------------------------------------------------------------

    def _parse_generic_card(
        self, card: Tag, base_url: str, source_name: str
    ) -> Optional[ScrapedItem]:
        text = card.get_text(" ", strip=True)

        m = _SET_NO_IN_PARENS.search(text) or _SET_NO_FALLBACK.search(text)
        if not m:
            return None
        item_number = m.group(1)

        name_el = card.select_one(
            ".prd_name, .product_name, .goods_name, h3, h4, "
            "a[class*='name'], span[class*='name']"
        )
        name = name_el.get_text(strip=True) if name_el else text[:80]

        price_el = card.select_one(
            ".sale_price, .dc_price, .sell_price, "
            "[class*='sale_price'], [class*='dc_price'], [class*='price']"
        )
        if price_el is None:
            return None

        listed_price = self._price_int(price_el.get_text())
        if not listed_price:
            return None

        link_el = card.select_one("a[href]")
        product_url = self._absolute_url(link_el["href"], base_url) if link_el else base_url

        return ScrapedItem(
            item_number=item_number,
            name=name,
            listed_price=listed_price,
            additional_discount=None,
            product_url=product_url,
            source_name=source_name,
            source_url=base_url,
        )

    # ------------------------------------------------------------------
    # Regex fallback
    # ------------------------------------------------------------------

    def _regex_fallback(
        self, soup: BeautifulSoup, base_url: str, source_name: str
    ) -> list[ScrapedItem]:
        results: list[ScrapedItem] = []
        seen: set[str] = set()
        price_re = re.compile(r"[\d,]{4,}원?")

        for a_tag in soup.find_all("a", href=True):
            block_text = a_tag.get_text(" ", strip=True)
            m = _SET_NO_IN_PARENS.search(block_text) or _SET_NO_FALLBACK.search(block_text)
            if not m:
                continue
            item_number = m.group(1)
            if item_number in seen:
                continue

            prices = [self._price_int(p) for p in price_re.findall(block_text)]
            prices = [p for p in prices if p and p > 1000]
            if not prices:
                continue

            listed_price = min(prices)
            product_url = self._absolute_url(a_tag["href"], base_url)

            seen.add(item_number)
            results.append(
                ScrapedItem(
                    item_number=item_number,
                    name=block_text[:80],
                    listed_price=listed_price,
                    additional_discount=None,
                    product_url=product_url,
                    source_name=source_name,
                    source_url=base_url,
                )
            )

        return results
