# Step 2 전처리 계층 상세 문서

> [Step 2 구현 정리](./STEP2_PROCESSING_IMPLEMENTATION.md)의 전처리 관련 내용을 분리·확장한 문서입니다.

## 목차

1. [전처리 목적과 위치](#1-전처리-목적과-위치)
2. [처리 흐름 개요](#2-처리-흐름-개요)
3. [텍스트 정제 (clean_text)](#3-텍스트-정제-clean_text)
4. [토큰화 (tokenize)](#4-토큰화-tokenize)
5. [복합명사 병합 (merge_compound_nouns)](#5-복합명사-병합-merge_compound_nouns)
6. [불용어 관리](#6-불용어-관리)
7. [사용자 사전](#7-사용자-사전)
8. [라이브러리 소개](#8-라이브러리-소개)
9. [Fallback 전략](#9-fallback-전략)
10. [Spark에서의 전처리 연결](#10-spark에서의-전처리-연결)
11. [현재 한계 및 개선 방향](#11-현재-한계-및-개선-방향)

---

## 1. 전처리 목적과 위치

전처리 계층의 책임은 Kafka에서 읽어 들인 원문 기사 텍스트를 **키워드 집계에 적합한 토큰 리스트**로 변환하는 것이다.

```
Kafka 메시지
    └─ parsing (schemas.py)
        └─ clean_text()          ← 텍스트 정제
            └─ tokenize()        ← 형태소 분석 + 품사 필터링
                └─ merge_compound_nouns()  ← 복합명사 병합
                    └─ stopword 제거
                        └─ keyword 리스트 → Spark 집계
```

구현 위치: [`src/news_trend_pipeline/processing/preprocessing.py`](../src/news_trend_pipeline/processing/preprocessing.py)

---

## 2. 처리 흐름 개요

Spark 스트리밍 잡(`spark_job.py`)에서 전처리를 호출하는 방식은 다음과 같다.

```python
# spark_job.py 내 핵심 흐름
parsed = (
    raw_stream
    .withColumn("article_text", expr("concat_ws(' ', title, description, content)"))
    .withColumn("tokens", tokenize_udf(col("article_text")))
)
```

1. `title + description + content`를 하나의 분석용 본문으로 합친다.
2. `tokenize()` 결과인 토큰 배열이 이후 집계의 단위가 된다.

---

## 3. 텍스트 정제 (clean_text)

**파일**: `preprocessing.py`

### 정제 단계

| 순서 | 처리 | 정규식/방법 |
|------|------|------------|
| 1 | Unicode NFC 정규화 | `unicodedata.normalize("NFC", text)` |
| 2 | URL 제거 | `http\S+` → 공백 |
| 3 | HTML 태그 제거 | `<[^>]+>` → 공백 |
| 4 | NewsAPI 잔여 문자열 제거 | `\[\+\d+\s+chars\]` → 공백 |
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

> 숫자·영문이 모두 제거된다. 영문 고유명사(`AI`, `GPT`)가 필요한 경우 [개선 방향](#11-현재-한계-및-개선-방향)을 참고한다.

---

## 4. 토큰화 (tokenize)

**파일**: `preprocessing.py`

`clean_text()` 호출 후 Kiwi 형태소 분석으로 명사를 추출한다.

```
cleaned text
    └─ kiwi.tokenize()
        └─ 명사 태그 필터 (NNG, NNP)
            └─ 한글 전용 패턴 매칭
                └─ merge_compound_nouns()
                    └─ 길이 > 1 + 불용어 제거
```

- **Kiwi** 형태소 분석기로 명사(NNG=일반명사, NNP=고유명사)만 추출한다.
- 추출된 명사 시퀀스에 대해 사용자 사전 기반 복합명사 병합을 수행한다.
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

형태소 분석 후 인접 명사 토큰을 결합해 사용자 사전에 있는 복합어를 복원한다.

### 동작 원리

1. `max_window`를 사용자 사전 최장 단어 길이 기준으로 계산한다 (최소 2, 최대 6).
2. 현재 위치에서 가장 긴 윈도우부터 줄여가며 후보 결합어를 생성한다.
3. 후보가 사용자 사전에 있으면 병합하고 다음 위치로 이동한다.
4. `spans` 파라미터가 제공된 경우 실제 인접한 토큰만 결합한다.

### 예시

```python
tokens = ["인공", "지능", "반도체"]
user_dict = frozenset({"인공지능", "반도체"})

# 결과: ["인공지능", "반도체"]
# "인공" + "지능" → "인공지능" (사전 hit)
# "반도체" → 그대로 유지
```

### 연속성 검사 (spans)

Kiwi 토큰화 경로에서는 `(start, start+len)` 스팬 정보를 함께 넘긴다. 이를 통해 원문에서 실제로 붙어 있었던 토큰만 병합한다. 공백으로 분리된 전혀 다른 어절의 명사들이 잘못 결합되는 문제를 방지한다.

---

## 6. 불용어 관리

**파일**: `preprocessing.py`

### 한국어 불용어 (`KOREAN_STOPWORDS`)

뉴스 기사에서 빈번하게 나타나지만 트렌드 분석에 정보가 없는 단어들로 구성된다.

```python
# 대표 예시
{"기자", "뉴스", "이번", "지난", "통해", "대한", "관련", "위해",
 "사진", "정도", "서비스", "시장", "기술", "최근", "예정", ...}
```

현재 55개 항목. 명사 추출 이후 길이 > 1 조건과 함께 적용된다.

### 추가 필터링 조건

불용어 제거와 독립적으로 아래 조건도 함께 적용한다:

- 토큰 길이 > 1 (단자 제거)
- 한글 전용 패턴(`[\uAC00-\uD7A3]+`)에 맞지 않는 토큰 제거

---

## 7. 사용자 사전

**파일**: [`src/news_trend_pipeline/core/korean_user_dict.txt`](../src/news_trend_pipeline/core/korean_user_dict.txt)

### 역할

1. 복합명사 병합의 기준이 되는 어휘 목록을 제공한다.
2. Kiwi에 `NNP(고유명사)` 태그로 등록해 형태소 분석 품질을 향상시킨다.

### 현재 등록 단어 (9개)

```
인공지능, 생성형AI, 머신러닝, 딥러닝, 챗봇,
반도체, 자율주행, 클라우드, 빅데이터
```

IT/기술 도메인에 특화된 복합명사들이다.

### 사전 로딩 규칙

- `#`으로 시작하는 줄은 주석으로 건너뛴다.
- NFC 정규화 후 한글 전용 패턴(`[\uAC00-\uD7A3]+`)에 맞지 않으면 무시한다.
- 중복 단어는 한 번만 등록한다.
- `@lru_cache`로 프로세스 수명 동안 한 번만 파일을 읽는다.

### 사전 경로 커스터마이징

```bash
KOREAN_USER_DICT_PATH=/custom/path/dict.txt python ...
```

기본값은 `src/news_trend_pipeline/core/korean_user_dict.txt`이다.

### Kiwi 등록 방식

```python
kiwi.add_user_word(word, "NNP", USER_WORD_SCORE)  # score=5.0
```

`USER_WORD_SCORE = 5.0`으로 사전 등재 단어에 높은 가중치를 부여해 분리 분석보다 복합 인식을 우선시한다.

---

## 8. 라이브러리 소개

### kiwipiepy (Kiwi)

| 항목 | 내용 |
|------|------|
| 역할 | 한국어 형태소 분석 |
| 사용 이유 | 순수 Python, 사용자 사전 동적 추가 지원, 빠른 토큰화 |
| 주요 기능 | `tokenize()`, `add_user_word()` |
| 설치 | `pip install kiwipiepy` |
| 버전 요구 | Python 3.8+ |

**`kiwi.tokenize()` 반환 토큰 구조**

```python
Token(
    form="인공지능",   # 표면형
    tag="NNG",         # 품사 태그
    start=0,           # 시작 위치 (문자 인덱스)
    len=4,             # 길이
)
```

---

## 9. Fallback 전략

Kiwi가 설치되지 않은 환경이나 로드 실패 시에도 전처리가 동작하도록 fallback이 구현되어 있다.

```
Kiwi 사용 가능? ─── YES → Kiwi 형태소 분석 + 복합명사 병합
      │
      NO ↓
공백 분리 + 한글 패턴 필터 + 복합명사 병합
```

Fallback은 품질이 낮아지지만 파이프라인 자체는 중단되지 않는다. `ImportError`는 모듈 로드 시점에 처리하고, 로드 실패는 `get_kiwi()` 내에서 `None` 반환으로 처리한다.

---

## 10. Spark에서의 전처리 연결

`spark_job.py`에서 `tokenize()`를 Spark UDF로 등록해 DataFrame 컬럼에 적용한다.

```python
tokenize_udf = udf(extract_tokens, ArrayType(StringType()))

parsed = (
    raw_stream
    .withColumn("article_text", expr("concat_ws(' ', title, description, content)"))
    .withColumn("tokens", tokenize_udf(col("article_text")))
)
```

### UDF 성능 고려사항

- Python UDF는 JVM ↔ Python 직렬화 비용이 발생한다.
- `get_kiwi()`는 `@lru_cache`로 캐싱되어 워커 프로세스당 한 번만 초기화된다.
- 각 Spark 워커에서 독립적으로 Kiwi가 로드되므로 워커 이미지에 `kiwipiepy`가 포함되어야 한다.

---

## 11. 현재 한계 및 개선 방향

### 단기 개선

#### 불용어 사전 동적 관리
현재 불용어는 코드에 하드코딩되어 있다. 도메인이나 키워드 풀에 따라 달라질 수 있으므로 외부 파일이나 DB에서 로드하는 방식으로 개선할 수 있다.

```python
# 현재 (하드코딩)
KOREAN_STOPWORDS = {"기자", "뉴스", ...}

# 개선안
KOREAN_STOPWORDS = load_stopwords_from_file("korean_stopwords.txt")
```

#### 사용자 사전 자동 확장
현재 9개의 IT 도메인 단어만 등록되어 있다. 수집 키워드 풀(`NAVER_THEME_KEYWORDS`)을 기반으로 사전을 자동 생성하거나 주기적으로 갱신하는 방안을 검토할 수 있다.

### 중기 개선

#### Pandas UDF (Vectorized UDF) 전환
현재 Row 단위 Python UDF는 직렬화 오버헤드가 크다. Apache Arrow를 활용하는 Pandas UDF로 전환하면 배치 처리 성능이 크게 향상된다.

```python
from pyspark.sql.functions import pandas_udf
import pandas as pd

@pandas_udf(ArrayType(StringType()))
def tokenize_pandas_udf(texts: pd.Series) -> pd.Series:
    return texts.apply(tokenize)
```

#### 전처리 품질 모니터링
토큰 수 분포, 빈 토큰 비율, fallback 경로 호출 빈도 등을 메트릭으로 수집해 전처리 품질을 모니터링하면 사전 관리 및 불용어 조정에 근거가 생긴다.

### 장기 개선

#### 도메인 적응형 키워드 추출
단순 명사 추출이 아니라 TF-IDF, TextRank, KeyBERT 등 통계적 또는 의미 기반 키워드 추출 방법을 조합하면 키워드 품질이 향상된다.

#### 영문 고유명사 처리
현재 한글만 남기기 때문에 영문 고유명사(`AI`, `ChatGPT`, `GPU`)가 모두 제거된다. 한글+영문 혼재 처리 로직 추가를 검토할 수 있다.

```python
# 현재: 한글만 유지
text = re.sub(r"[^\uAC00-\uD7A3\s]", " ", text)

# 개선안: 한글 + 영문 대문자(고유명사 후보) 유지
text = re.sub(r"[^\uAC00-\uD7A3A-Z\s]", " ", text)
```

---

## 관련 문서

- [Step 2 구현 정리](./STEP2_PROCESSING_IMPLEMENTATION.md) — 전체 Step 2 설계·인프라·구현 내역
- [Step 1 Kafka 수집](./STEP1_KAFKA.md) — 전처리 이전 단계 수집 흐름
