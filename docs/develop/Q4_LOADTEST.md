# 로드 테스트 및 장애 대응

>  로드 테스트, 장애 대응, 모니터링, Fallback/Alert 

## 현재 구현 기준 요약

현재 프로젝트는 도메인별 뉴스 키워드를 수집하고 Kafka, Spark, PostgreSQL 파이프라인으로 처리한 뒤 FastAPI와 Dashboard로 조회하는 구조이다.

- Airflow 기반 수집 오케스트레이션
- Naver News API 수집 및 Kafka 적재
- Spark Structured Streaming 기반 기사 전처리와 키워드 집계
- PostgreSQL staging 및 upsert 기반 저장 계층
- 운영 지표 조회 
- 실패 건은 `runtime/state/dead_letter.jsonl`에 기록하고 `auto_replay_dag`에서 재처리

아직 전용 부하 생성 스크립트, 장애 시뮬레이션 스크립트, Prometheus/Grafana 같은 통합 모니터링 스택, Slack/Email Alert 자동화는 레포지토리 기준으로 미구현 상태로 본다.

---

## 1. 부하 시나리오 설계 (Excalidraw/Notion)

### 1.1 테스트 목적

검증하려는 상황은 다음과 같다.

1. Naver News API 수집량 증가 시 Kafka Producer가 안정적으로 메시지를 발행하는가?
2. Kafka topic에 메시지가 누적될 때 Spark Structured Streaming이 처리 지연 없이 소비하는가?
3. Spark 처리 결과가 PostgreSQL staging 및 upsert 경로로 정상 저장되는가?
5. 장애 발생 시 dead letter, replay, 재시도, 수동 복구 절차로 데이터 유실을 최소화할 수 있는가?

### 1.2 예상 트래픽/데이터량

| 구분 | 평상시 | 피크 시 | 비고 |
| --- | --- | --- | --- |
| 검색어 수 | 8개 | 8개 | `query_keywords` 기준 확장 |
| 수집 주기 | 15분 단위 | 2분 단위 | Airflow DAG 동적 schedule 조정 필요 |
| 기사 수집량 | 실행 1회당 최대 300건 | 실행 1회당 최대 300건 | 무료 Naver API quota |
| Kafka 메시지량 | 낮음 | 단시간 burst 발생 | local Kafka 단일 broker 한계, 문제 없을것같음. |
| Spark 처리량 | local 처리 가능 수준 | micro-batch 처리로 충분 | CPU/메모리 제약 영향 큼 |

> 실제 데이터 처리량은 API한건당 최대치가 정해져있어서 최대 부하가 정해져있다. 300 x 24  = 7200건이 15분마다 최대치

> Peek 시간때 15분내에 검색어당 300건이상의 기사가 발행되면 수집이 누락이 되는 문제가 있다. 9시 ~11시 사이 2만건의 뉴스가 나왔다는 사례도 확인. 피크시간에는 2분단위 수집

> 미구현: 실제 측정값은 아직 없다. `load_test.py` 또는 `stress_test.py`를 작성해 처리량, 지연 시간, 에러율을 측정해야 한다.

### 1.3 테스트 환경

현재 기본 실행 환경은 local Docker Compose 기반으로 가정한다.

| 항목 | 현재 기준 | 준비 방향 |
| --- | --- | --- |
| Kafka | local broker, `9092` | broker 중단/재시작 시나리오  |
| Spark | Spark Master UI `8080`, History UI `18080` | 메모리 제한 조정 및 OOM 재현  |
| Airflow | UI/API `9080` | DAG 실행 실패 |
| PostgreSQL | App DB `5432` | DB 연결 끊김, 저장 실패 fallback 검증  |


## 2. 장애 시나리오 및 대응 전략 (Excalidraw/Notion)

컴포넌트별 장애 발생 시 대응 전략은 다음과 같이 정리한다.

### 2.1 Kafka 장애

