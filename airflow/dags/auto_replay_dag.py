from __future__ import annotations

"""auto_replay_dag — Dead Letter 자동 재처리 DAG (15분 주기)

Task 흐름:
    check_kafka_health
        └── replay_dead_letters
            ├── summarize_replay_results
            └── check_permanent_failures

설계 원칙:
  - max_active_runs=1 : 동시 실행 방지
  - catchup=False     : 과거 누락 실행 스킵
  - 15분마다 자동 실행되어 news_ingest_dag와 병렬로 동작
  - `python -m news_trend_pipeline.ingestion.replay` 를 subprocess로 호출해 dead_letter.jsonl 재처리
  - 재처리 결과를 XCom으로 집계해 모니터링
  - 영구 실패 메시지는 별도 모니터링 태스크에서 감시

src layout: DAG → airflow/dags/ → 프로젝트 루트의 `src/` 를 sys.path에 추가하여
`news_trend_pipeline` 패키지를 import합니다.
"""

from datetime import datetime, timedelta
from pathlib import Path
import subprocess

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator

# ── 공통 설정 ─────────────────────────────────────────────────────────────────

default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _ensure_src_on_syspath() -> Path:
    """프로젝트의 `src/` 디렉토리를 sys.path에 추가하고 프로젝트 루트 Path를 반환한다."""
    import sys
    project_root = Path(__file__).resolve().parents[2]
    src_dir = project_root / "src"
    if src_dir.exists() and str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    return project_root


# ── Task 함수 ─────────────────────────────────────────────────────────────────


def task_check_kafka_health() -> None:
    """KafkaAdminClient로 브로커 연결 상태를 확인합니다.

    연결 실패 시 예외를 발생시켜 후속 Task를 차단합니다.
    """
    _ensure_src_on_syspath()

    from kafka import KafkaAdminClient
    from kafka.errors import NoBrokersAvailable

    from news_trend_pipeline.core.config import settings
    from news_trend_pipeline.core.logger import get_logger

    logger = get_logger(__name__)

    try:
        admin = KafkaAdminClient(
            bootstrap_servers=settings.kafka_bootstrap_servers,
            request_timeout_ms=10_000,
        )
        topics = admin.list_topics()
        admin.close()
        logger.info("Kafka 헬스체크 통과 (재처리 DAG): broker=%s", settings.kafka_bootstrap_servers)
    except NoBrokersAvailable as exc:
        raise RuntimeError(
            f"Kafka 브로커에 연결할 수 없습니다: {settings.kafka_bootstrap_servers}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(f"Kafka 헬스체크 실패: {exc}") from exc


def task_replay_dead_letters(**context: object) -> dict[str, int]:
    """news_trend_pipeline.ingestion.replay 모듈을 subprocess로 호출해 Dead Letter를 재처리합니다.

    dead_letter.jsonl이 없으면 빈 결과를 반환합니다.
    결과를 딕셔너리로 반환하고 XCom에 push합니다.
    """
    import os
    import sys

    project_root = _ensure_src_on_syspath()
    # Docker 환경에서는 PYTHONPATH=/opt/news-trend-pipeline/src 가 설정되어 있으므로
    # 그 부모를 프로젝트 루트로 사용한다.
    pythonpath_env = os.getenv("PYTHONPATH", "")
    if pythonpath_env:
        first_entry = pythonpath_env.split(os.pathsep)[0]
        candidate_root = Path(first_entry).parent
        if (candidate_root / "runtime").exists() or (candidate_root / "src").exists():
            project_root = candidate_root

    from news_trend_pipeline.core.config import settings
    from news_trend_pipeline.core.logger import get_logger

    logger = get_logger(__name__)

    # dead_letter.jsonl 파일 확인
    state_dir = Path(settings.state_dir)
    dead_letter_file = state_dir / "dead_letter.jsonl"
    if not dead_letter_file.exists():
        logger.info("Dead Letter 파일이 없습니다. 재처리할 메시지가 없습니다.")
        return {
            "success": 0,
            "skip": 0,
            "retry_fail": 0,
            "permanent_fail": 0,
            "total_processed": 0,
        }

    src_dir = project_root / "src"

    try:
        logger.info("재처리 모듈 실행: python -m news_trend_pipeline.ingestion.replay (cwd=%s)", project_root)

        env = os.environ.copy()
        # src/ 를 PYTHONPATH 앞에 유지
        existing = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            f"{src_dir}{os.pathsep}{existing}" if existing else str(src_dir)
        )

        result = subprocess.run(
            [sys.executable, "-m", "news_trend_pipeline.ingestion.replay"],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,  # 5분 타임아웃
            env=env,
        )

        if result.returncode != 0:
            logger.error("재처리 모듈 실패 (code=%d): %s", result.returncode, result.stderr)
            raise RuntimeError(f"replay 실행 실패: {result.stderr}")

        logger.info("재처리 모듈 완료:\n%s", result.stderr)

        # 결과 파일들의 건수를 파악해 결과 딕셔너리 생성
        replayed_file = state_dir / "dead_letter_replayed.jsonl"
        permanent_file = state_dir / "dead_letter_permanent.jsonl"

        replayed_count = sum(1 for _ in replayed_file.open(encoding="utf-8")) if replayed_file.exists() else 0
        permanent_count = sum(1 for _ in permanent_file.open(encoding="utf-8")) if permanent_file.exists() else 0
        remaining_count = sum(1 for _ in dead_letter_file.open(encoding="utf-8")) if dead_letter_file.exists() else 0

        results = {
            "success": replayed_count,  # 이번 실행에서 성공한 건수 (누적)
            "skip": 0,  # 로그에서 파싱 필요
            "retry_fail": remaining_count,
            "permanent_fail": permanent_count,
            "total_processed": replayed_count + remaining_count + permanent_count,
        }

        ti = context["ti"]
        ti.xcom_push(key="replay_results", value=results)

        logger.info(
            "재처리 결과 (DAG): 성공=%d건 | 재실패=%d건 | 영구실패=%d건",
            replayed_count,
            remaining_count,
            permanent_count,
        )

        return results

    except subprocess.TimeoutExpired as exc:
        logger.error("재처리 모듈 타임아웃 (5분 초과)")
        raise RuntimeError("replay 타임아웃") from exc
    except Exception as exc:
        logger.error("재처리 중 예외 발생: %s", exc)
        raise


