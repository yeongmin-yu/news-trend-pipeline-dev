# 전체 초기화 및 재기동 가이드

이 문서는 `news-trend-pipeline-v2`를 **완전히 초기화한 뒤 새 스키마 기준으로 다시 올리는 절차**를 정리한 운영 메모다.


## 초기화 대상

전체 초기화 시 정리 대상은 아래 네 범주다.

### 1. Docker 볼륨

- `app-postgres-data`
  - 기사 원문, 키워드, 트렌드, 연관 키워드 저장 DB
- `airflow-postgres-data`
  - Airflow 메타데이터 DB

### 2. 런타임 디렉터리

- `runtime/checkpoints/`
  - Spark Structured Streaming checkpoint
- `runtime/state/`
  - producer 상태, dead letter, replay 상태 파일
- `runtime/spark-events/`
  - Spark history event log
- `runtime/logs/`
  - Airflow 로그

### 3. 컨테이너 상태

- Kafka, Spark, Airflow, PostgreSQL 컨테이너 전체

### 4. 주의

- 이 절차를 수행하면 **기존 기사 데이터와 집계 결과는 모두 삭제**된다.
- Airflow의 과거 실행 이력도 사라진다.
- Dead Letter 파일도 삭제되므로 미재처리 실패 메시지를 보존하지 않는다.

## 권장 절차

프로젝트 루트:

```powershell
cd C:\Project\news-trend-pipeline-v2
```

### 1. 컨테이너 및 볼륨 전체 제거

```powershell
docker compose down -v --remove-orphans
```

설명:

- `down`: 컨테이너 정지 및 제거
- `-v`: named volume 삭제
- `--remove-orphans`: compose에 없는 잔여 컨테이너도 정리

이 단계로 아래가 삭제된다.

- `app-postgres-data`
- `airflow-postgres-data`

### 2. 런타임 디렉터리 비우기

```powershell
Remove-Item -LiteralPath .\runtime\checkpoints\* -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\runtime\state\* -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\runtime\spark-events\* -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\runtime\logs\* -Recurse -Force -ErrorAction SilentlyContinue
```

빈 디렉터리 유지가 필요하면 `.gitkeep`를 다시 만들어 둔다.

```powershell
New-Item -ItemType File -Path .\runtime\checkpoints\.gitkeep -Force | Out-Null
New-Item -ItemType File -Path .\runtime\state\.gitkeep -Force | Out-Null
New-Item -ItemType File -Path .\runtime\spark-events\.gitkeep -Force | Out-Null
New-Item -ItemType File -Path .\runtime\logs\.gitkeep -Force | Out-Null
```

### 3. 이미지 재빌드 포함 재기동

```powershell
docker compose up -d --build
```

설명:

- Airflow / Spark 이미지가 현재 코드와 문서를 반영한 상태로 다시 빌드된다.
- PostgreSQL은 새 volume로 다시 생성된다.
- Spark는 비어 있는 checkpoint로 처음부터 시작한다.

### 4. 초기화 완료 확인

컨테이너 상태:

```powershell
docker compose ps
```

주요 로그 확인:

```powershell
docker logs -f news-trend-develop-airflow-apiserver-1
docker logs -f news-trend-develop-spark-streaming-1
docker logs -f news-trend-develop-kafka-1
```

DB 확인:

```powershell
docker exec -it news-trend-develop-app-postgres-1 psql -U postgres -d news_pipeline
```

예시 확인 쿼리:

```sql
\d news_raw
SELECT COUNT(*) FROM news_raw;
SELECT COUNT(*) FROM keywords;
SELECT COUNT(*) FROM keyword_trends;
SELECT COUNT(*) FROM keyword_relations;
```

`news_raw` 컬럼이 아래처럼 보이면 새 스키마가 반영된 것이다.

- `provider`
- `source`
- `title`
- `summary`
- `url`
- `published_at`
- `ingested_at`

## 빠른 전체 초기화 명령 모음

아래 순서대로 실행하면 된다.

