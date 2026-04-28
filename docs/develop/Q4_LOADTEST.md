# 로드 테스트 및 장애 대응

> 이 문서는 6회차 발표를 위한 로드 테스트, 장애 대응, 모니터링, Fallback/Alert 준비 내용을 정리한다.
>
> 현재 레포지토리 기준으로 구현된 내용과 미구현된 내용을 분리해 기록하며, 미구현 항목은 향후 준비 방향을 함께 명시한다.

## 현재 구현 기준 요약

현재 프로젝트는 도메인별 뉴스 키워드를 수집하고 Kafka, Spark, PostgreSQL 파이프라인으로 처리한 뒤 FastAPI와 Dashboard로 조회하는 구조이다.

- Airflow 기반 수집 오케스트레이션
- Naver News API 수집 및 Kafka 적재
- Spark Structured Streaming 기반 기사 전처리와 키워드 집계
- PostgreSQL staging 및 upsert 기반 저장 계층
- FastAPI 조회/관리 API
- React + Vite Dashboard
- Health API, Airflow UI, Spark UI, 운영 지표 조회 등 STEP6 Monitoring 일부 반영
- 실패 건은 `runtime/state/dead_letter.jsonl`에 기록하고 `auto_replay_dag`에서 재처리

아직 전용 부하 생성 스크립트, 장애 시뮬레이션 스크립트, Prometheus/Grafana 같은 통합 모니터링 스택, Slack/Email Alert 자동화는 레포지토리 기준으로 미구현 상태로 본다.

---

## 1. 부하 시나리오 설계 (Excalidraw/Notion)

### 1.1 테스트 목적

검증하려는 상황은 다음과 같다.

1. Naver News API 수집량 증가 시 Kafka Producer가 안정적으로 메시지를 발행하는가?
2. Kafka topic에 메시지가 누적될 때 Spark Structured Streaming이 처리 지연 없이 소비하는가?
3. Spark 처리 결과가 PostgreSQL staging 및 upsert 경로로 정상 저장되는가?
4. FastAPI와 Dashboard 조회 API가 데이터 증가 상황에서도 응답 가능한가?
5. 장애 발생 시 dead letter, replay, 재시도, 수동 복구 절차로 데이터 유실을 최소화할 수 있는가?

### 1.2 예상 트래픽/데이터량

| 구분 | 평상시 | 피크 시 | 비고 |
| --- | --- | --- | --- |
| 검색어 수 | 5~10개 | 30~50개 | `query_keywords` 기준 확장 |
| 수집 주기 | 10~30분 단위 | 1~5분 단위 | Airflow DAG schedule 조정 필요 |
| 기사 수집량 | 실행 1회당 수십~수백 건 | 실행 1회당 수백~수천 건 | Naver API quota 고려 필요 |
| Kafka 메시지량 | 낮음 | 단시간 burst 발생 | local Kafka 단일 broker 한계 고려 |
| Spark 처리량 | local 처리 가능 수준 | micro-batch 지연 가능 | CPU/메모리 제약 영향 큼 |
| API 조회 | 개발자 수동 조회 | 발표/데모 중 반복 조회 | Dashboard 새로고침 포함 |

> 미구현: 실제 측정값은 아직 없다. `load_test.py` 또는 `stress_test.py`를 작성해 처리량, 지연 시간, 에러율을 측정해야 한다.

### 1.3 테스트 환경

현재 기본 실행 환경은 local Docker Compose 기반으로 가정한다.

| 항목 | 현재 기준 | 준비 방향 |
| --- | --- | --- |
| 실행 방식 | `docker compose up --build -d` | 동일 환경에서 재현 가능한 테스트 절차 작성 |
| Kafka | local broker, `9092` | broker 중단/재시작 시나리오 준비 |
| Spark | Spark Master UI `8080`, History UI `18080` | executor 메모리 제한 조정 및 OOM 재현 준비 |
| Airflow | UI/API `9080` | DAG 실패/재시도/SLA 미달 확인 절차 준비 |
| PostgreSQL | App DB `5432` | DB 연결 끊김, 저장 실패 fallback 검증 준비 |
| FastAPI | `8000`, `/health` | API 부하 테스트 및 health check 확인 |
| Dashboard | `3000` | 부하 후 조회 결과 확인 |

