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
    word = str(params.get("word") or "").strip()
    domain = str(params.get("domain") or "all").strip() or "all"
    since = params.get("since") or None
    until = params.get("until") or None
    dry_run = bool(params.get("dry_run") or False)
    logger.info(
        "[복합 키워드 재처리] 과거 데이터 재토큰화를 시작합니다. 단어=%s, 도메인=%s, 시작일=%s, 종료일=%s, 미리보기=%s",
        word or "(전체)",
        domain,
        since or "(제한 없음)",
        until or "(제한 없음)",
        dry_run,
    )
    result = run_compound_keyword_backfill(
        word=word,
        domain=domain,
        since=since,
        until=until,
        dry_run=dry_run,
    )
    logger.info("[복합 키워드 재처리] 과거 데이터 재토큰화 완료: %s", result)
    return result


with DAG(
    dag_id="compound_keyword_backfill",
    default_args=default_args,
    description="복합명사 기준으로 과거 news_raw 데이터를 재토큰화하고 영향받은 키워드 집계를 재생성",
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
