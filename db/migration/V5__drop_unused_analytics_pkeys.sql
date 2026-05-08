-- Analytics tables are written and queried through natural unique indexes.
-- These id-based primary keys were not used by the application path and added
-- large write-heavy indexes on hot tables.
ALTER TABLE IF EXISTS keywords
    DROP CONSTRAINT IF EXISTS keywords_pkey;

ALTER TABLE IF EXISTS keyword_trends
    DROP CONSTRAINT IF EXISTS keyword_trends_pkey;

ALTER TABLE IF EXISTS keyword_relations
    DROP CONSTRAINT IF EXISTS keyword_relations_pkey;
