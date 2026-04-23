# Step 2 전처리 계층 상세 문서

> [Step 2 구현 정리](./STEP2_PROCESSING_IMPLEMENTATION.md)의 전처리 관련 내용을 분리·확장한 문서입니다.

## 목차

1. [전처리 목적과 위치](#1-전처리-목적과-위치)
2. [처리 흐름 개요](#2-처리-흐름-개요)
3. [텍스트 정제 (clean_text)](#3-텍스트-정제-clean_text)
4. [토큰화 (tokenize)](#4-토큰화-tokenize)
5. [복합명사 병합 (merge_compound_nouns)](#5-복합명사-병합-merge_compound_nouns)
6. [사전 DB 연동 구조](#6-사전-db-연동-구조)
7. [복합명사 사전 (compound_noun_dict)](#7-복합명사-사전-compound_noun_dict)
8. [불용어 사전 (stopword_dict)](#8-불용어-사전-stopword_dict)
9. [복합명사 후보 자동 추출](#9-복합명사-후보-자동-추출)
10. [사전 라이프사이클](#10-사전-라이프사이클)
11. [라이브러리 소개](#11-라이브러리-소개)
12. [Fallback 전략](#12-fallback-전략)
13. [Spark에서의 전처리 연결](#13-spark에서의-전처리-연결)
14. [연관 키워드 집계 방식](#14-연관-키워드-집계-방식)
15. [현재 한계 및 개선 방향](#15-현재-한계-및-개선-방향)

---

## 1. 전처리 목적과 위치

전처리 계층의 책임은 Kafka에서 읽어 들인 원문 기사 텍스트를 **키워드 집계에 적합한 토큰 리스트**로 변환하는 것이다.

<details>
<summary>?? ??</summary>

```
Kafka 메시지
    └─ parsing (schemas.py)
        └─ clean_text()               ← 텍스트 정제
            └─ tokenize()             ← 형태소 분석 + 품사 필터링
                └─ merge_compound_nouns()   ← 복합명사 병합 (DB 사전 기반)
                    └─ _get_stopwords()     ← 불용어 제거 (DB 사전 기반)
                        └─ keyword 리스트 → Spark 집계
```

</details>

관련 파일:

| 파일 | 역할 |
|------|------|
| [`processing/preprocessing.py`](../src/news_trend_pipeline/processing/preprocessing.py) | 정제·토큰화·병합 |
| [`analytics/compound_extractor.py`](../src/news_trend_pipeline/analytics/compound_extractor.py) | 복합명사 후보 자동 추출 배치 |
| [`storage/db.py`](../src/news_trend_pipeline/storage/db.py) | 사전 CRUD (`fetch_compound_nouns`, `fetch_stopwords`, `upsert_compound_candidates`) |
| [`storage/models.sql`](../src/news_trend_pipeline/storage/models.sql) | 사전 테이블 스키마 |

---

## 2. 처리 흐름 개요

Spark 스트리밍 잡(`spark_job.py`)에서 전처리를 호출하는 방식은 다음과 같다.

<details>
<summary>??</summary>

```python
# spark_job.py 내 핵심 흐름
parsed = (
    raw_stream
    .withColumn("article_text", expr("concat_ws(' ', title, summary)"))
    .withColumn("tokens", tokenize_udf(col("article_text")))
)
```

</details>

1. `title + summary`를 하나의 분석용 본문으로 합친다.
2. `tokenize_udf` 첫 호출 시 워커 프로세스 내 `@lru_cache`가 트리거되어 DB에서 사전을 로드한다.
3. `tokenize()` 결과인 토큰 배열이 이후 집계의 단위가 된다.

---

## 3. 텍스트 정제 (clean_text)

**파일**: `preprocessing.py`

### 정제 단계

| 순서 | 처리 | 정규식/방법 |
|------|------|------------|
| 1 | Unicode NFC 정규화 | `unicodedata.normalize("NFC", text)` |
| 2 | URL 제거 | `http\S+` → 공백 |
| 3 | HTML 태그 제거 | `<[^>]+>` → 공백 |
| 4 | 잔여 문자열 제거 | `\[\+\d+\s+chars\]` → 공백 |
| 5 | 소문자 변환 | `text.lower()` |
| 6 | 한글 외 문자 제거 | `[^\uAC00-\uD7A3\s]` → 공백 |
| 7 | 연속 공백 정리 | `\s+` → 단일 공백 |

### 케이스별 예시

| 입력 | 출력 |
|------|------|
| `<b>AI</b> 2026 혁신!` | `혁신` |
| `[+1500 chars]...더 읽기` | `` (빈 문자열) |
| `인공지능 반도체 https://t.co/abc` | `인공지능 반도체` |
| `<p>GPT 기반 챗봇</p>` | `기반 챗봇` |

> 숫자·영문이 모두 제거된다. 영문 고유명사(`AI`, `GPT`)가 필요한 경우 [개선 방향](#14-현재-한계-및-개선-방향)을 참고한다.

---

## 4. 토큰화 (tokenize)

**파일**: `preprocessing.py`

`clean_text()` 호출 후 Kiwi 형태소 분석으로 명사를 추출한다.

<details>
<summary>?? ??</summary>

```
cleaned text
    └─ _get_stopwords()         ← DB에서 불용어 로드 (lru_cache)
    └─ get_kiwi()               ← DB 복합명사 사전이 등록된 Kiwi 인스턴스 (lru_cache)
        └─ kiwi.tokenize()
            └─ 명사 태그 필터 (NNG, NNP)
                └─ 한글 전용 패턴 매칭
                    └─ merge_compound_nouns()   ← DB 사전 기반 병합
                        └─ 길이 > 1 + 불용어 제거
```

</details>

- **Kiwi** 형태소 분석기로 명사(NNG=일반명사, NNP=고유명사)만 추출한다.
- 추출된 명사 시퀀스에 대해 `compound_noun_dict` 기반 복합명사 병합을 수행한다.
- Kiwi가 없으면 공백 분리 fallback으로 동작한다.

### 품사 태그 참조 (Kiwi 표준)

| 태그 | 의미 |
|------|------|
| `NNG` | 일반명사 |
| `NNP` | 고유명사 |
| `NNB` | 의존명사 (미사용) |
| `VV` | 동사 (미사용) |
| `VA` | 형용사 (미사용) |

---

## 5. 복합명사 병합 (merge_compound_nouns)

**파일**: `preprocessing.py`

형태소 분석 후 인접 명사 토큰을 결합해 `compound_noun_dict`에 있는 복합어를 복원한다.

### 동작 원리

1. `max_window`를 사전 최장 단어 길이 기준으로 계산한다 (최소 2, 최대 6).
2. 현재 위치에서 가장 긴 윈도우부터 줄여가며 후보 결합어를 생성한다.
3. 후보가 사전에 있으면 병합하고 다음 위치로 이동한다.
4. `spans` 파라미터가 제공된 경우 원문에서 실제로 붙어 있는 토큰만 결합한다.

### 예시

<details>
<summary>??</summary>

```python
tokens = ["인공", "지능", "반도체"]
user_dict = frozenset({"인공지능", "반도체"})

# 결과: ["인공지능", "반도체"]
# "인공" + "지능" → "인공지능" (사전 hit)
# "반도체" → 그대로 유지
```

</details>

### 연속성 검사 (spans)

Kiwi 토큰화 경로에서는 `(start, start+len)` 스팬 정보를 함께 넘긴다. 원문에서 실제로 붙어 있던 토큰만 병합해, 공백으로 분리된 다른 어절의 명사들이 잘못 결합되는 문제를 방지한다.

<details>
<summary>??</summary>

```python
# spans[j].end == spans[j+1].start → 연속 판정
contiguous = all(spans[j][1] == spans[j + 1][0] for j in range(i, i + window_size - 1))
```

</details>

---

## 6. 사전 DB 연동 구조

복합명사 사전과 불용어는 PostgreSQL DB에 저장되며, `@lru_cache`를 통해 프로세스 수명 동안 한 번만 로드된다.

### 로딩 순서

<details>
<summary>?? ??</summary>

```
get_user_dictionary()           _get_stopwords()
    │                               │
    ▼                               ▼
DB fetch_compound_nouns()       DB fetch_stopwords()
    │ 성공 시 반환                    │ 성공 시 반환
    │ 실패 시 ↓                      │ 실패 시 ↓
    ▼                               ▼
txt 파일 로드 (fallback)        _KOREAN_STOPWORDS_DEFAULT (fallback)
```

</details>

### Circular Import 방지

`db.py`는 모듈 상단에서 `preprocessing.py`의 `tokenize`를 import한다. `preprocessing.py`가 `db.py`를 상단에서 import하면 순환 참조가 발생하므로, **함수 내부에서 lazy import**로 처리한다.

<details>
<summary>??</summary>

```python
# preprocessing.py
@lru_cache(maxsize=1)
def get_user_dictionary() -> tuple[str, ...]:
    try:
        from news_trend_pipeline.storage.db import fetch_compound_nouns  # lazy import
        words = fetch_compound_nouns()
        if words:
            return tuple(words)
    except Exception:
        pass
    return tuple(_load_user_dictionary_from_file())
```

</details>

### 사전 갱신 반영 시점

`@lru_cache`는 프로세스가 살아 있는 동안 결과를 캐시한다. 따라서 DB에 새 단어가 추가되어도 **해당 프로세스 재시작 전까지는 반영되지 않는다**.

| 컴포넌트 | 반영 시점 |
|---------|---------|
| Spark 스트리밍 잡 | 잡 재시작 시 |
| 복합명사 추출 배치 잡 | 실행마다 새로 로드 (프로세스 단위 실행) |
| 로컬 테스트 | 프로세스 재시작 또는 `lru_cache` 수동 클리어 |

---

## 7. 복합명사 사전 (compound_noun_dict)

**DB 테이블**: `compound_noun_dict`

<details>
<summary>?? ??</summary>

```sql
CREATE TABLE IF NOT EXISTS compound_noun_dict (
    id         SERIAL PRIMARY KEY,
    word       VARCHAR(50)  NOT NULL,
    source     VARCHAR(20)  NOT NULL DEFAULT 'manual',  -- 'manual' or 'auto'
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_compound_noun_dict_word UNIQUE (word)
);
```

</details>

### 역할

1. 복합명사 병합(`merge_compound_nouns`)의 매칭 기준을 제공한다.
2. Kiwi에 `NNP(고유명사)` 태그로 등록(`add_user_word`)해 형태소 분석 품질을 향상시킨다.

### 초기 데이터 적재

`initialize_database()` 호출 시 `seed_initial_data()`가 실행되어 `korean_user_dict.txt`의 단어들을 `source='manual'`로 적재한다.

<details>
<summary>?? ??</summary>

```
인공지능, 생성형AI, 머신러닝, 딥러닝, 챗봇, 반도체, 자율주행, 클라우드, 빅데이터
```

</details>

### Kiwi 등록 방식

<details>
<summary>??</summary>

```python
kiwi.add_user_word(word, "NNP", USER_WORD_SCORE)  # score=5.0
```

</details>

`USER_WORD_SCORE = 5.0`으로 사전 등재 단어에 높은 가중치를 부여해, Kiwi가 분리 분석보다 복합 인식을 우선하도록 한다.

---

## 8. 불용어 사전 (stopword_dict)

**DB 테이블**: `stopword_dict`

<details>
<summary>?? ??</summary>

```sql
CREATE TABLE IF NOT EXISTS stopword_dict (
    id         SERIAL      PRIMARY KEY,
    word       VARCHAR(50) NOT NULL,
    language   VARCHAR(10) NOT NULL DEFAULT 'ko',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_stopword_dict_word_lang UNIQUE (word, language)
);
```

</details>

### 초기 데이터 적재

`seed_initial_data()` 호출 시 `db.py`의 `_STOPWORD_SEED`에 정의된 한국어 불용어 42개가 `language='ko'`로 적재된다.

### 적용 조건

불용어 제거와 함께 아래 추가 필터링이 함께 적용된다.

| 조건 | 설명 |
|------|------|
| 길이 > 1 | 단자 제거 |
| 한글 전용 패턴 매칭 | `[\uAC00-\uD7A3]+` 에 맞지 않으면 제거 |
| DB 불용어 집합 포함 여부 | `_get_stopwords()` 반환값과 대조 |

---

## 9. 복합명사 후보 자동 추출

**파일**: [`analytics/compound_extractor.py`](../src/news_trend_pipeline/analytics/compound_extractor.py)  
**DAG**: [`airflow/dags/compound_extraction_dag.py`](../airflow/dags/compound_extraction_dag.py)

### 목적

수집된 기사에서 아직 사전에 없는 복합명사 후보를 자동으로 발굴해 `compound_noun_candidates` 테이블에 누적한다. 관리자가 검토 후 승인하면 `compound_noun_dict`에 반영된다.

### 후보 DB 테이블 (compound_noun_candidates)

<details>
<summary>?? ??</summary>

```sql
CREATE TABLE IF NOT EXISTS compound_noun_candidates (
    id            SERIAL      PRIMARY KEY,
    word          VARCHAR(50) NOT NULL,
    frequency     INTEGER     NOT NULL DEFAULT 1,   -- 총 출현 횟수
    doc_count     INTEGER     NOT NULL DEFAULT 1,   -- 출현 기사 수
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_at   TIMESTAMPTZ,
    reviewed_by   VARCHAR(100),
    CONSTRAINT uq_compound_noun_candidates_word UNIQUE (word),
    CONSTRAINT ck_status CHECK (status IN ('pending', 'approved', 'rejected'))
);
```

</details>

### 추출 알고리즘

<details>
<summary>?? ??</summary>

```
1. news_raw에서 지정 기간(ingested_at 기준) 기사 조회
2. Kiwi를 사용자 사전 없이 초기화          ← 미등록 복합어가 형태소로 분리됨
3. 기사별 처리:
a. title + summary 합산 → clean_text()
   b. kiwi.tokenize() → NNG/NNP 명사 추출
   c. 연속 형태소 조합 탐색 (2 ~ max_morpheme_count개)
      └─ 스팬 연속성 검사: spans[j].end == spans[j+1].start
      └─ 조합 길이 ≥ min_char_length
      └─ 이미 승인된 단어(compound_noun_dict) 제외
4. 전체 기사 집계 → frequency(총 출현), doc_count(기사 수)
5. frequency ≥ min_frequency 인 후보만 선별
6. upsert_compound_candidates():
   - 신규: INSERT
   - 기존 pending: frequency/doc_count 누적 UPDATE
   - 기존 approved/rejected: 변경 없음
```

</details>

#### Kiwi를 사용자 사전 없이 사용하는 이유

전처리(`get_kiwi`)에서는 승인된 단어를 `add_user_word`로 등록해 복합어를 하나의 토큰으로 인식하지만, 후보 추출에서는 의도적으로 등록하지 않는다. 그래야 "인공지능" 같은 단어가 ["인공", "지능"]으로 분리되어 새 조합으로 탐색된다. 즉, **이미 아는 단어를 제외하고 모르는 복합어를 찾는 구조**다.

#### 스팬 연속성 검사 상세

<details>
<summary>??</summary>

```python
# i번째 형태소부터 count개가 모두 연속된 경우에만 병합 후보로 인정
contiguous = all(
    noun_tokens[j][2] == noun_tokens[j + 1][1]   # j.end == (j+1).start
    for j in range(i, i + count - 1)
)
if not contiguous:
    break  # 더 긴 window도 같은 gap을 포함하므로 중단
```

</details>

#### 추출 파라미터 (config.py / 환경변수)

| 설정 | 환경변수 | 기본값 | 의미 |
|------|----------|--------|------|
| 분석 기간 | `COMPOUND_EXTRACTION_WINDOW_DAYS` | `1` | 최근 N일치 기사 |
| 최소 빈도 | `COMPOUND_EXTRACTION_MIN_FREQUENCY` | `3` | N회 이상 출현한 조합 |
| 최소 글자 수 | `COMPOUND_EXTRACTION_MIN_CHAR_LENGTH` | `4` | 형태소 합산 N자 이상 |
| 최대 형태소 수 | `COMPOUND_EXTRACTION_MAX_MORPHEME_COUNT` | `4` | 최대 N개 형태소 결합 |

### Airflow DAG 스케줄

| 항목 | 값 |
|------|-----|
| DAG ID | `compound_noun_extraction` |
| 스케줄 | `0 3 * * *` (매일 03:00 UTC) |
| catchup | `False` |
| 멱등성 | `data_interval_end` 기준으로 window 계산 |
| 재시도 | 1회, 10분 후 |

---

## 10. 사전 라이프사이클

복합명사 사전 항목 하나가 거치는 전체 흐름이다.

<details>
<summary>?? ??</summary>

```
[매일 03:00] compound_noun_extraction DAG
    └─ news_raw 기사 조회 (ingested_at 기준 최근 1일)
    └─ Kiwi 무사전 분석 → 스팬 인접 명사 조합
    └─ compound_noun_candidates 에 upsert
                │
                ▼  status = 'pending'
    [추후 Web/API] 관리자 검토 화면
        ├─ 승인 → compound_noun_dict INSERT (source='auto')
        │              + candidates status = 'approved'
        └─ 거부 → candidates status = 'rejected'
                │              (이후 재추출 시 빈도 누적 안 됨)
                ▼  compound_noun_dict에 반영됨
    [다음 Spark 잡 재시작 시]
        └─ get_user_dictionary() → DB 재조회 → lru_cache 갱신
        └─ get_kiwi() → 새 단어 add_user_word 등록
        └─ 이후 기사부터 새 복합명사로 토큰화됨
```

</details>

### 상태 전이

<details>
<summary>?? ??</summary>

```
[자동 추출]
    pending ──── 관리자 승인 ──── approved
        │
        └────── 관리자 거부 ──── rejected
```

</details>

- `approved` 단어는 `compound_noun_dict`에 복사 후 전처리에 반영된다.
- `rejected` 단어는 이후 추출에서 다시 `pending`으로 삽입되지 않는다 (upsert의 WHERE 조건으로 보호).
- `pending` 단어는 매일 배치가 돌 때 `frequency`와 `doc_count`가 누적된다. 빈도가 높을수록 승인 우선순위가 높다.

---

## 11. 라이브러리 소개

### kiwipiepy (Kiwi)

| 항목 | 내용 |
|------|------|
| 역할 | 한국어 형태소 분석 |
| 사용 이유 | 순수 Python, 사용자 사전 동적 추가 지원, 빠른 토큰화 |
| 주요 기능 | `tokenize()`, `add_user_word()` |
| 설치 | `pip install kiwipiepy` |
| 버전 요구 | Python 3.8+ |

**`kiwi.tokenize()` 반환 토큰 구조**

<details>
<summary>??</summary>

```python
Token(
    form="인공지능",   # 표면형
    tag="NNG",         # 품사 태그
    start=0,           # 시작 위치 (문자 인덱스)
    len=4,             # 길이
)
```

</details>

**두 가지 사용 방식 비교**

| 용도 | 사전 등록 여부 | 이유 |
|------|--------------|------|
| 전처리 (`get_kiwi`) | `compound_noun_dict` 전체 등록 | 승인된 복합어를 하나의 토큰으로 인식 |
| 후보 추출 (`_build_raw_kiwi`) | 등록 없음 | 미등록 복합어가 분리되어야 새 조합을 발견할 수 있음 |

---

## 12. Fallback 전략

DB·라이브러리 가용성에 따라 3단계 fallback이 작동한다.

<details>
<summary>?? ??</summary>

```
복합명사 로딩 (get_user_dictionary)        불용어 로딩 (_get_stopwords)
    │                                           │
    ▼  1순위                                    ▼  1순위
DB compound_noun_dict 조회                  DB stopword_dict 조회
    │ 성공 + 비어 있지 않으면 반환               │ 성공 + 비어 있지 않으면 반환
    │ 실패 또는 빈 결과 ↓                        │ 실패 또는 빈 결과 ↓
    ▼  2순위                                    ▼  2순위
korean_user_dict.txt 파일 로드             _KOREAN_STOPWORDS_DEFAULT (코드 상수)
    │ 파일 없으면 빈 tuple                        항상 반환됨
    ▼

Kiwi 토큰화 (get_kiwi)
    │
    ▼  1순위
Kiwi 사용 가능 → 형태소 분석 + 복합명사 병합
    │ ImportError 또는 초기화 실패 ↓
    ▼  2순위
공백 분리 + 한글 패턴 필터 + 복합명사 병합
```

</details>

**Fallback 품질 비교**

| 경로 | 품질 | 비고 |
|------|------|------|
| DB + Kiwi | 최고 | 정상 운영 경로 |
| DB + 공백분리 | 보통 | Kiwi 미설치 환경 |
| 파일 + Kiwi | 높음 | DB 미연결 개발 환경 |
| 파일 + 공백분리 | 낮음 | 완전 오프라인 테스트 |

---

## 13. Spark에서의 전처리 연결

`spark_job.py`에서 `tokenize()`를 Spark UDF로 등록해 DataFrame 컬럼에 적용한다.

<details>
<summary>??</summary>

```python
tokenize_udf = udf(extract_tokens, ArrayType(StringType()))

parsed = (
    raw_stream
.withColumn("article_text", expr("concat_ws(' ', title, summary)"))
    .withColumn("tokens", tokenize_udf(col("article_text")))
)
```

</details>

### UDF 성능 고려사항

- Python UDF는 JVM ↔ Python 직렬화 비용이 발생한다.
- `get_kiwi()` / `_get_stopwords()` / `get_user_dictionary()`는 `@lru_cache`로 캐싱되어 **워커 프로세스당 한 번만 DB 조회 및 Kiwi 초기화**가 일어난다.
- 각 Spark 워커에서 독립적으로 DB에 연결하므로, 워커 이미지에 `kiwipiepy`와 `psycopg2-binary`가 포함되어야 한다.

---

## 14. 연관 키워드 집계 방식

전처리 문서에서 토큰화까지만 설명하면 `keyword_relations`가 어떻게 만들어지는지 흐름이 끊길 수 있다. 현재 구현에서 연관 키워드는 **같은 기사 안에서 함께 등장한 상위 키워드 쌍을 시간 윈도우별로 누적 집계**하는 방식으로 생성된다.

### 처리 흐름

`tokenize()` 결과는 먼저 기사별 키워드 빈도(`article_keywords`)로 집계되고, 그 다음 연관 키워드 계산에 사용된다.

<details>
<summary>?? ??</summary>

```text
title + summary
    -> tokenize()
    -> article_keywords (기사별 keyword_count)
    -> 기사별 상위 키워드 선택
    -> 같은 기사 내 키워드 쌍 생성
    -> 10분 window 기준 co-occurrence 집계
    -> keyword_relations 저장
```

</details>

### 1. 기사별 키워드 빈도 생성

Spark는 토큰 배열을 `explode()`로 펼친 뒤, 기사 단위로 키워드 빈도를 먼저 계산한다.

<details>
<summary>??</summary>

```python
article_keywords = (
    batch_df.select("provider", "url", "event_time", explode(col("tokens")).alias("keyword"))
    .groupBy("provider", "url", "event_time", "keyword")
    .agg(spark_count("*").alias("keyword_count"))
)
```

</details>

이 단계 결과는 아래와 같은 형태다.

| provider | url | event_time | keyword | keyword_count |
|------|------|------------|---------|---------------|
| naver | article-1 | 01:10 | 검색 | 2 |
| naver | article-1 | 01:10 | 네이버 | 2 |
| naver | article-1 | 01:10 | 생성형 | 2 |

### 2. 기사별 대표 키워드 선택

연관 키워드는 모든 토큰 조합을 다 만들지 않고, 기사별 상위 키워드만 대상으로 만든다. 현재 구현은 기사 내부에서:

1. `keyword_count` 내림차순
2. 같은 빈도면 `keyword` 오름차순

으로 정렬한 뒤, `RELATION_KEYWORD_LIMIT` 개수만 남긴다.

<details>
<summary>??</summary>

```python
article_window = Window.partitionBy("provider", "url", "event_time").orderBy(
    col("keyword_count").desc(),
    col("keyword").asc(),
)

representative_keywords = (
    article_keywords.withColumn("keyword_rank", row_number().over(article_window))
    .filter(col("keyword_rank") <= settings.relation_keyword_limit)
)
```

</details>

기본값은 `RELATION_KEYWORD_LIMIT=8` 이다. 이 제한을 두는 이유는 기사 하나에서 토큰 수가 많아질수록 조합 수가 급격히 늘어나는 것을 막기 위해서다.

### 3. 같은 기사 안에서 키워드 쌍 생성

대표 키워드를 자기 자신과 self join 해서, 같은 기사 안에서 함께 등장한 키워드 쌍만 만든다.

<details>
<summary>??</summary>

```python
relation_pairs = (
    left.join(
        right,
        (col("left.provider") == col("right.provider"))
        & (col("left.url") == col("right.url"))
        & (col("left.event_time") == col("right.event_time"))
        & (col("left.keyword_rank") < col("right.keyword_rank")),
    )
    .select(
        col("left.provider").alias("provider"),
        col("left.event_time").alias("event_time"),
        col("left.keyword").alias("keyword_a"),
        col("right.keyword").alias("keyword_b"),
    )
)
```

</details>

여기서 `left.keyword_rank < right.keyword_rank` 조건을 써서:

- 자기 자신과의 조합은 제외하고
- `(A, B)` 와 `(B, A)` 중복 생성을 막는다.

예를 들어 기사 1건의 대표 키워드가 아래와 같다면:

<details>
<summary>?? ??</summary>

```text
["네이버", "검색", "생성형", "기술"]
```

</details>

생성되는 연관 키워드 쌍은 다음과 같다.

<details>
<summary>?? ??</summary>

```text
("네이버", "검색")
("네이버", "생성형")
("네이버", "기술")
("검색", "생성형")
("검색", "기술")
("생성형", "기술")
```

</details>

### 4. 시간 윈도우 기준으로 co-occurrence 집계

생성된 키워드 쌍은 다시 `event_time` 기준 10분 윈도우로 묶어서 `cooccurrence_count`를 계산한다.

<details>
<summary>??</summary>

```python
relation_trends = (
    relation_pairs.groupBy(
        col("provider"),
        window(col("event_time"), settings.keyword_window_duration),
        "keyword_a",
        "keyword_b",
    )
    .agg(spark_count("*").alias("cooccurrence_count"))
)
```

</details>

즉, `cooccurrence_count`는 "해당 시간 구간 안에서 이 두 키워드가 같은 기사에 몇 번 함께 등장했는가"를 의미한다.

### 5. 저장 방식

집계 결과는 `stg_keyword_relations`에 먼저 적재한 뒤 `keyword_relations`로 upsert 한다.

<details>
<summary>??</summary>

```python
_jdbc_write(relation_trends, "stg_keyword_relations", jdbc_url, jdbc_props)
upsert_from_staging_keyword_relations()
```

</details>

DB에서는 아래 unique 기준으로 누적 저장된다.

- `provider`
- `window_start`
- `window_end`
- `keyword_a`
- `keyword_b`

동일 윈도우와 동일 키워드 쌍이 다시 들어오면 `cooccurrence_count`를 더하는 방식으로 누적한다.

### 예시

두 기사에서 같은 시간대에 아래 대표 키워드가 추출되었다고 가정하면:

<details>
<summary>?? ??</summary>

```text
기사 A: ["네이버", "검색", "생성형"]
기사 B: ["네이버", "검색", "광고"]
```

</details>

10분 윈도우 집계 결과는 다음처럼 저장될 수 있다.

| keyword_a | keyword_b | cooccurrence_count |
|------|------|--------------------|
| 네이버 | 검색 | 2 |
| 네이버 | 생성형 | 1 |
| 검색 | 생성형 | 1 |
| 네이버 | 광고 | 1 |
| 검색 | 광고 | 1 |

즉, 연관 키워드는 의미 기반 모델로 직접 계산하는 것이 아니라, **전처리된 대표 키워드의 기사 내 동시 출현 빈도**를 기준으로 만든다.

---

## 15. 현재 한계 및 개선 방향

### 단기 개선

#### lru_cache 무효화 메커니즘
현재 사전이 업데이트되어도 실행 중인 Spark 잡은 재시작 전까지 반영하지 못한다. `foreachBatch` 내에서 일정 배치 수마다 캐시를 클리어하거나, TTL 기반 캐시로 교체하면 다운타임 없이 사전을 갱신할 수 있다.

<details>
<summary>??</summary>

```python
# 개선안: 일정 배치마다 캐시 클리어
if batch_id % 100 == 0:
    get_user_dictionary.cache_clear()
    get_kiwi.cache_clear()
    _get_stopwords.cache_clear()
```

</details>

#### 후보 추출 품질 지표
현재 `frequency`와 `doc_count`만 기록한다. PMI(Pointwise Mutual Information) 또는 C-value 등 통계 지표를 추가하면 관리자 검토 우선순위 결정에 도움이 된다.

### 중기 개선

#### Pandas UDF (Vectorized UDF) 전환
현재 Row 단위 Python UDF는 직렬화 오버헤드가 크다. Apache Arrow를 활용하는 Pandas UDF로 전환하면 배치 처리 성능이 크게 향상된다.

<details>
<summary>??</summary>

```python
from pyspark.sql.functions import pandas_udf
import pandas as pd

@pandas_udf(ArrayType(StringType()))
def tokenize_pandas_udf(texts: pd.Series) -> pd.Series:
    return texts.apply(tokenize)
```

</details>

#### 전처리 품질 모니터링
토큰 수 분포, 빈 토큰 비율, fallback 경로 호출 빈도 등을 메트릭으로 수집해 전처리 품질을 모니터링하면 사전 관리 및 불용어 조정에 근거가 생긴다.

### 장기 개선

#### 도메인 적응형 키워드 추출
단순 명사 추출이 아니라 TF-IDF, TextRank, KeyBERT 등 통계적 또는 의미 기반 키워드 추출 방법을 조합하면 키워드 품질이 향상된다.

#### 영문 고유명사 처리
현재 한글만 남기기 때문에 영문 고유명사(`AI`, `ChatGPT`, `GPU`)가 모두 제거된다. 한글+영문 혼재 처리 로직 추가를 검토할 수 있다.

<details>
<summary>??</summary>

```python
# 개선안: 한글 + 영문 대문자(고유명사 후보) 유지
text = re.sub(r"[^\uAC00-\uD7A3A-Z\s]", " ", text)
```

</details>

---

## 관련 문서

- [Step 2 구현 정리](./STEP2_PROCESSING_IMPLEMENTATION.md) — 전체 Step 2 설계·인프라·구현 내역
- [Step 1 Kafka 수집](./STEP1_KAFKA.md) — 전처리 이전 단계 수집 흐름
