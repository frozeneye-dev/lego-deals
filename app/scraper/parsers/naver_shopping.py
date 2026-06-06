"""
Naver Shopping Search API parser.

소스 URL 형식: https://openapi.naver.com/v1/search/shop?query=레고&display=100
API 키는 settings의 naver_client_id / naver_client_secret 에서 읽음.

공식 문서: https://developers.naver.com/docs/serviceapi/search/shopping/shopping.md
- 무료: 하루 25,000건
- robots.txt 준수 불필요 (공식 API 경유)
"""

import logging
import re
from urllib.parse import parse_qs, urlparse

import requests

from .base import BaseParser, ScrapedItem

log = logging.getLogger(__name__)

_API_ENDPOINT = "https://openapi.naver.com/v1/search/shop"

# LEGO set numbers: 4~6자리 숫자
# 우선순위: 괄호 안 > 끝자리 > "레고"/"LEGO" 바로 뒤
_SET_RE = re.compile(
    r'[(\[]\s*(\d{4,6})\s*[)\]]'   # (75192) 또는 [75192]
    r'|\s(\d{4,6})\s*$'             # 맨 끝 숫자
    r'|레고\s*(\d{4,6})'            # 레고75192
    r'|LEGO\s*(\d{4,6})',           # LEGO75192
    re.IGNORECASE,
)

_HTML_TAG_RE = re.compile(r'<[^>]+>')


def _clean(html: str) -> str:
    return _HTML_TAG_RE.sub('', html).strip()


def _extract_set_number(title: str) -> str | None:
    m = _SET_RE.search(title)
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


class NaverShoppingParser(BaseParser):
    """네이버 쇼핑 검색 API — 공식 API만 사용"""

    def can_parse(self, url: str) -> bool:
        return "openapi.naver.com/v1/search/shop" in url

    def parse(self, url: str, source_name: str) -> list[ScrapedItem]:
        import config as cfg
        settings = cfg.load_settings()
        client_id = settings.get("naver_client_id", "").strip()
        client_secret = settings.get("naver_client_secret", "").strip()

        if not client_id or not client_secret:
            log.warning("[Naver] Client ID/Secret 미설정 — 건너뜀. 설정 페이지에서 입력해 주세요.")
            return []

        # URL 쿼리 파라미터를 API 호출에 그대로 사용
        qs = parse_qs(urlparse(url).query)
        params = {k: v[0] for k, v in qs.items()}
        params.setdefault("display", "100")
        params.setdefault("sort", "sim")

        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }

        try:
            resp = requests.get(_API_ENDPOINT, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            log.exception("[Naver] API 호출 실패")
            return []

        items: list[ScrapedItem] = []
        skipped = 0
        for raw in data.get("items", []):
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
            ))

        log.info("[Naver] 파싱 완료: %d개 (품번 없어 제외: %d개)", len(items), skipped)
        return items
