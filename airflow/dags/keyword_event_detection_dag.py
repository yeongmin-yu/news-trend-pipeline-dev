from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

_DEFAULT_ARGS = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _run_event_detection(**context) -> None:
    import sys

    src_path = str(Path(__file__).resolve().parents[2] / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from analytics.event_detector import run_event_detection_job
    from core.logger import get_logger

    logger = get_logger(__name__)

    until: datetime = context["data_interval_end"]
    logger.info("[이벤트 탐지] 키워드 이벤트 후보 계산을 시작합니다. 기준시각=%s, 조회기간=%d시간", until, 24)
    result = run_event_detection_job(until=until, lookback_hours=24)
    logger.info(
        "[이벤트 탐지] 키워드 이벤트 후보 계산 완료: 원본행=%s건, 이벤트행=%s건",
        result["source_row_count"],
        result["event_row_count"],
    )


with DAG(
    dag_id="keyword_event_detection",
    description="keyword_trends를 기반으로 STEP3 이벤트 후보를 계산해 keyword_events에 적재",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["분석", "이벤트탐지", "급상승"],
) as dag:
    detect_events = PythonOperator(
        task_id="detect_keyword_events",
        python_callable=_run_event_detection,
    )