### 1.4 local 환경의 리소스 제약

local 환경은 실제 운영 환경보다 리소스가 작기 때문에 다음 제약을 문서화하고 테스트 결과 해석에 반영한다.

- CPU: Kafka, Spark, Airflow, PostgreSQL, FastAPI, Dashboard가 동시에 실행되므로 Spark micro-batch 지연이 쉽게 발생할 수 있다.
- 메모리: Spark executor/driver, Airflow scheduler/webserver, PostgreSQL이 동시에 메모리를 사용하므로 OOM 테스트 시 전체 Docker Desktop 메모리 제한도 함께 확인해야 한다.
- 디스크: Spark checkpoint, event log, Airflow log, dead letter 파일이 `runtime/` 아래에 누적될 수 있다.
- 네트워크: local Docker network 기준이므로 외부 Naver API 호출 지연과 내부 컨테이너 간 통신 지연을 구분해야 한다.

### 1.5 테스트 도구 선택

| 대상 | 도구 | 상태 | 준비 방향 |
| --- | --- | --- | --- |
| Kafka Producer 부하 | Python 스크립트 | 미구현 | `scripts/load_test.py` 작성, 더미 뉴스 메시지를 Kafka topic에 대량 발행 |
| API 조회 부하 | Python `requests` 또는 `locust` | 미구현 | `/health`, `/api/v1/dashboard/*` 반복 호출 |
| Spark 처리 확인 | Spark UI, History UI | 부분 구현 | batch duration, input rows, processing time 캡처 |
| Airflow DAG 확인 | Airflow UI/API | 부분 구현 | DAG success/failure, retry 횟수, duration 기록 |
| DB 상태 확인 | SQL query, FastAPI system API | 부분 구현 | row count, upsert 실패 여부, connection error 확인 |
| 통합 대시보드 | Prometheus/Grafana | 미구현 | 선택 사항으로 docker-compose에 exporter와 Grafana 추가 |

---

## 2. 장애 시나리오 및 대응 전략 (Excalidraw/Notion)

컴포넌트별 장애 발생 시 대응 전략은 다음과 같이 정리한다.

### 2.1 Kafka 장애

#### Broker 다운 시 Producer 동작

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Kafka broker 컨테이너 중단 또는 네트워크 단절 |
| 예상 현상 | Producer send 실패, Airflow 수집 task 실패 가능 |
| 현재 구현 | Kafka 적재 실패 시 dead letter 기록 및 replay 경로가 있는 것으로 정리됨 |
| 미구현/확인 필요 | broker 다운 상황에서 실제 producer retry, timeout, dead letter 기록 여부 테스트 필요 |
| 대응 전략 | Producer timeout/retry 설정 확인, 실패 메시지는 `runtime/state/dead_letter.jsonl`에 저장, broker 복구 후 `auto_replay_dag` 또는 수동 replay 실행 |
| 발표 데모 | `docker compose stop kafka` 후 수집 실행 → 실패 확인 → `docker compose start kafka` → replay 실행 |

#### Consumer lag 급증 시 대응

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Kafka 입력량이 Spark 처리량보다 많아 consumer lag 증가 |
| 예상 현상 | Dashboard 데이터 반영 지연, Spark micro-batch 처리 시간 증가 |
| 현재 구현 | Spark Structured Streaming 처리와 Spark UI/History UI 확인 가능 |
| 미구현/확인 필요 | consumer lag 측정 스크립트 또는 Kafka exporter 미구현 |
| 대응 전략 | Spark executor 메모리/코어 조정, micro-batch trigger 조정, keyword 처리 로직 최적화, topic partition 수 확장 검토 |
| 발표 데모 | 더미 메시지 대량 발행 후 Spark UI에서 batch duration 증가 확인 |

#### 메시지 유실/중복 시 처리

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Producer 재시도, replay, Spark 재처리로 동일 기사 중복 처리 가능 |
| 예상 현상 | `news_raw`, `keywords`, `keyword_trends` 중복 증가 가능 |
| 현재 구현 | `provider + domain + url` 기준 중복 제어 및 PostgreSQL upsert 경로가 있는 것으로 정리됨 |
| 미구현/확인 필요 | 중복 메시지 주입 테스트와 결과 테이블 중복 검증 자동화 미구현 |
| 대응 전략 | Kafka message key를 안정적으로 설정하고 DB unique constraint/upsert를 최종 방어선으로 사용, replay 시 idempotent 처리 보장 |
| 발표 데모 | 같은 URL 메시지를 여러 번 발행한 뒤 DB row count가 중복 증가하지 않는지 확인 |

