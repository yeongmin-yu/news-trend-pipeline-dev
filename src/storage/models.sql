CREATE TABLE IF NOT EXISTS domain_catalog (
    domain_id        VARCHAR(50) PRIMARY KEY,
    label            VARCHAR(100) NOT NULL,
    group_id         VARCHAR(50) NOT NULL DEFAULT 'news_core',
    group_label      VARCHAR(100) NOT NULL DEFAULT '주요뉴스',
    group_sort_order INTEGER NOT NULL DEFAULT 1,
    sort_order       INTEGER NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE domain_catalog ADD COLUMN IF NOT EXISTS group_id VARCHAR(50) NOT NULL DEFAULT 'news_core';
ALTER TABLE domain_catalog ADD COLUMN IF NOT EXISTS group_label VARCHAR(100) NOT NULL DEFAULT '주요뉴스';
ALTER TABLE domain_catalog ADD COLUMN IF NOT EXISTS group_sort_order INTEGER NOT NULL DEFAULT 1;

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

WITH seed(domain_id, label, group_id, group_label, group_sort_order, sort_order) AS (
    VALUES
        ('politics', '정치·정책', 'politics', '정치·정책', 1, 1),
        ('economy', '경제·금융·부동산', 'economy', '경제·금융·부동산', 2, 1),
        ('society', '국제·지역·사회', 'society', '국제·지역·사회', 3, 1),
        ('tech_science', 'IT·과학·테크', 'tech', 'IT·과학·테크', 4, 1),
        ('culture_life', '엔터·문화·생활', 'culture', '엔터·문화·생활', 5, 1),
        ('sports', '스포츠', 'sports', '스포츠', 6, 1)
)
INSERT INTO domain_catalog (domain_id, label, group_id, group_label, group_sort_order, sort_order, is_active)
SELECT domain_id, label, group_id, group_label, group_sort_order, sort_order, TRUE
FROM seed
ON CONFLICT (domain_id) DO UPDATE SET
    label = EXCLUDED.label,
    group_id = EXCLUDED.group_id,
    group_label = EXCLUDED.group_label,
    group_sort_order = EXCLUDED.group_sort_order,
    sort_order = EXCLUDED.sort_order,
    is_active = TRUE;

UPDATE domain_catalog
SET is_active = FALSE
WHERE domain_id NOT IN (
    'politics',
    'economy',
    'society',
    'tech_science',
    'culture_life',
    'sports'
);

UPDATE query_keywords
SET is_active = FALSE,
    updated_at = NOW()
WHERE provider = 'naver';

WITH seed(provider, domain_id, query, sort_order) AS (
    VALUES
        ('naver', 'politics', '대통령', 1),
        ('naver', 'politics', '국회', 2),
        ('naver', 'politics', '정부', 3),
        ('naver', 'politics', '정당', 4),
        ('naver', 'politics', '선거', 5),
        ('naver', 'politics', '외교', 6),
        ('naver', 'politics', '안보', 7),
        ('naver', 'politics', '검찰', 8),
        ('naver', 'politics', '사법', 9),
        ('naver', 'politics', '행정', 10),
        ('naver', 'politics', '사설', 11),
        ('naver', 'politics', '칼럼', 12),
        ('naver', 'politics', '논설', 13),
        ('naver', 'politics', '여론', 14),
        ('naver', 'economy', '경제', 1),
        ('naver', 'economy', '금리', 2),
        ('naver', 'economy', '물가', 3),
        ('naver', 'economy', '환율', 4),
        ('naver', 'economy', '수출', 5),
        ('naver', 'economy', '무역', 6),
        ('naver', 'economy', '기업', 7),
        ('naver', 'economy', '산업', 8),
        ('naver', 'economy', '고용', 9),
        ('naver', 'economy', '소비', 10),
        ('naver', 'economy', '코스피', 11),
        ('naver', 'economy', '코스닥', 12),
        ('naver', 'economy', '증시', 13),
        ('naver', 'economy', '주식', 14),
        ('naver', 'economy', '채권', 15),
        ('naver', 'economy', '은행', 16),
        ('naver', 'economy', '보험', 17),
        ('naver', 'economy', '부동산', 18),
        ('naver', 'economy', '아파트', 19),
        ('naver', 'economy', '분양', 20),
        ('naver', 'society', '사회', 1),
        ('naver', 'society', '사건사고', 2),
        ('naver', 'society', '교육', 3),
        ('naver', 'society', '노동', 4),
        ('naver', 'society', '의료', 5),
        ('naver', 'society', '복지', 6),
        ('naver', 'society', '환경', 7),
        ('naver', 'society', '재난', 8),
        ('naver', 'society', '경찰', 9),
        ('naver', 'society', '법원', 10),
        ('naver', 'society', '서울', 11),
        ('naver', 'society', '수도권', 12),
        ('naver', 'society', '부산', 13),
        ('naver', 'society', '대구', 14),
        ('naver', 'society', '광주', 15),
        ('naver', 'society', '대전', 16),
        ('naver', 'society', '울산', 17),
        ('naver', 'society', '강원', 18),
        ('naver', 'society', '충청', 19),
        ('naver', 'society', '전라', 20),
        ('naver', 'society', '경상', 21),
        ('naver', 'society', '제주', 22),
        ('naver', 'society', '미국', 23),
        ('naver', 'society', '중국', 24),
        ('naver', 'society', '일본', 25),
        ('naver', 'society', '유럽', 26),
        ('naver', 'society', '러시아', 27),
        ('naver', 'society', '중동', 28),
        ('naver', 'society', '우크라이나', 29),
        ('naver', 'society', '북한', 30),
        ('naver', 'society', '국제유가', 31),
        ('naver', 'society', '세계경제', 32),
        ('naver', 'tech_science', 'AI', 1),
        ('naver', 'tech_science', '인공지능', 2),
        ('naver', 'tech_science', '생성형 AI', 3),
        ('naver', 'tech_science', '반도체', 4),
        ('naver', 'tech_science', '배터리', 5),
        ('naver', 'tech_science', '로봇', 6),
        ('naver', 'tech_science', '바이오', 7),
        ('naver', 'tech_science', '우주', 8),
        ('naver', 'tech_science', '기후기술', 9),
        ('naver', 'tech_science', '사이버보안', 10),
        ('naver', 'culture_life', '문화', 1),
        ('naver', 'culture_life', '책', 2),
        ('naver', 'culture_life', '전시', 3),
        ('naver', 'culture_life', '공연', 4),
        ('naver', 'culture_life', '여행', 5),
        ('naver', 'culture_life', '건강', 6),
        ('naver', 'culture_life', '생활', 7),
        ('naver', 'culture_life', '음식', 8),
        ('naver', 'culture_life', '패션', 9),
        ('naver', 'culture_life', '종교', 10),
        ('naver', 'culture_life', '연예', 11),
        ('naver', 'culture_life', 'K팝', 12),
        ('naver', 'culture_life', '아이돌', 13),
        ('naver', 'culture_life', '드라마', 14),
        ('naver', 'culture_life', '영화', 15),
        ('naver', 'culture_life', 'OTT', 16),
        ('naver', 'culture_life', '방송', 17),
        ('naver', 'culture_life', '가요', 18),
        ('naver', 'culture_life', '배우', 19),
        ('naver', 'culture_life', '콘서트', 20),
        ('naver', 'sports', '야구', 1),
        ('naver', 'sports', '축구', 2),
        ('naver', 'sports', '농구', 3),
        ('naver', 'sports', '배구', 4),
        ('naver', 'sports', '골프', 5),
        ('naver', 'sports', '올림픽', 6),
        ('naver', 'sports', '월드컵', 7),
        ('naver', 'sports', 'K리그', 8),
        ('naver', 'sports', '프로야구', 9),
        ('naver', 'sports', 'e스포츠', 10)
),
updated AS (
    UPDATE query_keywords q
    SET sort_order = seed.sort_order,
        is_active = TRUE,
        updated_at = NOW()
    FROM seed
    WHERE q.provider = seed.provider
      AND q.domain_id = seed.domain_id
      AND q.query = seed.query
    RETURNING q.provider, q.domain_id, q.query
)
INSERT INTO query_keywords (provider, domain_id, query, sort_order, is_active, updated_at)
SELECT seed.provider, seed.domain_id, seed.query, seed.sort_order, TRUE, NOW()
FROM seed
WHERE NOT EXISTS (
    SELECT 1
    FROM updated
    WHERE updated.provider = seed.provider
      AND updated.domain_id = seed.domain_id
      AND updated.query = seed.query
);

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
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS domain VARCHAR(50) NOT NULL DEFAULT 'ai_tech';
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS query VARCHAR(100);
ALTER TABLE news_raw ADD COLUMN IF NOT EXISTS summary TEXT;

DO $$
DECLARE
    idx_keywords_unique_oid REGCLASS := to_regclass('idx_keywords_unique');
    idx_keyword_trends_unique_oid REGCLASS := to_regclass('idx_keyword_trends_unique');
BEGIN
    IF idx_keywords_unique_oid IS NOT NULL
       AND pg_get_indexdef(idx_keywords_unique_oid) NOT ILIKE '%article_domain%' THEN
        DROP INDEX idx_keywords_unique;
    END IF;

    IF idx_keyword_trends_unique_oid IS NOT NULL
       AND pg_get_indexdef(idx_keyword_trends_unique_oid) NOT ILIKE '%domain%' THEN
        DROP INDEX idx_keyword_trends_unique;
    END IF;
    -- keyword_relations 의 unique 인덱스 검사는 더 이상 필요 없음:
    -- 비파티션 테이블이 남아있으면 후속 블록에서 DROP TABLE 로 cascade 처리됨.
END $$;

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

-- keyword_relations: window_start RANGE 월별 파티셔닝.
-- 개발 단계 — 기존 데이터 보존 안 함. 비파티션 테이블이 남아있으면 그냥 폐기.
-- (운영 환경에선 Flyway 등 별도 마이그레이션 도구로 전환 예정)
DO $$
DECLARE
    rel_kind char;
BEGIN
    SELECT relkind INTO rel_kind
      FROM pg_class
     WHERE relname = 'keyword_relations'
       AND relnamespace = 'public'::regnamespace;

    IF rel_kind = 'r' THEN
        DROP TABLE keyword_relations CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS keyword_relations (
    id                  BIGINT GENERATED BY DEFAULT AS IDENTITY,
    provider            VARCHAR(50)  NOT NULL DEFAULT 'naver',
    domain              VARCHAR(50)  NOT NULL DEFAULT 'ai_tech',
    window_start        TIMESTAMPTZ  NOT NULL,
    window_end          TIMESTAMPTZ  NOT NULL,
    keyword_a           VARCHAR(255) NOT NULL,
    keyword_b           VARCHAR(255) NOT NULL,
    cooccurrence_count  INTEGER      NOT NULL,
    processed_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, window_start)
) PARTITION BY RANGE (window_start);

