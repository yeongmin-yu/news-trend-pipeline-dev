# STEP4 FastAPI 구현

## 1. 목적

대시보드 프론트엔드가 요구하는 데이터를 FastAPI에서 일관된 JSON 계약으로 제공한다. 이번 단계에서는 도메인 확장과 용어 사전 API 복구를 우선하며, DB 스키마가 아직 없어서 완전 구현이 어려운 항목은 뼈대와 계획만 남긴다.

## 2. 현재 구현 범위

### 2.1 메타/필터

- `GET /health`
- `GET /api/v1/meta/filters`
  - source 목록
  - domain 목록
  - range 목록

### 2.2 대시보드 API

- `GET /api/v1/dashboard/kpis`
- `GET /api/v1/dashboard/keywords`
- `GET /api/v1/dashboard/trend`
- `GET /api/v1/dashboard/spikes`
- `GET /api/v1/dashboard/related`
- `GET /api/v1/dashboard/articles`
- `GET /api/v1/dashboard/system`

공통 query param

- `source`
- `domain`
- `range`

### 2.3 용어 사전 API

- `GET /api/v1/dictionary`
- `POST /api/v1/dictionary/compound-nouns`
- `DELETE /api/v1/dictionary/compound-nouns/{id}`
- `POST /api/v1/dictionary/compound-candidates/{id}/approve`
- `POST /api/v1/dictionary/compound-candidates/{id}/reject`
- `POST /api/v1/dictionary/stopwords`
- `DELETE /api/v1/dictionary/stopwords/{id}`

## 3. 현재 DB 기반 구현 상세

### 3.1 사용 테이블

- `domain_catalog`
- `query_keywords`
- `news_raw`
- `keywords`
- `keyword_trends`
- `keyword_relations`
- `compound_noun_dict`
- `compound_noun_candidates`
- `stopword_dict`
- `dictionary_versions`

### 3.2 API별 데이터 소스

#### `dashboard/kpis`

- `news_raw`
- `keyword_trends`

#### `dashboard/keywords`

- `keyword_trends`
- `keywords`
- `news_raw`

#### `dashboard/trend`

- `keyword_trends`

#### `dashboard/spikes`

- `keyword_trends`

#### `dashboard/related`

- `keyword_relations`

#### `dashboard/articles`

- `news_raw`
- `keywords`

#### `dashboard/system`

- DB ping
- Kafka TCP probe
- Spark/airflow HTTP probe

#### `dictionary`

- 사전 3개 테이블 + version 메타

## 4. 프론트 요구 대비 API 설계

### 4.1 반드시 필요한 API

| 화면 기능 | 메서드 | 경로 | 상태 |
|---|---|---|---|
| 필터 로딩 | GET | `/api/v1/meta/filters` | 구현 |
| KPI 카드 | GET | `/api/v1/dashboard/kpis` | 구현 |
| 상위 키워드 | GET | `/api/v1/dashboard/keywords` | 구현 |
| 키워드 트렌드 | GET | `/api/v1/dashboard/trend` | 구현 |
| 급상승 히트맵 | GET | `/api/v1/dashboard/spikes` | 구현 |
| 연관 키워드 | GET | `/api/v1/dashboard/related` | 구현 |
| 기사 목록 | GET | `/api/v1/dashboard/articles` | 구현 |
| 시스템 상태 | GET | `/api/v1/dashboard/system` | 구현 |
| 용어 사전 조회 | GET | `/api/v1/dictionary` | 구현 |
| 용어 사전 수정 | POST/DELETE | `/api/v1/dictionary/*` | 구현 |

### 4.2 추가로 필요한 API

| 기능 | 메서드 | 경로 제안 | 상태 |
|---|---|---|---|
| query keyword 목록 조회 | GET | `/api/v1/admin/query-keywords` | 설계만 |
| query keyword 생성/비활성화 | POST/PATCH | `/api/v1/admin/query-keywords` | 설계만 |
| 도메인별 수집량 모니터링 | GET | `/api/v1/admin/collection-metrics` | 설계만 |
| 기사 중복 클러스터 | GET | `/api/v1/dashboard/article-clusters` | 설계만 |
| 관련도 기반 기사 정렬 점수 | GET | `/api/v1/dashboard/articles/relevance-debug` | 설계만 |
| 용어 사전 변경 이력 | GET | `/api/v1/dictionary/history` | 설계만 |

## 5. DB 부재로 미구현인 API 뼈대

### 5.1 Query Keyword 관리

#### 목적

- 도메인별 네이버 API 쿼리 키워드를 운영 중 수정
- 비활성화/우선순위 조정

#### 필요한 테이블

- 현재 `query_keywords`는 존재
- 추가 권장
  - `query_keyword_audit_logs`
  - `updated_by`
  - `change_reason`

#### 스켈레톤

- `GET /api/v1/admin/query-keywords`
- `POST /api/v1/admin/query-keywords`
- `PATCH /api/v1/admin/query-keywords/{id}`

### 5.2 기사 중복 클러스터

#### 목적

- 우측 기사 패널의 `duplicates` 값을 실제 데이터로 채움

#### 필요한 테이블

- `article_clusters`
  - `cluster_id`
  - `provider`
  - `domain`
  - `canonical_url`
  - `member_url`
  - `similarity_score`

#### 스켈레톤

- `GET /api/v1/dashboard/article-clusters?keyword=...`

### 5.3 관련도 정렬

#### 목적

- 기사 목록의 `relevance` 정렬을 단순 fallback이 아닌 계산식 기반으로 제공

#### 필요한 테이블 또는 materialized view

- `article_keyword_scores`
  - keyword TF-IDF
  - title match boost
  - recency decay

#### 스켈레톤

- `GET /api/v1/dashboard/articles?sort=relevance`
  - 현재는 완전한 점수 모델이 없어 최신순 fallback 성격

### 5.4 용어 사전 이력

#### 목적

- 누가 어떤 단어를 추가/삭제/승인했는지 추적

#### 필요한 테이블

- `dictionary_audit_logs`
  - `entity_type`
  - `entity_id`
  - `action`
  - `before_json`
  - `after_json`
  - `actor`
  - `acted_at`

#### 스켈레톤

- `GET /api/v1/dictionary/history`

## 6. 구현 파일 맵

- `src/api/app.py`
  - 라우트 정의
- `src/api/service.py`
  - SQL 기반 서비스 로직
- `src/api/schemas.py`
  - 요청 body schema
- `src/storage/db.py`
  - DB 연결, seed, helper
- `src/storage/models.sql`
  - schema 정의

## 7. 구현 원칙

- 프론트가 이미 사용하는 계약은 최대한 유지
- 디자인 변경 없이 파라미터와 데이터만 확장
- `domain`은 모든 dashboard API의 1급 필터로 취급
- DB 없는 기능은 임시 mock으로 숨기지 않고 문서에 명시
