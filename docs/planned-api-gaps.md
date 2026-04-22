# Planned API Gaps

This document lists frontend-driven API needs that are not implemented yet because the current database schema does not provide the required persistence model.

## Not Implemented Yet

### Domain taxonomy and domain-scoped analytics
- Frontend need: domain filters beyond `ai_tech` and domain-specific counts/widgets.
- Missing schema: article-to-domain mapping table or a normalized domain dimension on `news_raw` / `keyword_trends`.
- Suggested tables:
  - `domains (id, code, name, created_at)`
  - `article_domains (article_provider, article_url, domain_id, score, assigned_at)`

### Dictionary audit history
- Frontend need: history tab showing who changed what, when it was applied, and outcome.
- Missing schema: immutable audit log table for dictionary operations.
- Suggested table:
  - `dictionary_change_log (id, dictionary_name, action, target_word, payload_json, operator, status, applied_at, created_at)`

### Compound noun metadata used by the original mock UI
- Frontend need: `components`, `domain`, `active/disabled/pending` state for approved dictionary rows.
- Current schema only stores `word`, `source`, and `created_at` in `compound_noun_dict`.
- Suggested schema change:
  - add `components`, `domain_code`, `status`, `updated_at`, `updated_by` to `compound_noun_dict`

### Stopword metadata used by the original mock UI
- Frontend need: `domain`, `reason`, `status`, `added_by`.
- Current schema only stores `word`, `language`, and `created_at` in `stopword_dict`.
- Suggested schema change:
  - add `domain_code`, `reason`, `status`, `added_by`, `updated_at`

### Duplicate article clustering
- Frontend need: duplicate count / cluster insights on article rows.
- Missing schema: deduplication result table or article cluster mapping.
- Suggested tables:
  - `article_clusters (id, cluster_key, created_at)`
  - `article_cluster_members (cluster_id, article_provider, article_url, similarity_score)`

### Relevance scoring for article sort
- Frontend currently supports a simple keyword-match fallback.
- Missing schema: per-article ranking or semantic relevance score table.
- Suggested table:
  - `article_rankings (article_provider, article_url, keyword, relevance_score, computed_at)`

## Implemented With Current Schema

- KPI summary from `news_raw` and `keyword_trends`
- top keywords from `keyword_trends`
- trend series from `keyword_trends`
- related keywords from `keyword_relations`
- article list from `news_raw` + `keywords`
- system health probes
- compound noun CRUD
- compound candidate approve / reject
- stopword CRUD
