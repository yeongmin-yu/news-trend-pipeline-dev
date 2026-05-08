-- Staging tables are transient per-batch buffers. They are truncated after each
-- upsert, so avoiding WAL for these tables reduces Spark JDBC write overhead.
ALTER TABLE IF EXISTS stg_news_raw SET UNLOGGED;
ALTER TABLE IF EXISTS stg_keywords SET UNLOGGED;
ALTER TABLE IF EXISTS stg_keyword_trends SET UNLOGGED;
ALTER TABLE IF EXISTS stg_keyword_relations SET UNLOGGED;
