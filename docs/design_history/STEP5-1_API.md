# STEP5-1: API (FastAPI)

## 1. 구현 방식

STEP5 API는 FastAPI 기반으로 구현되어 있다.

- framework: FastAPI
- app entry: `src/api/app.py`
- service layer: `src/api/service.py`
- schema: `src/api/schemas.py`
- DB access: `src/storage/db.py`

애플리케이션 시작 시 `safe_initialize_database()`를 실행해 DB 스키마를 초기화한다.

```text
startup
→ safe_initialize_database()
```

## 2. API 역할

API는 다음 영역을 담당한다.

- 대시보드 조회용 데이터 제공
- keyword trend / spike / article 조회
- dictionary 관리
- compound noun candidate 수동 리뷰
- stopword / stopword candidate 관리
- query keyword 관리
- collection metrics 조회
- 운영 상태 조회

## 3. 현재 사용 API

### 3.1 Health

```text
GET /health
```

응답:

```json
{
  "status": "ok"
}
```

용도:

- API 프로세스 health check
- container / load balancer 상태 확인

---

### 3.2 Meta / Filter API

```text
GET /api/v1/meta/filters
```

용도:

- 대시보드 필터 목록 조회
- source, domain, range 목록 제공

주요 응답:

```text
domains
sources
ranges
```

---

## 4. Dashboard API

### 4.1 Overview Window

```text
GET /api/v1/dashboard/overview-window
```

현재 대시보드의 중심 API이다.

용도:

- KPI, keywords, spikes를 한 번에 조회
- frontend cache-friendly bucket 데이터 제공
- 표시 구간과 fetch 구간을 분리해 프론트 재집계 지원

Query params:

| 이름 | 설명 |
| --- | --- |
| `source` | `all`, `naver`, `global` |
| `domain` | `all` 또는 domain id |
| `range` | `10m`, `30m`, `1h`, `6h`, `12h`, `1d` |
| `startAt` | 표시 구간 시작 |
| `endAt` | 표시 구간 종료 |
| `fetchStartAt` | cache 조회 시작 |
| `fetchEndAt` | cache 조회 종료 |
| `bucket` | `5m`, `15m`, `30m`, `1h`, `4h`, `1d` |
| `search` | keyword 검색어 |
| `limit` | keyword limit, 1~100 |

주요 응답:

```text
summary.kpis
summary.keywords
summary.spikes
cache.articleBuckets
cache.keywordBuckets
```

---

### 4.2 KPI

```text
GET /api/v1/dashboard/kpis
```

용도:

- 기사 수, 고유 키워드 수, spike 수, 성장률, 마지막 업데이트 시각 조회

Query params:

```text
source
domain
range
startAt
endAt
```

---

### 4.3 Keywords

```text
GET /api/v1/dashboard/keywords
```

용도:

- 기간 내 top keyword 목록 조회
- mention, growth, delta, spike 여부 제공

Query params:

```text
source
domain
range
limit
search
startAt
endAt
```

---

### 4.4 Trend

```text
GET /api/v1/dashboard/trend
```

용도:

- range 기반 keyword trend series 조회
- 단일 keyword 또는 복수 keyword 비교 지원

Query params:

| 이름 | 설명 |
| --- | --- |
| `keyword` | 기준 keyword |
| `keywords` | comma-separated keyword 목록 |
| `source` | source filter |
| `domain` | domain filter |
| `range` | range id |
| `compareLimit` | 비교 keyword 수, 1~5 |

---

### 4.5 Trend Window

```text
GET /api/v1/dashboard/trend-window
```

용도:

- 지정 시간 구간의 복수 keyword trend 조회
- custom window + bucket 기반 chart rendering 지원

Query params:

```text
keywords
source
domain
startAt
endAt
bucket
```

---

### 4.6 Spikes

```text
GET /api/v1/dashboard/spikes
```

용도:

- 급상승 keyword event 조회
- heatmap / event marker 표시용 데이터 제공

Query params:

```text
source
domain
range
limit
startAt
endAt
bucket
```

---

### 4.7 Related Keywords

