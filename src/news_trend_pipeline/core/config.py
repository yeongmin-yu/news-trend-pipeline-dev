from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[3]
load_dotenv(BASE_DIR / ".env", override=True)


def _parse_csv(raw: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _resolve_path(raw: str | None, default: Path) -> str:
    if not raw:
        return str(default)
    candidate = Path(raw)
    if candidate.is_absolute():
        return str(candidate)
    return str((BASE_DIR / candidate).resolve())


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
    news_providers: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(os.getenv("NEWS_PROVIDERS", "naver"))
    )

    naver_client_id: str = os.getenv("NAVER_CLIENT_ID", "")
    naver_client_secret: str = os.getenv("NAVER_CLIENT_SECRET", "")
    naver_news_api_url: str = os.getenv(
        "NAVER_NEWS_API_URL", "https://openapi.naver.com/v1/search/news.json"
    )
    naver_theme_keywords: tuple[str, ...] = field(
        default_factory=lambda: _parse_csv(
            os.getenv("NAVER_THEME_KEYWORDS", ",".join(DEFAULT_THEME_KEYWORDS))
        )
        or DEFAULT_THEME_KEYWORDS
    )
    naver_news_display: int = int(os.getenv("NAVER_NEWS_DISPLAY", "100"))
    naver_news_sort: str = os.getenv("NAVER_NEWS_SORT", "date")
    naver_news_max_pages: int = int(os.getenv("NAVER_NEWS_MAX_PAGES", "3"))
    naver_max_workers: int = int(os.getenv("NAVER_MAX_WORKERS", "4"))
    naver_page_request_delay_seconds: float = float(os.getenv("NAVER_PAGE_REQUEST_DELAY_SECONDS", "0.75"))
    naver_query_stagger_seconds: float = float(os.getenv("NAVER_QUERY_STAGGER_SECONDS", "0.15"))

    kafka_bootstrap_servers: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "news_topic")
    kafka_acks: str = os.getenv("KAFKA_ACKS", "all")
    kafka_retries: int = int(os.getenv("KAFKA_RETRIES", "5"))
    kafka_max_in_flight: int = int(os.getenv("KAFKA_MAX_IN_FLIGHT", "1"))
    kafka_request_timeout_ms: int = int(os.getenv("KAFKA_REQUEST_TIMEOUT_MS", "30000"))
    kafka_max_block_ms: int = int(os.getenv("KAFKA_MAX_BLOCK_MS", "60000"))
    kafka_compression_type: str = os.getenv("KAFKA_COMPRESSION_TYPE", "gzip")
    schema_version: str = os.getenv("SCHEMA_VERSION", "v1")
    state_dir: str = _resolve_path(os.getenv("STATE_DIR"), BASE_DIR / "runtime" / "state")

    spark_master: str = os.getenv("SPARK_MASTER", "local[*]")
    spark_app_name: str = os.getenv("SPARK_APP_NAME", "news-trend-pipeline")
    spark_checkpoint_dir: str = _resolve_path(
        os.getenv("SPARK_CHECKPOINT_DIR"),
        BASE_DIR / "runtime" / "checkpoints",
    )
    spark_shuffle_partitions: str = os.getenv("SPARK_SHUFFLE_PARTITIONS", "2")
    spark_starting_offsets: str = os.getenv("SPARK_STARTING_OFFSETS", "latest")
    keyword_window_duration: str = os.getenv("KEYWORD_WINDOW_DURATION", "10 minutes")
    relation_keyword_limit: int = int(os.getenv("RELATION_KEYWORD_LIMIT", "8"))

    compound_extraction_window_days: int = int(os.getenv("COMPOUND_EXTRACTION_WINDOW_DAYS", "1"))
    compound_extraction_min_frequency: int = int(os.getenv("COMPOUND_EXTRACTION_MIN_FREQUENCY", "3"))
    compound_extraction_min_char_length: int = int(os.getenv("COMPOUND_EXTRACTION_MIN_CHAR_LENGTH", "4"))
    compound_extraction_max_morpheme_count: int = int(os.getenv("COMPOUND_EXTRACTION_MAX_MORPHEME_COUNT", "4"))
    dictionary_refresh_interval_seconds: int = int(os.getenv("DICTIONARY_REFRESH_INTERVAL_SECONDS", "60"))

    postgres_host: str = os.getenv("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.getenv("POSTGRES_PORT", "5432"))
    postgres_db: str = os.getenv("POSTGRES_DB", "news_pipeline")
    postgres_user: str = os.getenv("POSTGRES_USER", "postgres")
    postgres_password: str = os.getenv("POSTGRES_PASSWORD", "postgres")

    @property
    def postgres_dsn(self) -> str:
        return (
            f"host={self.postgres_host} "
            f"port={self.postgres_port} "
            f"dbname={self.postgres_db} "
            f"user={self.postgres_user} "
            f"password={self.postgres_password}"
        )

    @property
    def spark_jdbc_url(self) -> str:
        return f"jdbc:postgresql://{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"


settings = Settings()
