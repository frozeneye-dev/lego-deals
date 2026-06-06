import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "docs"
RESULTS_DIR = BASE_DIR / "results"

for _d in [CONFIG_DIR, OUTPUT_DIR, RESULTS_DIR]:
    _d.mkdir(exist_ok=True)


def _load(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_sources():
    return _load(CONFIG_DIR / "sources.json", [])


def save_sources(data):
    _save(CONFIG_DIR / "sources.json", data)


def load_prices():
    return _load(CONFIG_DIR / "prices.json", {})


def save_prices(data):
    _save(CONFIG_DIR / "prices.json", data)


_SETTINGS_DEFAULTS = {
    "discord_webhook_url": "",
    "schedule_hour": 9,
    "schedule_minute": 0,
    "global_additional_discount": 0.0,
    "github_pages_url": "https://frozeneye-dev.github.io/lego-deals",
    "github_username": "frozeneye-dev",
    "github_repo": "lego-deals",
    "brickset_api_key": "",   # https://brickset.com/api/v3.asmx — 무료 발급
    "naver_client_id": "",    # https://developers.naver.com — 쇼핑 검색 API
    "naver_client_secret": "",
}


def load_settings():
    return {**_SETTINGS_DEFAULTS, **_load(CONFIG_DIR / "settings.json", {})}


def save_settings(data):
    _save(CONFIG_DIR / "settings.json", data)
