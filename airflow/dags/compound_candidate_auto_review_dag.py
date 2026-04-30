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
    from core.logger import get_logger

    logger = get_logger(__name__)
    limit = 2000
    logger.info("[자동 검토] 복합명사 후보 자동 검토를 시작합니다. limit=%d", limit)
    result = run_auto_review(limit=limit)
    logger.info("[자동 검토] 복합명사 후보 자동 검토 완료: %s", result)
    return result


with DAG(
    dag_id="compound_candidate_auto_review_dag",
    default_args=default_args,
    description="복합명사 후보 자동 검토",
    start_date=datetime(2026, 1, 1),
    schedule="0 */2 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["용어사전", "복합명사", "자동검토"],
) as dag:

    auto_review = PythonOperator(
        task_id="auto_review",
        python_callable=task_auto_review,
    )
