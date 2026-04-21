# Step 2 처리 계층 구현 정리

## 개요

현재 프로젝트의 Step 2는 Kafka에 적재된 뉴스 기사를 읽어 전처리하고, 키워드 및 연관 키워드를 집계해 저장하는 처리 계층이다.

이번 단계에서 정리한 범위는 아래와 같다.

- Spark 스트리밍 진입점 구성
- 기사 텍스트 전처리 및 키워드 추출 로직 정리
- PostgreSQL 스키마 및 저장 계층 추가
- 정규화된 뉴스 기사 스키마 클래스 도입
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
  - 집계 결과 저장
  - 재처리용 조회 및 치환 함수

### 2. 설정 관리

Step 2에서 필요한 실행 설정은 모두 `core/config.py`에 모았다.

추가한 주요 설정은 아래와 같다.

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

구현한 기본 처리 흐름은 아래와 같다.

1. Kafka 토픽에서 기사 메시지를 읽는다.
2. 정규화 기사 스키마에 맞는 구조로 파싱한다.
3. `title + description + content`를 합쳐 분석용 본문을 만든다.
4. provider에 맞는 전처리와 토큰 추출을 수행한다.
5. event time 기준 10분 윈도우로 키워드 빈도를 집계한다.
6. 기사별 상위 키워드 조합으로 연관 키워드를 계산한다.
7. 결과를 PostgreSQL에 저장한다.

## 구현 파일

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
- `requirements/requirements-ingestion.txt`
- `pyproject.toml`
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
- event time 기준 윈도우 집계
- 키워드 빈도 집계
- 연관 키워드 집계
- PostgreSQL 저장 계층 연결

### 3. 저장 계층 추가

`storage/` 패키지에 PostgreSQL 스키마와 저장 함수를 추가했다.

- 테이블 생성 SQL
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
즉, 프로듀서/컨슈머/재전송 경계에서는 클래스 기반 검증과 직렬화를 사용하고, Spark 내부 집계 연산은 그대로 DataFrame 중심으로 유지했다.

### 5. 의존성 및 테스트 정리

Step 2 실행에 필요한 의존성을 정리했다.

- `psycopg2-binary`
- `pyspark`
- `kiwipiepy`
- `spacy`

테스트는 아래 범위를 추가했다.

- 전처리 동작 확인
- 정규화 기사 스키마 직렬화 확인

## 현재 범위와 남은 작업

이번 작업은 Step 2 처리 코드를 현재 프로젝트 구조에 맞춰 정리한 단계다.
처리 로직과 공통 스키마는 들어왔지만, 실행 인프라까지 모두 연결된 상태는 아니다.

현재 남아 있는 주요 작업은 아래와 같다.

1. `docker-compose.yml`에 Spark/PostgreSQL 서비스 연결
2. Step 2 실행 스크립트 또는 실행 명령 정리
3. DB 저장까지 포함한 통합 테스트 추가
4. ingestion 단계에서 `news_raw`를 어떤 시점에 저장할지 정책 확정
