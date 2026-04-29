from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


def _ensure_src_on_syspath() -> None:
    import sys

    src_dir = Path(__file__).resolve().parents[2] / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def task_run_compound_keyword_backfill(**context: Any) -> dict[str, Any]:
    _ensure_src_on_syspath()

    from analytics.compound_backfill import run_compound_keyword_backfill
    from core.logger import get_logger

    logger = get_logger(__name__)
    params = context["params"]
    result = run_compound_keyword_backfill(
        word=str(params.get("word") or "").strip(),
        domain=str(params.get("domain") or "all").strip() or "all",
        since=params.get("since") or None,
        until=params.get("until") or None,
        dry_run=bool(params.get("dry_run") or False),
    )
    logger.info("compound keyword backfill result: %s", result)
    return result


with DAG(
    dag_id="compound_keyword_backfill",
    default_args=default_args,
    description="Re-tokenize historical news_raw rows for a compound noun and rebuild impacted keyword aggregates",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    params={
        "word": "",
        "domain": "all",
        "since": "",
        "until": "",
        "dry_run": False,
    },
    tags=["용어사전", "복합명사", "과거재처리"],
) as dag:
    run_backfill = PythonOperator(
        task_id="run_compound_keyword_backfill",
        python_callable=task_run_compound_keyword_backfill,
    )
