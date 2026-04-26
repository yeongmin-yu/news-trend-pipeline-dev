from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
}


def _ensure_src_on_syspath() -> None:
    import sys
    src_dir = Path(__file__).resolve().parents[2] / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def task_auto_review(**context):
    _ensure_src_on_syspath()
    from analytics.compound_auto_reviewer import run_auto_review
    return run_auto_review(limit=2000)


with DAG(
    dag_id="compound_candidate_auto_review_dag",
    default_args=default_args,
    description="compound candidate auto review",
    start_date=datetime(2026, 1, 1),
    schedule="0 */2 * * *",
    catchup=False,
    max_active_runs=1,
) as dag:

    auto_review = PythonOperator(
        task_id="auto_review",
        python_callable=task_auto_review,
    )
