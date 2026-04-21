# Step 2 처리 계층 구현 정리

## 개요

Step 2는 Kafka에 적재된 뉴스 기사를 읽어 전처리하고, `news_raw`, 키워드 트렌드, 연관 키워드를 PostgreSQL에 저장하는 처리 계층이다.

이번 단계에서 정리한 범위는 아래와 같다.

- Spark 스트리밍 처리 진입점 구성
- 기사 텍스트 전처리 및 키워드 추출 로직 정리
- PostgreSQL 스키마 및 저장 계층 추가
- 정규화된 뉴스 기사 스키마 클래스 도입
- Spark/PostgreSQL 실행용 인프라 구성 추가
- 전처리 및 스키마 직렬화에 대한 최소 단위 테스트 추가

## 설계 방향

### 1. 패키지 배치

Step 2 책임은 아래 두 계층으로 나누었다.

- `src/news_trend_pipeline/processing/`
  - `preprocessing.py`
  - `spark_job.py`
- `src/news_trend_pipeline/storage/`
  - `db.py`
  - `models.sql`

역할은 다음처럼 구분했다.

- `processing`
  - Kafka 메시지 파싱
  - 기사 텍스트 전처리
  - 키워드 추출
  - Spark 집계
- `storage`
  - PostgreSQL 스키마 정의
  - 원문 기사 및 집계 결과 저장
  - 재처리용 조회 및 치환 함수

### 2. 설정 관리

Step 2에서 필요한 실행 설정은 모두 `core/config.py`에 모았다.

주요 설정은 아래와 같다.

- Spark 실행
  - `SPARK_MASTER`
  - `SPARK_APP_NAME`
  - `SPARK_CHECKPOINT_DIR`
  - `SPARK_SHUFFLE_PARTITIONS`
  - `SPARK_STARTING_OFFSETS`
- 집계 동작
  - `KEYWORD_WINDOW_DURATION`
  - `RELATION_KEYWORD_LIMIT`
- PostgreSQL 연결
  - `POSTGRES_HOST`
  - `POSTGRES_PORT`
  - `POSTGRES_DB`
  - `POSTGRES_USER`
  - `POSTGRES_PASSWORD`

경로성 설정은 프로젝트 루트를 기준으로 해석되도록 맞춰서 로컬 실행과 컨테이너 실행 모두에서 같은 규칙으로 동작하게 했다.

### 3. 처리 흐름

현재 구현한 기본 처리 흐름은 아래와 같다.

1. Kafka 토픽에서 기사 메시지를 읽는다.
2. 정규화 기사 스키마에 맞는 구조로 파싱한다.
3. Step 2 경계에서 원문 기사 데이터를 `news_raw`에 저장한다.
4. `title + description + content`를 합쳐 분석용 본문을 만든다.
5. provider에 맞는 전처리와 토큰 추출을 수행한다.
6. event time 기준 10분 윈도우로 키워드 빈도를 집계한다.
7. 기사별 상위 키워드 조합으로 연관 키워드를 계산한다.
8. 결과를 PostgreSQL에 저장한다.

### 4. `news_raw` 저장 정책

`news_raw`는 ingestion 단계가 아니라 Step 2에서 저장하도록 정리했다.

이 정책을 선택한 이유는 아래와 같다.

- Kafka에 적재된 실제 처리 기준 메시지를 그대로 원문 저장 대상으로 삼을 수 있다.
- Processing 단계 진입 시점에 스키마 검증을 거친 뒤 저장하므로 저장 데이터 일관성이 좋아진다.
- 향후 프로듀서 로직이 바뀌어도 저장 책임이 ingestion에 묶이지 않는다.
- `news_raw`와 집계 결과가 같은 처리 경계에서 생성되므로 재처리 정책을 맞추기 쉽다.

현재 `spark_job.py`의 `foreachBatch`에서 먼저 `news_raw`를 적재한 뒤 키워드 집계를 수행한다.

## 인프라 구성

### 1. Docker Compose

`docker-compose.yml`에 Step 2 실행에 필요한 서비스 구성을 추가했다.

- `app-postgres`
  - 기사 원문과 집계 결과 저장용 PostgreSQL
- `spark-master`
  - Spark 클러스터 마스터
- `spark-worker-1`
  - Spark 워커 1
- `spark-worker-2`
  - Spark 워커 2
- `spark-history`
  - Spark 히스토리 서버
- `spark-streaming`
  - `scripts/run_processing.py`를 실행하는 처리 서비스

Airflow 서비스에서도 같은 PostgreSQL과 Spark 설정을 공유하도록 환경변수를 맞췄다.

### 2. Spark 이미지

`infra/spark/Dockerfile.spark`를 추가했다.

이 이미지는 아래를 포함한다.

- Java 17 런타임
- Spark 3.5.7
- Python 처리 의존성
- 현재 프로젝트 소스 코드

