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
from news_trend_pipeline.ingestion.api_client import (
    BaseNewsClient,
    FetchResult,
    NaverNewsClient,
)


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
        """producer_state.json을 읽어 **신 포맷** 으로 정규화해 반환합니다.

        신 포맷 구조 (프로바이더 단위):
            {
              "providers": {
                "naver": {
                  "keyword_timestamps": { "AI": "...", "GPT": "..." },
                  "published_urls": [ "..." ]
                }
              }
            }

        기존 파일이 구 포맷(`last_timestamp` 단일 값, 혹은 `providers` 래퍼 없음)으로
        저장돼 있으면 **로드 시점에 한 번만** 다음 규칙으로 변환한 뒤, 구 키는 제거합니다.
          1) `providers` 래퍼가 없으면 전체를 `providers.naver` 로 감쌉니다.
          2) 각 프로바이더의 `last_timestamp` 값은, 해당 프로바이더가 **naver** 인 경우
             현재 설정된 `naver_theme_keywords` 모든 키워드의 초기값으로 시드됩니다.
             비-Naver 프로바이더는 프로바이더명을 키로 단일 엔트리로 시드합니다.
          3) 변환 후 `last_timestamp` 키는 영구히 삭제되고, 다음 save_state() 부터는
             신 포맷만 저장됩니다. (= "구키 자체 제거" 정책)
        """
        raw = read_json(STATE_FILE, {"providers": {}})

        # (1) `providers` 래퍼가 없는 초기 구 포맷 보정.
        if "providers" not in raw:
            logger.info("이전 상태 파일(providers 래퍼 없음) 을 신 포맷으로 변환합니다.")
            legacy_last_ts: str = raw.get("last_timestamp", "") or ""
            legacy_urls = raw.get("published_urls", [])
            raw = {
                "providers": {
                    "naver": {
                        "last_timestamp": legacy_last_ts,
                        "published_urls": legacy_urls,
                    }
                }
            }

        providers: dict[str, Any] = raw.setdefault("providers", {})
        migrated_any = False

        for provider_name, provider_state in providers.items():
            if not isinstance(provider_state, dict):
                continue

            keyword_timestamps: dict[str, str] = provider_state.setdefault(
                "keyword_timestamps", {}
            )
            provider_state.setdefault("published_urls", [])

            # (2) `last_timestamp` 가 남아 있으면 keyword_timestamps 로 흡수.
            legacy_ts = provider_state.pop("last_timestamp", None)
            if legacy_ts:
                if provider_name == "naver":
                    # Naver 는 테마 키워드별 체크포인트이므로,
                    # 현재 설정된 키워드 전부에 구 타임스탬프를 초기 시드.
                    for keyword in settings.naver_theme_keywords:
                        if keyword and keyword not in keyword_timestamps:
                            keyword_timestamps[keyword] = legacy_ts
                else:
                    # 기타 프로바이더: 프로바이더명을 키로 단일 엔트리로 시드.
                    keyword_timestamps.setdefault(provider_name, legacy_ts)
                migrated_any = True

        if migrated_any:
            logger.info(
                "producer_state.json 의 구 `last_timestamp` 필드를 `keyword_timestamps` 로 "
                "마이그레이션했습니다. 다음 저장부터 구키는 파일에서 사라집니다."
            )
        return raw

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
    def _derive_from_timestamps(
        keyword_list: list[str],
        keyword_timestamps: dict[str, str],
    ) -> dict[str, str | None]:
        """키워드 목록에 대한 from_timestamp 매핑을 계산합니다.

        - 이미 체크포인트가 있는 키워드는 그 값을 그대로 사용.
        - 이번 실행에서 새로 추가된 키워드는 **기존 체크포인트들의 최댓값**으로
          초기화해 "전체 이력 재수집(flood)" 을 방지합니다. ISO8601 UTC 문자열은
          사전식 비교가 시간순 비교와 일치하므로 `max()` 가 안전합니다.
        - 상태가 완전히 비어 있는 최초 실행이면 None (증분 필터 없음).
        """
        fallback: str | None = max(keyword_timestamps.values()) if keyword_timestamps else None
        return {
            keyword: keyword_timestamps.get(keyword, fallback) or None
            for keyword in keyword_list
        }

    @classmethod
    def _collect_articles(
        cls,
        client: BaseNewsClient,
        provider_state: dict[str, Any],
    ) -> dict[str, FetchResult]:
        """프로바이더별 수집 방식을 분기하고, **키워드별 (articles, ok) 결과 dict** 를 반환합니다.

        - Naver: 테마 키워드별 독립 체크포인트로 병렬 호출(fetch_news_parallel).
        - 그 외 프로바이더: 프로바이더명을 키로 사용하는 단일 엔트리 dict로 포장하여
          상위 로직의 분기 없이 동일한 per-keyword 경로를 탈 수 있도록 합니다.
        """
        keyword_timestamps: dict[str, str] = provider_state.get("keyword_timestamps", {})

        if isinstance(client, NaverNewsClient):
            keyword_list = [q for q in settings.naver_theme_keywords if q]
            from_timestamps = cls._derive_from_timestamps(keyword_list, keyword_timestamps)
            return client.fetch_news_parallel(
                queries=keyword_list,
                from_timestamps=from_timestamps,
            )

        # 비-Naver 프로바이더: 프로바이더명을 "단일 키워드" 로 취급해 동일 인터페이스 유지.
        single_ts = keyword_timestamps.get(client.provider) or None
        articles, ok = client.fetch_news(from_timestamp=single_ts)
        return {client.provider: (articles, ok)}

    # ── 핵심 실행 로직 ────────────────────────────────────────────────────────

    def run_once(self) -> int:
        """전체 수집 → 중복 제거 → 전송 → 상태 저장 사이클을 1회 실행합니다.

        중복 제거 2-Layer:
          Layer 1: **키워드별** keyword_timestamps 기반 증분 수집 (API 호출 최소화).
                   키워드 단위로 체크포인트를 관리하므로, 한 키워드의 부분 실패가
                   다른 키워드의 재수집을 유발하지 않습니다.
          Layer 2: published_urls Set 으로 URL 중복 체크 (키: "provider::url").
                   프로바이더 단위 공유이므로, 여러 키워드에서 동일 기사가 잡히면
                   먼저 도착한 쪽 기준으로 한 번만 발행됩니다.

        체크포인트 전진 정책 (키워드 단위):
          - ok=True  → keyword_timestamps[keyword] = run_started_at 로 전진.
          - ok=False → 체크포인트 **유지**. 다음 실행에서 동일 from_timestamp 로 재시도.
          이 정책은 `fetch_news` 가 중간 페이지 실패 시 (articles, False) 를 돌려주는
          계약과 짝을 이룹니다. 부분 수집분도 중복제거 로직을 거쳐 발행되지만,
          뒷페이지 미수집 기사가 threshold 로 필터링되어 유실되는 사고를 막습니다.

        유실 방지:
          - acks=all + idempotence 로 브로커 레벨 보장
          - flush() 후 콜백 오류를 Dead Letter 로 기록
          - save_state() 는 atomic rename 으로 상태 파일 손상 방지
        """
        run_started_at: str = utc_now_iso()
        state = self.load_state()
        provider_states: dict[str, Any] = state.setdefault("providers", {})
        published_count = 0
        self._send_errors.clear()

        for client in self.clients:
            # 프로바이더별 상태 슬롯. 신규 프로바이더는 빈 keyword_timestamps 로 초기화.
            provider_state: dict[str, Any] = provider_states.setdefault(
                client.provider,
                {"keyword_timestamps": {}, "published_urls": []},
            )
            # 방어적 정리: 혹시라도 구 포맷 잔재가 남아 있으면 제거.
            provider_state.pop("last_timestamp", None)

            keyword_timestamps: dict[str, str] = provider_state.setdefault(
                "keyword_timestamps", {}
            )
            seen_urls: set[str] = set(provider_state.get("published_urls", []))

            logger.info(
                "[%s] 수집 시작 — tracked_keywords=%d seen_urls=%d",
                client.provider,
                len(keyword_timestamps),
                len(seen_urls),
            )

            # 수집 자체가 통째로 터진 경우(네트워크 단절 등) → 전체 provider skip.
            # 이 분기에서는 keyword_timestamps 를 **건드리지 않음** 으로써
            # 다음 실행에서 동일 체크포인트로 재시도됩니다 (유실 없음).
            try:
                results = self._collect_articles(client, provider_state)
            except Exception as exc:  # noqa: BLE001
                logger.error("[%s] API 수집 실패: %s", client.provider, exc)
                continue

            fetch_count = 0
            skip_count = 0
            advanced_keywords = 0
            failed_keywords = 0

            # 키워드별 루프: 각 키워드의 (articles, ok) 를 독립적으로 처리.
            for keyword, (articles, ok) in results.items():
                fetch_count += len(articles)

                for article in articles:
                    url: str | None = article.get("url")
                    unique_key = f"{client.provider}::{url}"

                    # Layer 2 중복 체크: URL Set (프로바이더 단위 공유)
                    if not url or unique_key in seen_urls:
                        skip_count += 1
                        continue

                    if self._publish(article):
                        seen_urls.add(unique_key)
                        published_count += 1

                # Layer 1: 성공한 키워드만 체크포인트 전진.
                # published_at 기준 대신 run_started_at 을 사용하는 이유는
                # 분 단위 경계 기사 누락(시각이 같은 기사가 서로 다른 페이지에 걸침)을 피하기 위함.
                if ok:
                    keyword_timestamps[keyword] = run_started_at
                    advanced_keywords += 1
                else:
                    logger.warning(
                        "[%s] 키워드 %r 부분실패/오류 — 체크포인트 유지(%s)",
                        client.provider,
                        keyword,
                        keyword_timestamps.get(keyword, "없음"),
                    )
                    failed_keywords += 1

            # 현재 설정에서 제거된 "고아 키워드" 의 체크포인트는 파일에서도 정리.
            # (Naver 에만 해당. 다른 프로바이더는 provider 이름 = keyword 이므로 대상 아님.)
            if isinstance(client, NaverNewsClient):
                active_keywords = {q for q in settings.naver_theme_keywords if q}
                stale = [k for k in list(keyword_timestamps.keys()) if k not in active_keywords]
                for k in stale:
                    logger.info("[%s] 고아 키워드 체크포인트 제거: %r", client.provider, k)
                    keyword_timestamps.pop(k, None)

            provider_state["keyword_timestamps"] = keyword_timestamps
            provider_state["published_urls"] = list(seen_urls)[-1000:]

            logger.info(
                "[%s] 완료 — fetch=%d skip(중복)=%d publish=%d "
                "ok_keywords=%d failed_keywords=%d",
                client.provider,
                fetch_count,
                skip_count,
                fetch_count - skip_count,
                advanced_keywords,
                failed_keywords,
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