```text
GET /api/v1/dashboard/related
```

용도:

- 특정 keyword와 같이 등장하는 related keyword 조회

Query params:

```text
keyword
source
domain
range
limit
startAt
endAt
```

---

### 4.8 Theme Distribution

```text
GET /api/v1/dashboard/theme-distribution
```

용도:

- 특정 keyword의 source/domain 기반 theme 분포 조회

Query params:

```text
keyword
source
range
startAt
endAt
```

---

### 4.9 Articles

```text
GET /api/v1/dashboard/articles
```

용도:

- 기간, source, domain, keyword 기준 관련 기사 조회

Query params:

```text
source
domain
range
keyword
limit
sort
startAt
endAt
```

---

### 4.10 System Status

```text
GET /api/v1/dashboard/system
```

용도:

- 시스템 상태 요약 조회
- Kafka, DB, 수집 상태 등 운영 UI 표시용

---

## 5. Dictionary API

### 5.1 Dictionary Overview

```text
GET /api/v1/dictionary
```

용도:

- dictionary dashboard overview 조회
- compound noun, stopword, candidate 현황 조회

---

### 5.2 Dictionary History

```text
GET /api/v1/dictionary/history
```

Query params:

```text
limit: 1~500, default 100
```

용도:

- dictionary audit log 조회

---

### 5.3 Compound Noun 목록

```text
GET /api/v1/dictionary/compound-nouns
```

Query params:

```text
page
limit
q
domain
```

용도:

- 승인된 복합명사 사전 목록 조회

---

### 5.4 Compound Noun 등록

```text
POST /api/v1/dictionary/compound-nouns
```

Body:

```json
{
  "word": "생성형AI",
  "domain": "ai_tech",
  "source": "manual",
  "actor": "dashboard-admin"
}
```

용도:

- 수동 복합명사 등록
- 기본 source는 `manual`

---

### 5.5 Compound Noun domain 수정

```text
PATCH /api/v1/dictionary/compound-nouns/{item_id}/domain
```

Body:

```json
{
  "domain": "business",
  "actor": "dashboard-admin"
}
```

---

### 5.6 Compound Noun 삭제

```text
DELETE /api/v1/dictionary/compound-nouns/{item_id}
```

용도:

- 등록된 복합명사 삭제

---

### 5.7 Compound Candidate 목록

```text
GET /api/v1/dictionary/candidates
```

Query params:

```text
page
limit
q
status
domain
```

용도:

- 복합명사 후보 목록 조회
- 자동평가 컬럼 포함 대상
  - `auto_score`
  - `auto_evidence`
  - `auto_checked_at`
  - `auto_decision`

---

### 5.8 Compound Candidate 수동 승인

```text
POST /api/v1/dictionary/compound-candidates/{candidate_id}/approve
```

Body:

```json
{
  "reviewed_by": "dashboard-admin"
}
```

처리:

```text
compound_noun_candidates.status = approved
compound_noun_dict insert
```

---

### 5.9 Compound Candidate 수동 반려

```text
POST /api/v1/dictionary/compound-candidates/{candidate_id}/reject
```

Body:

```json
{
  "reviewed_by": "dashboard-admin"
}
```

처리:

```text
compound_noun_candidates.status = rejected
```

---

### 5.10 Stopword 목록

```text
GET /api/v1/dictionary/stopwords
```

Query params:

```text
page
limit
q
domain
```

---

### 5.11 Stopword 등록

```text
POST /api/v1/dictionary/stopwords
```

Body:

```json
{
  "word": "관련",
  "language": "ko",
  "domain": "all",
  "actor": "dashboard-admin"
}
```

---

### 5.12 Stopword domain 수정

```text
PATCH /api/v1/dictionary/stopwords/{item_id}/domain
```

---

### 5.13 Stopword 삭제

```text
DELETE /api/v1/dictionary/stopwords/{item_id}
```

---

### 5.14 Stopword Candidate 목록

```text
GET /api/v1/dictionary/stopword-candidates
```

Query params:

```text
page
limit
q
status
domain
```

