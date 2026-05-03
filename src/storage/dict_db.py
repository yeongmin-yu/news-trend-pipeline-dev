from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import Json, RealDictCursor

from storage.db import _jsonable, get_connection


def fetch_dictionary_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    """사전 변경 감사 로그를 최신순으로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, entity_type, entity_id, action, before_json, after_json, actor, acted_at
                FROM dictionary_audit_logs
                ORDER BY acted_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def fetch_compound_nouns(domain: str = "all") -> list[str]:
    """형태소 분석에 사용할 복합명사 단어 목록을 반환한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if domain == "all":
                cursor.execute("SELECT word FROM compound_noun_dict ORDER BY word")
            else:
                cursor.execute(
                    "SELECT word FROM compound_noun_dict WHERE domain = %s OR domain = 'all' ORDER BY word",
                    (domain,),
                )
            return [row[0] for row in cursor.fetchall()]


def fetch_compound_noun_item(item_id: int) -> dict[str, Any] | None:
    """단일 복합명사 항목을 ID로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, word, domain, source, created_at FROM compound_noun_dict WHERE id = %s",
                (item_id,),
            )
            return cursor.fetchone()


def fetch_stopwords(language: str = "ko", domain: str = "all") -> set[str]:
    """키워드 추출에서 제외할 불용어 집합을 반환한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            if domain == "all":
                cursor.execute("SELECT word FROM stopword_dict WHERE language = %s", (language,))
            else:
                cursor.execute(
                    "SELECT word FROM stopword_dict WHERE language = %s AND (domain = %s OR domain = 'all')",
                    (language, domain),
                )
            return {row[0] for row in cursor.fetchall()}


def fetch_stopword_item(item_id: int) -> dict[str, Any] | None:
    """단일 불용어 항목을 ID로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT id, word, domain, language, created_at FROM stopword_dict WHERE id = %s",
                (item_id,),
            )
            return cursor.fetchone()


def fetch_compound_candidate_item(item_id: int) -> dict[str, Any] | None:
    """단일 복합명사 후보 항목을 ID로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, frequency, doc_count, first_seen_at, last_seen_at,
                       status, reviewed_at, reviewed_by
                FROM compound_noun_candidates
                WHERE id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def fetch_stopword_candidate_item(item_id: int) -> dict[str, Any] | None:
    """단일 불용어 후보 항목을 ID로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, language, score, domain_breadth, repetition_rate,
                       trend_stability, cooccurrence_breadth, short_word, frequency,
                       status, first_seen_at, last_seen_at, reviewed_at, reviewed_by
                FROM stopword_candidates
                WHERE id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def fetch_dictionary_versions() -> dict[str, int]:
    """복합명사·불용어 사전의 현재 버전 번호를 반환한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT dict_name, version
                FROM dictionary_versions
                WHERE dict_name IN ('compound_noun_dict', 'stopword_dict')
                ORDER BY dict_name
                """
            )
            return {row[0]: int(row[1]) for row in cursor.fetchall()}


def update_compound_noun_domain(*, item_id: int, domain: str) -> dict[str, Any] | None:
    """복합명사 항목의 도메인 컬럼을 업데이트한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "UPDATE compound_noun_dict SET domain = %s WHERE id = %s RETURNING id, word, domain, source, created_at",
                (domain, item_id),
            )
            return cursor.fetchone()


