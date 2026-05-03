from __future__ import annotations

"""pg_partman 의 run_maintenance_proc() 를 일 1회 호출.

미래 파티션을 미리 만들고(premake), 만료된 과거 파티션을 자동 회수한다.
대상 테이블 등록과 retention 정책은 db/migration/V2__pg_partman_setup.sql 참조.
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
}


def _ensure_src_on_syspath() -> None:
    import sys

    src_dir = Path(__file__).resolve().parents[2] / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))


def task_run_partman_maintenance() -> None:
    _ensure_src_on_syspath()

    import psycopg2

    from core.config import settings
    from core.logger import get_logger

    logger = get_logger(__name__)

    # run_maintenance_proc() 는 내부적으로 COMMIT 을 호출하는 stored procedure 이므로
    # autocommit=True 로 두어 트랜잭션 밖에서 실행해야 한다.
    conn = psycopg2.connect(settings.postgres_dsn)
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            logger.info("partman 유지보수 시작")
            cursor.execute("CALL partman.run_maintenance_proc()")

            cursor.execute(
                """
                SELECT parent_table, retention, premake
                  FROM partman.part_config
                 ORDER BY parent_table
                """
            )
            for parent_table, retention, premake in cursor.fetchall():
                logger.info(
                    "partman 등록 테이블: %s | retention=%s | premake=%s",
                    parent_table,
                    retention,
                    premake,
                )

            cursor.execute(
                """
                SELECT inhparent::regclass AS parent,
                       count(*) AS partition_count
                  FROM pg_inherits
                 WHERE inhparent IN (
                     'public.keyword_relations'::regclass,
                     'public.keyword_trends'::regclass
                 )
                 GROUP BY inhparent
                 ORDER BY parent
                """
            )
            for parent, partition_count in cursor.fetchall():
                logger.info("현재 파티션 수: %s = %s개", parent, partition_count)
    finally:
        conn.close()

    logger.info("partman 유지보수 완료")


with DAG(
    dag_id="partition_maintenance",
    description="pg_partman 으로 keyword_* 파티션 자동 생성/회수",
    default_args=default_args,
    start_date=datetime(2026, 1, 1),
    schedule="0 2 * * *",  # 매일 새벽 2시 KST
    catchup=False,
    max_active_runs=1,
    tags=["maintenance", "db"],
) as dag:
    PythonOperator(
        task_id="run_partman_maintenance",
        python_callable=task_run_partman_maintenance,
    )
