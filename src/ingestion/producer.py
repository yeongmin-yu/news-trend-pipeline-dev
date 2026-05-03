from __future__ import annotations

import json
import sys
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kafka import KafkaProducer
from kafka.errors import KafkaError, KafkaTimeoutError, NoBrokersAvailable

from core.config import settings
from core.logger import get_logger
from core.schemas import NormalizedNewsArticle
from core.utils import ensure_dir, read_json, utc_now_iso
from ingestion.api_client import BaseNewsClient, FetchResult, NaverNewsClient, RssNewsClient
from storage.db import fetch_active_query_keywords, insert_collection_metric


logger = get_logger(__name__)

STATE_DIR = Path(settings.state_dir)
DEAD_LETTER_FILE = STATE_DIR / "dead_letter.jsonl"


def _make_dead_letter_record(
    article: Mapping[str, Any] | NormalizedNewsArticle,
    reason: str,
    attempt: int = 1,
) -> dict[str, Any]:
    if isinstance(article, NormalizedNewsArticle):
        payload = article.to_dict(include_internal=True)
    else:
        payload = dict(article)
    return {
        "failed_at": utc_now_iso(),
        "reason": reason,
        "attempt": attempt,
        "payload": payload,
    }


def build_message(article: Mapping[str, Any] | NormalizedNewsArticle) -> dict[str, Any]:
    normalized = article if isinstance(article, NormalizedNewsArticle) else NormalizedNewsArticle.from_dict(article)
    return normalized.to_message(schema_version=settings.schema_version)