#### Broker 다운 시 Producer 동작

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Kafka broker 컨테이너 중단 또는 네트워크 단절 |
| 예상 현상 | Producer send 실패, Airflow 수집 task 실패 가능 |
| 현재 구현 | Kafka 적재 실패 시 dead letter 기록 및 replay  |
| 확인 | broker 다운 상황에서 실제 producer retry, timeout, dead letter 기록 여부 테스트 필요 |
| 대응 전략 | Producer timeout/retry 설정 확인, 실패 메시지는 `runtime/state/dead_letter.jsonl`에 저장, broker 복구 후 `auto_replay_dag` 또는 수동 replay 실행 |
| 데모 | `docker compose stop kafka` 후 수집 실행 → 실패 확인 → `docker compose start kafka` → replay 실행 |

produce_naver에서 Dead Letter까지 못 가고 죽은 이유는 send() 단계가 아니라 NewsKafkaProducer() 생성 시점에서 KafkaProducer 초기화가 NoBrokersAvailable로 터지면 deadletter를 기록하지 않고 task가 에러로 끝나는 문제 해결을 위해 경고성 task로 변경
변경전
```
        self.producer: KafkaProducer = self._create_producer()
```
변경후
```
        try:
            self.producer = self._create_producer()
        except NoBrokersAvailable as exc:
            self._kafka_unavailable = True
            logger.warning(
                "Kafka producer 초기화 실패: 브로커에 연결할 수 없습니다. 수집 데이터는 Dead Letter로 저장합니다. broker=%s error=%s",
                settings.kafka_bootstrap_servers,
                exc,
            )
        except KafkaError as exc:
            self._kafka_unavailable = True
            logger.warning(
                "Kafka producer 초기화 실패: 수집 데이터는 Dead Letter로 저장합니다. broker=%s error=%s",
                settings.kafka_bootstrap_servers,
                exc,
            )
```
news_ingest_dag
>> kafka 통신
- 뉴스 수집을 계속 수행
- Kafka 상태는 경고성으로만 확인
- Kafka 발행 실패 데이터는 dead_letter.jsonl에 저장

kafka_recovery_dag
- Kafka 컨테이너 health 상태 확인
- unhealthy 상태면 Kafka 컨테이너 재시작
- Kafka broker 연결 복구 여부 검증

auto_replay_dag
- dead_letter.jsonl에 쌓인 메시지 재처리
- Kafka가 복구되면 실패 메시지를 다시 발행
- 반복 실패 메시지는 영구 실패 파일로 분리

#### Consumer lag 급증 시 대응 - 만약에 발생한다면

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Kafka 입력량이 Spark 처리량보다 많아 consumer lag 증가 |
| 예상 현상 | Spark micro-batch 처리 시간 증가 |
| 현재 구현 | Spark UI/History UI 확인 가능 |
| 미구현 |  |
| 대응 전략 | Spark executor 메모리/코어 조정, micro-batch trigger 조정, keyword 처리 로직 최적화, topic partition 수 확장 검토 |
| 데모 | 더미 메시지 대량 발행 후 Spark UI에서 batch duration 증가 확인 |

#### 메시지 유실/중복 시 처리

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | Producer 재시도, replay, Spark 재처리로 동일 기사 중복 처리 가능 |
| 예상 현상 | `news_raw`, `keywords`, `keyword_trends` 중복 증가 가능, 유실 기간에 대한 back fill 필요|
| 현재 구현 | `provider + domain + url` 기준 중복 제어 및 PostgreSQL upsert  |
| 미구현 | api 한계로 backfill 불가. 현재시간 기준으로 최근기사만 가져옴. |
| 대응 전략 | deadletter를 통한 backfill |
| 데모 | |

### 2.2 Spark 장애

#### OOM (Out of Memory) 발생 시

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | 큰 batch, 과도한 collect/cache, 실행 메모리 부족 |
| 예상 현상 | Spark job 실패, streaming query 중단, checkpoint 기준 재시작 필요 |
| 현재 구현 | Spark Structured Streaming, checkpoint 디렉터리, Spark UI/History UI 존재 |
| 미구현/확인 필요 | OOM 재현 스크립트 및 복구 절차 자동화 미구현 |
| 대응 전략 | |
| 발표 데모 |  |


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
| 미구현/확인 필요 |  |
| 대응 전략 | dead letter 파일 확인, 장애 복구 후 replay DAG 실행, 필요 시 수동 backfill |