-- 월별 파티션 (2024-01 ~ 2027-12). 누락 월은 매월 cron 으로 보충 권장.
DO $$
DECLARE
    cur date := DATE '2024-01-01';
    end_date date := DATE '2028-01-01';
    next_date date;
    partition_name text;
BEGIN
    WHILE cur < end_date LOOP
        next_date := (cur + INTERVAL '1 month')::date;
        partition_name := 'keyword_relations_' || to_char(cur, 'YYYY_MM');
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF keyword_relations '
            'FOR VALUES FROM (%L) TO (%L)',
            partition_name, cur, next_date
        );
        cur := next_date;
    END LOOP;
END $$;

-- 범위 밖 데이터를 흡수할 DEFAULT 파티션 (월별 파티션 뒤에 생성).
CREATE TABLE IF NOT EXISTS keyword_relations_default
    PARTITION OF keyword_relations DEFAULT;

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

-- 미사용/중복 인덱스 정리.
--   - idx_keyword_relations_window : window_end 단독 cleanup 외 사용처 없음
--   - idx_keyword_relations_keywords : (keyword_a, keyword_b) prefix 만 활용되어
--                                       UNION 의 keyword_b 쪽엔 무용. (keyword_*, window_start)
--                                       조합으로 대체.
--   - idx_keyword_relations_provider_domain_window : UNIQUE 인덱스의 좌측 4컬럼과 동일하여 redundant
DROP INDEX IF EXISTS idx_keyword_relations_window;
DROP INDEX IF EXISTS idx_keyword_relations_keywords;
DROP INDEX IF EXISTS idx_keyword_relations_provider_domain_window;

