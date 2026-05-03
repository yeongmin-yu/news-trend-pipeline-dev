from __future__ import annotations

# 이 파일은 하위 호환성을 위한 파사드입니다.
# DB 연결·공통 유틸은 이 파일에 직접 구현되며,
# 분할된 모듈(dict_db, news_db, admin_db)의 함수는 여기서 re-export 합니다.

from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

import psycopg2
from psycopg2.extras import RealDictCursor

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


# ── 공통 유틸 ─────────────────────────────────────────────────────────────────

def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


@contextmanager
def get_connection() -> Iterator[psycopg2.extensions.connection]:
    conn = psycopg2.connect(settings.postgres_dsn)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def fetch_domain_catalog() -> list[dict[str, Any]]:
    """활성화된 도메인 카탈로그를 정렬 순서대로 반환한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT domain_id AS id, label, group_id, group_label, group_sort_order, is_active AS available
                FROM domain_catalog
                WHERE is_active = TRUE
                ORDER BY group_sort_order ASC, sort_order ASC, domain_id ASC
                """
            )
            return list(cursor.fetchall())


# ── dict_db re-export ─────────────────────────────────────────────────────────

from storage.dict_db import (
    delete_keyword_data_for_stopword,
    fetch_articles_for_extraction,
    fetch_compound_candidate_item,
    fetch_compound_noun_item,
    fetch_compound_nouns,
    fetch_dictionary_audit_logs,
    fetch_dictionary_versions,
    fetch_stopword_candidate_item,
    fetch_stopword_item,
    fetch_stopwords,
    log_dictionary_audit,
    review_stopword_candidate,
    update_compound_noun_domain,
    update_stopword_domain,
    upsert_compound_candidates,
)

# ── news_db re-export ─────────────────────────────────────────────────────────

from storage.news_db import (
    aggregate_keyword_relations,
    aggregate_keyword_trends,
    cleanup_old_trends,
    fetch_keyword_events,
    insert_collection_metric,
    insert_keyword_relations,
    insert_keyword_trends,
    insert_news_raw,
    replace_keyword_events,
    upsert_from_staging_keyword_relations,
    upsert_from_staging_keyword_trends,
    upsert_from_staging_keywords,
    upsert_from_staging_news_raw,
)

# ── admin_db re-export ────────────────────────────────────────────────────────

from storage.admin_db import (
    create_query_keyword,
    delete_query_keyword,
    fetch_active_query_keywords,
    fetch_all_query_keywords,
    fetch_collection_metrics_summary,
    fetch_query_keyword_audit_logs,
    fetch_query_keyword_by_id,
    log_query_keyword_audit,
    update_query_keyword,
)

__all__ = [
    # 연결·공통
    "_jsonable",
    "get_connection",
    "fetch_domain_catalog",
    # dict_db
    "delete_keyword_data_for_stopword",
    "fetch_articles_for_extraction",
    "fetch_compound_candidate_item",
    "fetch_compound_noun_item",
    "fetch_compound_nouns",
    "fetch_dictionary_audit_logs",
    "fetch_dictionary_versions",
    "fetch_stopword_candidate_item",
    "fetch_stopword_item",
    "fetch_stopwords",
    "log_dictionary_audit",
    "review_stopword_candidate",
    "update_compound_noun_domain",
    "update_stopword_domain",
    "upsert_compound_candidates",
    # news_db
    "aggregate_keyword_relations",
    "aggregate_keyword_trends",
    "cleanup_old_trends",
    "fetch_keyword_events",
    "insert_collection_metric",
    "insert_keyword_relations",
    "insert_keyword_trends",
    "insert_news_raw",
    "replace_keyword_events",
    "upsert_from_staging_keyword_relations",
    "upsert_from_staging_keyword_trends",
    "upsert_from_staging_keywords",
    "upsert_from_staging_news_raw",
    # admin_db
    "create_query_keyword",
    "delete_query_keyword",
    "fetch_active_query_keywords",
    "fetch_all_query_keywords",
    "fetch_collection_metrics_summary",
    "fetch_query_keyword_audit_logs",
    "fetch_query_keyword_by_id",
    "log_query_keyword_audit",
    "update_query_keyword",
]