def task_summarize_replay_results(**context: object) -> None:
    """재처리 결과를 XCom에서 읽어 요약 로그를 남깁니다."""
    _ensure_src_on_syspath()

    from news_trend_pipeline.core.logger import get_logger

    logger = get_logger(__name__)
    ti = context["ti"]

    results = ti.xcom_pull(task_ids="replay_dead_letters", key="replay_results") or {}

    success = results.get("success", 0)
    skip = results.get("skip", 0)
    retry_fail = results.get("retry_fail", 0)
    permanent_fail = results.get("permanent_fail", 0)
    total = results.get("total_processed", 0)

    if total == 0:
        logger.info("Dead Letter가 없습니다. 재처리할 메시지가 없습니다.")
        return

    logger.info(
        "=== 재처리 실행 요약 === 성공=%d건 | 중복skip=%d건 | 재실패=%d건 | 영구실패=%d건 | 합계=%d건",
        success,
        skip,
        retry_fail,
        permanent_fail,
        total,
    )

    if permanent_fail > 0:
        logger.warning(
            "[경고] %d건의 메시지가 영구 실패 상태입니다. "
            "상세 내용은 runtime/state/dead_letter_permanent.jsonl을 확인하고 수동 개입하세요.",
            permanent_fail,
        )


def task_check_permanent_failures() -> None:
    """dead_letter_permanent.jsonl을 모니터링하고 영구 실패 메시지 상세 정보를 기록합니다."""
    _ensure_src_on_syspath()

    from news_trend_pipeline.core.config import settings
    from news_trend_pipeline.core.logger import get_logger

    logger = get_logger(__name__)

    perm_file = Path(settings.state_dir) / "dead_letter_permanent.jsonl"

    if not perm_file.exists():
        logger.info("영구 실패 메시지 없음 (파일 미존재).")
        return

    try:
        count = sum(1 for _ in perm_file.open(encoding="utf-8"))
    except (IOError, OSError) as exc:
        logger.error("영구 실패 파일 읽기 실패: %s", exc)
        return

    if count == 0:
        logger.info("영구 실패 메시지 없음.")
        return

    logger.warning("[주의] 영구 실패 메시지 %d건 발견. 수동 개입이 필요합니다.", count)

    # 최근 5건의 영구 실패 메시지 표시
    import json

    try:
        recent_failures = []
        with perm_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        recent_failures.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        logger.warning("JSON 파싱 오류 (skip): %s", exc)

        # 최근 5건 표시
        for i, record in enumerate(recent_failures[-5:], start=1):
            payload = record.get("payload", {})
            logger.warning(
                "  [%d] provider=%s url=%s reason=%s attempt=%d permanent_fail_at=%s",
                i,
                payload.get("provider"),
                payload.get("url"),
                record.get("reason"),
                record.get("attempt"),
                record.get("permanent_fail_at"),
            )

        # 알림 발송 권장 (Slack, Email 등)
        logger.error(
            "➜ 권장 조치: "
            "1. runtime/state/dead_letter_permanent.jsonl 내용 확인 "
            "2. API 설정 또는 Kafka 설정 검토 "
            "3. 원인 해결 후 영구 실패 메시지 수동 재처리"
        )
    except (IOError, OSError) as exc:
        logger.error("영구 실패 메시지 상세 정보 읽기 실패: %s", exc)


# ── DAG 정의 ─────────────────────────────────────────────────────────────────

with DAG(
    dag_id="auto_replay_dag",
    default_args=default_args,
    description="Dead Letter 자동 재처리 파이프라인 (15분 주기)",
    start_date=datetime(2026, 1, 1),
    schedule="*/15 * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["news", "kafka", "replay"],
) as dag:

    check_kafka_health = PythonOperator(
        task_id="check_kafka_health",
        python_callable=task_check_kafka_health,
    )

    replay_dead_letters = PythonOperator(
        task_id="replay_dead_letters",
        python_callable=task_replay_dead_letters,
    )

    summarize_replay_results = PythonOperator(
        task_id="summarize_replay_results",
        python_callable=task_summarize_replay_results,
    )

    check_permanent_failures = PythonOperator(
        task_id="check_permanent_failures",
        python_callable=task_check_permanent_failures,
    )

    # Task 의존성 정의
    check_kafka_health >> replay_dead_letters
    replay_dead_letters >> [summarize_replay_results, check_permanent_failures]
