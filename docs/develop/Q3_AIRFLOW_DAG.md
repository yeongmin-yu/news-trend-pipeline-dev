# STEP1: Airflow DAG 설계

## 1. 개요

본 문서는 프로젝트에서 사용하는 Airflow DAG 전체와, 그중 수집(Ingestion) DAG의 상세 실행 구조를 정의한다.

Airflow의 역할:

- 뉴스 수집 작업 스케줄링
- 실패 메시지 재처리
- 사전 후보 추출/추천 배치 실행
- 키워드 이벤트 탐지 배치 실행
- Kafka 발행 전 사전 상태 확인
- 실패 시 재시도 및 dead letter 확인
- 수집 결과 요약 로그 기록

---

## 2. Airflow DAG 전체 구성

현재 Airflow는 단일 DAG가 아니라 여러 운영 DAG를 통해 파이프라인을 보조한다.

```mermaid
flowchart LR
    A["Airflow Scheduler"] --> B["news_ingest_dag<br/>뉴스 수집 / Kafka 발행"]
    A --> C["auto_replay_dag<br/>dead letter 재처리"]
    A --> D["compound_noun_extraction<br/>복합명사 후보 추출"]
    A --> E["keyword_event_detection<br/>급상승 이벤트 탐지"]

    B --> K["Kafka<br/>news_topic"]
    C --> K

    K --> S["Spark Streaming<br/>상시 실행"]
    S --> DB["PostgreSQL<br/>analysis tables"]

    D --> DICT["Dictionary Tables<br/>compound_noun_candidates<br/>stopword_candidates"]
    DICT -. reload .-> S

    DB --> E
    E --> EV["keyword_events"]
    style B fill:#ffffde,stroke:#333,stroke-width:2px,color:black
    style C fill:#ffffde,stroke:#333,stroke-width:2px,color:black
    style D fill:#ffffde,stroke:#333,stroke-width:2px,color:black
    style E fill:#ffffde,stroke:#333,stroke-width:2px,color:black
```

### DAG 목록

| DAG | 역할 | 실행 주기/조건 | 주요 출력 |
| --- | --- | --- | --- |
| `news_ingest_dag` | Naver 뉴스 수집 후 Kafka 발행 | 15분 주기 | `news_topic`, `collection_metrics` |
| `auto_replay_dag` | `dead_letter.jsonl` 재처리 | 15분 주기 | 재발행 메시지, replay 결과 로그 |
| `compound_noun_extraction` | 기사 데이터 기반 복합명사/불용어 후보 생성 | 일 1회 | `compound_noun_candidates(복합명사추천테이블)`, `stopword_candidates(불용어추천테이블)` |
| `keyword_event_detection` | `keyword_trends` 기반 급상승 이벤트 계산 | 15분 주기 | `keyword_events` |

정리:

- `news_ingest_dag`와 `auto_replay_dag`는 Kafka 입력 품질과 수집 안정성을 담당한다.
- Spark Structured Streaming은 Airflow task가 아니라 상시 실행되는 처리 계층이다.
- 사전 관련 DAG는 Spark 전처리 품질에 영향을 준다.
- 이벤트 탐지 DAG는 Spark/Storage 결과인 `keyword_trends`를 기반으로 분석 결과를 만든다.

---

## 3. 수집 DAG 중심 파이프라인 구성도

