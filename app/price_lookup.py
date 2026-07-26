"""
자동 정가 조회 모듈.

접근 방식 결정 기록 (2026-06-07):
  - brickset.com: 공식 API(/api/v3.asmx) 제공. API 키 없이 HTML을 긁는 방식은
    robots.txt에서 막지는 않으나, 사이트가 공식 API 사용을 권장하므로
    HTML 스크래핑은 제거하고 공식 API만 사용한다.
    무료 API 키가 settings.json에 없으면 건너뜀.
  - lego.com: 사용자 요청으로 제외.

소스 우선순위 (coordinator.py 참고):
  1. 소스 페이지 취소선 가격 (ScrapedItem.original_price) — 마트 표시 원가, KRW
  2. brickset.com 공식 API — API 키 필요, USD 가격
"""

import logging
from typing import Optional

import requests

log = logging.getLogger(__name__)

_BRICKSET_API_URL = "https://brickset.com/api/v3.asmx/getSets"


def lookup_official_price(item_number: str, api_key: str = "") -> Optional[dict]:
    """
    brickset 공식 API로 품번의 가격을 조회합니다.
    api_key 가 비어 있으면 즉시 None 반환.
    Returns:
      {
        "official_price": int,
        "currency": "USD"|"GBP"|"EUR"|"KRW",
        "name": str,
        "source": "brickset API",
        "auto": True,
        "year": int,   # 있으면 포함
      }
    or None.
    """
    if not api_key:
        return None

    s = _brickset_get_set(item_number, api_key)
    if not s:
        return None

    name = s.get("name", "")

    # retailPrice / retailPriceCurrency 필드 사용
    retail_price = s.get("retailPrice")
    if retail_price is None:
        log.debug("[brickset API] retailPrice 없음: %s", item_number)
        return None

    # brickset은 ISO 통화 코드를 반환 (예: "USD", "GBP")
    currency = s.get("retailPriceCurrency") or "USD"
    price_int = int(float(retail_price))

    log.info("[brickset API] %s → %s %s  (%s)", item_number, price_int, currency, name[:40])
    result = {
        "official_price": price_int,
        "currency": currency,
        "name": name,
        "source": "brickset API",
        "auto": True,
    }
    year = s.get("year")
    if year:
        result["year"] = int(year)
    return result


def lookup_set_year(item_number: str, api_key: str = "") -> Optional[int]:
    """
    brickset 공식 API로 품번의 출시년도만 조회합니다 (정가 유무와 무관).
    api_key 가 비어 있으면 즉시 None 반환.
    """
    if not api_key:
        return None
    s = _brickset_get_set(item_number, api_key)
    if not s:
        return None
    year = s.get("year")
    return int(year) if year else None


def _brickset_get_set(item_number: str, api_key: str) -> Optional[dict]:
    """
    brickset API v3 getSets 엔드포인트 호출. 첫 매칭 set 객체를 반환.
    공식 문서: https://brickset.com/article/52664/api-version-3-documentation
    -1(정식판) variant를 먼저 시도하고, 없으면 -2(대체판)를 시도합니다.
    """
    for variant in ("-1", "-2"):
        params = {
            "apiKey": api_key,
            "userHash": "",
            "params": f'{{"setNumber":"{item_number}{variant}"}}',
        }
        try:
            resp = requests.get(_BRICKSET_API_URL, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.debug("[brickset API] 오류 (%s%s): %s", item_number, variant, e)
            continue

        if data.get("status") != "success":
            log.debug("[brickset API] 실패 응답 (%s%s): %s", item_number, variant, data.get("message"))
            continue

        sets = data.get("sets", [])
        if sets:
            return sets[0]

    log.debug("[brickset API] 검색 결과 없음: %s", item_number)
    return None
