"""복합명사 후보 자동 추출 DAG.

매일 새벽 3시에 전날 수집된 기사를 대상으로 복합명사 후보를 추출하고
compound_noun_candidates 테이블에 누적한다.

관리자는 Web/API를 통해 후보를 검토한 뒤 승인(→ compound_noun_dict 반영)
또는 거부(rejected) 처리한다. 승인된 단어는 다음 Spark 잡 재시작 시
Kiwi 사용자 사전에 자동 반영된다.

설정값 (환경변수):
    COMPOUND_EXTRACTION_WINDOW_DAYS   기본 1 (전날 하루치 기사)
    COMPOUND_EXTRACTION_MIN_FREQUENCY 기본 3 (최소 3회 이상 출현한 조합)
    COMPOUND_EXTRACTION_MIN_CHAR_LENGTH 기본 4 (최소 4글자 이상)
    COMPOUND_EXTRACTION_MAX_MORPHEME_COUNT 기본 4 (최대 4개 형태소 합산)
"""

from __future__ import annotations

from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


_DEFAULT_ARGS = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=10),
}


def _run_extraction(**context) -> None:
    """Airflow task 진입점 — compound_extractor.run_extraction_job() 호출."""
    import sys
    from pathlib import Path

    # Airflow 컨테이너에서 src 경로를 PYTHONPATH에 추가
    src_path = str(Path(__file__).resolve().parents[2] / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    from analytics.compound_extractor import run_extraction_job

    # data_interval_end 기준으로 window를 설정해 재처리 멱등성 확보
    until: datetime = context["data_interval_end"]
    result = run_extraction_job(until=until)

    print(
        f"[compound_extraction] "
        f"articles={result['article_count']} "
        f"candidates={result['candidate_count']} "
        f"new={result['new_count']} "
        f"updated={result['updated_count']}"
    )


with DAG(
    dag_id="compound_noun_extraction",
    description="수집된 기사에서 복합명사 후보를 자동 추출해 DB에 누적",
    schedule="0 3 * * *",
    start_date=datetime(2025, 1, 1),
    catchup=False,
    max_active_runs=1,
    default_args=_DEFAULT_ARGS,
    tags=["nlp", "dictionary"],
) as dag:
    extract_candidates = PythonOperator(
        task_id="extract_compound_candidates",
        python_callable=_run_extraction,
    )
