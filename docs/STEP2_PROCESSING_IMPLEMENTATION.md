# Step 2 처리 계층 구현 정리

## 개요

Step 2는 Kafka에 적재된 뉴스 기사를 읽어 전처리하고, `news_raw`, 키워드 트렌드, 연관 키워드, 복합명사 후보를 PostgreSQL에 저장하는 처리 계층이다.

이번 단계에서 정리한 범위는 아래와 같다.

- Spark 스트리밍 처리 진입점 구성
- 한국어(Naver) 전용 기사 텍스트 전처리 및 키워드 추출 로직 정리
- PostgreSQL 스키마 및 저장 계층 추가
- 복합명사·불용어 사전 DB화 및 후보 자동 추출 배치 구성
- collect() 제거 → JDBC staging 테이블 upsert 방식으로 전환
- 정규화된 뉴스 기사 스키마 클래스 도입
- Spark/PostgreSQL 실행용 인프라 구성 추가

## 설계 방향

### 1. 패키지 배치

Step 2 책임은 아래 계층으로 나누었다.

- `src/news_trend_pipeline/processing/`
  - `preprocessing.py` — 텍스트 정제, 형태소 분석, 키워드 추출
  - `spark_job.py` — Spark Structured Streaming 진입점
- `src/news_trend_pipeline/storage/`
  - `db.py` — PostgreSQL 접속, 스키마 초기화, CRUD, upsert 함수
  - `models.sql` — 테이블 정의, 인덱스, staging 테이블
- `src/news_trend_pipeline/analytics/`
  - `compound_extractor.py` — 복합명사 후보 자동 추출 배치
- `airflow/dags/`
  - `compound_extraction_dag.py` — 매일 새벽 3시 배치 스케줄

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
  - `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD`
  - `postgres_dsn` property (psycopg2용)
  - `spark_jdbc_url` property (JDBC용: `jdbc:postgresql://host:port/db`)
- 복합명사 후보 추출
  - `COMPOUND_EXTRACTION_WINDOW_DAYS` (기본 1)
  - `COMPOUND_EXTRACTION_MIN_FREQUENCY` (기본 3)
  - `COMPOUND_EXTRACTION_MIN_CHAR_LENGTH` (기본 4)
  - `COMPOUND_EXTRACTION_MAX_MORPHEME_COUNT` (기본 4)

### 3. 처리 흐름

현재 구현한 기본 처리 흐름은 아래와 같다.

1. Kafka 토픽에서 기사 메시지를 읽는다.
2. 정규화 기사 스키마에 맞는 구조로 파싱한다.
3. `news_raw` 컬럼을 `stg_news_raw`에 JDBC bulk write한다.
4. `upsert_from_staging_news_raw()` 호출 → `news_raw`에 upsert, staging TRUNCATE.
5. `title + summary`를 합쳐 분석용 본문을 만든다.
6. 한국어 전처리(Kiwi 형태소 분석 + 복합명사 병합 + 불용어 제거)로 토큰을 추출한다.
7. 기사별 키워드 빈도를 `stg_keywords`에 JDBC write → `keywords` 테이블 upsert.
8. event time 기준 10분 윈도우로 키워드 빈도를 집계 → `stg_keyword_trends` → upsert.
9. 기사별 상위 키워드 조합으로 연관 키워드를 계산 → `stg_keyword_relations` → upsert.

### 4. JDBC staging 테이블 방식

`foreachBatch`에서 `collect()`로 전체 결과를 드라이버에 모으는 대신 JDBC bulk write를 사용한다.

```
Spark DataFrame
    → _jdbc_write(stg_* 테이블, mode=append)  ← Spark executor가 직접 DB write
    → upsert_from_staging_*()                 ← PostgreSQL 내부에서 INSERT ... ON CONFLICT
    → staging TRUNCATE                         ← 동일 트랜잭션 내
```

이 방식을 선택한 이유는 아래와 같다.

- `collect()`는 모든 데이터를 드라이버 JVM 메모리에 올리므로 배치 크기에 비례해 드라이버 병목 발생.
- JDBC write는 executor가 직접 DB에 쓰므로 분산 이점을 유지할 수 있다.
- staging → main upsert를 같은 트랜잭션에서 처리하므로 부분 실패 시 staging이 남아 재처리 가능.
- `keyword_trends` / `keyword_relations`는 `ON CONFLICT DO UPDATE`로 누적 집계하므로 스트리밍 재처리 시 중복 없이 값이 더해진다.

### 5. `news_raw` 저장 정책

`news_raw`는 ingestion 단계가 아니라 Step 2에서 저장하도록 정리했다.