def update_stopword_domain(*, item_id: int, domain: str) -> dict[str, Any] | None:
    """불용어 항목의 도메인 컬럼을 업데이트한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "UPDATE stopword_dict SET domain = %s WHERE id = %s RETURNING id, word, domain, language, created_at",
                (domain, item_id),
            )
            return cursor.fetchone()


def delete_keyword_data_for_stopword(*, word: str, domain: str = "all") -> dict[str, int]:
    """불용어로 등록된 단어와 관련된 키워드 데이터를 모든 테이블에서 정리한다."""
    domain_filter = None if domain == "all" else domain
    counts: dict[str, int] = {}
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM keyword_relations WHERE (keyword_a = %s OR keyword_b = %s) AND (%s IS NULL OR domain = %s)",
                (word, word, domain_filter, domain_filter),
            )
            counts["keyword_relations"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM keyword_events WHERE keyword = %s AND (%s IS NULL OR domain = %s)",
                (word, domain_filter, domain_filter),
            )
            counts["keyword_events"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM keyword_trends WHERE keyword = %s AND (%s IS NULL OR domain = %s)",
                (word, domain_filter, domain_filter),
            )
            counts["keyword_trends"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM keywords WHERE keyword = %s AND (%s IS NULL OR article_domain = %s)",
                (word, domain_filter, domain_filter),
            )
            counts["keywords"] = cursor.rowcount
            cursor.execute(
                "DELETE FROM stg_keyword_relations WHERE keyword_a = %s OR keyword_b = %s",
                (word, word),
            )
            counts["stg_keyword_relations"] = cursor.rowcount
            cursor.execute("DELETE FROM stg_keyword_trends WHERE keyword = %s", (word,))
            counts["stg_keyword_trends"] = cursor.rowcount
            cursor.execute("DELETE FROM stg_keywords WHERE keyword = %s", (word,))
            counts["stg_keywords"] = cursor.rowcount
    return counts


def log_dictionary_audit(
    *,
    entity_type: str,
    entity_id: int | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: str,
) -> None:
    """사전 항목 변경 이력을 dictionary_audit_logs 테이블에 기록한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO dictionary_audit_logs (entity_type, entity_id, action, before_json, after_json, actor)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    entity_type, entity_id, action,
                    Json(_jsonable(before)) if before is not None else None,
                    Json(_jsonable(after)) if after is not None else None,
                    actor,
                ),
            )


def fetch_articles_for_extraction(since: datetime, until: datetime) -> list[dict[str, Any]]:
    """복합명사 추출을 위해 지정 기간의 뉴스 기사 title·summary·domain을 반환한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "SELECT title, summary, domain FROM news_raw WHERE ingested_at >= %s AND ingested_at < %s ORDER BY ingested_at ASC",
                (since, until),
            )
            return list(cursor.fetchall())


def upsert_compound_candidates(candidates: dict[str, tuple[int, int]], domain: str = "all") -> tuple[int, int]:
    """자동 추출된 복합명사 후보를 compound_noun_candidates 테이블에 upsert한다."""
    if not candidates:
        return 0, 0
    now = datetime.now(timezone.utc)
    new_count = 0
    updated_count = 0
    insert_sql = """
        INSERT INTO compound_noun_candidates (word, domain, frequency, doc_count, first_seen_at, last_seen_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (word, domain) DO NOTHING
    """
    update_sql = """
        UPDATE compound_noun_candidates
        SET frequency = frequency + %s, doc_count = doc_count + %s, last_seen_at = %s
        WHERE word = %s AND domain = %s AND status = 'needs_review'
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for word, (freq, doc_cnt) in candidates.items():
                cursor.execute(insert_sql, (word, domain, freq, doc_cnt, now, now))
                if cursor.rowcount > 0:
                    new_count += 1
                else:
                    cursor.execute(update_sql, (freq, doc_cnt, now, word, domain))
                    if cursor.rowcount > 0:
                        updated_count += 1
    return new_count, updated_count


def review_stopword_candidate(candidate_id: int, action: str, reviewed_by: str) -> dict[str, Any] | None:
    """불용어 후보를 승인/반려 처리하고 승인 시 stopword_dict에 등록한다."""
    reviewed_at = datetime.now(timezone.utc)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE stopword_candidates
                SET status = %s, reviewed_at = %s, reviewed_by = %s
                WHERE id = %s
                RETURNING id, word, domain, language, score, status, reviewed_at, reviewed_by
                """,
                (action, reviewed_at, reviewed_by, candidate_id),
            )
            row = cursor.fetchone()
            if row and action == "approved":
                cursor.execute(
                    """
                    INSERT INTO stopword_dict (word, domain, language)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (word, domain, language) DO NOTHING
                    """,
                    (row["word"], row["domain"], row["language"]),
                )
    return row