### 2.2 Spark 장애

#### OOM (Out of Memory) 발생 시

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | 큰 batch, 과도한 collect/cache, executor 메모리 부족 |
| 예상 현상 | Spark job 실패, streaming query 중단, checkpoint 기준 재시작 필요 |
| 현재 구현 | Spark Structured Streaming, checkpoint 디렉터리, Spark UI/History UI 존재 |
| 미구현/확인 필요 | OOM 재현 스크립트 및 복구 절차 자동화 미구현 |
| 대응 전략 | executor/driver memory 조정, batch input size 제한, 불필요한 cache 제거, skew key 분산, checkpoint 유지 후 job 재시작 |
| 발표 데모 | Spark 메모리 제한을 낮춘 상태에서 대량 메시지 처리 후 실패 로그와 복구 방향 설명 |

#### 데이터 스큐(skew)로 인한 지연

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | 특정 domain/keyword에 데이터가 몰려 일부 task만 오래 실행 |
| 예상 현상 | Spark stage 지연, batch duration 증가 |
| 현재 구현 | 키워드/트렌드/연관어 집계 처리 경로 존재 |
| 미구현/확인 필요 | skew 데이터 생성기와 partition별 처리 시간 측정 미구현 |
| 대응 전략 | salting, repartition key 조정, hot keyword 별도 처리, 집계 전 필터링/샘플링 검토 |
| 발표 데모 | 특정 keyword에 편중된 메시지를 대량 발행하고 Spark UI에서 task duration 차이 설명 |

### 2.3 Airflow 장애

#### DAG 실패 시 알림

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Naver API 실패, Kafka 연결 실패, DB 연결 실패 등으로 DAG task 실패 |
| 예상 현상 | Airflow UI에서 task failed 표시 |
| 현재 구현 | Airflow UI/API로 DAG 상태 확인 가능 |
| 미구현/확인 필요 | Slack/Email alert callback 미구현 |
| 대응 전략 | DAG default_args에 retry, retry_delay, on_failure_callback 추가, Slack webhook 또는 EmailOperator 연동 |
| 발표 데모 | 환경 변수 누락 또는 Kafka 중단 상태에서 DAG 실패를 유도하고 UI에서 실패 확인 |

#### 재시도 후에도 실패 시 대응

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | retry 이후에도 외부 API/Kafka/DB 장애 지속 |
| 예상 현상 | 최종 task failed, 데이터 공백 발생 가능 |
| 현재 구현 | dead letter/replay 경로 존재 |
| 미구현/확인 필요 | retry exhausted 이후 runbook과 자동 알림 미구현 |
| 대응 전략 | 실패 원인별 runbook 작성, dead letter 파일 확인, 장애 복구 후 replay DAG 실행, 필요 시 수동 backfill |

#### SLA 미달 시 처리

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | DAG는 성공했지만 목표 시간 내 완료되지 않음 |
| 예상 현상 | 최신 데이터 반영 지연, Dashboard stale data 발생 |
| 현재 구현 | Airflow UI에서 duration 확인 가능 |
| 미구현/확인 필요 | SLA 설정과 SLA miss callback 미구현 |
| 대응 전략 | DAG별 목표 완료 시간 정의, SLA miss 알림, 지연 원인 Kafka/Spark/DB 병목 분리 |

---

## 3. 모니터링 전략 (Excalidraw/Notion)

수집, 처리, 저장, 서빙의 각 단계에서 어떤 지표를 수집하고 어떻게 시각화할지 정의한다.

### 3.1 Kafka 모니터링

| 지표 | 수집 방법 | 현재 상태 | 활용 |
| --- | --- | --- | --- |
| topic 메시지 수 | Kafka CLI 또는 Python consumer | 미구현 | producer 부하 확인 |
| consumer lag | Kafka consumer group describe 또는 exporter | 미구현 | Spark 처리 지연 감지 |
| producer error rate | producer 로그, Airflow task log | 부분 가능 | Kafka 장애 감지 |
| broker 상태 | Docker container status, Kafka exporter | 부분 가능 | broker 다운 감지 |

