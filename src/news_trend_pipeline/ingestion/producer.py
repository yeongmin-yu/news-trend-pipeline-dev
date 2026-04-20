from __future__ import annotations

import json
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kafka import KafkaProducer
from kafka.errors import KafkaError, KafkaTimeoutError

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.logger import get_logger
from news_trend_pipeline.core.utils import ensure_dir, read_json, utc_now_iso
from news_trend_pipeline.ingestion.api_client import BaseNewsClient, NaverNewsClient


logger = get_logger(__name__)

STATE_FILE = Path(settings.state_dir) / "producer_state.json"
DEAD_LETTER_FILE = Path(settings.state_dir) / "dead_letter.jsonl"
LOCK_FILE = STATE_FILE.with_suffix(".lock")


# ── Dead Letter 레코드 ─────────────────────────────────────────────────────────

def _make_dead_letter_record(
    article: dict[str, Any],
    reason: str,
    attempt: int = 1,
) -> dict[str, Any]:
    """Kafka 전송 실패 메시지를 Dead Letter 레코드로 감쌉니다."""
    return {
        "failed_at": utc_now_iso(),
        "reason": reason,
        "attempt": attempt,
        "payload": article,
    }


# ── 메시지 빌더 ───────────────────────────────────────────────────────────────

def build_message(article: dict[str, Any]) -> dict[str, Any]:
    """article dict에 metadata 블록을 추가하여 최종 Kafka 메시지를 반환합니다.

    내부 필드(`_`로 시작)는 Kafka로 나가지 않도록 제거합니다.
    `_query` 필드는 수집 시 사용한 테마 키워드를 담고 있으며, metadata.query로 옮깁니다.
    """
    provider = article.get("provider", "unknown")
    query = article.get("_query") or ""
    # 내부 전용 필드(_로 시작) 제거
    clean_article = {k: v for k, v in article.items() if not k.startswith("_")}
    return {
        **clean_article,
        "metadata": {
            "source": provider,
            "version": settings.schema_version,
            "query": query,
        },
    }


# ── Producer ─────────────────────────────────────────────────────────────────

