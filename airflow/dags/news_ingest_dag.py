from __future__ import annotations

"""뉴스 수집 DAG.

Naver News API와 언론사 RSS를 각각 수집한 뒤 동일한 Kafka topic에
정규화된 기사 메시지로 발행한다. downstream Spark는 기존처럼
news_raw에 upsert한다.
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}


def _ensure_src_on_syspath() -> None:
    import sys

    src_dir = Path(__file__).resolve().parents[2] / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def task_check_kafka_health() -> None:
    _ensure_src_on_syspath()

    from kafka import KafkaAdminClient
    from kafka.errors import NoBrokersAvailable

    from core.config import settings
    from core.logger import get_logger

    logger = get_logger(__name__)
    admin = None
    try:
        logger.info("[Kafka 확인] 브로커 연결 상태를 확인합니다. bootstrap_servers=%s", settings.kafka_bootstrap_servers)
        admin = KafkaAdminClient(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            request_timeout_ms=10_000,
        )
        logger.info("[Kafka 확인] 연결 확인 완료. topics=%s", admin.list_topics())
    except NoBrokersAvailable as exc:
        logger.warning("[Kafka 확인] 브로커에 연결할 수 없습니다. 발행 실패분은 Dead Letter로 저장됩니다. error=%s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Kafka 확인] 상태 확인 중 예기치 못한 오류가 발생했습니다. 수집은 계속 진행합니다. error=%s", exc)
    finally:
        if admin is not None:
            admin.close()


def _produce_provider(provider: str, xcom_key: str, **context: object) -> int:
    _ensure_src_on_syspath()

    from core.logger import get_logger
    from ingestion.producer import NewsKafkaProducer

    logger = get_logger(__name__)
    logger.info("[뉴스 수집] provider=%s 수집을 시작합니다.", provider)
    count = NewsKafkaProducer().run_for_provider(provider)
    logger.info("[뉴스 수집] provider=%s Kafka 발행 완료: %d건", provider, count)

    ti = context["ti"]
    ti.xcom_push(key=xcom_key, value=count)
    return count


def task_produce_naver(**context: object) -> int:
    return _produce_provider("naver", "naver_count", **context)


def task_produce_rss(**context: object) -> int:
    return _produce_provider("rss", "rss_count", **context)


def task_summarize_results(**context: object) -> None:
    _ensure_src_on_syspath()

    from core.logger import get_logger

    logger = get_logger(__name__)
    ti = context["ti"]
    naver_count: int = ti.xcom_pull(task_ids="produce_naver", key="naver_count") or 0
    rss_count: int = ti.xcom_pull(task_ids="produce_rss", key="rss_count") or 0

    logger.info("[수집 요약] Naver=%d건 RSS=%d건 전체=%d건", naver_count, rss_count, naver_count + rss_count)
    if naver_count == 0 and rss_count == 0:
        logger.warning("[수집 요약] 이번 실행에서 발행된 기사가 없습니다. API/RSS 상태와 수집 설정을 확인하세요.")


def task_check_dead_letter() -> None:
    _ensure_src_on_syspath()

    from core.config import settings
    from core.logger import get_logger

    logger = get_logger(__name__)
    dl_file = Path(settings.state_dir) / "dead_letter.jsonl"
    if not dl_file.exists():
        logger.info("[Dead Letter 확인] Dead Letter 파일이 없습니다. 실패 메시지가 없습니다.")
        return

    line_count = sum(1 for _ in dl_file.open(encoding="utf-8"))
    logger.info("[Dead Letter 확인] 누적 실패 메시지: %d건 path=%s", line_count, dl_file)
    if line_count >= 100:
        logger.warning("[Dead Letter 확인] 누적 실패 메시지가 임계치를 초과했습니다. count=%d", line_count)


with DAG(
    dag_id="news_ingest_dag",
    default_args=default_args,
    description="Naver News API와 언론사 RSS를 수집해 정규화된 뉴스 메시지를 Kafka로 발행",
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

    produce_rss = PythonOperator(
        task_id="produce_rss",
        python_callable=task_produce_rss,
    )

    summarize_results = PythonOperator(
        task_id="summarize_results",
        python_callable=task_summarize_results,
    )

    check_dead_letter = PythonOperator(
        task_id="check_dead_letter",
        python_callable=task_check_dead_letter,
        trigger_rule="all_done",
    )

    check_kafka_health >> [produce_naver, produce_rss, check_dead_letter]
    [produce_naver, produce_rss] >> summarize_results
    [produce_naver, produce_rss] >> check_dead_letter
