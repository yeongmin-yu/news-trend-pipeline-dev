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
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


default_args = {
    "owner": "ymyu",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}


def _run_command(command: list[str]) -> str:
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(command)}\nstdout={result.stdout}\nstderr={result.stderr}"
        )
    return result.stdout.strip()


def task_check_kafka_container_health(**context: object) -> str:
    container_name = os.getenv("KAFKA_CONTAINER_NAME", "kafka")
    status = _run_command([
        "docker",
        "inspect",
        "--format",
        "{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}",
        container_name,
    ])

    context["ti"].xcom_push(key="kafka_container_status", value=status)
    print(f"Kafka container status: {status}")
    return status


def task_restart_kafka_if_unhealthy(**context: object) -> str:
    container_name = os.getenv("KAFKA_CONTAINER_NAME", "kafka")
    status = context["ti"].xcom_pull(
        task_ids="check_kafka_container_health",
        key="kafka_container_status",
    )

    if status == "healthy":
        print("Kafka container is healthy. Restart is skipped.")
        return "skipped"

    if status == "starting":
        print("Kafka container is still starting. Restart is skipped to avoid interrupting bootstrap.")
        return "skipped_starting"

    print(f"Kafka container status is {status}. Restarting {container_name}...")
    _run_command(["docker", "restart", container_name])
    return "restarted"


def task_verify_kafka_broker() -> None:
    from kafka import KafkaAdminClient

    bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
    admin = KafkaAdminClient(
        bootstrap_servers=bootstrap_servers,
        request_timeout_ms=10_000,
    )
    try:
        topics = admin.list_topics()
        print(f"Kafka broker recovered: bootstrap={bootstrap_servers}, topics={topics}")
    finally:
        admin.close()


with DAG(
    dag_id="kafka_recovery_dag",
    default_args=default_args,
    description="Check Kafka Docker health status and restart the Kafka container when unhealthy",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["kafka", "recovery", "docker"],
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
