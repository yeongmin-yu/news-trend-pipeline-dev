from __future__ import annotations

"""Kafka Docker health recovery DAG.

이 DAG는 Docker health status를 확인하고 unhealthy 상태인 Kafka 컨테이너를
재시작한 뒤 Kafka broker 연결이 회복되었는지 검증합니다.

전제 조건:
  - docker-compose.yml에서 Kafka 컨테이너 이름이 KAFKA_CONTAINER_NAME과 일치해야 합니다.
  - Airflow 컨테이너에 /var/run/docker.sock 이 mount되어 있어야 합니다.
  - Docker CLI가 Airflow 이미지에 포함되어 있거나 설치되어 있어야 합니다.
"""

import os
import logging
import subprocess
import time
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


LOGGER = logging.getLogger(__name__)


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


def _run_command(command: list[str]) -> str:
    LOGGER.info("[공통] 명령어 실행: %s", " ".join(command))
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        LOGGER.error(
            "[공통] 명령어 실행 실패: returncode=%s, stdout=%s, stderr=%s",
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
        raise RuntimeError(
            f"명령어 실행 실패: {' '.join(command)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    LOGGER.info("[공통] 명령어 실행 성공: %s", result.stdout.strip() or "(출력 없음)")
    return result.stdout.strip()


def task_check_kafka_container_health(**context: object) -> str:
    container_name = os.getenv("KAFKA_CONTAINER_NAME", "kafka")
    LOGGER.info("[상태 확인] Kafka 컨테이너 상태 확인을 시작합니다. 컨테이너=%s", container_name)
    status = _run_command([
        "docker",
        "inspect",
        "--format",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        container_name,
    ])

    context["ti"].xcom_push(key="kafka_container_status", value=status)
    LOGGER.info("[상태 확인] Kafka 컨테이너 현재 상태: %s", status)
    LOGGER.info("[상태 확인] 다음 task에서 사용할 상태 값을 XCom에 저장했습니다. key=kafka_container_status")
    return status


def task_restart_kafka_if_unhealthy(**context: object) -> str:
    container_name = os.getenv("KAFKA_CONTAINER_NAME", "kafka")
    LOGGER.info("[재시작 판단] Kafka 컨테이너 재시작 필요 여부를 확인합니다. 컨테이너=%s", container_name)
    status = context["ti"].xcom_pull(
        task_ids="check_kafka_container_health",
        key="kafka_container_status",
    )
    LOGGER.info("[재시작 판단] 이전 task에서 전달받은 Kafka 상태: %s", status)

    if status == "healthy":
        LOGGER.info("[재시작 판단] Kafka가 healthy 상태입니다. 재시작하지 않고 건너뜁니다.")
        return "skipped"

    if status == "starting":
        LOGGER.info("[재시작 판단] Kafka가 아직 starting 상태입니다. 부팅 중단을 피하기 위해 재시작하지 않습니다.")
        return "skipped_starting"

    LOGGER.warning(
        "[재시작 실행] Kafka 상태가 정상적이지 않습니다. 컨테이너를 재시작합니다. 상태=%s, 컨테이너=%s",
        status,
        container_name,
    )
    _run_command(["docker", "restart", container_name])
    LOGGER.info("[재시작 실행] Kafka 컨테이너 재시작 명령이 완료되었습니다. 컨테이너=%s", container_name)
    return "restarted"


def task_verify_kafka_broker() -> None:
    from kafka import KafkaAdminClient

    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    max_wait_seconds = int(os.getenv("KAFKA_RECOVERY_VERIFY_MAX_WAIT_SECONDS", "180"))
    retry_interval_seconds = int(os.getenv("KAFKA_RECOVERY_VERIFY_RETRY_INTERVAL_SECONDS", "10"))
    request_timeout_ms = int(os.getenv("KAFKA_RECOVERY_VERIFY_REQUEST_TIMEOUT_MS", "5000"))
    deadline = time.monotonic() + max_wait_seconds
    attempt = 0

    LOGGER.info(
        "[브로커 검증] Kafka 브로커 연결 검증을 시작합니다. 부트스트랩서버=%s, 최대대기=%d초, 재시도간격=%d초",
        bootstrap_servers,
        max_wait_seconds,
        retry_interval_seconds,
    )

    while True:
        attempt += 1
        admin = None
        remaining_seconds = max(0, int(deadline - time.monotonic()))
        LOGGER.info(
            "[브로커 검증] Kafka 브로커 연결 확인 시도 중입니다. 시도=%d, 남은대기=%d초",
            attempt,
            remaining_seconds,
        )

        try:
            admin = KafkaAdminClient(
                bootstrap_servers=bootstrap_servers,
                request_timeout_ms=request_timeout_ms,
            )
            topics = admin.list_topics()
            LOGGER.info(
                "[브로커 검증] Kafka 브로커 연결 성공. 시도=%d, 부트스트랩서버=%s, 토픽수=%d, 토픽목록=%s",
                attempt,
                bootstrap_servers,
                len(topics),
                topics,
            )
            return
        except Exception as exc:
            if time.monotonic() >= deadline:
                LOGGER.error(
                    "[브로커 검증] Kafka 브로커 연결 검증 실패. 최대 대기시간을 초과했습니다. 시도=%d, 최대대기=%d초, 마지막오류=%s",
                    attempt,
                    max_wait_seconds,
                    exc,
                )
                raise RuntimeError(
                    f"Kafka 브로커 연결 검증 실패: {max_wait_seconds}초 동안 연결되지 않았습니다."
                ) from exc

            sleep_seconds = min(retry_interval_seconds, max(1, int(deadline - time.monotonic())))
            LOGGER.warning(
                "[브로커 검증] 아직 Kafka 브로커에 연결할 수 없습니다. 컨테이너 기동을 기다린 뒤 재시도합니다. 시도=%d, 다음재시도=%d초후, 오류=%s",
                attempt,
                sleep_seconds,
                exc,
            )
            time.sleep(sleep_seconds)
        finally:
            if admin is not None:
                admin.close()
                LOGGER.info("[브로커 검증] Kafka admin client 연결을 종료했습니다. 시도=%d", attempt)


with DAG(
    dag_id="kafka_recovery_dag",
    default_args=default_args,
    description="Kafka Docker health 상태를 확인하고 비정상 컨테이너를 재시작",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["카프카", "복구", "도커"],
) as dag:
    check_kafka_container_health = PythonOperator(
        task_id="check_kafka_container_health",
        python_callable=task_check_kafka_container_health,
    )

    restart_kafka_if_unhealthy = PythonOperator(
        task_id="restart_kafka_if_unhealthy",
        python_callable=task_restart_kafka_if_unhealthy,
    )

    verify_kafka_broker = PythonOperator(
        task_id="verify_kafka_broker",
        python_callable=task_verify_kafka_broker,
    )

    check_kafka_container_health >> restart_kafka_if_unhealthy >> verify_kafka_broker