별도 의존성 파일은 `requirements/requirements-spark.txt`로 분리했다.

### 3. 실행 보조 스크립트

`scripts/run_processing.py`를 추가했다.

이 스크립트는 현재 프로젝트 구조 기준으로 `src/`를 경로에 포함한 뒤 `news_trend_pipeline.processing.spark_job.run_streaming_job()`를 실행한다.

컨테이너에서는 이 스크립트를 `spark-submit` 진입점으로 사용한다.

### 4. 런타임 디렉터리

아래 런타임 디렉터리를 명시적으로 관리하도록 정리했다.

- `runtime/checkpoints/`
- `runtime/spark-events/`

둘 다 `.gitkeep`만 유지하고 실제 실행 산출물은 `.gitignore`로 제외했다.

## 구현 파일

- `docker-compose.yml`
- `infra/spark/Dockerfile.spark`
- `requirements/requirements-spark.txt`
- `scripts/run_processing.py`
- `src/news_trend_pipeline/core/config.py`
- `src/news_trend_pipeline/core/schemas.py`
- `src/news_trend_pipeline/core/korean_user_dict.txt`
- `src/news_trend_pipeline/processing/__init__.py`
- `src/news_trend_pipeline/processing/preprocessing.py`
- `src/news_trend_pipeline/processing/spark_job.py`
- `src/news_trend_pipeline/storage/__init__.py`
- `src/news_trend_pipeline/storage/db.py`
- `src/news_trend_pipeline/storage/models.sql`
- `src/news_trend_pipeline/ingestion/producer.py`
- `src/news_trend_pipeline/ingestion/replay.py`
- `scripts/consumer_check.py`
- `.env.example`
- `.gitignore`
- `tests/unit/test_processing_preprocessing.py`
- `tests/unit/test_core_schemas.py`

## 개발 내역

### 1. 전처리 계층 정리

`processing/preprocessing.py`에 기사 텍스트 정제와 키워드 추출 로직을 구성했다.

- Naver 기사용 한국어 전처리
- 사용자 사전 기반 복합명사 병합
- 영어 기사 대응용 일반 토큰 추출 fallback
- spaCy와 Kiwi가 없는 환경에서도 동작 가능한 fallback 유지

### 2. Spark 집계 진입점 추가

`processing/spark_job.py`에 Spark 스트리밍 집계 진입점을 구성했다.

- Kafka 메시지 파싱
- `news_raw` 선저장
- event time 기준 윈도우 집계
- 키워드 빈도 집계
- 연관 키워드 집계
- PostgreSQL 저장 계층 연결

### 3. 저장 계층 추가

`storage/` 패키지에 PostgreSQL 스키마와 저장 함수를 추가했다.

- `news_raw` 저장
- 키워드 트렌드 저장
- 연관 키워드 저장
- 일자 기준 재처리 함수

### 4. 정규화 기사 스키마 클래스 도입

`core/schemas.py`에 `NormalizedNewsArticle`와 `ArticleMetadata`를 추가했다.

이 스키마는 다음 목적을 가진다.

- 기사 필드 구조를 한 곳에서 관리
- Kafka 메시지 직렬화 규칙 통일
- 프로듀서, 컨슈머, 재전송 스크립트가 같은 필드 검증 로직 사용
- Spark에서 공통 기사 스키마를 직접 재사용

적용 방식은 아래와 같다.

- 프로듀서
  - `build_message()`에서 `NormalizedNewsArticle`를 사용해 Kafka 메시지 생성
- Dead Letter / Replay
  - 실패 payload를 정규화 기사 스키마로 읽고 다시 메시지 생성
- Consumer 확인 스크립트
  - Kafka에서 읽은 값을 정규화 기사 스키마로 복원 후 출력
- Spark
  - `NormalizedNewsArticle.spark_schema()`를 사용해 메시지 스키마 정의

핵심 원칙은 "경계에서는 클래스, Spark 집계 본체에서는 DataFrame"이다.

### 5. 의존성 및 테스트 정리

Step 2 실행에 필요한 의존성을 정리했다.

- `psycopg2-binary`
- `pyspark`
- `kiwipiepy`
- `spacy`

테스트는 아래 범위를 추가했다.

- 전처리 동작 확인
- 정규화 기사 스키마 직렬화 확인

## 관련 문서

- [전처리 상세 문서](./STEP2_PREPROCESSING.md) — 텍스트 정제·토큰화·복합명사 병합·불용어·라이브러리·개선 방향

## 남은 작업

현재 Step 2의 처리 코드와 실행 인프라는 갖춰졌고, 남은 작업은 상위 단계 구현 중심이다.

1. analytics 계층에서 급상승 키워드 탐지 로직 추가
2. API 계층에서 집계 결과 조회 기능 추가
3. dashboard 계층에서 시각화 화면 추가
4. PostgreSQL/Spark가 실제 올라온 상태에서 통합 테스트 보강