class NewsKafkaProducer:
    """뉴스 기사를 Kafka 토픽에 발행하는 Producer.

    설계 원칙:
    - acks=all + enable_idempotence=True 로 유실 방지
    - URL 기반 2-layer 중복 제거로 중복 수집 방지
    - URL을 partition key로 사용해 동일 콘텐츠가 항상 같은 partition으로 라우팅
    - 전송 실패 메시지는 Dead Letter 파일에 기록
    - filelock으로 CeleryExecutor 병렬 실행 시 상태 파일 충돌 방지
    """

    def __init__(self) -> None:
        self.clients: list[BaseNewsClient] = self._build_clients()
        self.producer: KafkaProducer = self._create_producer()
        self._send_errors: list[tuple[dict[str, Any], Exception]] = []
        self._lock = threading.Lock()
        ensure_dir(STATE_FILE.parent)

    # ── KafkaProducer 초기화 ──────────────────────────────────────────────────

    @staticmethod
    def _create_producer() -> KafkaProducer:
        """신뢰성 중심 KafkaProducer를 생성합니다.

        acks=all + enable_idempotence=True: 브로커 전체 복제 완료 후 ack 수신.
        max_in_flight_requests_per_connection=1: idempotence 조건 충족.
        retries: 일시적 네트워크 오류에 자동 재시도.
        """
        return KafkaProducer(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k else None,
            acks=settings.kafka_acks,
            retries=settings.kafka_retries,
            enable_idempotence=True,
            max_in_flight_requests_per_connection=settings.kafka_max_in_flight,
            request_timeout_ms=settings.kafka_request_timeout_ms,
            max_block_ms=settings.kafka_max_block_ms,
            linger_ms=50,
            compression_type=settings.kafka_compression_type,
        )

    # ── 클라이언트 빌드 ───────────────────────────────────────────────────────

    @staticmethod
    def _build_clients() -> list[BaseNewsClient]:
        """NEWS_PROVIDERS 순회하며 자격 증명 오류 시 해당 프로바이더를 skip합니다."""
        clients: list[BaseNewsClient] = []
        for provider in settings.news_providers:
            try:
                if provider == "naver":
                    clients.append(NaverNewsClient())
                else:
                    logger.warning("지원하지 않는 프로바이더입니다 (skip): %s", provider)
            except ValueError as exc:
                logger.warning("프로바이더 설정 오류로 skip: %s — %s", provider, exc)
        if not clients:
            logger.warning(
                "사용 가능한 뉴스 프로바이더가 없습니다. NEWS_PROVIDERS 및 API 자격 증명을 확인하세요."
            )
        return clients

    # ── 상태 관리 (filelock 적용) ─────────────────────────────────────────────

    def load_state(self) -> dict[str, Any]:
        """producer_state.json을 읽어 반환합니다. 구 포맷은 자동 마이그레이션합니다."""
        state = read_json(STATE_FILE, {"providers": {}})
        if "providers" in state:
            return state
        # 구 포맷 → 신 포맷 마이그레이션
        logger.info("이전 상태 파일 포맷을 마이그레이션합니다.")
        return {
            "providers": {
                "naver": {
                    "last_timestamp": state.get("last_timestamp", ""),
                    "published_urls": state.get("published_urls", []),
                }
            }
        }

    def save_state(self, state: dict[str, Any]) -> None:
        """producer_state.json을 원자적으로 저장합니다 (임시 파일 → rename).

        rename은 대부분의 OS에서 원자적이므로, 쓰기 도중 프로세스가 죽어도
        이전 상태 파일이 보존됩니다 (유실 방지).
        """
        ensure_dir(STATE_FILE.parent)
        tmp_fd, tmp_path = tempfile.mkstemp(dir=STATE_FILE.parent, suffix=".tmp")
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            Path(tmp_path).replace(STATE_FILE)
        except OSError:
            Path(tmp_path).unlink(missing_ok=True)
            raise

    # ── Dead Letter 처리 ──────────────────────────────────────────────────────

    def _append_dead_letter(self, article: dict[str, Any], reason: str, attempt: int = 1) -> None:
        """실패 메시지를 dead_letter.jsonl에 추가합니다 (오프라인 재처리용).

        Kafka 자체가 장애일 때도 로컬 파일에 보존되므로, 두 채널을 함께 유지합니다.
        """
        record = _make_dead_letter_record(article, reason, attempt)
        ensure_dir(DEAD_LETTER_FILE.parent)
        with DEAD_LETTER_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.warning("Dead Letter 기록: url=%s reason=%s", article.get("url"), reason)


    # ── 전송 콜백 ─────────────────────────────────────────────────────────────

    def _make_callbacks(self, article: dict[str, Any]) -> tuple:
        """send()에 등록할 on_delivery 콜백 쌍을 반환합니다."""

        def on_success(metadata: Any) -> None:
            logger.debug(
                "전송 성공: topic=%s partition=%d offset=%d url=%s",
                metadata.topic,
                metadata.partition,
                metadata.offset,
                article.get("url"),
            )

        def on_error(exc: Exception) -> None:
            logger.error("전송 실패 콜백: url=%s error=%s", article.get("url"), exc)
            with self._lock:
                self._send_errors.append((article, exc))

        return on_success, on_error

    # ── 단일 메시지 전송 ──────────────────────────────────────────────────────

    @staticmethod
    def _resolve_partition_key(article: dict[str, Any]) -> str:
        """Partition key 결정: URL(유니크키) 우선, 폴백은 provider.

        URL을 key로 쓰면 kafka-python의 murmur2 해시에 의해
        동일 URL이 항상 같은 partition으로 라우팅되어:
          - 중복 콘텐츠 처리 경로 단순화
          - partition skew 감소 (provider 단위 쏠림 제거)
          - consumer 측 디버깅 용이
        URL이 비어 있는 예외적 경우에만 provider로 폴백합니다.
        """
        url = article.get("url")
        if url:
            return url
        return article.get("provider", "unknown")

    def _publish(self, article: dict[str, Any]) -> bool:
        """메시지 하나를 Kafka에 전송합니다.

        전송 성공 시 True, 즉시 오류 발생 시 Dead Letter로 기록 후 False 반환.
        실제 브로커 오류는 flush() 이후 콜백을 통해 _send_errors에 수집됩니다.
        """
        message = build_message(article)
        partition_key = self._resolve_partition_key(article)
        on_success, on_error = self._make_callbacks(article)
        try:
            self.producer.send(
                settings.kafka_topic,
                value=message,
                key=partition_key,
            ).add_callback(on_success).add_errback(on_error)
            return True
        except KafkaTimeoutError as exc:
            logger.error("Kafka 타임아웃 (버퍼 꽉 참): url=%s error=%s", article.get("url"), exc)
            self._append_dead_letter(article, f"KafkaTimeoutError: {exc}")
            return False
        except KafkaError as exc:
            logger.error("Kafka 전송 오류: url=%s error=%s", article.get("url"), exc)
            self._append_dead_letter(article, f"KafkaError: {exc}")
            return False

    # ── 기사 수집 (병렬/단일 분기) ────────────────────────────────────────────

    @staticmethod
    def _collect_articles(
        client: BaseNewsClient,
        last_timestamp: str | None,
    ) -> list[dict[str, Any]]:
        """프로바이더별 수집 방식을 분기합니다.

        Naver는 테마 키워드 병렬 호출(fetch_news_parallel), 그 외는 단일 호출.
        """
        if isinstance(client, NaverNewsClient):
            return client.fetch_news_parallel(
                queries=settings.naver_theme_keywords,
                from_timestamp=last_timestamp,
            )
        return client.fetch_news(from_timestamp=last_timestamp)

    # ── 핵심 실행 로직 ────────────────────────────────────────────────────────

    def run_once(self) -> int:
        """전체 수집 → 중복 제거 → 전송 → 상태 저장 사이클을 1회 실행합니다.

        중복 제거 2-Layer:
          Layer 1: last_timestamp 기반 증분 수집 (API 호출 최소화)
          Layer 2: published_urls Set으로 URL 중복 체크 (키: "provider::url")

        유실 방지:
          - acks=all + idempotence로 브로커 레벨 보장
          - flush() 후 콜백 오류를 Dead Letter로 기록
          - save_state()는 atomic rename으로 상태 파일 손상 방지
        """
        run_started_at: str = utc_now_iso()
        state = self.load_state()
        provider_states: dict[str, Any] = state.setdefault("providers", {})
        published_count = 0
        self._send_errors.clear()

        for client in self.clients:
            provider_state: dict[str, Any] = provider_states.setdefault(
                client.provider,
                {"last_timestamp": "", "published_urls": []},
            )
            seen_urls: set[str] = set(provider_state.get("published_urls", []))
            last_timestamp: str | None = provider_state.get("last_timestamp") or None

            logger.info(
                "[%s] 수집 시작 — last_timestamp=%s seen_urls=%d",
                client.provider,
                last_timestamp or "없음",
                len(seen_urls),
            )

            try:
                articles = self._collect_articles(client, last_timestamp)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] API 수집 실패: %s", client.provider, exc)
                continue

            fetch_count = len(articles)
            skip_count = 0

            for article in articles:
                url: str | None = article.get("url")
                unique_key = f"{client.provider}::{url}"

                # Layer 2 중복 체크: URL Set
                if not url or unique_key in seen_urls:
                    skip_count += 1
                    continue

                if self._publish(article):
                    seen_urls.add(unique_key)
                    published_count += 1

            # Layer 1: 다음 실행의 from 기준을 수집 시작 시각으로 고정
            # (published_at 기준 시 분 단위 경계 기사 누락 방지)
            provider_state["last_timestamp"] = run_started_at
            provider_state["published_urls"] = list(seen_urls)[-1000:]

            logger.info(
                "[%s] 완료 — fetch=%d skip(중복)=%d publish=%d",
                client.provider,
                fetch_count,
                skip_count,
                fetch_count - skip_count,
            )

        # 브로커에 버퍼링된 메시지를 모두 플러시
        try:
            self.producer.flush(timeout=60)
        except KafkaTimeoutError as exc:
            logger.error("flush() 타임아웃: %s", exc)

        # 콜백 오류 수집 후 Dead Letter 처리
        if self._send_errors:
            logger.warning("전송 실패 %d건을 Dead Letter로 기록합니다.", len(self._send_errors))
            for failed_article, exc in self._send_errors:
                self._append_dead_letter(failed_article, f"delivery_error: {exc}")

        self.save_state(state)
        logger.info(
            "발행 완료: %d건 → topic=%s | 실패(DL)=%d건",
            published_count,
            settings.kafka_topic,
            len(self._send_errors),
        )
        return published_count

    def run_for_provider(self, provider_name: str) -> int:
        """특정 프로바이더 하나만 실행합니다. Airflow 병렬 Task에서 호출됩니다.

        filelock으로 상태 파일 동시 쓰기를 방지합니다 (CeleryExecutor 대응).
        """
        try:
            from filelock import FileLock  # type: ignore[import]
            lock: Any = FileLock(str(LOCK_FILE), timeout=120)
        except ModuleNotFoundError:
            logger.warning("filelock 미설치 — 동시 실행 시 상태 파일 충돌 가능. `pip install filelock>=3.13`")
            lock = _NullLock()

        original_clients = self.clients
        self.clients = [c for c in self.clients if c.provider == provider_name]
        if not self.clients:
            logger.warning("프로바이더 '%s'를 찾을 수 없습니다.", provider_name)
            self.clients = original_clients
            return 0

        try:
            with lock:
                return self.run_once()
        except Exception:  # noqa: BLE001 — filelock Timeout도 포함
            logger.exception("run_for_provider('%s') 실패", provider_name)
            return 0
        finally:
            self.clients = original_clients


class _NullLock:
    """filelock 미설치 환경에서 사용하는 no-op 컨텍스트 매니저."""

    def __enter__(self) -> "_NullLock":
        return self

    def __exit__(self, *_: object) -> None:
        pass


if __name__ == "__main__":
    NewsKafkaProducer().run_once()
