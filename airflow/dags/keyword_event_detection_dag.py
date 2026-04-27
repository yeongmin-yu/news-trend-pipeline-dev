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

    until: datetime = context["data_interval_end"]
    result = run_event_detection_job(until=until, lookback_hours=24)
    print(
        f"[keyword_event_detection] source_rows={result['source_row_count']} "
        f"event_rows={result['event_row_count']}"
    )


with DAG(
    dag_id="keyword_event_detection",
    description="keyword_trends를 기반으로 STEP3 이벤트 후보를 계산해 keyword_events에 적재",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["event", "analytics", "step3"],
) as dag:
    detect_events = PythonOperator(
        task_id="detect_keyword_events",
        python_callable=_run_event_detection,
    )