```mermaid
flowchart LR
    S["Airflow Scheduler<br/>*/15 * * * *<br/>catchup=false<br/>max_active_runs=1"] --> D["DAG<br/>news_ingest_dag"]

    subgraph AIRFLOW["news_ingest_dag 상세"]
        D --> H["check_kafka_health<br/>Kafka 연결 확인"]
        H -->|"정상"| P["produce_naver<br/>Naver 수집 + Kafka 발행"]
        H -.->|"실패"| R["Airflow retry<br/>3회 / exponential backoff"]

        P --> X["summarize_results<br/>발행 건수 요약"]
        P --> L["check_dead_letter<br/>실패 메시지 누적 확인"]
    end

    P --> K["Kafka<br/>news_topic"]
    P --> M["PostgreSQL<br/>collection_metrics"]
    L --> DL["dead_letter.jsonl"]

    K --> NEXT["다음 단계 축약<br/>Spark Streaming 처리<br/>전처리 / 키워드 집계 / 저장 upsert"]
    NEXT --> FINAL["최종 목적지<br/>PostgreSQL Analysis Tables<br/>news_raw / keywords / keyword_trends / keyword_relations"]
```

설명:

- `news_ingest_dag`는 Airflow Scheduler에 의해 15분마다 실행된다.
- `catchup=false`이므로 과거 누락 구간을 자동으로 몰아서 실행하지 않는다.
- `max_active_runs=1`로 동시에 여러 수집 cycle이 실행되지 않게 한다.
- DAG 내부에서는 Kafka 상태 확인을 먼저 수행한다.
- Kafka가 정상일 때만 `produce_naver`가 실행된다.
- `produce_naver`는 Naver News API 수집, 메시지 정규화, 중복 제거, Kafka 발행, 수집 지표 저장을 수행한다.
- DAG가 직접 영향을 주는 다음 단계는 Kafka `news_topic`이다.
- 이후 Spark Structured Streaming이 Kafka 메시지를 consume하고, 최종 결과는 PostgreSQL analysis tables에 저장된다.
- Spark는 Airflow가 매번 실행하는 task가 아니라 상시 실행되는 처리 계층이다.

---

## 4. news_ingest_dag 설계

### 4.1 목적

- Naver 뉴스 수집 producer 실행
- Kafka `news_topic`에 뉴스 메시지 발행
- 수집 결과를 `collection_metrics`에 기록
- Kafka 또는 발행 실패 상황을 조기에 감지

### 4.2 실행 단위

- DAG 실행 단위: 15분 주기 수집 cycle
- Producer 내부 처리 단위: provider + domain + query
- 현재 provider: `naver`

Airflow의 `ds`는 실행 context로 제공되지만, 현재 producer는 `ds`별 파티션 적재 방식이 아니라 실행 시각 기준의 incremental 수집 상태를 사용한다.

---

## 4.3 입력 / 출력

### 입력

- `query_keywords` 테이블의 활성 수집 키워드
- Naver News API credential
- producer state (`runtime/state/producer_state.json`)
- Kafka broker 상태

### 출력

- Kafka topic: `news_topic`
- PostgreSQL: `collection_metrics`
- producer state: `producer_state.json`
- 실패 메시지: `dead_letter.jsonl`
- Airflow XCom: `naver_count`

---

## 4.4 실제 DAG 구조

현재 구현 파일:

```text
airflow/dags/news_ingest_dag.py
```

실제 태스크 구조:

```mermaid
flowchart LR
    A[check_kafka_health] --> B[produce_naver]
    B --> C[summarize_results]
    B --> D[check_dead_letter]
```

`check_dead_letter`는 `trigger_rule=all_done`으로 설정되어 있어 `produce_naver` 성공/실패와 관계없이 실행된다.

### 태스크 설명

| Task | 설명 | 실패 시 영향 |
|------|------|--------------|
| `check_kafka_health` | Kafka broker 연결과 topic 조회 가능 여부 확인 | 실패하면 `produce_naver` 실행 차단 |
| `produce_naver` | Naver API 수집, 메시지 정규화, 중복 제거, Kafka 발행, metrics 저장 | Airflow retry 대상 |
| `summarize_results` | XCom의 `naver_count`를 읽어 발행 결과 요약 | 요약 로그 실패만 해당 |
| `check_dead_letter` | `dead_letter.jsonl` 누적 건수 확인 및 임계치 초과 경고 | producer 실패 여부와 무관하게 실행 |

---

## 4.5 `validate`의 의미

