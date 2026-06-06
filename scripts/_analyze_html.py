"""카드 4-7 가격 구조 분석"""
import sys, re
sys.path.insert(0, ".")
import requests
from bs4 import BeautifulSoup

url = "https://lottemartzetta.com/offers/97ef75de-f748-4503-86d8-4d4108021482"
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9",
}
r = requests.get(url, headers=headers, timeout=30)
r.encoding = "utf-8"
soup = BeautifulSoup(r.text, "lxml")

cards = soup.select("div.product-card-container")
# Inspect cards 4-7 (index 3-6)
for i in range(3, len(cards)):
    card = cards[i]
    print(f"\n=== Card {i+1} ===")
    print("Full text:", card.get_text(" | ", strip=True)[:200])
    print("\nAll spans with price-like text:")
    for span in card.find_all("span"):
        t = span.get_text(strip=True)
        cls = " ".join(span.get("class", []))
        if re.search(r"\d{4,}", t.replace(",", "")):
            print(f"  class={cls!r} -> {t}")
    print("All divs/spans containing '원':")
    for el in card.find_all(["span", "div", "p"]):
        t = el.get_text(strip=True)
        if "원" in t and re.search(r"\d", t):
            cls = " ".join(el.get("class", []))
            print(f"  <{el.name}> class={cls!r} -> {t[:80]}")
