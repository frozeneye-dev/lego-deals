# 🧱 레고 할인 추적 봇

레고 할인 페이지를 매일 자동 수집해 공식 정가 대비 할인율을 계산하고,
결과를 GitHub Pages 웹페이지로 게시한 뒤 Discord로 알림을 보내는 봇입니다.

---

## 파일 구조

```
lego_deals_bot/
├── app/
│   ├── __init__.py          Flask 앱 팩토리
│   ├── routes.py            웹 UI 라우트 (소스·정가·설정·실행)
│   ├── scheduler.py         APScheduler 설정
│   ├── generator.py         HTML 페이지 생성
│   ├── notifier.py          Discord 웹훅 전송
│   └── scraper/
│       ├── coordinator.py   스크래핑 파이프라인
│       └── parsers/
│           ├── base.py      파서 베이스 클래스
│           └── lottemartzetta.py  롯데마트 제타 파서
├── config/
│   ├── sources.json         등록된 소스 URL 목록
│   ├── prices.json          품번별 공식 정가
│   └── settings.json        봇 설정
├── output/                  생성된 HTML 페이지 (GitHub Pages 배포)
├── results/                 날짜별 결과 JSON
├── templates/
│   ├── deals.html           공개 할인 페이지 템플릿
│   ├── index.html           아카이브 목록 템플릿
│   └── admin/               웹 UI 템플릿
├── static/css/style.css     웹 UI 스타일
├── scripts/run_scrape.py    GitHub Actions 진입점
├── .github/workflows/
│   └── daily_scrape.yml     GitHub Actions 워크플로우
├── config.py                설정 로드/저장 헬퍼
├── run.py                   로컬 Flask 서버 진입점
└── requirements.txt
```

---

## 빠른 시작

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 로컬 웹 UI 실행

```bash
python run.py
```

브라우저에서 `http://127.0.0.1:5000` 접속.

### 3. 기본 설정 (웹 UI에서)

| 메뉴 | 할 일 |
|---|---|
| **설정** | GitHub Pages URL, Discord 웹훅 URL, 자동 실행 시각, 전역 추가 할인율 입력 |
| **소스** | 롯데마트 제타 LEGO 할인 페이지 URL 추가 |
| **정가 관리** | 품번별 레고 공식 정가 등록 |
| **파싱 테스트** | 소스 URL이 잘 읽히는지 확인 |
| **수동 실행** | 바로 실행 후 결과 확인 |

---

## GitHub Actions로 매일 자동 실행

PC가 꺼져 있어도 GitHub Actions가 매일 스크래핑 → HTML 생성 → Discord 알림을 수행합니다.

### 설정 단계

#### 1) GitHub 레포지터리 생성

```bash
git init
git add .
git commit -m "init"
git remote add origin https://github.com/<username>/lego-deals.git
git push -u origin main
```

#### 2) Discord 웹훅 Secret 등록

레포지터리 → **Settings → Secrets and variables → Actions → New repository secret**

- Name: `DISCORD_WEBHOOK_URL`
- Value: Discord 웹훅 URL (채널 설정 → 연동 → 웹훅)

#### 3) GitHub Pages 활성화

레포지터리 → **Settings → Pages**

- Source: **GitHub Actions** 선택

#### 4) 웹 UI에서 GitHub Pages URL 입력

```
https://<username>.github.io/lego-deals
```

`config/settings.json`이 업데이트되면 커밋 & 푸시:

```bash
git add config/settings.json
git commit -m "config: set github pages url"
git push
```

#### 5) 자동 실행 시각 변경 (선택)

`.github/workflows/daily_scrape.yml` 의 cron 표현식을 수정합니다.

```yaml
- cron: "0 0 * * *"   # 00:00 UTC = 09:00 KST
```

KST 기준 원하는 시각에 맞게 UTC로 환산해 입력하세요.

---

## 새 사이트 파서 추가

1. `app/scraper/parsers/` 에 파이썬 파일 생성 (예: `emart.py`)
2. `BaseParser` 를 상속하고 `can_parse` / `parse` 구현

```python
from app.scraper.parsers.base import BaseParser, ScrapedItem

class EmartParser(BaseParser):
    def can_parse(self, url: str) -> bool:
        return "emart.com" in url

    def parse(self, url: str, source_name: str) -> list[ScrapedItem]:
        # fetch + parse HTML, return ScrapedItem list
        ...
```

3. `app/scraper/parsers/__init__.py` 의 `ALL_PARSERS` 에 추가

```python
from app.scraper.parsers.emart import EmartParser

ALL_PARSERS = [
    LotteMartZettaParser(),
    EmartParser(),
]
```

> **주의**: 추가 전 해당 사이트의 `robots.txt` 와 이용약관을 반드시 확인하세요.
> 쿠팡·네이버쇼핑·다나와·롯데ON 등 JS 렌더링/봇 차단 사이트는 지원하지 않습니다.

---

## 최종 할인가 계산 방식

```
공식 정가 = 레고 공식 홈페이지 기준 (prices.json 등록값)
표시가    = 마트/쇼핑몰 페이지에 표시된 할인가
추가할인  = 결제 시 추가 할인율 (예: 카드 20%)

최종가    = 표시가 × (1 - 추가할인율)
할인율    = 1 - (최종가 / 공식 정가)
```

예시)
- 공식 정가: 139,900원
- 마트 표시가: 111,920원
- 추가 할인: 20%
- 최종가: 111,920 × 0.8 = **89,536원**
- 공식 정가 대비 할인율: 1 - (89,536 / 139,900) = **36%**

---

## 롯데마트 제타 파서 관련

- `robots.txt` 확인 결과 (2026-06-06 기준): 상품 페이지 크롤링 **허용** (`Allow: /`)
- 소스 URL 등록 전 브라우저에서 해당 페이지가 LEGO 상품을 HTML로 직접 렌더링하는지 확인하세요.
- 파싱이 안 될 경우 웹 UI의 **파싱 테스트** 메뉴에서 URL을 입력하고 결과를 확인한 뒤,
  `app/scraper/parsers/lottemartzetta.py` 의 `card_selectors` 리스트에 해당 페이지의 CSS 셀렉터를 추가하세요.

---

## 출력 페이지 URL

| 주소 | 내용 |
|---|---|
| `https://<username>.github.io/lego-deals/` | 날짜별 아카이브 목록 |
| `https://<username>.github.io/lego-deals/today.html` | 최신 할인 목록 |
| `https://<username>.github.io/lego-deals/2026-06-06.html` | 특정 날짜 목록 |

---

## 할인율 카테고리

| 카테고리 | 기준 |
|---|---|
| 🔥 40% 이상 | 공식 정가 대비 최종가 40% 이상 할인 |
| ✨ 30%대 | 30% 이상 40% 미만 |
| 💡 20%대 | 20% 이상 30% 미만 |
| ❓ 정가 미등록 | 공식 정가 없어 할인율 계산 불가 |

20% 미만 할인 상품은 페이지에 표시되지 않습니다.
