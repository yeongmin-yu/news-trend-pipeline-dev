from __future__ import annotations

"""stopword_recommender_dag — 불용어 후보 자동 추천 DAG.

Task 흐름:
    run_stopword_recommender
        └── summarize_results

설계 원칙:
  - 최근 7일 keyword_trends / keywords / keyword_relations 데이터를 기반으로
    다중 신호 스코어를 계산해 stopword_candidates 테이블에 누적한다.
  - 이미 approved / rejected 된 단어는 건너뛴다.
  - 매일 새벽 3시 KST 실행 (파티션 유지보수 새벽 2시와 겹치지 않도록 1시간 후 배치).
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 1,
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


def task_run_stopword_recommender(**context: object) -> dict[str, int]:
    """최근 7일 키워드 데이터에서 불용어 후보를 추천해 stopword_candidates에 upsert한다."""
    _ensure_src_on_syspath()

    from analytics.stopword_recommender import run_stopword_recommender
    from core.logger import get_logger

    logger = get_logger(__name__)
    logger.info("[불용어 추천] 불용어 후보 자동 추천을 시작합니다.")
    result = run_stopword_recommender()
    logger.info("[불용어 추천] 완료: %s", result)

    context["ti"].xcom_push(key="recommender_result", value=result)
    return result


def task_summarize_results(**context: object) -> None:
    """추천 결과를 XCom에서 읽어 요약 로그를 남긴다."""
    _ensure_src_on_syspath()

    from core.logger import get_logger

    logger = get_logger(__name__)
    result = context["ti"].xcom_pull(
        task_ids="run_stopword_recommender", key="recommender_result"
    ) or {}

    total = result.get("total_analyzed", 0)
    candidates = result.get("candidates", 0)
    new = result.get("new", 0)
    updated = result.get("updated", 0)

    logger.info(
        "[불용어 추천 요약] total_analyzed=%d | candidates=%d | new=%d | updated=%d",
        total, candidates, new, updated,
    )
    if candidates == 0:
        logger.info("[불용어 추천 요약] 임계값 이상의 신규 후보가 없습니다.")


with DAG(
    dag_id="stopword_recommender_dag",
    default_args=default_args,
    description="최근 7일 키워드 데이터 기반 불용어 후보 자동 추천 DAG",
    start_date=datetime(2026, 1, 1),
    schedule="0 3 * * *",  # 매일 새벽 3시 KST
    catchup=False,
    max_active_runs=1,
    tags=["용어사전", "불용어", "후보추천"],
) as dag:

    run_stopword_recommender = PythonOperator(
        task_id="run_stopword_recommender",
        python_callable=task_run_stopword_recommender,
    )

    summarize_results = PythonOperator(
        task_id="summarize_results",
        python_callable=task_summarize_results,
    )

    run_stopword_recommender >> summarize_results