- Kafka에 적재된 실제 처리 기준 메시지를 그대로 원문 저장 대상으로 삼을 수 있다.
- Processing 단계 진입 시점에 스키마 검증을 거친 뒤 저장하므로 저장 데이터 일관성이 좋아진다.
- `news_raw`와 집계 결과가 같은 처리 경계에서 생성되므로 재처리 정책을 맞추기 쉽다.

현재 `news_raw`의 canonical 컬럼은 아래와 같다.

- `provider`
- `source`
- `title`
- `summary`
- `url`
- `published_at`
- `ingested_at`

Naver 응답에는 작성자(`author`)와 기사 본문(`content`)이 안정적으로 제공되지 않으므로 저장 스키마에서 제거했다. 기존 `description`은 의미를 더 분명히 하기 위해 `summary`로 통일했다.

## DB 스키마

### 주요 테이블

| 테이블 | 설명 |
|--------|------|
| `news_raw` | Naver 정규화 기사 원문 (`provider`, `url` unique) |
| `keywords` | 기사별 키워드 빈도 (article_provider, article_url, keyword unique) |
| `keyword_trends` | 윈도우 집계 키워드 빈도 (provider, window_start, window_end, keyword unique) |
| `keyword_relations` | 윈도우 집계 연관 키워드 (provider, window_start, window_end, keyword_a, keyword_b unique) |
| `compound_noun_dict` | 승인된 복합명사 사전 |
| `compound_noun_candidates` | 자동 추출된 복합명사 후보 (pending / approved / rejected) |
| `stopword_dict` | 불용어 사전 (언어별) |

### Staging 테이블

Spark JDBC bulk write 전용 임시 테이블. upsert 후 TRUNCATE.

| 테이블 | 대상 |
|--------|------|
| `stg_news_raw` | → `news_raw` |
| `stg_keywords` | → `keywords` |
| `stg_keyword_trends` | → `keyword_trends` |
| `stg_keyword_relations` | → `keyword_relations` |

### Upsert 정책

| 테이블 | ON CONFLICT 처리 |
|--------|-----------------|
| `news_raw` | DO NOTHING (중복 기사 무시) |
| `keywords` | DO UPDATE keyword_count, processed_at (최신 값으로 덮어씀) |
| `keyword_trends` | DO UPDATE keyword_count += EXCLUDED (누적 합산) |
| `keyword_relations` | DO UPDATE cooccurrence_count += EXCLUDED (누적 합산) |

## 복합명사·불용어 사전 DB화

### 사전 라이프사이클

```
자동 추출 배치 (Airflow, 매일 03:00)
    └─ compound_extractor.py
        └─ Kiwi (사용자 사전 없이) 형태소 분석
        └─ 인접 명사 n-gram 조합 (span 연속성 검사)
        └─ compound_noun_candidates 테이블에 upsert (pending 상태로 누적)

관리자 검토 (추후 Web/API)
    └─ pending → approved : compound_noun_dict에 반영
    └─ pending → rejected : 후보에서 제외

Spark 잡 재시작 시
    └─ preprocessing.py의 get_user_dictionary() (lru_cache)가
       compound_noun_dict를 DB에서 로드 → Kiwi 사용자 사전 등록
```

### DB 우선 로딩 전략

전처리 계층(`preprocessing.py`)은 Spark executor 프로세스 기동 시 첫 UDF 호출에서 DB에서 사전을 로드한다.

```
get_user_dictionary()  → compound_noun_dict (DB)   → 실패 시 korean_user_dict.txt (파일)
_get_stopwords()       → stopword_dict (DB)         → 실패 시 _KOREAN_STOPWORDS_DEFAULT (코드 내 기본값)
```

`@lru_cache(maxsize=1)`로 프로세스당 1회만 로드하므로 매 UDF 호출마다 DB 조회가 발생하지 않는다. 새 단어 반영은 Spark 잡 재시작이 필요하다.

## 인프라 구성

### 1. Docker Compose 서비스

- `app-postgres` — 기사 원문과 집계 결과 저장용 PostgreSQL
- `spark-master` — Spark 클러스터 마스터
- `spark-worker-1` / `spark-worker-2` — Spark 워커
- `spark-history` — Spark 히스토리 서버
- `spark-streaming` — `scripts/run_processing.py`를 `spark-submit`으로 실행하는 처리 서비스

### 2. Spark 이미지

`infra/spark/Dockerfile.spark` 기반 `news-trend-spark-runtime:latest` 이미지.