준비 방향:

- `scripts/consumer_check.py`를 확장해 topic 메시지 확인과 lag 확인 기능을 추가한다.
- 선택 사항으로 Kafka exporter와 Prometheus/Grafana를 docker-compose에 추가한다.
- 발표에서는 최소한 Kafka broker 중단 전후 producer 실패 로그와 복구 후 replay 결과를 보여준다.

### 3.2 Spark 모니터링

| 지표 | 수집 방법 | 현재 상태 | 활용 |
| --- | --- | --- | --- |
| input rows per second | Spark UI/Streaming query progress | 부분 가능 | 입력 부하 확인 |
| processed rows per second | Spark UI/로그 | 부분 가능 | 처리량 확인 |
| batch duration | Spark UI/History UI | 가능 | 지연 여부 판단 |
| failed tasks | Spark UI/History UI | 가능 | OOM/skew 확인 |
| checkpoint 상태 | `runtime/checkpoints` | 가능 | 재시작/복구 확인 |

준비 방향:

- Spark streaming query progress 로그를 파일 또는 DB에 남기는 방식 검토.
- OOM/skew 테스트 결과는 Spark UI 캡처 또는 로그로 발표 자료에 첨부.
- batch duration이 trigger interval보다 길어지는 경우 consumer lag 증가 가능성을 함께 설명한다.

### 3.3 Airflow 모니터링

| 지표 | 수집 방법 | 현재 상태 | 활용 |
| --- | --- | --- | --- |
| DAG run success/failure | Airflow UI/API | 가능 | 수집/분석 정상 여부 확인 |
| task duration | Airflow UI/API | 가능 | 병목 task 식별 |
| retry count | Airflow UI/API | 가능 | 외부 의존성 불안정 감지 |
| SLA miss | Airflow SLA 기능 | 미구현 | 목표 시간 초과 감지 |
| alert delivery | Slack/Email | 미구현 | 장애 즉시 인지 |

준비 방향:

- DAG별 실패 callback을 추가한다.
- Slack webhook 또는 Email 알림 채널을 `.env` 기반으로 설정한다.
- 발표에서는 Airflow UI에서 실패/재시도 상태를 보여주고, 알림은 미구현이면 Notion/Excalidraw에 설계로 대체한다.

---

## 4. Fallback / Alert 전략

### 4.1 알림 조건

| 조건 | 심각도 | 알림 필요 여부 | 대응 |
| --- | --- | --- | --- |
| Kafka broker 다운 | Critical | 즉시 알림 | broker 복구 후 replay |
| Producer send 실패율 증가 | Critical | 즉시 알림 | dead letter 확인, API/Kafka 상태 확인 |
| Consumer lag 임계치 초과 | Warning/Critical | 알림 | Spark 리소스/처리량 확인 |
| Spark query 중단 | Critical | 즉시 알림 | checkpoint 기반 재시작 |
| Spark batch duration 지속 증가 | Warning | 알림 | skew, 메모리, partition 확인 |
| Airflow DAG 실패 | Critical | 즉시 알림 | retry 후 원인별 runbook 수행 |
| Airflow SLA miss | Warning | 알림 | DAG duration 분석 |
| DB 저장 실패 | Critical | 즉시 알림 | fallback 파일 저장 및 재처리 |
| FastAPI `/health` 실패 | Critical | 즉시 알림 | API container/log/DB 연결 확인 |

### 4.2 알림 채널

| 채널 | 상태 | 준비 방향 |
| --- | --- | --- |
| Airflow UI | 구현됨 | 기본 장애 확인 채널 |
| Spark UI/History UI | 구현됨 | 처리 지연/OOM 확인 채널 |
| FastAPI health endpoint | 구현됨 | API 상태 확인 |
| Slack | 미구현 | Airflow failure callback 또는 별도 notifier로 webhook 연동 |
| Email | 미구현 | Airflow email alert 설정 또는 SMTP 연동 |
| Grafana Alert | 미구현 | Prometheus/Grafana 도입 시 선택 |

### 4.3 Fallback 로직