class NewsKafkaProducer:
    def __init__(self) -> None:
        self.clients: list[BaseNewsClient] = self._build_clients()
        self.producer: KafkaProducer | None = None
        self._send_errors: list[tuple[dict[str, Any], Exception]] = []
        self._kafka_unavailable = False
        self._lock = threading.Lock()
        ensure_dir(STATE_DIR)
        try:
            self.producer = self._create_producer()
        except NoBrokersAvailable as exc:
            self._kafka_unavailable = True
            logger.warning(
                "Kafka producer 초기화 실패: 브로커에 연결할 수 없습니다. 수집 데이터는 Dead Letter로 저장합니다. broker=%s error=%s",
                settings.kafka_bootstrap_servers,
                exc,
            )
        except KafkaError as exc:
            self._kafka_unavailable = True
            logger.warning(
                "Kafka producer 초기화 실패: 수집 데이터는 Dead Letter로 저장합니다. broker=%s error=%s",
                settings.kafka_bootstrap_servers,
                exc,
            )

    @staticmethod
    def _state_file_for(provider: str) -> Path:
        return STATE_DIR / f"producer_state_{provider}.json"

    @staticmethod
    def _lock_file_for(provider: str) -> Path:
        return STATE_DIR / f"producer_state_{provider}.lock"

    @staticmethod
    def _create_producer() -> KafkaProducer:
        return KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda key: key.encode("utf-8") if key else None,
            acks=settings.kafka_acks,
            retries=settings.kafka_retries,
            enable_idempotence=True,
            max_in_flight_requests_per_connection=settings.kafka_max_in_flight,
            request_timeout_ms=settings.kafka_request_timeout_ms,
            max_block_ms=settings.kafka_max_block_ms,
            linger_ms=50,
            compression_type=settings.kafka_compression_type,
        )

    @staticmethod
    def _build_clients() -> list[BaseNewsClient]:
        clients: list[BaseNewsClient] = []
        for provider in settings.news_providers:
            try:
                if provider == "naver":
                    clients.append(NaverNewsClient())
                elif provider == "rss":
                    clients.append(RssNewsClient())
                else:
                    logger.warning("Unsupported provider skipped: %s", provider)
            except ValueError as exc:
                logger.warning("Provider configuration invalid, skipping %s: %s", provider, exc)
        return clients

    def load_state(self, state_file: Path) -> dict[str, Any]:
        raw = read_json(state_file, {"providers": {}})
        if "providers" not in raw:
            raw = {"providers": {}}
        providers: dict[str, Any] = raw.setdefault("providers", {})
        for provider_name, provider_state in providers.items():
            if not isinstance(provider_state, dict):
                continue
            provider_state.setdefault("keyword_timestamps", {})
            provider_state.setdefault("published_urls", [])
            previous_ts = provider_state.pop("last_timestamp", None)
            if previous_ts and provider_name == "naver":
                for row in fetch_active_query_keywords(provider=provider_name):
                    state_key = self._state_key(row["domain"], row["query"])
                    provider_state["keyword_timestamps"].setdefault(state_key, previous_ts)
            elif previous_ts:
                provider_state["keyword_timestamps"].setdefault(provider_name, previous_ts)
        return raw

    def save_state(self, state: dict[str, Any], state_file: Path) -> None:
        ensure_dir(state_file.parent)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=state_file.parent, suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as file:
                json.dump(state, file, ensure_ascii=False, indent=2)
            Path(tmp_path).replace(state_file)
        except OSError:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    def _append_dead_letter(self, article: dict[str, Any], reason: str, attempt: int = 1) -> None:
        record = _make_dead_letter_record(article, reason, attempt)
        ensure_dir(DEAD_LETTER_FILE.parent)
        with DEAD_LETTER_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.warning("Dead letter appended: url=%s reason=%s", article.get("url"), reason)

    def _make_callbacks(self, article: dict[str, Any]) -> tuple:
        def on_success(metadata: Any) -> None:
            logger.debug(
                "Published topic=%s partition=%d offset=%d url=%s",
                metadata.topic,
                metadata.partition,
                metadata.offset,
                article.get("url"),
            )

        def on_error(exc: Exception) -> None:
            logger.error("Kafka 발행 실패: url=%s error=%s", article.get("url"), exc)
            with self._lock:
                self._kafka_unavailable = True
                self._send_errors.append((article, exc))

        return on_success, on_error

    @staticmethod
    def _resolve_partition_key(article: dict[str, Any]) -> str:
        return article.get("url") or article.get("provider", "unknown")

    def _publish(self, article: dict[str, Any]) -> bool:
        if self._kafka_unavailable:
            self._append_dead_letter(article, "kafka_unavailable: 이번 수집 실행에서 Kafka 발행 실패가 이미 감지되어 즉시 Dead Letter로 저장")
            return False

        try:
            message = build_message(article)
        except ValueError as exc:
            self._append_dead_letter(article, f"validation_error: {exc}")
            return False
        partition_key = self._resolve_partition_key(article)
        on_success, on_error = self._make_callbacks(article)
        try:
            if self.producer is None:
                self._kafka_unavailable = True
                self._append_dead_letter(article, "kafka_unavailable: Kafka producer가 초기화되지 않아 Dead Letter로 저장")
                return False

            self.producer.send(
                settings.kafka_topic,
                value=message,
                key=partition_key,
            ).add_callback(on_success).add_errback(on_error)
            return True
        except KafkaTimeoutError as exc:
            self._kafka_unavailable = True
            self._append_dead_letter(article, f"KafkaTimeoutError: {exc}")
            return False
        except KafkaError as exc:
            self._kafka_unavailable = True
            self._append_dead_letter(article, f"KafkaError: {exc}")
            return False

    @staticmethod
    def _state_key(domain: str, query: str) -> str:
        return f"{domain}::{query}"

    @classmethod
    def _derive_from_timestamps(
        cls,
        query_rows: list[dict[str, Any]],
        keyword_timestamps: dict[str, str],
    ) -> dict[str, str | None]:
        fallback: str | None = max(keyword_timestamps.values()) if keyword_timestamps else None
        return {
            row["query"]: keyword_timestamps.get(cls._state_key(row["domain"], row["query"]), fallback) or None
            for row in query_rows
        }

    @classmethod
    def _iter_articles(
        cls,
        client: BaseNewsClient,
        provider_state: dict[str, Any],
    ) -> Generator[tuple[str, list[dict[str, Any]], bool, str], None, None]:
        """(query, articles, ok, state_key) 를 fetch 완료 즉시 yield 하는 generator.

        fetch 가 끝난 query 부터 publish 가 시작되어 Kafka 에 데이터가 즉시 흐른다.
        """
        keyword_timestamps: dict[str, str] = provider_state.get("keyword_timestamps", {})

        if isinstance(client, NaverNewsClient):
            query_rows = fetch_active_query_keywords(provider=client.provider)
            query_list = [row["query"] for row in query_rows]
            state_keys = {row["query"]: cls._state_key(row["domain"], row["query"]) for row in query_rows}
            row_by_query = {row["query"]: row for row in query_rows}
            from_timestamps = cls._derive_from_timestamps(query_rows, keyword_timestamps)
            for query, articles, ok in client.fetch_news_parallel_iter(queries=query_list, from_timestamps=from_timestamps):
                row = row_by_query.get(query, {})
                enriched = [{**article, "domain": row.get("domain", ""), "query": query} for article in articles]
                yield query, enriched, ok, state_keys.get(query, query)
            return

        if isinstance(client, RssNewsClient):
            state_keys = {client._feed_key(feed): client._feed_key(feed) for feed in client.feeds}
            for feed_key, articles, ok in client.fetch_news_parallel_iter(from_timestamps=keyword_timestamps):
                yield feed_key, articles, ok, state_keys.get(feed_key, feed_key)
            return

        single_ts = keyword_timestamps.get(client.provider) or None
        articles, ok = client.fetch_news(from_timestamp=single_ts)
        yield client.provider, articles, ok, client.provider

    def run_once(self) -> int:
        run_started_at = utc_now_iso()
        run_started_dt = datetime.fromisoformat(run_started_at.replace("Z", "+00:00")).astimezone(timezone.utc)
        published_count = 0
        self._send_errors.clear()

        for client in self.clients:
            state_file = self._state_file_for(client.provider)
            state = self.load_state(state_file)
            provider_state: dict[str, Any] = state.setdefault("providers", {}).setdefault(
                client.provider,
                {"keyword_timestamps": {}, "published_urls": []},
            )
            keyword_timestamps: dict[str, str] = provider_state.setdefault("keyword_timestamps", {})
            seen_urls: set[str] = set(provider_state.get("published_urls", []))

            fetch_count = 0
            skip_count = 0
            client_published_count = 0
            advanced_keywords = 0
            failed_keywords = 0
            seen_state_keys: set[str] = set()

            try:
                article_iter = self._iter_articles(client, provider_state)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] collection setup failed: %s", client.provider, exc)
                continue

            for query, articles, ok, state_key in article_iter:
                seen_state_keys.add(state_key)
                fetch_count += len(articles)
                query_duplicate_count = 0
                query_publish_count = 0
                query_domain = articles[0].get("domain", "ai_tech") if articles else (
                    state_key.split("::", 1)[0] if "::" in state_key else "ai_tech"
                )
                for article in articles:
                    url: str | None = article.get("url")
                    unique_key = f"{article.get('provider')}::{article.get('domain')}::{url}"
                    if not url or unique_key in seen_urls:
                        skip_count += 1
                        query_duplicate_count += 1
                        continue
                    if self._publish(article):
                        seen_urls.add(unique_key)
                        published_count += 1
                        client_published_count += 1
                        query_publish_count += 1

                if ok:
                    keyword_timestamps[state_key] = run_started_at
                    advanced_keywords += 1
                else:
                    failed_keywords += 1

                metric_provider = articles[0].get("provider", client.provider) if articles else client.provider
                insert_collection_metric(
                    {
                        "provider": metric_provider,
                        "domain": query_domain,
                        "query": query,
                        "window_start": run_started_dt,
                        "window_end": datetime.now(timezone.utc),
                        "request_count": 1,
                        "success_count": 1 if ok else 0,
                        "article_count": len(articles),
                        "duplicate_count": query_duplicate_count,
                        "publish_count": query_publish_count,
                        "error_count": 0 if ok else 1,
                    }
                )

            stale_keys = [key for key in list(keyword_timestamps.keys()) if key not in seen_state_keys]
            for stale_key in stale_keys:
                keyword_timestamps.pop(stale_key, None)

            provider_state["keyword_timestamps"] = keyword_timestamps
            provider_state["published_urls"] = list(seen_urls)[-5000:]
            self.save_state(state, state_file)

            logger.info(
                "[%s] fetch=%d skipped=%d published=%d ok_queries=%d failed_queries=%d",
                client.provider,
                fetch_count,
                skip_count,
                client_published_count,
                advanced_keywords,
                failed_keywords,
            )

        if self.producer is not None:
            try:
                self.producer.flush(timeout=settings.kafka_flush_timeout_seconds)
            except KafkaTimeoutError as exc:
                logger.error("Kafka flush 타임아웃: 제한시간=%d초, 오류=%s", settings.kafka_flush_timeout_seconds, exc)
            except KafkaError as exc:
                logger.error("Kafka flush 실패: 오류=%s", exc)
        else:
            logger.warning("Kafka producer가 초기화되지 않아 flush를 건너뜁니다.")

        if self._send_errors:
            for failed_article, exc in self._send_errors:
                self._append_dead_letter(failed_article, f"delivery_error: {exc}")

        logger.info("Producer cycle finished: published=%d", published_count)
        return published_count

    def run_for_provider(self, provider_name: str) -> int:
        try:
            from filelock import FileLock  # type: ignore[import]

            lock: Any = FileLock(str(self._lock_file_for(provider_name)), timeout=120)
        except ModuleNotFoundError:
            lock = _NullLock()

        original_clients = self.clients
        self.clients = [client for client in self.clients if client.provider == provider_name]
        if not self.clients:
            self.clients = original_clients
            return 0

        try:
            with lock:
                return self.run_once()
        finally:
            self.clients = original_clients


class _NullLock:
    def __enter__(self) -> "_NullLock":
        return self

    def __exit__(self, *_: object) -> None:
        return None


if __name__ == "__main__":
    NewsKafkaProducer().run_once()
