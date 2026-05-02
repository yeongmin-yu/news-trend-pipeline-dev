from __future__ import annotations

"""RSS news ingestion DAG."""

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
        logger.info("[Kafka check] Checking broker connection: bootstrap_servers=%s", settings.kafka_bootstrap_servers)
        admin = KafkaAdminClient(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            request_timeout_ms=10_000,
        )
        logger.info("[Kafka check] Broker connection ok. topics=%s", admin.list_topics())
    except NoBrokersAvailable as exc:
        logger.warning("[Kafka check] Broker unavailable. Failed publishes will go to dead letter. error=%s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[Kafka check] Unexpected health check error. Collection will continue. error=%s", exc)
    finally:
        if admin is not None:
            admin.close()


def task_produce_rss(**context: object) -> int:
    _ensure_src_on_syspath()

    from core.logger import get_logger
    from ingestion.producer import NewsKafkaProducer

    logger = get_logger(__name__)
    logger.info("[RSS collection] Starting collection")
    count = NewsKafkaProducer().run_for_provider("rss")
    logger.info("[RSS collection] Kafka publish finished: published=%d", count)

    ti = context["ti"]
    ti.xcom_push(key="rss_count", value=count)
    return count


def task_summarize_results(**context: object) -> None:
    _ensure_src_on_syspath()

    from core.logger import get_logger

    logger = get_logger(__name__)
    ti = context["ti"]
    rss_count: int = ti.xcom_pull(task_ids="produce_rss", key="rss_count") or 0

    logger.info("[RSS collection summary] published=%d", rss_count)
    if rss_count == 0:
        logger.warning("[RSS collection summary] No articles were published in this run.")


def task_check_dead_letter() -> None:
    _ensure_src_on_syspath()

    from core.config import settings
    from core.logger import get_logger

    logger = get_logger(__name__)
    dl_file = Path(settings.state_dir) / "dead_letter.jsonl"
    if not dl_file.exists():
        logger.info("[Dead letter check] Dead letter file does not exist.")
        return

    line_count = sum(1 for _ in dl_file.open(encoding="utf-8"))
    logger.info("[Dead letter check] accumulated_failed_messages=%d path=%s", line_count, dl_file)
    if line_count >= 100:
        logger.warning("[Dead letter check] Failed message count exceeded threshold: count=%d", line_count)


with DAG(
    dag_id="rss_ingest_dag",
    default_args=default_args,
    description="Collect RSS feeds and publish normalized messages to Kafka",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["news", "kafka", "ingestion", "rss"],
) as dag:
    check_kafka_health = PythonOperator(
        task_id="check_kafka_health",
        python_callable=task_check_kafka_health,
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

    check_kafka_health >> [produce_rss, check_dead_letter]
    produce_rss >> summarize_results
    produce_rss >> check_dead_letter