| 실패 지점 | Fallback | 현재 상태 | 준비 방향 |
| --- | --- | --- | --- |
| Naver API 호출 실패 | retry 후 task 실패 처리 | 부분 구현 추정 | API error별 retry/backoff 명시 |
| Kafka 발행 실패 | dead letter 파일 저장 | 구현됨으로 정리 | 실제 broker 중단 테스트로 검증 |
| Spark 처리 실패 | checkpoint 유지 후 재시작 | 부분 구현 | runbook 작성, 재시작 명령 정리 |
| DB 저장 실패 | 파일 임시 저장 후 재처리 | 미구현 | `runtime/state/db_failed_records.jsonl` 같은 임시 저장 경로 설계 |
| Dashboard/API 실패 | health check 및 container restart | 부분 구현 | API 장애 runbook 작성 |

### 4.4 수동 개입 vs 자동 복구

| 구분 | 자동 복구 가능 | 수동 개입 필요 |
| --- | --- | --- |
| Kafka 일시 장애 | Producer retry, dead letter replay | broker 설정 손상, 데이터 디스크 문제 |
| Spark 일시 실패 | checkpoint 기반 재시작 | OOM 반복, skew 로직 수정 필요 |
| Airflow task 실패 | retry, replay DAG | 외부 API quota 초과, 인증키 만료 |
| DB 일시 장애 | retry, fallback 파일 저장 | schema 오류, unique constraint 설계 오류 |
| API 일시 장애 | container restart | 코드 버그, DB migration 누락 |

---

## 5. 실행 가능한 코드 (예시)

### 5.1 `scripts/load_test.py` 또는 `scripts/stress_test.py`

현재 상태: 미구현

준비 방향:

- Kafka topic에 더미 뉴스 메시지를 대량 발행한다.
- 메시지에는 `provider`, `domain`, `url`, `title`, `summary`, `published_at` 등 실제 schema와 유사한 필드를 포함한다.
- `--count`, `--rate`, `--domain`, `--keyword`, `--burst` 옵션을 제공한다.
- 실행 후 producer 처리량, 실패 건수, 평균 send latency를 출력한다.

예시 인터페이스:

```bash
python scripts/load_test.py --count 1000 --rate 100 --topic news_topic
python scripts/load_test.py --count 5000 --burst --domain technology
```

예시 구현 방향:

```python
# scripts/load_test.py 예시 구조
# 실제 구현 시 프로젝트의 config/schema와 Kafka producer 유틸을 재사용한다.

import argparse
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from kafka import KafkaProducer


def build_message(index: int, domain: str) -> dict:
    return {
        "provider": "load_test",
        "domain": domain,
        "url": f"https://example.com/load-test/{index}-{uuid4()}",
        "title": f"로드 테스트 뉴스 제목 {index}",
        "summary": "Kafka-Spark-PostgreSQL 처리량 검증용 더미 메시지입니다.",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-servers", default="localhost:9092")
    parser.add_argument("--topic", default="news_topic")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--rate", type=int, default=100, help="messages per second")
    parser.add_argument("--domain", default="technology")
    args = parser.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap_servers,
        value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
        acks="all",
        retries=3,
    )

    interval = 1 / args.rate if args.rate > 0 else 0
    success = 0
    failed = 0
    started_at = time.time()

    for index in range(args.count):
        message = build_message(index, args.domain)
        try:
            producer.send(args.topic, message).get(timeout=10)
            success += 1
        except Exception:
            failed += 1
        if interval:
            time.sleep(interval)

    producer.flush()
    elapsed = time.time() - started_at
    print({
        "count": args.count,
        "success": success,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_msg_per_sec": round(success / elapsed, 2) if elapsed > 0 else 0,
    })


if __name__ == "__main__":
    main()
```

### 5.2 `docker-compose.yml`: 모니터링 도구 추가

현재 상태: 선택 사항, 미구현

준비 방향:

- Prometheus 추가
- Grafana 추가
- Kafka exporter 추가
- PostgreSQL exporter 추가
- Airflow metrics 또는 StatsD exporter 검토
- Spark metrics endpoint/exporter 검토

발표 범위에서는 시간이 부족하면 UI 기반 모니터링으로 대체 가능하다.

### 5.3 `scripts/`: 장애 시뮬레이션 스크립트

현재 상태: 미구현

준비 방향:

