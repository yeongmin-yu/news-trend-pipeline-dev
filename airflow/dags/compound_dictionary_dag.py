from __future__ import annotations

"""compound_dictionary_dag — 복합명사 후보 추출 및 자동 승인 DAG.

Task 흐름:
    extract_compound_candidates
        └── auto_approve_compound_candidates
            └── summarize_dictionary_results

설계 원칙:
  - 후보 생성과 외부 API 기반 자동 승인을 Spark streaming 경로에서 분리한다.
  - extraction은 news_raw를 읽어 compound_noun_candidates에 후보를 누적한다.
  - auto approve는 검토 대기 후보에 대해 Naver 백과사전 API를 호출한다.
  - 검색 결과가 확인된 후보는 approved 처리 후 compound_noun_dict에 source='auto-approved'로 반영한다.
  - max_active_runs=1로 같은 후보 집합에 대한 중복 승인 실행을 방지한다.
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
}


def _ensure_src_on_syspath() -> None:
    """프로젝트의 src 디렉토리를 sys.path에 추가한다."""
    import sys

    src_dir = Path(__file__).resolve().parents[2] / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def task_extract_compound_candidates(**context: object) -> dict[str, int]:
    """news_raw 기반 복합명사 후보를 추출해 compound_noun_candidates에 upsert한다."""
    _ensure_src_on_syspath()

    from analytics.compound_extractor import run_extraction_job
    from core.logger import get_logger

    logger = get_logger(__name__)
    result = run_extraction_job()
    logger.info("복합명사 후보 추출 결과: %s", result)

    ti = context["ti"]
    ti.xcom_push(key="extraction_result", value=result)
    return result


def task_auto_approve_compound_candidates(**context: object) -> dict[str, int]:
    """검토 대기 복합명사 후보를 Naver 백과사전 기반으로 자동 승인한다."""
    _ensure_src_on_syspath()

    from analytics.compound_auto_approver import run_compound_auto_approve
    from core.logger import get_logger

    logger = get_logger(__name__)
    result = run_compound_auto_approve()
    logger.info("복합명사 자동 승인 결과: %s", result)

    ti = context["ti"]
    ti.xcom_push(key="auto_approve_result", value=result)
    return result


def task_summarize_dictionary_results(**context: object) -> None:
    """후보 추출/자동 승인 결과를 XCom에서 읽어 요약 로그를 남긴다."""
    _ensure_src_on_syspath()

    from core.logger import get_logger

    logger = get_logger(__name__)
    ti = context["ti"]

    extraction = ti.xcom_pull(task_ids="extract_compound_candidates", key="extraction_result") or {}
    auto_approve = ti.xcom_pull(task_ids="auto_approve_compound_candidates", key="auto_approve_result") or {}

    logger.info(
        "=== 복합명사 사전 처리 요약 === extraction=%s auto_approve=%s",
        extraction,
        auto_approve,
    )

    if int(extraction.get("candidate_count", 0) or 0) == 0:
        logger.info("이번 실행에서 새로 추출된 복합명사 후보가 없습니다.")

    if int(auto_approve.get("total", 0) or 0) == 0:
        logger.info("이번 실행에서 자동 승인 검토 대상 후보가 없습니다.")


with DAG(
    dag_id="compound_dictionary_dag",
    default_args=default_args,
    description="news_raw 기반 복합명사 후보 추출 후 Naver 백과사전으로 자동 승인하는 DAG",
    start_date=datetime(2026, 1, 1),
    schedule="0 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["dictionary", "compound-noun", "analytics"],
) as dag:

    extract_compound_candidates = PythonOperator(
        task_id="extract_compound_candidates",
        python_callable=task_extract_compound_candidates,
    )

    auto_approve_compound_candidates = PythonOperator(
        task_id="auto_approve_compound_candidates",
        python_callable=task_auto_approve_compound_candidates,
    )

    summarize_dictionary_results = PythonOperator(
        task_id="summarize_dictionary_results",
        python_callable=task_summarize_dictionary_results,
    )

    extract_compound_candidates >> auto_approve_compound_candidates >> summarize_dictionary_results
