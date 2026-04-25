# DATABASE 설계

> 기준 파일: `src/storage/models.sql`
>
> 개발 완료 이후 GitHub 이력과 최신 스키마를 기준으로 정리한 refactor DB 문서이다. 기존 `docs/design` 문서는 수정하지 않고, 현재 문서는 `docs/design_refactor` 기준 문서로 관리한다.

## 1. 최근 스키마 변경 추적 요약

최근 이력 기준으로 DB 설계에서 특히 달라진 부분은 다음과 같다.

| 변경 | 의미 |
| --- | --- |
| `provider + domain` 기준 확대 | 수집/저장/분석/조회가 도메인 단위로 분리됨 |
| staging table 도입 | Spark `collect()` 대신 JDBC append 후 DB 내부 upsert 수행 |
| 사전 테이블 domain-aware 전환 | 복합명사/불용어를 전역(`all`) 또는 도메인별로 관리 가능 |
| 후보 상태값 변경 | 후보 상태가 `pending`이 아니라 `needs_review / approved / rejected` 기준 |
| `stopword_candidates` 추가 | 불용어도 점수 기반 후보 추천 및 관리자 검토 흐름으로 확장 |
| audit log 강화 | 검색어/사전 변경 이력 추적 |
| `dictionary_versions` 유지 | 사전 변경 감지와 Spark 캐시 갱신 기준 |

## 2. 전체 테이블 분류

| 분류 | 테이블 |
| --- | --- |
| 도메인/검색어 | `domain_catalog`, `query_keywords`, `query_keyword_audit_logs` |
| 원문/키워드 | `news_raw`, `keywords` |
| 집계 | `keyword_trends`, `keyword_relations` |
| 사전 | `compound_noun_dict`, `compound_noun_candidates`, `stopword_dict`, `stopword_candidates`, `dictionary_versions`, `dictionary_audit_logs` |
| 수집/이벤트 | `collection_metrics`, `keyword_events` |
| staging | `stg_news_raw`, `stg_keywords`, `stg_keyword_trends`, `stg_keyword_relations` |

## 3. 도메인/검색어 관리

### 3-1. domain_catalog

도메인 기준 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `domain_id` | 도메인 식별자. PK |
| `label` | 화면 표시 이름 |
| `sort_order` | 정렬 순서 |
| `is_active` | 사용 여부 |
| `created_at` | 생성 시각 |

### 3-2. query_keywords

도메인별 수집 검색어 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 수집원. 기본값 `naver` |
| `domain_id` | `domain_catalog.domain_id` 참조 |
| `query` | 검색어 |
| `sort_order` | 도메인 내 정렬 순서 |
| `is_active` | 사용 여부 |

Unique 기준:

```text
(provider, domain_id, query)
```

### 3-3. query_keyword_audit_logs

검색어 추가/수정/삭제 이력을 저장한다.

```text
query_keyword_id
action
before_json
after_json
actor
acted_at
```

## 4. 원문 및 키워드 저장

### 4-1. news_raw

기사 원문 저장 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 수집원 |
| `domain` | 도메인 |
| `query` | 수집 검색어 |
| `source` | 기사 출처 |
| `title` | 제목 |
| `summary` | 요약 |
| `url` | 기사 URL |
| `published_at` | 기사 발행 시각 |
| `ingested_at` | 수집 시각 |

Unique 기준:

```text
(provider, domain, url)
```

중요한 변경:

```text
description/content/author 중심 구조가 아니라 summary 중심 구조
```

### 4-2. keywords

기사별 키워드 빈도 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `article_provider` | 기사 provider |
| `article_domain` | 기사 domain |
| `article_url` | 기사 URL |
| `keyword` | 키워드 |
| `keyword_count` | 기사 내 빈도 |
| `processed_at` | 처리 시각 |

Unique 기준:

```text
(article_provider, article_domain, article_url, keyword)
```

## 5. 집계 테이블

### 5-1. keyword_trends

시간 윈도우별 키워드 집계 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 수집원 |
| `domain` | 도메인 |
| `window_start` | 집계 시작 |
| `window_end` | 집계 종료 |
| `keyword` | 키워드 |
| `keyword_count` | 빈도 |
| `processed_at` | 처리 시각 |

Unique 기준:

```text
(provider, domain, window_start, window_end, keyword)
```

### 5-2. keyword_relations

같은 기사 내 대표 키워드 동시 출현 관계를 window 단위로 저장한다.

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 수집원 |
| `domain` | 도메인 |
| `window_start` | 집계 시작 |
| `window_end` | 집계 종료 |
| `keyword_a` | 키워드 A |
| `keyword_b` | 키워드 B |
| `cooccurrence_count` | 동시 출현 수 |
| `processed_at` | 처리 시각 |

Unique 기준:

```text
(provider, domain, window_start, window_end, keyword_a, keyword_b)
```

## 6. 사전 테이블

### 6-1. compound_noun_dict

승인된 복합명사 사전이다.

| 컬럼 | 설명 |
| --- | --- |
| `word` | 복합명사 |
| `domain` | 적용 도메인. 기본값 `all` |
| `source` | `manual` 또는 자동 승인 출처 |
| `created_at` | 생성 시각 |

Unique 기준:

```text
(word, domain)
```

의미:

```text
all: 전역 복합명사
domain_id: 특정 도메인 전용 복합명사
```

### 6-2. compound_noun_candidates

