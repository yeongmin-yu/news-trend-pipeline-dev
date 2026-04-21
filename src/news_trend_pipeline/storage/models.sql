CREATE TABLE IF NOT EXISTS news_raw (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL DEFAULT 'newsapi',
    source VARCHAR(255),
    author VARCHAR(255),
    title TEXT NOT NULL,
    description TEXT,
    content TEXT,
    url TEXT NOT NULL,
    published_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS keywords (
    id BIGSERIAL PRIMARY KEY,
    article_provider VARCHAR(50) NOT NULL DEFAULT 'newsapi',
    article_url TEXT NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    keyword_count INTEGER NOT NULL DEFAULT 1,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS keyword_trends (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL DEFAULT 'newsapi',
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    keyword VARCHAR(255) NOT NULL,
    keyword_count INTEGER NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS keyword_relations (
    id BIGSERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL DEFAULT 'newsapi',
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    keyword_a VARCHAR(255) NOT NULL,
    keyword_b VARCHAR(255) NOT NULL,
    cooccurrence_count INTEGER NOT NULL,
    processed_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE news_raw DROP CONSTRAINT IF EXISTS news_raw_url_key;
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS provider VARCHAR(50) NOT NULL DEFAULT 'newsapi';
ALTER TABLE keywords ADD COLUMN IF NOT EXISTS article_provider VARCHAR(50) NOT NULL DEFAULT 'newsapi';
ALTER TABLE keyword_trends ADD COLUMN IF NOT EXISTS provider VARCHAR(50) NOT NULL DEFAULT 'newsapi';
ALTER TABLE keyword_relations ADD COLUMN IF NOT EXISTS provider VARCHAR(50) NOT NULL DEFAULT 'newsapi';

CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_keyword_trends_window ON keyword_trends(window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_window ON keyword_relations(window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_keywords ON keyword_relations(keyword_a, keyword_b);
CREATE UNIQUE INDEX IF NOT EXISTS idx_news_raw_provider_url ON news_raw(provider, url);
CREATE INDEX IF NOT EXISTS idx_news_raw_provider_published_at ON news_raw(provider, published_at);
CREATE INDEX IF NOT EXISTS idx_keyword_trends_provider_window ON keyword_trends(provider, window_start, window_end);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_provider_window ON keyword_relations(provider, window_start, window_end);