현재 `news_ingest_dag`에는 `validate`라는 별도 Airflow task가 없다.

문서상 `validate`는 다음 검증 행위들을 포괄하는 개념으로 해석한다.

### 1) 실행 전 검증

담당 task:

```text
check_kafka_health
```

검증 내용:

- Kafka broker 연결 가능 여부
- KafkaAdminClient로 topic list 조회 가능 여부

목적:

- Kafka가 비정상인 상태에서 API 수집을 진행하지 않도록 차단
- 불필요한 API 호출과 메시지 유실 위험 방지

### 2) 메시지 검증

담당 위치:

```text
src/ingestion/producer.py
build_message()
NormalizedNewsArticle
```

검증 내용:

- 수집 기사 payload가 표준 메시지 스키마로 변환 가능한지 확인
- 필수 필드 누락 또는 잘못된 값이 있으면 Kafka로 발행하지 않음

실패 처리:

- 해당 레코드는 `dead_letter.jsonl`에 기록
- producer 전체는 계속 진행

### 3) 중복 검증

담당 위치:

```text
NewsKafkaProducer.run_once()
```

검증 내용:

- `provider + domain + url` 기준으로 이미 발행한 기사인지 확인

실패 처리:

- 중복이면 Kafka에 발행하지 않고 skip
- query별 duplicate count를 `collection_metrics`에 기록

### 4) 실행 후 검증

담당 task:

```text
check_dead_letter
summarize_results
```

검증 내용:

- 발행 건수 확인
- dead letter 누적 건수 확인
- dead letter가 100건 이상이면 경고 로그 출력

목적:

- producer 실행은 성공했지만 일부 메시지가 실패한 경우를 확인
- replay 필요 여부를 판단

---

## 4.6 데이터 전달 방식

- XCom: `produce_naver` → `summarize_results` 발행 건수 전달
- Kafka: producer → Spark 처리 계층 메시지 전달
- PostgreSQL: 수집 지표 저장
- 파일: producer state와 dead letter 저장

---

## 5. 기타 DAG 요약

### 5.1 auto_replay_dag

구현 파일:

```text
airflow/dags/auto_replay_dag.py
```

목적:

- `dead_letter.jsonl`에 쌓인 실패 메시지를 재처리한다.
- Kafka가 정상일 때만 replay를 수행한다.

태스크 구조:

```mermaid
flowchart LR
    A[check_kafka_health] --> B[replay_dead_letters]
    B --> C[summarize_replay_results]
    B --> D[check_permanent_failures]
```

주요 특징:

- 15분 주기 실행
- `max_active_runs=1`
- replay 결과를 XCom과 로그로 요약
- 영구 실패 메시지는 별도 파일과 로그로 관리

### 5.2 compound_noun_extraction

목적:

- 최근 기사 데이터를 기반으로 복합명사 후보와 불용어 후보를 추천한다.
- 생성된 후보는 사전 관리 화면/API를 통해 승인 또는 반려된다.
- 승인된 사전은 Spark 전처리 단계의 토큰 품질에 영향을 준다.

주요 출력:

- `compound_noun_candidates`
- `stopword_candidates`
- `dictionary_versions`

### 5.3 keyword_event_detection

구현 파일:

```text
airflow/dags/keyword_event_detection_dag.py
```

목적:

- `keyword_trends`를 기반으로 급상승 이벤트를 계산한다.
- 결과를 `keyword_events`에 저장한다.

태스크 구조:

```mermaid
flowchart LR
    A[detect_keyword_events] --> B[keyword_events]
```

주요 특징:

- 15분 주기 실행
- 최근 24시간 lookback
- `provider + domain + keyword` 기준 growth와 event score 계산

---

## 6. 스케줄

`news_ingest_dag` 실제 구현 기준:

- schedule: `*/15 * * * *`
- start_date: `2026-01-01`
- catchup: `false`
- max_active_runs: `1`

설계 근거:

- 15분 단위 near real-time 수집
- API 호출량과 처리 안정성 균형
- 동시 실행을 막아 중복 수집 위험 감소

---

## 7. Retry / Failure Handling

### 재시도 정책

`news_ingest_dag` 실제 구현 기준:

- retries: 3
- retry_delay: 5 minutes
- retry_exponential_backoff: true
- max_retry_delay: 30 minutes

### 재시도 대상

- Kafka broker 일시 장애
- Naver API 일시 오류
- Kafka 발행 오류
- DB 연결 오류

### 재시도 제외 또는 격리 대상

- 개별 기사 schema validation 실패
- 개별 메시지 발행 실패
- 중복 기사

처리 방식:

- validation 실패 또는 발행 실패는 dead letter 기록
- 중복 기사는 skip
- producer cycle 전체 실패는 Airflow retry

---

## 8. Idempotency

전략:

- `max_active_runs=1`로 DAG 동시 실행 차단
- producer state에 최근 발행 URL 유지
- `provider + domain + url` 기준 중복 제거
- Kafka producer idempotence 활성화
- storage 단계에서 unique/upsert로 중복 방지

보장:

- 동일 기사가 재수집되어도 Kafka 발행과 DB 저장에서 중복 가능성을 줄인다.
- DAG 재시도 시 이미 발행된 URL은 producer state 기준으로 skip된다.

---

## 9. 코드 구조

DAG 파일:

```text
airflow/dags/news_ingest_dag.py
airflow/dags/auto_replay_dag.py
airflow/dags/keyword_event_detection_dag.py
```

관련 구현:

```text
src/ingestion/producer.py
src/ingestion/replay.py
src/ingestion/api_client.py
src/analytics/event_detector.py
src/storage/db.py
```

---

## 10. 실행 환경

필수 구성:

- Airflow scheduler / webserver
- Kafka broker
- PostgreSQL
- Naver API credential

주요 환경 변수:

```text
NAVER_CLIENT_ID
NAVER_CLIENT_SECRET
KAFKA_BOOTSTRAP_SERVERS
KAFKA_TOPIC
POSTGRES_HOST
POSTGRES_DB
POSTGRES_USER
POSTGRES_PASSWORD
STATE_DIR
```

---

## 11. 실행 시나리오

### 정상 수집 실행

```text
check_kafka_health
→ produce_naver
→ Kafka news_topic
→ Spark Structured Streaming
→ PostgreSQL analysis tables
```

보조 결과:

- `collection_metrics` 저장
- producer state 갱신
- `summarize_results` 발행 건수 요약
- `check_dead_letter` 실패 메시지 누적 확인

### Kafka 장애

```text
check_kafka_health 실패
→ produce_naver 실행 안 됨
→ Airflow retry
```

### 일부 메시지 실패

```text
produce_naver 내부에서 validation/publish 실패
→ dead_letter.jsonl 기록
→ auto_replay_dag가 이후 재처리 시도
```

### 이벤트 탐지 실행

```text
keyword_trends
→ keyword_event_detection
→ keyword_events
```

### 재실행

```text
동일 실행 구간 재시도
→ producer state와 URL 중복 기준 적용
→ 이미 발행한 기사는 skip
→ storage upsert로 최종 테이블 중복 방지
```

---

## 12. 요약

Airflow는 단일 수집 DAG만 관리하지 않는다.

현재 Airflow는 수집, dead letter 재처리, 사전 후보 추출, 이벤트 탐지 배치를 담당한다.

이 중 `news_ingest_dag`는 Kafka로 메시지를 발행하는 수집 entry point이며, 이후 단계는 Kafka topic을 기준으로 Spark 처리와 PostgreSQL 저장 계층으로 이어진다.

`validate`는 별도 task가 아니라 Kafka 사전 검증, 메시지 schema 검증, 중복 검증, dead letter 사후 확인으로 나뉘어 구현되어 있다.