-- UNIQUE 는 partition key(window_start) 를 포함해야 한다 (PG 요구사항).
CREATE UNIQUE INDEX IF NOT EXISTS idx_keyword_relations_unique
    ON keyword_relations(provider, domain, window_start, window_end, keyword_a, keyword_b);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_keyword_a_window
    ON keyword_relations(keyword_a, window_start);
CREATE INDEX IF NOT EXISTS idx_keyword_relations_keyword_b_window
    ON keyword_relations(keyword_b, window_start);

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
ALTER TABLE compound_noun_candidates
ADD COLUMN IF NOT EXISTS auto_score NUMERIC,
ADD COLUMN IF NOT EXISTS auto_evidence JSONB,
ADD COLUMN IF NOT EXISTS auto_checked_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS auto_decision TEXT;

CREATE INDEX IF NOT EXISTS idx_compound_candidates_auto_review
ON compound_noun_candidates (
    status,
    auto_checked_at,
    frequency DESC,
    doc_count DESC,
    last_seen_at DESC
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

WITH seed(word) AS (
    VALUES
        ('기자'),
        ('뉴스'),
        ('이번'),
        ('관련'),
        ('통해'),
        ('대한'),
        ('경우'),
        ('이후'),
        ('당시'),
        ('이날'),
        ('사진'),
        ('정도'),
        ('발표'),
        ('계획'),
        ('진행'),
        ('기업'),
        ('시장'),
        ('기술'),
        ('정부'),
        ('국회'),
        ('기반'),
        ('확대'),
        ('지원'),
        ('글로벌'),
        ('지역'),
        ('공개'),
        ('강화'),
        ('전략'),
        ('운영'),
        ('활용'),
        ('최대'),
        ('규모'),
        ('핵심'),
        ('대비'),
        ('분야'),
        ('추진'),
        ('구축'),
        ('가능'),
        ('주요')
)
INSERT INTO stopword_dict (word, domain, language)
SELECT word, 'all', 'ko'
FROM seed
ON CONFLICT (word, domain, language) DO NOTHING;

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

