import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, ".")

from app.scraper.coordinator import enrich_prices
from app.scraper.parsers.base import ScrapedItem

# 취소선 가격 있는 상품
with_orig = [
    ScrapedItem("31167", "크리에이터 레고 유령 맨션 (31167)", 111920, "https://x.com/1",
                "롯데마트 제타", "https://x.com", original_price=139900),
    ScrapedItem("76924", "스피드챔피언 레고 (76924)", 59415, "https://x.com/2",
                "롯데마트 제타", "https://x.com", original_price=69900),
]
# 취소선 없는 상품 (brickset 폴백, API 키 없음)
no_orig = [
    ScrapedItem("77047", "애니멀크로싱 캠핑 (77047)", 29900, "https://x.com/3",
                "롯데마트 제타", "https://x.com", original_price=None),
]

prices = {}
settings_no_key = {"brickset_api_key": ""}

added = enrich_prices(with_orig + no_orig, prices, settings_no_key)
print(f"자동 등록: {added}개  (77047은 brickset 키 없어서 미등록 예상)")
print()
for num, info in prices.items():
    src = info["source"]
    tag = "⚠ 마트표시원가" if "마트 표시 원가" in src else "🌐 brickset"
    print(f"  [{num}] {tag}  | {info['official_price']:,} {info['currency']}  auto={info['auto']}")
    print(f"          출처: {src}")

print()
print("77047 정가미등록 (정상):", "77047" not in prices)
print()

# 설정 UI 렌더링 확인
from app import create_app
app = create_app()
with app.test_client() as c:
    r = c.get("/settings")
    body = r.data.decode("utf-8")
    print("설정 페이지 200:", r.status_code == 200)
    print("brickset_api_key 입력란:", "brickset_api_key" in body)
    print("자동 정가 조회 섹션:", "자동 정가 조회" in body)
    print("마트 표시 원가 설명:", "마트 표시 원가" in body)

    r2 = c.get("/prices")
    body2 = r2.data.decode("utf-8")
    print("정가 페이지 200:", r2.status_code == 200)
    print("⚠ 마트 표시 원가 경고 아이콘:", "마트 표시 원가" in body2)