#### SLA 미달 시 처리

| 항목 | 내용 |
| --- | --- |
| 장애 상황 | DAG는 성공했지만 목표 시간 내 완료되지 않음 |
| 예상 현상 | 최신 데이터 반영 지연 |
| 현재 구현 | Airflow UI에서 duration 확인 가능 |
| 미구현/확인 필요 | SLA 설정과 SLA miss callback 미구현 |
| 대응 전략 | DAG별 목표 완료 시간 정의, SLA miss 알림, 지연 원인 Kafka/Spark/DB 병목 분리 |

---

## 3. 모니터링 전략 (Excalidraw/Notion)

수집, 처리, 저장, 서빙의 각 단계에서 어떤 지표를 수집하고 어떻게 시각화할지 정의한다.
Prometheus/Grafana 도입 고려

### 3.1 Kafka 모니터링

| 지표 | 수집 방법 | 현재 상태 | 활용 |
| --- | --- | --- | --- |
| topic 메시지 수 | Kafka CLI 또는 Python consumer | 미구현 | producer 부하 확인 |
| consumer lag | Kafka consumer group describe 또는 exporter | 미구현 | Spark 처리 지연 감지 |
| producer error rate | producer 로그, Airflow task log | 부분 가능 | Kafka 장애 감지 |
| broker 상태 | Docker container status, Kafka exporter | 부분 가능 | broker 다운 감지 |

준비 방향:

- `scripts/consumer_check.py`를 확장해 topic 메시지 확인과 lag 확인 기능을 추가한다.
- Kafka 자동복구 프로세스 

### 3.2 Spark 모니터링

| 지표 | 수집 방법 | 현재 상태 | 활용 |
| --- | --- | --- | --- |
| input rows per second | Spark UI/Streaming query progress | 부분 가능 | 입력 부하 확인 |
| processed rows per second | Spark UI/로그 | 부분 가능 | 처리량 확인 |
| batch duration | Spark UI/History UI | 가능 | 지연 여부 판단 |
| failed tasks | Spark UI/History UI | 가능 | OOM/skew 확인 |
| checkpoint 상태 | `runtime/checkpoints` | 가능 | 재시작/복구 확인 |

준비 방향:



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
- Slack webhook 또는 Email 알림 채널설정.

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

### 4.2 알림 채널

| 채널 | 상태 | 비고 |
| --- | --- | --- |
| Airflow UI | 구현됨 | 기본 장애 확인 채널 |
| Spark UI/History UI | 구현됨 | 처리 지연/OOM 확인 채널 |
| Slack | 미구현 | Airflow failure callback 또는 별도 notifier로 webhook 연동 |
| Email | 미구현 | Airflow email alert 설정 또는 SMTP 연동 |
| Grafana Alert | 미구현 | Prometheus/Grafana 도입 시 선택 |

### 4.3 Fallback 로직

| 실패 지점 | Fallback | 현재 상태 | 비고 |
| --- | --- | --- | --- |
| Naver API 호출 실패 | retry 후 task 실패 처리 | 부분 구현  | API error별 retry/backoff 명시 해야함 |
| Kafka 발행 실패 | dead letter 파일 저장 | 구현 | 실제 broker 중단 테스트로 검증 |
| Spark 처리 실패 | checkpoint 유지 후 재시작 | 부분 구현 | 대응 매뉴얼 작성, 재시작 명령 정리 |
| DB 저장 실패 | 파일 임시 저장 후 재처리 | 미구현 | `runtime/state/db_failed_records.jsonl` 같은 임시 저장 경로 설계 |


### 4.4 수동 개입 vs 자동 복구

정리 필요.

---

## 5. 실행 가능한 코드 (예시)

### 5.1 `scripts/load_test.py` 또는 `scripts/stress_test.py` 
>> 미구현


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

## 6. 테스트 결과

