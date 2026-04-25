# ERD (Entity Relationship Diagram)

> `models.sql` 기준 현재 데이터베이스 구조

```mermaid
erDiagram

    domain_catalog ||--o{ query_keywords : has

    domain_catalog ||--o{ news_raw : categorizes
    domain_catalog ||--o{ keyword_trends : categorizes
    domain_catalog ||--o{ keyword_relations : categorizes
    domain_catalog ||--o{ keyword_events : categorizes
    domain_catalog ||--o{ collection_metrics : categorizes

    news_raw ||--o{ keywords : generates

    keyword_trends ||--o{ keyword_events : derives

    compound_noun_dict ||--o{ dictionary_versions : versioned
    stopword_dict ||--o{ dictionary_versions : versioned

    compound_noun_candidates ||--o{ compound_noun_dict : approved_to

    query_keywords ||--o{ query_keyword_audit_logs : tracked
    compound_noun_dict ||--o{ dictionary_audit_logs : tracked
    stopword_dict ||--o{ dictionary_audit_logs : tracked

    news_raw {
        string provider
        string domain
        string url
    }

    keywords {
        string article_provider
        string article_domain
        string article_url
        string keyword
    }

    keyword_trends {
        string provider
        string domain
        datetime window_start
        string keyword
    }

    keyword_relations {
        string provider
        string domain
        string keyword_a
        string keyword_b
    }

    keyword_events {
        string provider
        string domain
        string keyword
    }

    query_keywords {
        string provider
        string domain_id
        string query
    }

    compound_noun_dict {
        string word
    }

    compound_noun_candidates {
        string word
        string status
    }

    stopword_dict {
        string word
    }

```

## 핵심 관계 요약

- `domain_catalog`은 모든 분석 테이블의 기준 축이다
- `news_raw` → `keywords` → `keyword_trends` → `keyword_events` 흐름
- `compound_noun_candidates` → 승인 → `compound_noun_dict`
- 사전 변경은 `dictionary_versions`로 관리

## 설계 핵심

```text
이 시스템은
도메인 기반 분석 + 사전 기반 NLP + 스트리밍 집계 구조로 설계됨
```
