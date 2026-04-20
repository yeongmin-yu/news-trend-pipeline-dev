from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


# src layout: core/config.py → core → news_trend_pipeline → src → <project root>
BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env")


def _parse_csv(raw: str) -> tuple[str, ...]:
    """콤마(,)로 구분된 환경변수 값을 trim하여 tuple로 반환합니다."""
    return tuple(item.strip() for item in raw.split(",") if item.strip())


# DIRECTION.md — AI/기술 도메인 테마 키워드 (기본값)
DEFAULT_THEME_KEYWORDS = (
    "AI",
    "인공지능",
    "생성형AI",
    "GPT",
    "LLM",
    "챗GPT",
    "머신러닝",
    "딥러닝",
)


@dataclass(frozen=True)
class Settings:
    # ── News Provider 선택 ────────────────────────────────────────────────
    # NewsAPI는 무료 플랜 호출 한도가 너무 낮아 충분한 데이터를 확보할 수 없어
    # 제거되었습니다. 현재는 Naver만 지원합니다.
    news_providers: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(os.getenv("NEWS_PROVIDERS", "naver"))
    )

    # ── Naver API ────────────────────────────────────────────────────────
    naver_client_id: str = os.getenv("NAVER_CLIENT_ID", "")
    naver_client_secret: str = os.getenv("NAVER_CLIENT_SECRET", "")
    naver_news_api_url: str = os.getenv(
        "NAVER_NEWS_API_URL", "https://openapi.naver.com/v1/search/news.json"
    )
    # 테마 키워드 집합 (병렬 호출 대상). DIRECTION.md의 도메인 키워드 풀.
    naver_theme_keywords: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(
            os.getenv("NAVER_THEME_KEYWORDS", ",".join(DEFAULT_THEME_KEYWORDS))
        )
        or DEFAULT_THEME_KEYWORDS
    )
    naver_news_display: int = int(os.getenv("NAVER_NEWS_DISPLAY", "100"))
    naver_news_sort: str = os.getenv("NAVER_NEWS_SORT", "date")
    naver_news_max_pages: int = int(os.getenv("NAVER_NEWS_MAX_PAGES", "3"))
    # 병렬 호출 시 동시에 사용할 최대 워커 수
    naver_max_workers: int = int(os.getenv("NAVER_MAX_WORKERS", "8"))

    # ── Kafka ────────────────────────────────────────────────────────────
    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "news_topic")
    kafka_acks: str = os.getenv("KAFKA_ACKS", "all")
    kafka_retries: int = int(os.getenv("KAFKA_RETRIES", "5"))
    kafka_max_in_flight: int = int(os.getenv("KAFKA_MAX_IN_FLIGHT", "1"))
    kafka_request_timeout_ms: int = int(os.getenv("KAFKA_REQUEST_TIMEOUT_MS", "30000"))
    kafka_max_block_ms: int = int(os.getenv("KAFKA_MAX_BLOCK_MS", "60000"))
    kafka_compression_type: str = os.getenv("KAFKA_COMPRESSION_TYPE", "gzip")
    schema_version: str = os.getenv("SCHEMA_VERSION", "v1")
    state_dir: str = os.getenv("STATE_DIR", str(BASE_DIR / "runtime" / "state"))


settings = Settings()