자동 추출된 복합명사 후보 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `word` | 후보 단어 |
| `domain` | 후보가 발견된 도메인. 기본값 `all` |
| `frequency` | 총 출현 횟수 |
| `doc_count` | 출현 기사 수 |
| `status` | `needs_review`, `approved`, `rejected` |
| `reviewed_at` | 검토 시각 |
| `reviewed_by` | 검토자 |

Unique 기준:

```text
(word, domain)
```

### 6-3. stopword_dict

승인된 불용어 사전이다.

| 컬럼 | 설명 |
| --- | --- |
| `word` | 불용어 |
| `domain` | 적용 도메인. 기본값 `all` |
| `language` | 언어. 기본값 `ko` |
| `created_at` | 생성 시각 |

Unique 기준:

```text
(word, domain, language)
```

### 6-4. stopword_candidates

불용어 후보 추천 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `word` | 후보 단어 |
| `domain` | 후보 도메인. 기본값 `all` |
| `language` | 언어 |
| `score` | 최종 후보 점수 |
| `domain_breadth` | 여러 도메인에 넓게 등장하는 정도 |
| `repetition_rate` | 반복 출현 정도 |
| `trend_stability` | 트렌드 변화가 낮은 정도 |
| `cooccurrence_breadth` | 다양한 단어와 넓게 같이 등장하는 정도 |
| `short_word` | 짧은 단어 여부 |
| `frequency` | 출현 빈도 |
| `status` | `needs_review`, `approved`, `rejected` |
| `reviewed_at` | 검토 시각 |
| `reviewed_by` | 검토자 |

Unique 기준:

```text
(word, domain, language)
```

불용어 후보가 추가되면서 불용어도 복합명사와 같은 방식으로 관리 가능해졌다.

```text
후보 추천 -> 관리자 검토 -> stopword_dict 등록
```

### 6-5. dictionary_versions

사전 변경 감지용 버전 테이블이다.

현재 version bump trigger 대상:

```text
compound_noun_dict
stopword_dict
```

즉, 승인 사전 변경 시 version이 증가하고 Spark 전처리 캐시 갱신 기준으로 사용할 수 있다.

### 6-6. dictionary_audit_logs

사전 관련 변경 이력을 저장한다.

```text
entity_type
entity_id
action
before_json
after_json
actor
acted_at
```

## 7. 수집 품질 및 이벤트

### 7-1. collection_metrics

수집 품질 지표 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 수집원 |
| `domain` | 도메인 |
| `query` | 검색어 |
| `window_start` | 측정 시작 |
| `window_end` | 측정 종료 |
| `request_count` | 요청 수 |
| `success_count` | 성공 수 |
| `article_count` | 수집 기사 수 |
| `duplicate_count` | 중복 수 |
| `publish_count` | Kafka publish 수 |
| `error_count` | 오류 수 |

### 7-2. keyword_events

급상승 이벤트 테이블이다.

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 수집원 |
| `domain` | 도메인 |
| `keyword` | 키워드 |
| `event_time` | 이벤트 기준 시각 |
| `window_start` | 현재 윈도우 시작 |
| `window_end` | 현재 윈도우 종료 |
| `current_mentions` | 현재 언급량 |
| `prev_mentions` | 이전 언급량 |
| `growth` | 증가율 |
| `event_score` | 이벤트 점수 |
| `is_spike` | spike 여부 |
| `detected_at` | 탐지 시각 |

Unique 기준:

```text
(provider, domain, keyword, window_start)
```

## 8. Staging 테이블

Spark는 최종 테이블에 직접 upsert하지 않고 staging 테이블에 append한다.

```text
stg_news_raw
stg_keywords
stg_keyword_trends
stg_keyword_relations
```

이후 PostgreSQL 내부에서 dedup/upsert 후 staging을 truncate한다.

```text
Spark JDBC append
-> PostgreSQL INSERT ... ON CONFLICT
-> TRUNCATE staging
```

## 9. 주요 인덱스/Unique 기준

| 테이블 | 기준 |
| --- | --- |
| `news_raw` | unique `(provider, domain, url)` |
| `keywords` | unique `(article_provider, article_domain, article_url, keyword)` |
| `keyword_trends` | unique `(provider, domain, window_start, window_end, keyword)` |
| `keyword_relations` | unique `(provider, domain, window_start, window_end, keyword_a, keyword_b)` |
| `query_keywords` | unique `(provider, domain_id, query)` |
| `compound_noun_dict` | unique `(word, domain)` |
| `compound_noun_candidates` | unique `(word, domain)` |
| `stopword_dict` | unique `(word, domain, language)` |
| `stopword_candidates` | unique `(word, domain, language)` |
| `keyword_events` | unique `(provider, domain, keyword, window_start)` |

## 10. 마이그레이션 호환성

`models.sql`은 기존 배포와의 호환을 위해 일부 idempotent migration을 포함한다.

예:

```text
ALTER TABLE ... ADD COLUMN IF NOT EXISTS domain
DROP old single-column unique constraints
ADD new domain-aware unique constraints
```

이 설계 덕분에 기존 단일 사전 구조에서 도메인별 사전 구조로 점진 전환할 수 있다.

## 11. 설계 핵심 정리

```text
1. 수집/분석의 기준 축은 provider + domain
2. Spark write는 staging table을 거친다
3. 복합명사/불용어는 전역(all) + 도메인별 사전으로 확장 가능
4. 후보 테이블은 needs_review -> approved/rejected 검토 흐름을 가진다
5. collection_metrics와 keyword_events로 운영/분석 품질을 추적한다
```
