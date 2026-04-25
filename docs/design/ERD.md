# ERD

> 기준: [`src/storage/models.sql`](/C:/Project/news-trend-pipeline-v2/src/storage/models.sql)
>
> 이 문서는 현재 구현된 PostgreSQL 스키마를 기준으로 정리한다.  
> 실제 물리 FK는 많지 않으므로, 아래 다이어그램은 `물리 관계 + 운영상 논리 관계`를 함께 표현한다.

## 1. 엔터티 관계

```mermaid
erDiagram
    domain_catalog ||--o{ query_keywords : "FK(domain_id)"

    query_keywords ||--o{ query_keyword_audit_logs : "audit target"
    query_keywords ||--o{ collection_metrics : "collects by provider/domain/query"

    domain_catalog ||--o{ news_raw : "classified by domain"
    news_raw ||--o{ keywords : "tokenized from article"
    news_raw ||--o{ collection_metrics : "collection result source"

    keywords ||--o{ keyword_trends : "aggregated into window"
    keywords ||--o{ keyword_relations : "co-occurrence source"
    keyword_trends ||--o{ keyword_events : "event detection source"

    compound_noun_candidates ||--o| compound_noun_dict : "approved to dictionary"
    stopword_candidates ||--o| stopword_dict : "approved to dictionary"

    compound_noun_dict ||--|| dictionary_versions : "version bumped by trigger"
    stopword_dict ||--|| dictionary_versions : "version bumped by trigger"

    compound_noun_dict ||--o{ dictionary_audit_logs : "audit target"
    compound_noun_candidates ||--o{ dictionary_audit_logs : "audit target"
    stopword_dict ||--o{ dictionary_audit_logs : "audit target"
    stopword_candidates ||--o{ dictionary_audit_logs : "audit target"

    stg_news_raw ||--|| news_raw : "upsert"
    stg_keywords ||--|| keywords : "upsert"
    stg_keyword_trends ||--|| keyword_trends : "upsert"
    stg_keyword_relations ||--|| keyword_relations : "upsert"

    domain_catalog {
        varchar domain_id PK
        varchar label
        integer sort_order
        boolean is_active
        timestamptz created_at
    }

    query_keywords {
        serial id PK
        varchar provider
        varchar domain_id FK
        varchar query
        integer sort_order
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    query_keyword_audit_logs {
        bigserial id PK
        integer query_keyword_id
        varchar action
        jsonb before_json
        jsonb after_json
        varchar actor
        timestamptz acted_at
    }

    news_raw {
        bigserial id PK
        varchar provider
        varchar domain
        varchar query
        varchar source
        text title
        text summary
        text url
        timestamptz published_at
        timestamptz ingested_at
    }

    keywords {
        bigserial id PK
        varchar article_provider
        varchar article_domain
        text article_url
        varchar keyword
        integer keyword_count
        timestamptz processed_at
    }

    keyword_trends {
        bigserial id PK
        varchar provider
        varchar domain
        timestamptz window_start
        timestamptz window_end
        varchar keyword
        integer keyword_count
        timestamptz processed_at
    }

    keyword_relations {
        bigserial id PK
        varchar provider
        varchar domain
        timestamptz window_start
        timestamptz window_end
        varchar keyword_a
        varchar keyword_b
        integer cooccurrence_count
        timestamptz processed_at
    }

    collection_metrics {
        bigserial id PK
        varchar provider
        varchar domain
        varchar query
        timestamptz window_start
        timestamptz window_end
        integer request_count
        integer success_count
        integer article_count
        integer duplicate_count
        integer publish_count
        integer error_count
        timestamptz created_at
    }

    keyword_events {
        bigserial id PK
        varchar provider
        varchar domain
        varchar keyword
        timestamptz event_time
        timestamptz window_start
        timestamptz window_end
        integer current_mentions
        integer prev_mentions
        double growth
        integer event_score
        boolean is_spike
        timestamptz detected_at
    }

    compound_noun_dict {
        serial id PK
        varchar word
        varchar domain
        varchar source
        timestamptz created_at
    }

    compound_noun_candidates {
        serial id PK
        varchar word
        varchar domain
        integer frequency
        integer doc_count
        timestamptz first_seen_at
        timestamptz last_seen_at
        varchar status
        timestamptz reviewed_at
        varchar reviewed_by
    }

    stopword_dict {
        serial id PK
        varchar word
        varchar domain
        varchar language
        timestamptz created_at
    }

    stopword_candidates {
        serial id PK
        varchar word
        varchar domain
        varchar language
        float score
        float domain_breadth
        float repetition_rate
        float trend_stability
        float cooccurrence_breadth
        boolean short_word
        integer frequency
        varchar status
        timestamptz first_seen_at
        timestamptz last_seen_at
        timestamptz reviewed_at
        varchar reviewed_by
    }

    dictionary_audit_logs {
        bigserial id PK
        varchar entity_type
        integer entity_id
        varchar action
        jsonb before_json
        jsonb after_json
        varchar actor
        timestamptz acted_at
    }

    dictionary_versions {
        varchar dict_name PK
        bigint version
        timestamptz updated_at
    }

    stg_news_raw {
        varchar provider
        varchar domain
        varchar query
        varchar source
        text title
        text summary
        text url
        timestamptz published_at
        timestamptz ingested_at
    }

    stg_keywords {
        varchar article_provider
        varchar article_domain
        text article_url
        varchar keyword
        integer keyword_count
        timestamptz processed_at
    }

    stg_keyword_trends {
        varchar provider
        varchar domain
        timestamptz window_start
        timestamptz window_end
        varchar keyword
        integer keyword_count
        timestamptz processed_at
    }

    stg_keyword_relations {
        varchar provider
        varchar domain
        timestamptz window_start
        timestamptz window_end
        varchar keyword_a
        varchar keyword_b
        integer cooccurrence_count
        timestamptz processed_at
    }
```

## 2. 핵심 구조 요약

- `domain_catalog`와 `query_keywords`가 수집 정책의 기준 테이블이다.
- `news_raw`는 원문 기사 저장소이며, `provider + domain + url` 기준으로 중복을 제어한다.
- `keywords`는 기사 단위 키워드, `keyword_trends`는 시간 윈도우 집계, `keyword_relations`는 동시 출현 집계다.
- `keyword_events`는 `keyword_trends`를 입력으로 한 이벤트 탐지 결과 저장소다.
- `collection_metrics`는 수집 성공/중복/발행 건수 등 운영 메트릭을 저장한다.
- 사전 계층은 `compound_noun_dict`, `compound_noun_candidates`, `stopword_dict`, `stopword_candidates`로 분리되어 있다.
- `dictionary_versions`는 복합명사 사전과 불용어 사전 변경 시 trigger로 버전을 증가시킨다.
- `query_keyword_audit_logs`, `dictionary_audit_logs`는 관리자 변경 이력을 남긴다.
- `stg_*` 테이블은 Spark/배치 적재 후 최종 테이블로 upsert하는 staging 계층이다.

## 3. 구현 기준으로 확인한 주의사항

- 실제 FK는 `query_keywords.domain_id -> domain_catalog.domain_id`만 선언되어 있다.
- `news_raw -> keywords`, `keyword_trends -> keyword_events`, 후보 사전 -> 확정 사전 관계는 코드와 unique key 기준의 논리 관계다.
- `dictionary_audit_logs`는 다형성 로그 테이블이라 특정 사전 테이블에 직접 FK를 두지 않는다.
- `dictionary_versions`도 사전 테이블과 FK로 묶이지 않고, trigger 함수 `bump_dictionary_version()`으로 동기화된다.

