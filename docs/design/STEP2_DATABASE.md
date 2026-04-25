# Step 2 Database 설계

> 이 문서는 `src/storage/models.sql` 기준의 PostgreSQL 스키마를 설명한다.
> Step 2 Spark 문서에서는 DB 상세를 다루지 않고, 본 문서를 단일 기준으로 사용한다.

## 1. 설계 원칙

### 1-1. 도메인 기반 설계

모든 주요 테이블은 `provider + domain` 기준으로 분리된다.

```text
기존: provider 단위 분석
현재: provider + domain 단위 분석
```

### 1-2. Upsert 중심 구조

모든 집계 테이블은 다음 패턴을 따른다.

```text
staging table -> INSERT ... ON CONFLICT DO UPDATE -> TRUNCATE
```

### 1-3. 사전 DB 관리

복합명사 / 불용어는 코드가 아니라 DB에서 관리된다.

```text
compound_noun_dict
stopword_dict
```

## 2. 핵심 테이블

### 2-1. news_raw

기사 원문 저장

```text
provider
 domain
 query
 source
 title
 summary
 url
 published_at
 ingested_at
```

#### 특징

- unique key: `(provider, domain, url)`
- 동일 URL도 domain별로 분리 저장 가능

---

### 2-2. keywords

기사별 키워드

```text
article_provider
article_domain
article_url
keyword
keyword_count
```

#### 특징

- unique key: `(article_provider, article_domain, article_url, keyword)`

---

### 2-3. keyword_trends

시간 윈도우별 키워드 집계

```text
provider
domain
window_start
window_end
keyword
keyword_count
```

---

### 2-4. keyword_relations

연관 키워드

```text
provider
domain
window_start
window_end
keyword_a
keyword_b
cooccurrence_count
```

---

## 3. 도메인 및 수집 설정

### domain_catalog

```text
domain_id
label
sort_order
is_active
```

### query_keywords

```text
provider
domain_id
query
sort_order
is_active
```

---

## 4. 사전 테이블

### compound_noun_dict

```text
word
source
```

### compound_noun_candidates

```text
word
frequency
doc_count
status (pending/approved/rejected)
```

### stopword_dict

```text
word
language
```

### dictionary_versions

사전 변경 감지용

---

## 5. 이벤트 및 메트릭

### keyword_events

```text
keyword
current_mentions
prev_mentions
growth
event_score
is_spike
```

### collection_metrics

```text
request_count
success_count
article_count
duplicate_count
error_count
```

---

## 6. staging 테이블

```text
stg_news_raw
stg_keywords
stg_keyword_trends
stg_keyword_relations
```

Spark는 항상 staging에 쓰고 DB 내부에서 upsert한다.

---

## 7. 주요 변경 요약 (STEP2_SPARK 대비)

1. domain 컬럼 전면 도입
2. description/content 제거 → summary 통합
3. unique key 변경 (provider → provider+domain)
4. 사전 테이블 DB화
5. 이벤트/메트릭 테이블 추가
6. staging 기반 upsert 구조 도입

---

## 8. 한 줄 정리

```text
이 DB는 단순 저장소가 아니라
도메인 기반 분석 + 사전 관리 + 이벤트 탐지까지 포함하는 분석용 데이터 모델이다.
```