```powershell
cd C:\Project\news-trend-pipeline-v2
docker compose down -v --remove-orphans
Remove-Item -LiteralPath .\runtime\checkpoints\* -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\runtime\state\* -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\runtime\spark-events\* -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath .\runtime\logs\* -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType File -Path .\runtime\checkpoints\.gitkeep -Force | Out-Null
New-Item -ItemType File -Path .\runtime\state\.gitkeep -Force | Out-Null
New-Item -ItemType File -Path .\runtime\spark-events\.gitkeep -Force | Out-Null
New-Item -ItemType File -Path .\runtime\logs\.gitkeep -Force | Out-Null
docker compose up -d --build
docker compose ps
```

## 문제 상황별 체크포인트

### 1. Spark가 예전 데이터 기준으로 다시 꼬이는 경우

우선 확인:

- `runtime/checkpoints/`가 정말 비워졌는지
- `spark-streaming` 컨테이너가 새로 올라왔는지

재조치:

- `docker compose down -v`
- `runtime/checkpoints` 재삭제
- `docker compose up -d --build`

### 2. `news_raw` 컬럼이 예전 상태로 보이는 경우

우선 확인:

- `app-postgres-data` volume이 실제로 삭제됐는지
- 다른 Postgres 컨테이너/DB에 붙은 것은 아닌지

재조치:

- `docker volume ls`
- `docker compose down -v`
- `docker compose up -d --build`

### 3. Airflow UI는 뜨는데 DAG가 안 보이는 경우

우선 확인:

- `airflow-init`가 정상 완료됐는지
- `airflow/dags` 마운트가 정상인지
- `runtime/logs` 권한 문제는 없는지

### 4. Kafka는 올라왔는데 수집이 안 되는 경우

우선 확인:

- `.env`의 Naver API 키
- `kafka-init`가 `news_topic`을 생성했는지
- `news_ingest_dag`가 실제로 실행됐는지

## 언제 전체 초기화를 하지 않아도 되는가

아래 경우에는 전체 초기화까지 갈 필요가 없을 수 있다.

- 문서만 수정한 경우
- Spark checkpoint만 비우면 되는 경우
- Airflow 로그만 정리하고 싶은 경우

이럴 때는 필요한 대상만 부분 정리한다.

- Spark만 초기화:
  - `runtime/checkpoints/`
- 수집 상태만 초기화:
  - `runtime/state/`
- 로그만 정리:
  - `runtime/logs/`

## 관련 문서

- [README.md](../README.md)
- [STEP1_KAFKA_2.md](./STEP1_KAFKA_2.md)
- [STEP2_PROCESSING_IMPLEMENTATION.md](./STEP2_PROCESSING_IMPLEMENTATION.md)
- [FINAL_PRODUCTION_IMAGE_TRANSITION_CHECKLIST.md](./FINAL_PRODUCTION_IMAGE_TRANSITION_CHECKLIST.md)

## 옵션: 사전까지 삭제하는 경우

기본 절차에서 `app-postgres-data` 볼륨을 삭제하면 실제로는 아래 사전 테이블도 함께 초기화된다.

- `compound_noun_dict`
- `compound_noun_candidates`
- `stopword_dict`

즉, 아래 명령은 **사전까지 포함한 완전 초기화**다.

```powershell
docker compose down -v --remove-orphans
```

반대로, 사전을 유지하고 싶다면 `app-postgres-data` 볼륨 삭제는 피하고 아래 항목만 부분 정리해야 한다.

- `runtime/checkpoints/`
- `runtime/state/`
- `runtime/spark-events/`
- 필요 시 `runtime/logs/`

사전까지 삭제하는 것이 맞는 경우:

- 복합명사 후보를 처음부터 다시 쌓고 싶은 경우
- 불용어/사전 등록 이력도 모두 버리고 재설계하려는 경우
- 개발 중 DB 전체를 완전히 새로 시작하려는 경우

사전을 유지하는 것이 맞는 경우:

- 기사/집계 데이터만 초기화하고 싶은 경우
- 승인된 복합명사 사전은 계속 재사용하고 싶은 경우
- dead letter / checkpoint / 집계 결과만 비우고 싶은 경우
