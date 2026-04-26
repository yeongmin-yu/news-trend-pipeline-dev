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


def _ensure_src():
    import sys
    src_dir = Path(__file__).resolve().parents[2] / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def extract_candidates(**context):
    _ensure_src()
    from analytics.compound_extractor import run_extraction_job
    return run_extraction_job()


def auto_approve(**context):
    _ensure_src()
    from analytics.compound_auto_approver import run_compound_auto_approve
    return run_compound_auto_approve()


with DAG(
    dag_id="compound_noun_extraction",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="0 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["dictionary"],
) as dag:

    t1 = PythonOperator(
        task_id="extract_candidates",
        python_callable=extract_candidates,
    )

    t2 = PythonOperator(
        task_id="auto_approve",
        python_callable=auto_approve,
    )

    t1 >> t2
