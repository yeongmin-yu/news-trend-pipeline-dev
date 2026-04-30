# Kafka Health Recovery

이 문서는 Docker healthcheck와 Airflow 기반 Kafka 복구 DAG 운영 방법을 정리합니다.

## 구성

- `docker-compose.kafka-health.yml`
  - Kafka 컨테이너에 Docker healthcheck를 추가합니다.
  - Airflow 컨테이너에 `/var/run/docker.sock`을 mount합니다.
  - Airflow에서 사용할 `KAFKA_CONTAINER_NAME` 환경변수를 전달합니다.
- `airflow/dags/kafka_recovery_dag.py`
  - Kafka 컨테이너 health status를 `docker inspect`로 확인합니다.
  - 상태가 `healthy`이면 재시작하지 않습니다.
  - 상태가 `starting`이면 Kafka bootstrap 중일 수 있으므로 재시작하지 않습니다.
  - 그 외 상태이면 `docker restart`로 Kafka 컨테이너를 재시작합니다.
  - 재시작 후 `KafkaAdminClient`로 broker 연결을 검증합니다.
- `infra/airflow/Dockerfile.airflow`
  - Airflow 컨테이너에서 Docker CLI를 사용할 수 있도록 설치합니다.

## 실행 방법

기존 compose 파일에 override 파일을 함께 지정합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.kafka-health.yml up --build -d
```

Airflow UI에서 `kafka_recovery_dag`를 수동 실행합니다.

## 확인 명령

```bash
docker inspect --format='{{.State.Health.Status}}' kafka
docker compose ps kafka
```

## 주의 사항

Airflow 컨테이너에 `/var/run/docker.sock`을 mount하면 Airflow가 호스트 Docker daemon을 제어할 수 있습니다. 이 DAG는 운영자만 실행할 수 있도록 Airflow 권한을 제한하는 것을 권장합니다.

Docker healthcheck는 상태를 표시할 뿐 unhealthy 컨테이너를 자동 재시작하지 않습니다. 자동 복구는 이 DAG처럼 별도 실행 주체가 수행합니다.