---

### 5.15 Stopword Candidate 승인

```text
POST /api/v1/dictionary/stopword-candidates/{candidate_id}/approve
```

---

### 5.16 Stopword Candidate 반려

```text
POST /api/v1/dictionary/stopword-candidates/{candidate_id}/reject
```

---

## 6. Admin API

### 6.1 Query Keyword 목록

```text
GET /api/v1/admin/query-keywords
```

용도:

- 수집 query keyword 관리 화면 조회

---

### 6.2 Query Keyword 등록

```text
POST /api/v1/admin/query-keywords
```

Body:

```json
{
  "domain_id": "ai_tech",
  "query": "인공지능",
  "sort_order": 10,
  "is_active": true,
  "actor": "dashboard-admin"
}
```

---

### 6.3 Query Keyword 수정

```text
PATCH /api/v1/admin/query-keywords/{item_id}
```

---

### 6.4 Query Keyword 삭제

```text
DELETE /api/v1/admin/query-keywords/{item_id}
```

Query params:

```text
actor
```

---

### 6.5 Collection Metrics

```text
GET /api/v1/admin/collection-metrics
```

Query params:

```text
hours: 1~168, default 24
```

용도:

- 수집량, 중복, 실패 등 collection metrics 조회

---

### 6.6 Stopword Recommender 실행

```text
POST /api/v1/admin/run-stopword-recommender
```

용도:

- stopword candidate 추천 batch 수동 실행

---

## 7. Deprecated API

### 7.1 Compound Auto Approve 수동 실행

```text
POST /api/v1/admin/run-compound-auto-approve
```

상태:

```text
deprecated
```

기존 역할:

- API 호출로 `compound_auto_approver` 또는 자동승인 로직을 수동 실행

현재 정책:

- 복합명사 후보 자동평가/자동승인은 Airflow의 `compound_candidate_auto_review_dag`에서 수행한다.
- API를 통한 자동승인 수동 실행은 사용하지 않는다.
- 신규 구현 기준 자동 평가 근거는 `compound_auto_reviewer.py`의 `naver_webkr` evidence에 저장된다.

대체 경로:

```text
Airflow UI
→ compound_candidate_auto_review_dag
→ auto_review task 수동 실행
```

---

## 8. 외부 API 사용 현황

### 8.1 Naver News API

사용 위치:

```text
src/ingestion/api_client.py
src/ingestion/producer.py
```

용도:

- 뉴스 수집
- Kafka 발행 전 원천 기사 확보

---

### 8.2 Naver Web Search API

사용 위치:

```text
src/analytics/compound_auto_reviewer.py
```

Endpoint:

```text
https://openapi.naver.com/v1/search/webkr.json
```

용도:

- 복합명사 후보 자동평가 외부 근거 수집

판단 기준:

```text
items.title 또는 items.description에서 HTML 제거
→ 공백 제거
→ 후보 단어도 공백 제거
→ 후보 단어가 title/description에 포함되면 has_exact_compact_match = true
```

자동승인 조건:

```text
auto_score >= 85
AND doc_count >= 3
AND frequency >= 5
AND has_exact_compact_match = true
AND frequency_per_doc <= 8
```

---

## 9. Deprecated External API

### 9.1 Naver Encyc API

```text
https://openapi.naver.com/v1/search/encyc.json
```

상태:

```text
deprecated
```

기존 용도:

- 복합명사 후보 자동승인 근거 확인

현재 대체:

```text
Naver Web Search API /v1/search/webkr.json
```

---

### 9.2 Free Dictionary API

```text
https://freedictionaryapi.com/api/v1/entries/ko/{word}
```

상태:

```text
deprecated
```

기존 용도:

- 복합명사 후보 자동평가 근거 확인

현재 대체:

```text
Naver Web Search API /v1/search/webkr.json
```

---

## 10. 한 줄 정리

```text
FastAPI는 dashboard와 dictionary/admin UI를 위한 조회·관리 API를 제공하고,
복합명사 자동평가 실행은 API가 아니라 Airflow DAG에서 처리한다.
```