포함 내용:
- Java 17 런타임
- Spark 3.5.7 (Hadoop 3)
- Python 처리 의존성 (`requirements/requirements-spark.txt`)
- **PostgreSQL JDBC 드라이버** (`postgresql-42.7.3.jar`) — JDBC staging write에 필요
- 프로젝트 소스 코드

`spark-submit` 실행 시 `--packages`로 Kafka 커넥터와 JDBC 드라이버를 추가 로드한다.

### 3. 실행 흐름

`docker compose up -d` 만으로 `spark-streaming` 컨테이너가 자동으로 `spark-submit`을 실행한다. 별도 수동 실행 불필요.

로그 확인:
```bash
docker logs -f news-trend-develop-spark-streaming-1
```

### 4. Airflow 배치

`airflow/dags/compound_extraction_dag.py`가 매일 03:00에 `compound_extractor.run_extraction_job()`을 실행한다.

- `catchup=False`, `max_active_runs=1`
- `data_interval_end`를 `until` 파라미터로 사용 → 재실행 멱등성 보장

## 구현 파일

- `docker-compose.yml`
- `infra/spark/Dockerfile.spark`
- `requirements/requirements-spark.txt`
- `scripts/run_processing.py`
- `src/news_trend_pipeline/core/config.py`
- `src/news_trend_pipeline/core/schemas.py`
- `src/news_trend_pipeline/core/korean_user_dict.txt`
- `src/news_trend_pipeline/processing/preprocessing.py`
- `src/news_trend_pipeline/processing/spark_job.py`
- `src/news_trend_pipeline/storage/db.py`
- `src/news_trend_pipeline/storage/models.sql`
- `src/news_trend_pipeline/analytics/compound_extractor.py`
- `airflow/dags/compound_extraction_dag.py`
- `tests/unit/test_processing_preprocessing.py`
- `tests/unit/test_core_schemas.py`

## 개발 내역

### 1. NewsAPI·영어 전처리 제거

NewsAPI 연동과 spaCy 기반 영어 전처리 경로를 완전히 제거했다.

- 제거: `spacy` 의존성, `ENGLISH_STOPWORDS`, `ENGLISH_NOUN_TAGS`, `get_spacy_nlp()`, `clean_text(provider=)` 파라미터
- 결과: 전처리 계층이 한국어(Naver) 전용으로 단순화됨

### 2. 전처리 계층 정리

`processing/preprocessing.py`에 한국어 전처리 로직을 구성했다.

- Kiwi 기반 형태소 분석
- DB 우선 복합명사 사전 로드 (`lru_cache` 적용)
- DB 우선 불용어 로드 (fallback: 코드 내 기본값)
- Kiwi 미설치 환경에서도 동작 가능한 정규식 fallback 유지

### 3. Spark 저장 방식 전환 (collect() → JDBC staging)

`processing/spark_job.py`의 `foreachBatch`에서 3회 `collect()` 호출을 제거하고 JDBC staging 방식으로 전환했다.

- `_jdbc_write()` 헬퍼 함수 추가
- `stg_*` 테이블에 bulk write 후 `upsert_from_staging_*()` 함수 호출
- `keywords` 테이블 활성화 (기존에는 `article_keywords` DataFrame이 집계만 하고 저장되지 않았음)
- 컬럼명 통일: `count` → `keyword_count` / `cooccurrence_count`

### 4. 사전 DB화 및 복합명사 후보 자동 추출

- `models.sql`에 `compound_noun_dict`, `compound_noun_candidates`, `stopword_dict` 테이블 추가
- `db.py`에 `fetch_compound_nouns()`, `fetch_stopwords()`, `upsert_compound_candidates()`, `seed_initial_data()` 추가
- `analytics/compound_extractor.py` 신규 추가 — Kiwi 무사전 분석 + span 연속성 검사로 후보 추출
- Airflow DAG으로 매일 03:00 배치 실행

### 5. 저장 계층 upsert 강화

- `models.sql`에 unique index 3개 추가 (`keyword_trends`, `keyword_relations`, `keywords`)
- `models.sql`에 staging 테이블 4개 추가
- `db.py`에 `upsert_from_staging_*()` 함수 4개 추가

## 관련 문서

- [전처리 상세 문서](./STEP2_PREPROCESSING.md) — 텍스트 정제·토큰화·복합명사 병합·불용어·라이브러리·개선 방향

## 남은 작업

1. analytics 계층에서 급상승 키워드 탐지 로직 추가
2. API 계층에서 집계 결과 조회 기능 추가
3. dashboard 계층에서 시각화 화면 추가
4. 복합명사 후보 검토·승인용 Web/Admin API 구현
5. PostgreSQL/Spark가 실제 올라온 상태에서 통합 테스트 보강
