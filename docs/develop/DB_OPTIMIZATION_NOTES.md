# DB Optimization Notes

Date: 2026-05-08 KST

## Summary

The current pipeline writes most heavily to staging tables and keyword analytics tables. The first optimization pass reduced unnecessary write amplification from indexes that were either transient or not used by the application path.

Applied migrations:

- `V3__make_staging_tables_unlogged.sql`
  - Converted `stg_news_raw`, `stg_keywords`, `stg_keyword_trends`, `stg_keyword_relations` to `UNLOGGED`.
- `V4__drop_keyword_events_pkey.sql`
  - Dropped `keyword_events_pkey`.
- `V5__drop_unused_analytics_pkeys.sql`
  - Drops `keywords_pkey`, `keyword_trends_pkey`, `keyword_relations_pkey`.

## Why These Changes Were Made

The application does not address analytics rows by the surrogate `id` primary keys. Inserts and conflict handling use natural unique keys instead.

Natural unique indexes that remain active:

- `idx_keywords_unique(article_provider, article_domain, article_url, keyword)`
- `idx_keyword_trends_unique(provider, domain, window_start, window_end, keyword)`
- `idx_keyword_relations_unique(provider, domain, window_start, window_end, keyword_a, keyword_b)`

The removed primary key indexes were write-heavy because every insert had to maintain them, but they did not help the observed application query path.

## Observed Before Optimization

Representative sizes before removing the unused analytics PK indexes:

| Object | Approx Size | Note |
| --- | ---: | --- |
| `keywords` total | 1588 MB | table 448 MB, index/toast 1140 MB |
| `idx_keywords_unique` | 530 MB | required for keyword upsert |
| `idx_keywords_keyword_article` | 449 MB | lookup index, still under review |
| `keywords_pkey` | 85 MB | removed by V5 |
| `idx_keywords_domain_keyword` | 40 MB | scan count was 0, review separately |
| `keyword_trends_p20260501_pkey` | 74 MB | removed through parent PK drop |
| `keyword_relations_p20260501_pkey` | 55 MB | removed through parent PK drop |
| `keyword_events_pkey` | 411 MB | removed by V4 |

After V4, `keyword_events` retained only the unique and lookup indexes:

- `idx_keyword_events_unique`: about 54 MB
- `idx_keyword_events_lookup`: about 16 MB

## Operational Notes

- Apply with Flyway: `docker compose run --rm flyway`
- A normal application restart is not required for these DDL changes.
- The DDL can briefly lock the target tables while constraints are dropped.
- Dropping these primary keys does not remove the `id` columns or their sequences.
- Foreign key checks found no dependent foreign keys referencing these primary keys at the time of analysis.

## Remaining Candidates

- Review `idx_keywords_domain_keyword`.
  - It showed `idx_scan = 0` during the sampled period.
  - Drop only after confirming no dashboard or ad-hoc query depends on it.
- Review overlap between `idx_keywords_keyword_article` and `idx_keywords_unique`.
  - It is large, but may still be useful for keyword-first lookup paths.
- Run `VACUUM ANALYZE keyword_events`.
  - `keyword_events` had a high dead tuple ratio after delete/insert style replacement.
- Consider improving `keyword_events` replacement logic.
  - Avoiding unnecessary delete/insert cycles is likely more valuable than index-only tuning.
- Consider `REINDEX CONCURRENTLY` for remaining bloated indexes only after query paths are stable.
