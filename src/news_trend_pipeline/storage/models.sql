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

-- 복합명사 사전 (승인된 단어)
CREATE TABLE IF NOT EXISTS compound_noun_dict (
    id         SERIAL PRIMARY KEY,
    word       VARCHAR(50)  NOT NULL,
    source     VARCHAR(20)  NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now(),
    CONSTRAINT uq_compound_noun_dict_word UNIQUE (word)
);

-- 복합명사 후보 (자동 추출, 관리자 승인 대기)
CREATE TABLE IF NOT EXISTS compound_noun_candidates (
    id            SERIAL      PRIMARY KEY,
    word          VARCHAR(50) NOT NULL,
    frequency     INTEGER     NOT NULL DEFAULT 1,
    doc_count     INTEGER     NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',
    reviewed_at   TIMESTAMPTZ,
    reviewed_by   VARCHAR(100),
    CONSTRAINT uq_compound_noun_candidates_word UNIQUE (word),
    CONSTRAINT ck_compound_noun_candidates_status CHECK (status IN ('pending', 'approved', 'rejected'))
);

-- 불용어 사전
CREATE TABLE IF NOT EXISTS stopword_dict (
    id         SERIAL      PRIMARY KEY,
    word       VARCHAR(50) NOT NULL,
    language   VARCHAR(10) NOT NULL DEFAULT 'ko',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_stopword_dict_word_lang UNIQUE (word, language)
);

CREATE INDEX IF NOT EXISTS idx_compound_noun_candidates_status ON compound_noun_candidates(status);
CREATE INDEX IF NOT EXISTS idx_compound_noun_candidates_frequency ON compound_noun_candidates(frequency DESC);
CREATE INDEX IF NOT EXISTS idx_stopword_dict_language ON stopword_dict(language);