| 스크립트 | 목적 | 예시 |
| --- | --- | --- |
| `scripts/failure_stop_kafka.sh` | Kafka broker 중단 | `docker compose stop kafka` |
| `scripts/failure_start_kafka.sh` | Kafka broker 복구 | `docker compose start kafka` |
| `scripts/failure_stop_postgres.sh` | DB 연결 실패 유도 | `docker compose stop postgres` |
| `scripts/failure_restart_spark.sh` | Spark 재시작 | `docker compose restart spark-master spark-worker` |
| `scripts/check_pipeline_health.py` | 주요 health check | API, Kafka, DB, Airflow 상태 확인 |

---

## 6. 테스트 결과

현재 상태: 미구현

실제 로드 테스트 실행 후 아래 표를 채운다.

### 6.1 정상 상황 vs 부하 상황 비교

| 구분 | 정상 상황 | 부하 상황 | 결과 |
| --- | --- | --- | --- |
| Kafka producer 처리량 | 미측정 | 미측정 | 미구현 |
| Spark input rows/sec | 미측정 | 미측정 | 미구현 |
| Spark batch duration | 미측정 | 미측정 | 미구현 |
| DB upsert latency | 미측정 | 미측정 | 미구현 |
| FastAPI 평균 응답 시간 | 미측정 | 미측정 | 미구현 |
| 에러율 | 미측정 | 미측정 | 미구현 |

### 6.2 측정 지표

테스트 실행 시 다음 지표를 최소 측정한다.

- 처리량: 초당 Kafka 발행 메시지 수, Spark processed rows/sec
- 지연 시간: producer send latency, Spark batch duration, API response time
- 에러율: producer 실패율, Spark failed task 수, Airflow failed task 수, API 5xx 비율
- 저장 결과: `news_raw`, `keywords`, `keyword_trends`, `keyword_relations` row count 변화
- 복구 결과: dead letter 건수, replay 성공 건수

### 6.3 병목 지점 발견 및 분석

아직 실제 테스트 결과가 없으므로 병목 지점은 미확정이다.

예상 병목 후보:

1. Kafka 단일 broker local 환경에서 burst 발행 시 producer timeout 발생
2. Spark executor 메모리 부족으로 batch duration 증가 또는 OOM 발생
3. 키워드/연관어 집계 로직에서 특정 keyword/domain skew 발생
4. PostgreSQL upsert 과정에서 lock 또는 unique index 경합 발생
5. Dashboard 반복 조회 시 FastAPI와 DB query latency 증가

### 6.4 개선 방안

테스트 결과에 따라 다음 개선을 검토한다.

- Kafka topic partition 수 조정
- Producer retry/backoff/idempotence 설정 강화
- Spark executor memory/core 조정
- Spark repartition/salting으로 skew 완화
- DB index 및 upsert query 최적화
- FastAPI 조회 API pagination/cache 적용
- Prometheus/Grafana 기반 통합 모니터링 도입
- Slack/Email alert 자동화

---

## 7. 6회차 발표(데모/설명) 계획

### 7.1 발표 구성

1. 전체 파이프라인 구조 설명
2. 부하 시나리오 설명
3. 로드 테스트 실행 데모 또는 결과 공유
4. 장애 시뮬레이션 1~2가지
5. 발견한 병목/문제점 및 개선 방향
6. 미구현 항목과 향후 구현 계획 정리

### 7.2 부하 시나리오 설명

발표에서는 다음 흐름을 설명한다.

```text
load_test.py
  -> Kafka news_topic
  -> Spark Structured Streaming
  -> PostgreSQL staging/upsert
  -> FastAPI
  -> Dashboard
```

핵심 설명 포인트:

- 평상시 부하와 피크 부하를 메시지 수와 발행 속도로 구분한다.
- local 환경은 CPU/메모리 제약이 있으므로 실제 운영 성능이 아니라 병목 탐지와 복구 전략 검증이 목적이다.
- Spark UI와 Airflow UI를 통해 처리 상태를 관찰한다.

### 7.3 로드 테스트 실행 데모

현재 상태: 미구현

준비 후 실행 예시:

```bash
docker compose up --build -d
python scripts/load_test.py --count 1000 --rate 100 --topic news_topic
python scripts/consumer_check.py --max-messages 5
```

확인 항목:

- Kafka 메시지 발행 성공/실패 수
- Spark UI batch duration
- PostgreSQL row count 증가
- Dashboard 데이터 반영 여부
- FastAPI `/health` 응답 여부

