from __future__ import annotations

from typing import Any

from psycopg2.extras import Json, RealDictCursor

from storage.db import _jsonable, get_connection


def fetch_active_query_keywords(provider: str = "naver") -> list[dict[str, Any]]:
    """뉴스 수집에 사용되는 활성화된 검색 쿼리 키워드 목록을 반환한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT provider, domain_id AS domain, query, sort_order
                FROM query_keywords
                WHERE provider = %s AND is_active = TRUE
                ORDER BY domain_id ASC, sort_order ASC, query ASC
                """,
                (provider,),
            )
            return list(cursor.fetchall())


def fetch_all_query_keywords(provider: str = "naver") -> list[dict[str, Any]]:
    """도메인 정보를 포함한 전체 쿼리 키워드 목록을 반환한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT q.id, q.provider, q.domain_id, d.label AS domain_label,
                       q.query, q.sort_order, q.is_active, q.created_at, q.updated_at
                FROM query_keywords q
                JOIN domain_catalog d ON d.domain_id = q.domain_id
                WHERE q.provider = %s
                ORDER BY d.sort_order ASC, q.sort_order ASC, q.query ASC
                """,
                (provider,),
            )
            return list(cursor.fetchall())


def fetch_query_keyword_by_id(item_id: int) -> dict[str, Any] | None:
    """단일 쿼리 키워드 항목을 ID로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT q.id, q.provider, q.domain_id, d.label AS domain_label,
                       q.query, q.sort_order, q.is_active, q.created_at, q.updated_at
                FROM query_keywords q
                JOIN domain_catalog d ON d.domain_id = q.domain_id
                WHERE q.id = %s
                """,
                (item_id,),
            )
            return cursor.fetchone()


def fetch_query_keyword_audit_logs(limit: int = 100) -> list[dict[str, Any]]:
    """쿼리 키워드 변경 감사 로그를 최신순으로 조회한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, query_keyword_id, action, before_json, after_json, actor, acted_at
                FROM query_keyword_audit_logs
                ORDER BY acted_at DESC, id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return list(cursor.fetchall())


def fetch_collection_metrics_summary(hours: int = 24, provider: str = "naver") -> list[dict[str, Any]]:
    """최근 N시간 동안의 소스별 뉴스 수집 메트릭 집계를 반환한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT provider, domain, query,
                       SUM(request_count) AS request_count, SUM(success_count) AS success_count,
                       SUM(article_count) AS article_count, SUM(duplicate_count) AS duplicate_count,
                       SUM(publish_count) AS publish_count, SUM(error_count) AS error_count,
                       MAX(window_end) AS last_seen_at
                FROM collection_metrics
                WHERE provider = %s AND window_end >= NOW() - (%s || ' hours')::interval
                GROUP BY provider, domain, query
                ORDER BY domain ASC, article_count DESC, query ASC
                """,
                (provider, hours),
            )
            return list(cursor.fetchall())


def log_query_keyword_audit(
    *,
    query_keyword_id: int | None,
    action: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    actor: str,
) -> None:
    """쿼리 키워드 변경 이력을 query_keyword_audit_logs 테이블에 기록한다."""
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO query_keyword_audit_logs (query_keyword_id, action, before_json, after_json, actor)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    query_keyword_id, action,
                    Json(_jsonable(before)) if before is not None else None,
                    Json(_jsonable(after)) if after is not None else None,
                    actor,
                ),
            )


def create_query_keyword(*, provider: str, domain_id: str, query: str, sort_order: int, actor: str) -> dict[str, Any]:
    """새 쿼리 키워드를 등록하고 감사 로그를 기록한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                "INSERT INTO query_keywords (provider, domain_id, query, sort_order, is_active, updated_at) VALUES (%s, %s, %s, %s, TRUE, NOW()) RETURNING id",
                (provider, domain_id, query, sort_order),
            )
            row = cursor.fetchone()
    created = fetch_query_keyword_by_id(int(row["id"]))
    log_query_keyword_audit(query_keyword_id=int(row["id"]), action="create", before=None, after=created, actor=actor)
    return created or {}


def update_query_keyword(*, item_id: int, domain_id: str, query: str, sort_order: int, is_active: bool, actor: str) -> dict[str, Any]:
    """기존 쿼리 키워드를 수정하고 감사 로그를 기록한다."""
    before = fetch_query_keyword_by_id(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE query_keywords SET domain_id = %s, query = %s, sort_order = %s, is_active = %s, updated_at = NOW() WHERE id = %s",
                (domain_id, query, sort_order, is_active, item_id),
            )
    after = fetch_query_keyword_by_id(item_id)
    log_query_keyword_audit(query_keyword_id=item_id, action="update", before=before, after=after, actor=actor)
    return after or {}


def delete_query_keyword(*, item_id: int, actor: str) -> None:
    """쿼리 키워드를 삭제하고 감사 로그를 기록한다."""
    before = fetch_query_keyword_by_id(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM query_keywords WHERE id = %s", (item_id,))
    log_query_keyword_audit(query_keyword_id=item_id, action="delete", before=before, after=None, actor=actor)
