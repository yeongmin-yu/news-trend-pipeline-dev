-- keyword_events is addressed by the natural event key below, not by id.
-- Dropping the unused surrogate primary key removes a large write-heavy index.
ALTER TABLE IF EXISTS keyword_events
    DROP CONSTRAINT IF EXISTS keyword_events_pkey;