### 7.4 장애 시뮬레이션 1~2가지

#### 데모 1: Kafka 브로커 중단

```bash
docker compose stop kafka
python scripts/load_test.py --count 100 --rate 20 --topic news_topic
# 실패 로그 또는 dead letter 확인
docker compose start kafka
# replay DAG 또는 replay 명령 실행
```

설명 포인트:

- Producer가 Kafka 장애를 어떻게 감지하는지 확인한다.
- 실패 메시지를 dead letter에 저장하고 복구 후 replay하는 전략을 설명한다.
- 현재 자동화가 부족한 부분은 미구현으로 명시한다.

#### 데모 2: DB 연결 끊김

```bash
docker compose stop postgres
# Spark 처리 또는 API 조회 실행
# DB connection error 확인
docker compose start postgres
```

설명 포인트:

- DB 저장 실패 시 현재는 완전한 fallback 파일 저장이 미구현이다.
- 향후 `runtime/state/db_failed_records.jsonl`에 임시 저장 후 재처리하는 방식을 준비한다.

#### 대체 설명: 스키마 변동

실제 데모가 어렵다면 다음 내용을 설명한다.

- 메시지 schema에 신규 필드가 추가되거나 필수 필드가 누락될 수 있다.
- Spark 처리 전 schema validation을 강화한다.
- 유효하지 않은 메시지는 dead letter로 분리한다.
- schema version 필드를 추가해 하위 호환성을 관리한다.

### 7.5 발견한 병목/문제점 및 개선 방향

현재는 실제 측정 전이므로 다음과 같이 발표한다.

| 항목 | 현재 상태 | 개선 방향 |
| --- | --- | --- |
| 부하 테스트 스크립트 | 미구현 | `scripts/load_test.py` 추가 |
| 장애 시뮬레이션 스크립트 | 미구현 | Kafka/DB/Spark 중단 스크립트 추가 |
| 통합 모니터링 | 미구현 | Prometheus/Grafana 도입 검토 |
| Alert 자동화 | 미구현 | Airflow failure callback + Slack/Email 연동 |
| DB fallback | 미구현 | 실패 record jsonl 저장 및 replay 구현 |
| Consumer lag 측정 | 미구현 | Kafka CLI/exporter 또는 Python 측정 도구 추가 |
| 실제 테스트 결과 | 미구현 | 정상/부하 상황 지표 측정 후 표 업데이트 |

---

## 8. 작업 체크리스트

### 발표 전 필수

- [ ] `scripts/load_test.py` 작성
- [ ] 더미 메시지 schema를 실제 Spark 처리 schema와 맞추기
- [ ] 정상 상황 1회 테스트 결과 기록
- [ ] 피크 상황 1회 테스트 결과 기록
- [ ] Kafka broker 중단 시나리오 실행
- [ ] DB 연결 끊김 시나리오 실행 또는 설명 자료 준비
- [ ] Spark UI, Airflow UI, FastAPI health check 캡처
- [ ] 테스트 결과 표 업데이트

### 발표 전 선택

- [ ] Kafka consumer lag 측정 도구 추가
- [ ] Prometheus/Grafana docker-compose 확장
- [ ] Slack webhook alert 추가
- [ ] DB fallback jsonl 저장 구현
- [ ] 장애 시뮬레이션 shell script 추가

---

## 9. 결론

현재 레포지토리는 Kafka-Spark-PostgreSQL-Airflow-FastAPI-Dashboard 기반의 핵심 파이프라인은 구현되어 있으며, Health API와 Airflow/Spark UI를 통한 기본 모니터링도 일부 가능하다.

다만 6회차 발표에서 요구하는 로드 테스트와 장애 대응 관점에서는 다음 항목이 아직 미구현이다.

- 전용 부하 생성 스크립트
- 장애 시뮬레이션 스크립트
- 실제 측정 결과
- consumer lag 자동 측정
- Slack/Email Alert 자동화
- DB 저장 실패 fallback
- Prometheus/Grafana 기반 통합 모니터링

따라서 발표 전에는 최소 범위로 `scripts/load_test.py`, Kafka broker 중단 데모, Spark/Airflow UI 기반 관찰, 정상/부하 상황 비교 표를 준비하는 것을 우선순위로 둔다.
