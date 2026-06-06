"""
Naver Shopping Search API parser.

소스 URL 형식: https://openapi.naver.com/v1/search/shop?query=레고&display=100
API 키는 settings의 naver_client_id / naver_client_secret 에서 읽음.

공식 문서: https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md
- 무료: 하루 25,000건
- 자동 페이지네이션: total 값 기반으로 전체 결과 수집 (최대 1000건)
"""

import logging
import os
import re
from urllib.parse import parse_qs, urlparse

import requests

from .base import BaseParser, ScrapedItem

log = logging.getLogger(__name__)

_API_ENDPOINT = "https://openapi.naver.com/v1/search/shop"
_MAX_RESULTS = 1000   # Naver API 최대 허용치
_PAGE_SIZE = 100      # 한 번에 가져올 최대 수

# LEGO 품번은 5~6자리 숫자 (4자리는 연도·모델번호와 혼동 위험)
_SET_RE = re.compile(r'\b(\d{5,6})\b')
_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _clean(html: str) -> str:
    return _HTML_TAG_RE.sub('', html).strip()


def _extract_set_number(title: str) -> str | None:
    m = _SET_RE.search(title)
    return m.group(1) if m else None


class NaverShoppingParser(BaseParser):
    """네이버 쇼핑 검색 API — 공식 API만 사용, 자동 페이지네이션"""

    def can_parse(self, url: str) -> bool:
        return "openapi.naver.com/v1/search/shop" in url

    def parse(self, url: str, source_name: str) -> list[ScrapedItem]:
        import config as cfg
        settings = cfg.load_settings()
        client_id = (settings.get("naver_client_id", "") or os.environ.get("NAVER_CLIENT_ID", "")).strip()
        client_secret = (settings.get("naver_client_secret", "") or os.environ.get("NAVER_CLIENT_SECRET", "")).strip()

        if not client_id or not client_secret:
            log.warning("[Naver] Client ID/Secret 미설정 — 건너뜀. 설정 페이지에서 입력해 주세요.")
            return []

        qs = parse_qs(urlparse(url).query)
        base_params = {k: v[0] for k, v in qs.items()}
        base_params["display"] = str(_PAGE_SIZE)
        base_params.setdefault("sort", "sim")

        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }

        all_raw: list[dict] = []
        start = 1

        while start <= _MAX_RESULTS:
            params = {**base_params, "start": str(start)}
            try:
                resp = requests.get(_API_ENDPOINT, params=params, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                log.exception("[Naver] API 호출 실패 (start=%d)", start)
                break

            batch = data.get("items", [])
            if not batch:
                break

            all_raw.extend(batch)
            total = int(data.get("total", 0))
            log.debug("[Naver] start=%d, 이번 %d개, 전체 %d개", start, len(batch), total)

            if start + _PAGE_SIZE - 1 >= min(total, _MAX_RESULTS):
                break
            start += _PAGE_SIZE

        items: list[ScrapedItem] = []
        skipped = 0
        for raw in all_raw:
            title = _clean(raw.get("title", ""))
            set_number = _extract_set_number(title)
            if not set_number:
                skipped += 1
                continue

            try:
                listed_price = int(raw.get("lprice", 0))
            except (ValueError, TypeError):
                skipped += 1
                continue
            if listed_price <= 0:
                skipped += 1
                continue

            items.append(ScrapedItem(
                item_number=set_number,
                name=title,
                listed_price=listed_price,
                product_url=raw.get("link", ""),
                source_name=source_name,
                source_url=url,
                original_price=listed_price,
            ))

        log.info("[Naver] 총 %d개 수집, 파싱 완료: %d개 (품번 없어 제외: %d개)",
                 len(all_raw), len(items), skipped)
        return items
