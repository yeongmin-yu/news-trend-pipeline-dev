from __future__ import annotations

"""news_ingest_dag — 뉴스 수집 파이프라인 DAG (15분 주기)

Task 흐름:
    check_kafka_health
        └── produce_naver
            ├── summarize_results
            └── check_dead_letter   (all_done: 실패해도 항상 실행)

설계 원칙:
  - max_active_runs=1 : 동시 실행 방지 (중복 수집 방지)
  - catchup=False     : 과거 누락 실행 스킵
  - Kafka 헬스체크 통과 후 Naver 수집 실행
  - Naver 내부에서 테마 키워드(AI, 인공지능, 생성형AI 등) 8개를 병렬 호출
  - XCom으로 발행 건수를 집계해 요약 로그 기록
  - check_dead_letter는 all_done trigger_rule로 Dead Letter 누적 감시

NewsAPI는 무료 플랜 호출 한도가 너무 낮아 충분한 데이터를 확보할 수 없어
STEP1_KAFKA_2에서 소스에서 제외되었습니다.

src layout: DAG → airflow/dags/ → 프로젝트 루트의 `src/` 를 sys.path에 추가하여
평탄화된 패키지 구조를 import합니다.
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

# ── 공통 설정 ─────────────────────────────────────────────────────────────────

default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,   # 지수 백오프: 5m → 10m → 20m
    "max_retry_delay": timedelta(minutes=30),
}


def _ensure_src_on_syspath() -> None:
    """프로젝트의 `src/` 디렉토리를 sys.path에 추가한다.

    airflow/dags/<this>.py → parents[2] = 프로젝트 루트 → `/src`
    Docker 환경에서는 PYTHONPATH=/opt/news-trend-pipeline/src 가 이미 설정되어 있다.
    """
    import sys
    src_dir = Path(__file__).resolve().parents[2] / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


# ── Task 함수 ─────────────────────────────────────────────────────────────────


def task_check_kafka_health() -> None:
    """KafkaAdminClient로 브로커 연결 상태를 확인합니다.

    연결 실패 시 예외를 발생시켜 후속 Task(produce_naver)를 차단합니다.
    """
    _ensure_src_on_syspath()

    from kafka import KafkaAdminClient
    from kafka.errors import NoBrokersAvailable

    from core.config import settings
    from core.logger import get_logger

    logger = get_logger(__name__)

    try:
        admin = KafkaAdminClient(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            request_timeout_ms=10_000,
        )
        topics = admin.list_topics()
        admin.close()
        logger.info("Kafka 헬스체크 통과: broker=%s topics=%s", settings.kafka_bootstrap_servers, topics)
    except NoBrokersAvailable as exc:
        raise RuntimeError(
            f"Kafka 브로커에 연결할 수 없습니다: {settings.kafka_bootstrap_servers}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Kafka 헬스체크 실패: {exc}") from exc


def task_produce_naver(**context: object) -> int:
    """네이버 뉴스를 테마 키워드 병렬 호출로 수집해 Kafka에 발행합니다.

    테마 키워드 집합(NAVER_THEME_KEYWORDS)을 대상으로 ThreadPoolExecutor 기반
    병렬 호출이 수행되며, 결과는 URL 기준 dedup 후 Kafka로 전송됩니다.
    발행 건수를 XCom에 push합니다.
    """
    _ensure_src_on_syspath()

    from core.logger import get_logger
    from ingestion.producer import NewsKafkaProducer

    logger = get_logger(__name__)
    count = NewsKafkaProducer().run_for_provider("naver")
    logger.info("Naver 발행 완료: %d건", count)

    ti = context["ti"]
    ti.xcom_push(key="naver_count", value=count)
    return count


def task_summarize_results(**context: object) -> None:
    """Naver 발행 건수를 XCom으로 집계하여 요약 로그를 남깁니다."""
    _ensure_src_on_syspath()

    from core.logger import get_logger

    logger = get_logger(__name__)
    ti = context["ti"]

    naver_count: int = ti.xcom_pull(task_ids="produce_naver", key="naver_count") or 0

    logger.info("=== 수집 요약 === naver=%d건", naver_count)
    if naver_count == 0:
        logger.warning("이번 실행에서 발행된 기사가 없습니다. API 상태 및 키워드 설정을 확인하세요.")


def task_check_dead_letter() -> None:
    """dead_letter.jsonl 누적 건수를 확인하고 임계치 초과 시 경고를 남깁니다.

    trigger_rule=all_done이므로 produce_naver 실패 여부와 무관하게 항상 실행됩니다.
    """
    _ensure_src_on_syspath()

    from core.config import settings
    from core.logger import get_logger

    logger = get_logger(__name__)

    dl_file = Path(settings.state_dir) / "dead_letter.jsonl"
    if not dl_file.exists():
        logger.info("Dead Letter 파일 없음 — 실패 메시지 없음.")
        return

    line_count = sum(1 for _ in dl_file.open(encoding="utf-8"))
    logger.info("Dead Letter 누적: %d건 (%s)", line_count, dl_file)

    # 임계치: 100건 이상이면 경고 (운영 환경에서는 알림 연동 권장)
    if line_count >= 100:
        logger.warning(
            "[경고] Dead Letter가 %d건 쌓였습니다. `python -m ingestion.replay` 로 재처리하세요.",
            line_count,
        )


# ── DAG 정의 ─────────────────────────────────────────────────────────────────

with DAG(
    dag_id="news_ingest_dag",
    default_args=default_args,
    description="뉴스 수집 → Kafka 발행 파이프라인 (15분 주기, Naver 테마 키워드 병렬 호출)",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["뉴스", "카프카", "수집"],
) as dag:

    check_kafka_health = PythonOperator(
        task_id="check_kafka_health",
        python_callable=task_check_kafka_health,
    )

    produce_naver = PythonOperator(
        task_id="produce_naver",
        python_callable=task_produce_naver,
    )

    summarize_results = PythonOperator(
        task_id="summarize_results",
        python_callable=task_summarize_results,
    )

    check_dead_letter = PythonOperator(
        task_id="check_dead_letter",
        python_callable=task_check_dead_letter,
        trigger_rule="all_done",  # produce_naver 실패해도 항상 실행
    )

    # Task 의존성 정의
    check_kafka_health >> produce_naver
    produce_naver >> summarize_results
    produce_naver >> check_dead_letter
