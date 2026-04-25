CREATE TABLE IF NOT EXISTS domain_catalog (
    domain_id   VARCHAR(50) PRIMARY KEY,
    label       VARCHAR(100) NOT NULL,
    sort_order  INTEGER NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS query_keywords (
    id          SERIAL PRIMARY KEY,
    provider    VARCHAR(50) NOT NULL DEFAULT 'naver',
    domain_id   VARCHAR(50) NOT NULL REFERENCES domain_catalog(domain_id),
    query       VARCHAR(100) NOT NULL,
    sort_order  INTEGER NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_query_keywords_provider_domain_query UNIQUE (provider, domain_id, query)
);

CREATE INDEX IF NOT EXISTS idx_query_keywords_active
    ON query_keywords(provider, domain_id, is_active, sort_order);

CREATE TABLE IF NOT EXISTS query_keyword_audit_logs (
    id               BIGSERIAL PRIMARY KEY,
    query_keyword_id INTEGER,
    action           VARCHAR(50) NOT NULL,
    before_json      JSONB,
    after_json       JSONB,
    actor            VARCHAR(100) NOT NULL DEFAULT 'system',
    acted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_keyword_audit_logs_query_keyword
    ON query_keyword_audit_logs(query_keyword_id, acted_at DESC);

CREATE TABLE IF NOT EXISTS news_raw (
    id           BIGSERIAL PRIMARY KEY,
    provider     VARCHAR(50) NOT NULL DEFAULT 'naver',
    domain       VARCHAR(50) NOT NULL DEFAULT 'ai_tech',
    query        VARCHAR(100),
    source       VARCHAR(255),
    title        TEXT NOT NULL,
    summary      TEXT,
    url          TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    ingested_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE news_raw DROP CONSTRAINT IF EXISTS news_raw_url_key;
DROP INDEX IF EXISTS idx_news_raw_provider_url;
DROP INDEX IF EXISTS idx_keyword_trends_unique;
DROP INDEX IF EXISTS idx_keyword_relations_unique;
DROP INDEX IF EXISTS idx_keywords_unique;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'ai_tech';
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS query VARCHAR(100);
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS summary TEXT;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'news_raw' AND column_name = 'description'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'news_raw' AND column_name = 'summary'
    ) THEN
        EXECUTE 'ALTER TABLE news_raw RENAME COLUMN description TO summary';
    END IF;
END $$;

ALTER TABLE news_raw DROP COLUMN IF EXISTS author;
ALTER TABLE news_raw DROP COLUMN IF EXISTS content;

CREATE TABLE IF NOT EXISTS keywords (
    id                BIGSERIAL PRIMARY KEY,
    article_provider  VARCHAR(50) NOT NULL DEFAULT 'naver',
    article_domain    VARCHAR(50) NOT NULL DEFAULT 'ai_tech',
    article_url       TEXT NOT NULL,
    keyword           VARCHAR(255) NOT NULL,
    keyword_count     INTEGER NOT NULL DEFAULT 1,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE keywords ADD COLUMN IF NOT EXISTS article_domain VARCHAR(50) NOT NULL DEFAULT 'ai_tech';

CREATE TABLE IF NOT EXISTS keyword_trends (
    id            BIGSERIAL PRIMARY KEY,
    provider      VARCHAR(50) NOT NULL DEFAULT 'naver',
    domain        VARCHAR(50) NOT NULL DEFAULT 'ai_tech',
    window_start  TIMESTAMPTZ NOT NULL,
    window_end    TIMESTAMPTZ NOT NULL,
    keyword       VARCHAR(255) NOT NULL,
    keyword_count INTEGER NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE keyword_trends ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'ai_tech';

CREATE TABLE IF NOT EXISTS keyword_relations (
    id                  BIGSERIAL PRIMARY KEY,
    provider            VARCHAR(50) NOT NULL DEFAULT 'naver',
    domain              VARCHAR(50) NOT NULL DEFAULT 'ai_tech',
    window_start        TIMESTAMPTZ NOT NULL,
    window_end          TIMESTAMPTZ NOT NULL,
    keyword_a           VARCHAR(255) NOT NULL,
    keyword_b           VARCHAR(255) NOT NULL,
    cooccurrence_count  INTEGER NOT NULL,
    processed_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE keyword_relations ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'ai_tech';

CREATE INDEX IF NOT EXISTS idx_news_raw_provider_domain_published_at
    ON news_raw(provider, domain, published_at);
CREATE INDEX IF NOT EXISTS idx_news_raw_article_time
    ON news_raw((COALESCE(published_at, ingested_at)));
CREATE INDEX IF NOT EXISTS idx_news_raw_domain_article_time
    ON news_raw(domain, (COALESCE(published_at, ingested_at)));
CREATE INDEX IF NOT EXISTS idx_news_raw_provider_domain_article_time
    ON news_raw(provider, domain, (COALESCE(published_at, ingested_at)));
CREATE UNIQUE INDEX IF NOT EXISTS idx_news_raw_provider_domain_url
    ON news_raw(provider, domain, url);

CREATE INDEX IF NOT EXISTS idx_keywords_keyword
    ON keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword_article
    ON keywords(keyword, article_provider, article_domain, article_url);
CREATE INDEX IF NOT EXISTS idx_keywords_domain_keyword
    ON keywords(article_domain, keyword);
CREATE UNIQUE INDEX IF NOT EXISTS idx_keywords_unique
    ON keywords(article_provider, article_domain, article_url, keyword);

CREATE INDEX IF NOT EXISTS idx_keyword_trends_window
    ON keyword_trends(window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_keyword_trends_provider_domain_window
    ON keyword_trends(provider, domain, window_start, window_end);
CREATE UNIQUE INDEX IF NOT EXISTS idx_keyword_trends_unique
    ON keyword_trends(provider, domain, window_start, window_end, keyword);

CREATE INDEX IF NOT EXISTS idx_keyword_relations_window
    ON keyword_relations(window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_keywords
    ON keyword_relations(keyword_a, keyword_b);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_provider_domain_window
    ON keyword_relations(provider, domain, window_start, window_end);
CREATE UNIQUE INDEX IF NOT EXISTS idx_keyword_relations_unique
    ON keyword_relations(provider, domain, window_start, window_end, keyword_a, keyword_b);

CREATE TABLE IF NOT EXISTS compound_noun_dict (
    id         SERIAL PRIMARY KEY,
    word       VARCHAR(50)  NOT NULL,
    domain     VARCHAR(50)  NOT NULL DEFAULT 'all',
    source     VARCHAR(20)  NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_compound_noun_dict_word_domain UNIQUE (word, domain)
);

CREATE TABLE IF NOT EXISTS compound_noun_candidates (
    id            SERIAL PRIMARY KEY,
    word          VARCHAR(50)  NOT NULL,
    domain        VARCHAR(50)  NOT NULL DEFAULT 'all',
    frequency     INTEGER      NOT NULL DEFAULT 1,
    doc_count     INTEGER      NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    status        VARCHAR(20)  NOT NULL DEFAULT 'needs_review',
    reviewed_at   TIMESTAMPTZ,
    reviewed_by   VARCHAR(100),
    CONSTRAINT uq_compound_noun_candidates_word_domain UNIQUE (word, domain),
    CONSTRAINT ck_compound_noun_candidates_status CHECK (status IN ('needs_review', 'approved', 'rejected'))
);

CREATE TABLE IF NOT EXISTS stopword_dict (
    id         SERIAL PRIMARY KEY,
    word       VARCHAR(50)  NOT NULL,
    domain     VARCHAR(50)  NOT NULL DEFAULT 'all',
    language   VARCHAR(10)  NOT NULL DEFAULT 'ko',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_stopword_dict_word_domain_lang UNIQUE (word, domain, language)
);

-- Idempotent migrations for existing deployments without domain column
ALTER TABLE compound_noun_dict ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'all';
ALTER TABLE compound_noun_candidates ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'all';
ALTER TABLE stopword_dict ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'all';

-- Drop old single-column unique constraints and add new domain-aware ones
DO $$
BEGIN
    -- Drop old single-column unique constraints (various possible names)
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'compound_noun_dict_word_key' AND conrelid = 'compound_noun_dict'::regclass) THEN
        ALTER TABLE compound_noun_dict DROP CONSTRAINT compound_noun_dict_word_key;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_compound_noun_dict_word' AND conrelid = 'compound_noun_dict'::regclass) THEN
        ALTER TABLE compound_noun_dict DROP CONSTRAINT uq_compound_noun_dict_word;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_compound_noun_dict_word_domain' AND conrelid = 'compound_noun_dict'::regclass) THEN
        ALTER TABLE compound_noun_dict ADD CONSTRAINT uq_compound_noun_dict_word_domain UNIQUE (word, domain);
    END IF;

    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'compound_noun_candidates_word_key' AND conrelid = 'compound_noun_candidates'::regclass) THEN
        ALTER TABLE compound_noun_candidates DROP CONSTRAINT compound_noun_candidates_word_key;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_compound_noun_candidates_word' AND conrelid = 'compound_noun_candidates'::regclass) THEN
        ALTER TABLE compound_noun_candidates DROP CONSTRAINT uq_compound_noun_candidates_word;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_compound_noun_candidates_word_domain' AND conrelid = 'compound_noun_candidates'::regclass) THEN
        ALTER TABLE compound_noun_candidates ADD CONSTRAINT uq_compound_noun_candidates_word_domain UNIQUE (word, domain);
    END IF;

    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'stopword_dict_word_language_key' AND conrelid = 'stopword_dict'::regclass) THEN
        ALTER TABLE stopword_dict DROP CONSTRAINT stopword_dict_word_language_key;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_stopword_dict_word_lang' AND conrelid = 'stopword_dict'::regclass) THEN
        ALTER TABLE stopword_dict DROP CONSTRAINT uq_stopword_dict_word_lang;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_stopword_dict_word_domain_lang' AND conrelid = 'stopword_dict'::regclass) THEN
        ALTER TABLE stopword_dict ADD CONSTRAINT uq_stopword_dict_word_domain_lang UNIQUE (word, domain, language);
    END IF;
END $$;


CREATE INDEX IF NOT EXISTS idx_compound_noun_dict_domain
    ON compound_noun_dict(domain);
CREATE INDEX IF NOT EXISTS idx_compound_noun_candidates_status
    ON compound_noun_candidates(status);
CREATE INDEX IF NOT EXISTS idx_compound_noun_candidates_domain
    ON compound_noun_candidates(domain);
CREATE INDEX IF NOT EXISTS idx_compound_noun_candidates_frequency
    ON compound_noun_candidates(frequency DESC);
CREATE INDEX IF NOT EXISTS idx_stopword_dict_domain_language
    ON stopword_dict(domain, language);

CREATE TABLE IF NOT EXISTS dictionary_audit_logs (
    id          BIGSERIAL PRIMARY KEY,
    entity_type VARCHAR(50) NOT NULL,
    entity_id   INTEGER,
    action      VARCHAR(50) NOT NULL,
    before_json JSONB,
    after_json  JSONB,
    actor       VARCHAR(100) NOT NULL DEFAULT 'system',
    acted_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dictionary_audit_logs_entity
    ON dictionary_audit_logs(entity_type, entity_id, acted_at DESC);

CREATE TABLE IF NOT EXISTS stopword_candidates (
    id                   SERIAL PRIMARY KEY,
    word                 VARCHAR(50)  NOT NULL,
    domain               VARCHAR(50)  NOT NULL DEFAULT 'all',
    language             VARCHAR(10)  NOT NULL DEFAULT 'ko',
    score                FLOAT        NOT NULL DEFAULT 0,
    domain_breadth       FLOAT        NOT NULL DEFAULT 0,
    repetition_rate      FLOAT        NOT NULL DEFAULT 0,
    trend_stability      FLOAT        NOT NULL DEFAULT 0,
    cooccurrence_breadth FLOAT        NOT NULL DEFAULT 0,
    short_word           BOOLEAN      NOT NULL DEFAULT FALSE,
    frequency            INTEGER      NOT NULL DEFAULT 0,
    status               VARCHAR(20)  NOT NULL DEFAULT 'needs_review',
    first_seen_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    last_seen_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    reviewed_at          TIMESTAMPTZ,
    reviewed_by          VARCHAR(100),
    CONSTRAINT uq_stopword_candidates_word_domain_lang UNIQUE (word, domain, language),
    CONSTRAINT ck_stopword_candidates_status CHECK (status IN ('needs_review', 'approved', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_stopword_candidates_status
    ON stopword_candidates(status);
CREATE INDEX IF NOT EXISTS idx_stopword_candidates_score
    ON stopword_candidates(score DESC);
CREATE INDEX IF NOT EXISTS idx_stopword_candidates_domain
    ON stopword_candidates(domain);

CREATE TABLE IF NOT EXISTS collection_metrics (
    id              BIGSERIAL PRIMARY KEY,
    provider        VARCHAR(50) NOT NULL DEFAULT 'naver',
    domain          VARCHAR(50) NOT NULL,
    query           VARCHAR(100) NOT NULL,
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    request_count   INTEGER NOT NULL DEFAULT 0,
    success_count   INTEGER NOT NULL DEFAULT 0,
    article_count   INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    publish_count   INTEGER NOT NULL DEFAULT 0,
    error_count     INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_collection_metrics_window
    ON collection_metrics(provider, domain, window_start DESC, query);

CREATE TABLE IF NOT EXISTS keyword_events (
    id               BIGSERIAL PRIMARY KEY,
    provider         VARCHAR(50) NOT NULL DEFAULT 'naver',
    domain           VARCHAR(50) NOT NULL,
    keyword          VARCHAR(255) NOT NULL,
    event_time       TIMESTAMPTZ NOT NULL,
    window_start     TIMESTAMPTZ NOT NULL,
    window_end       TIMESTAMPTZ NOT NULL,
    current_mentions INTEGER NOT NULL DEFAULT 0,
    prev_mentions    INTEGER NOT NULL DEFAULT 0,
    growth           DOUBLE PRECISION NOT NULL DEFAULT 0,
    event_score      INTEGER NOT NULL DEFAULT 0,
    is_spike         BOOLEAN NOT NULL DEFAULT FALSE,
    detected_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_keyword_events_unique
    ON keyword_events(provider, domain, keyword, window_start);
CREATE INDEX IF NOT EXISTS idx_keyword_events_lookup
    ON keyword_events(provider, domain, event_time DESC, event_score DESC);

CREATE TABLE IF NOT EXISTS dictionary_versions (
    dict_name   VARCHAR(50) PRIMARY KEY,
    version     BIGINT NOT NULL DEFAULT 1,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO dictionary_versions (dict_name, version)
VALUES
    ('compound_noun_dict', 1),
    ('stopword_dict', 1)
ON CONFLICT (dict_name) DO NOTHING;

CREATE OR REPLACE FUNCTION bump_dictionary_version() RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO dictionary_versions (dict_name, version, updated_at)
    VALUES (TG_TABLE_NAME, 2, NOW())
    ON CONFLICT (dict_name)
    DO UPDATE SET
        version = dictionary_versions.version + 1,
        updated_at = NOW();

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_bump_compound_noun_dict_version ON compound_noun_dict;
CREATE TRIGGER trg_bump_compound_noun_dict_version
AFTER INSERT OR UPDATE OR DELETE ON compound_noun_dict
FOR EACH ROW
EXECUTE FUNCTION bump_dictionary_version();

DROP TRIGGER IF EXISTS trg_bump_stopword_dict_version ON stopword_dict;
CREATE TRIGGER trg_bump_stopword_dict_version
AFTER INSERT OR UPDATE OR DELETE ON stopword_dict
FOR EACH ROW
EXECUTE FUNCTION bump_dictionary_version();

CREATE TABLE IF NOT EXISTS stg_news_raw (
    provider     VARCHAR(50),
    domain       VARCHAR(50),
    query        VARCHAR(100),
    source       VARCHAR(255),
    title        TEXT,
    summary      TEXT,
    url          TEXT,
    published_at TIMESTAMPTZ,
    ingested_at  TIMESTAMPTZ
);
ALTER TABLE stg_news_raw ADD COLUMN IF NOT EXISTS domain VARCHAR(50);
ALTER TABLE stg_news_raw ADD COLUMN IF NOT EXISTS query VARCHAR(100);

CREATE TABLE IF NOT EXISTS stg_keywords (
    article_provider  VARCHAR(50),
    article_domain    VARCHAR(50),
    article_url       TEXT,
    keyword           VARCHAR(255),
    keyword_count     INTEGER,
    processed_at      TIMESTAMPTZ
);
ALTER TABLE stg_keywords ADD COLUMN IF NOT EXISTS article_domain VARCHAR(50);

CREATE TABLE IF NOT EXISTS stg_keyword_trends (
    provider      VARCHAR(50),
    domain        VARCHAR(50),
    window_start  TIMESTAMPTZ,
    window_end    TIMESTAMPTZ,
    keyword       VARCHAR(255),
    keyword_count INTEGER,
    processed_at  TIMESTAMPTZ
);
ALTER TABLE stg_keyword_trends ADD COLUMN IF NOT EXISTS domain VARCHAR(50);

CREATE TABLE IF NOT EXISTS stg_keyword_relations (
    provider            VARCHAR(50),
    domain              VARCHAR(50),
    window_start        TIMESTAMPTZ,
    window_end          TIMESTAMPTZ,
    keyword_a           VARCHAR(255),
    keyword_b           VARCHAR(255),
    cooccurrence_count  INTEGER,
    processed_at        TIMESTAMPTZ
);
ALTER TABLE stg_keyword_relations ADD COLUMN IF NOT EXISTS domain VARCHAR(50);
