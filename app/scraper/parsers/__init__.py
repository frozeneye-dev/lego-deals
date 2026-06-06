from app.scraper.parsers.lottemartzetta import LotteMartZettaParser
from app.scraper.parsers.naver_shopping import NaverShoppingParser

ALL_PARSERS = [
    LotteMartZettaParser(),
    NaverShoppingParser(),
]
