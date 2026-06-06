"""자동 정가 조회 포함 파이프라인 테스트 (처음 3개 품번만)"""
import sys, logging, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

import config as cfg
from app.scraper.coordinator import scrape_sources, enrich_prices, calculate_deals, categorize

sources  = cfg.load_sources()
settings = cfg.load_settings()

print(f"[소스] {len(sources)}개: {sources[0]['url'] if sources else '없음'}\n")

raw = scrape_sources(sources)
print(f"[수집] {len(raw)}개 상품\n")

# 처음 3개만 가지고 enrich 테스트 (전체 50개는 시간이 걸림)
sample = raw[:3]
prices = {}   # 빈 상태에서 시작 (처음 실행 상황 시뮬레이션)

print("[enrich] 처음 3개 품번 자동 정가 조회 시작...\n")
added = enrich_prices(sample, prices)
print(f"\n[enrich] 완료: {added}개 자동 등록\n")

for num, info in prices.items():
    flag = "자동" if info.get("auto") else "수동"
    curr = info.get("currency", "KRW")
    print(f"  [{num}] {flag} | {info['official_price']:,} {curr} | 출처: {info['source']}")
    print(f"         상품명: {info['name'][:50]}")

if prices:
    print("\n[계산] 최종 할인가 계산 (취소선 가격이 공식 정가면 정확함)")
    settings["global_additional_discount"] = 0.0  # 추가할인 없이 계산
    deals = calculate_deals(sample, prices, settings)
    for d in deals:
        if d.discount_rate is not None:
            print(f"  [{d.item_number}] 표시가 {d.listed_price:,}원 → 최종 {d.final_price:,}원 / {d.discount_rate*100:.1f}% 할인")
        else:
            print(f"  [{d.item_number}] 정가 미등록")
