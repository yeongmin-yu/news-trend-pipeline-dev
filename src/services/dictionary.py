from __future__ import annotations

from typing import Any

from psycopg2 import errors
from psycopg2.extras import RealDictCursor

from storage.db import (
    delete_keyword_data_for_stopword,
    fetch_compound_candidate_item,
    fetch_compound_noun_item,
    fetch_dictionary_versions,
    fetch_stopword_candidate_item,
    fetch_stopword_item,
    get_connection,
    log_dictionary_audit,
    review_stopword_candidate as db_review_stopword_candidate,
    update_compound_noun_domain as db_update_compound_noun_domain,
    update_stopword_domain as db_update_stopword_domain,
)
from services._utils import (
    DictionaryDomainConflictError,
    DictionaryItemNotFoundError,
    _now_utc,
)


# ── 직렬화 헬퍼 ───────────────────────────────────────────────────────────────

def _compound_noun_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "word": row["word"],
        "domain": row.get("domain", "all"),
        "source": row.get("source"),
        "createdAt": row.get("created_at"),
    }


def _stopword_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "word": row["word"],
        "domain": row.get("domain", "all"),
        "language": row.get("language"),
        "createdAt": row.get("created_at"),
    }


def _build_auto_evidence_summary(evidence: dict[str, Any] | None) -> dict[str, Any] | None:
    if not evidence:
        return None
    stats = evidence.get("stats") or {}
    webkr = evidence.get("naver_webkr") or {}
    return {
        "frequencyPerDoc": stats.get("frequency_per_doc"),
        "naverTotal": webkr.get("total"),
        "hasExactCompactMatch": webkr.get("has_exact_compact_match"),
        "matchedField": webkr.get("matched_field"),
        "matchedTitle": webkr.get("matched_title"),
        "matchedLink": webkr.get("matched_link"),
    }


def _compound_candidate_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "word": row["word"],
        "domain": row.get("domain", "all"),
        "frequency": row.get("frequency"),
        "docCount": row.get("doc_count"),
        "firstSeenAt": row.get("first_seen_at"),
        "lastSeenAt": row.get("last_seen_at"),
        "status": row.get("status"),
        "reviewedAt": row.get("reviewed_at"),
        "reviewedBy": row.get("reviewed_by"),
        "autoDecision": row.get("auto_decision"),
        "autoCheckedAt": row.get("auto_checked_at"),
        "autoEvidence": row.get("auto_evidence"),
        "autoEvidenceSummary": _build_auto_evidence_summary(row.get("auto_evidence")),
    }


def _stopword_candidate_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "word": row["word"],
        "domain": row.get("domain", "all"),
        "language": row.get("language"),
        "score": row.get("score"),
        "domainBreadth": row.get("domain_breadth"),
        "repetitionRate": row.get("repetition_rate"),
        "trendStability": row.get("trend_stability"),
        "cooccurrenceBreadth": row.get("cooccurrence_breadth"),
        "shortWord": row.get("short_word"),
        "frequency": row.get("frequency"),
        "status": row.get("status"),
        "firstSeenAt": row.get("first_seen_at"),
        "lastSeenAt": row.get("last_seen_at"),
        "reviewedAt": row.get("reviewed_at"),
        "reviewedBy": row.get("reviewed_by"),
    }


# ── 개요 ─────────────────────────────────────────────────────────────────────

def get_dictionary_overview() -> dict[str, Any]:
    """복합명사·불용어·후보 항목 수와 사전 버전을 한 번에 반환한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT COUNT(*) AS cnt FROM compound_noun_dict")
            compound_noun_count = int(cursor.fetchone()["cnt"])
            cursor.execute("SELECT COUNT(*) AS cnt FROM compound_noun_candidates")
            candidate_count = int(cursor.fetchone()["cnt"])
            cursor.execute("SELECT COUNT(*) AS cnt FROM stopword_dict")
            stopword_count = int(cursor.fetchone()["cnt"])
    versions = fetch_dictionary_versions()
    return {
        "compoundNounCount": compound_noun_count,
        "candidateCount": candidate_count,
        "stopwordCount": stopword_count,
        "versions": {
            "compoundNounDict": int(versions.get("compound_noun_dict", 0)),
            "stopwordDict": int(versions.get("stopword_dict", 0)),
        },
    }


# ── 복합명사 ──────────────────────────────────────────────────────────────────

def list_compound_nouns_paged(*, page: int = 1, limit: int = 50, q: str = "", domain: str = "") -> dict[str, Any]:
    """복합명사 사전을 검색·필터링하여 페이지네이션으로 반환한다."""
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    domain_clause = ""
    if domain and domain != "all":
        domain_clause = "AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM compound_noun_dict WHERE word ILIKE %s {domain_clause}", params)
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, source, created_at
                FROM compound_noun_dict
                WHERE word ILIKE %s {domain_clause}
                ORDER BY created_at DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = [_compound_noun_to_api(dict(row)) for row in cursor.fetchall()]
    return {"items": items, "total": total, "page": page, "limit": limit}


def create_compound_noun(word: str, source: str, actor: str = "dashboard-admin", domain: str = "all") -> None:
    """새 복합명사를 사전에 추가하고 감사 로그를 기록한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO compound_noun_dict (word, domain, source)
                VALUES (%s, %s, %s)
                ON CONFLICT (word, domain) DO UPDATE SET source = EXCLUDED.source
                RETURNING id, word, domain, source, created_at
                """,
                (word, domain, source),
            )
            after = cursor.fetchone()
    log_dictionary_audit(
        entity_type="compound_noun", entity_id=int(after["id"]) if after else None,
        action="upsert", before=None, after=after, actor=actor,
    )


def update_compound_noun_domain(item_id: int, domain: str, actor: str = "dashboard-admin") -> None:
    """복합명사 항목의 도메인을 변경하고 감사 로그를 기록한다."""
    before = fetch_compound_noun_item(item_id)
    if before is None:
        raise DictionaryItemNotFoundError("Compound noun not found")
    try:
        after = db_update_compound_noun_domain(item_id=item_id, domain=domain)
    except errors.UniqueViolation as exc:
        raise DictionaryDomainConflictError("Compound noun already exists in the target domain") from exc
    log_dictionary_audit(
        entity_type="compound_noun", entity_id=item_id,
        action="update_domain", before=before, after=after, actor=actor,
    )


def delete_compound_noun(item_id: int, actor: str = "dashboard-admin") -> None:
    """복합명사 항목을 사전에서 삭제하고 감사 로그를 기록한다."""
    before = fetch_compound_noun_item(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM compound_noun_dict WHERE id = %s", (item_id,))
    log_dictionary_audit(
        entity_type="compound_noun", entity_id=item_id,
        action="delete", before=before, after=None, actor=actor,
    )


# ── 복합명사 후보 ──────────────────────────────────────────────────────────────

def list_candidates_paged(*, page: int = 1, limit: int = 50, q: str = "", status: str = "", domain: str = "") -> dict[str, Any]:
    """복합명사 후보 목록을 상태·도메인 필터로 페이지네이션 조회한다."""
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    extra_clauses = ""
    if status and status != "all":
        extra_clauses += " AND status = %s"
        params.append(status)
    if domain and domain != "all":
        extra_clauses += " AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM compound_noun_candidates WHERE word ILIKE %s{extra_clauses}", params)
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, frequency, doc_count, first_seen_at, last_seen_at,
                       status, reviewed_at, reviewed_by, auto_decision, auto_checked_at, auto_evidence
                FROM compound_noun_candidates
                WHERE word ILIKE %s{extra_clauses}
                ORDER BY status ASC, frequency DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = [_compound_candidate_to_api(dict(row)) for row in cursor.fetchall()]
    return {"items": items, "total": total, "page": page, "limit": limit}


def review_compound_candidate(candidate_id: int, action: str, reviewed_by: str) -> None:
    """복합명사 후보를 승인/반려 처리하고 승인 시 사전에 등록한다."""
    before = fetch_compound_candidate_item(candidate_id)
    reviewed_at = _now_utc()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_candidates
                SET status = %s, reviewed_at = %s, reviewed_by = %s
                WHERE id = %s
                RETURNING id, word, frequency, doc_count, first_seen_at, last_seen_at, status, reviewed_at, reviewed_by
                """,
                (action, reviewed_at, reviewed_by, candidate_id),
            )
            row = cursor.fetchone()
            if row and action == "approved":
                cursor.execute(
                    """
                    INSERT INTO compound_noun_dict (word, domain, source)
                    VALUES (%s, %s, 'auto-approved')
                    ON CONFLICT (word, domain) DO NOTHING
                    """,
                    (row["word"], row.get("domain", "all")),
                )
    log_dictionary_audit(
        entity_type="compound_candidate", entity_id=candidate_id,
        action=action, before=before, after=row, actor=reviewed_by,
    )


# ── 불용어 ────────────────────────────────────────────────────────────────────

def list_stopwords_paged(*, page: int = 1, limit: int = 50, q: str = "", domain: str = "") -> dict[str, Any]:
    """불용어 사전을 검색·필터링하여 페이지네이션으로 반환한다."""
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    domain_clause = ""
    if domain and domain != "all":
        domain_clause = "AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM stopword_dict WHERE word ILIKE %s {domain_clause}", params)
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, language, created_at
                FROM stopword_dict
                WHERE word ILIKE %s {domain_clause}
                ORDER BY created_at DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = [_stopword_to_api(dict(row)) for row in cursor.fetchall()]
    return {"items": items, "total": total, "page": page, "limit": limit}


def create_stopword(word: str, language: str, actor: str = "dashboard-admin", domain: str = "all") -> dict[str, int]:
    """불용어를 사전에 추가하고 기존 키워드 데이터에서 해당 단어를 정리한다."""
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                INSERT INTO stopword_dict (word, domain, language)
                VALUES (%s, %s, %s)
                ON CONFLICT (word, domain, language) DO UPDATE SET language = EXCLUDED.language
                RETURNING id, word, domain, language, created_at
                """,
                (word, domain, language),
            )
            after = cursor.fetchone()
    log_dictionary_audit(
        entity_type="stopword", entity_id=int(after["id"]) if after else None,
        action="upsert", before=None, after=after, actor=actor,
    )
    return delete_keyword_data_for_stopword(word=word, domain=domain)


def update_stopword_domain(item_id: int, domain: str, actor: str = "dashboard-admin") -> None:
    """불용어 항목의 도메인을 변경하고 감사 로그를 기록한다."""
    before = fetch_stopword_item(item_id)
    if before is None:
        raise DictionaryItemNotFoundError("Stopword not found")
    try:
        after = db_update_stopword_domain(item_id=item_id, domain=domain)
    except errors.UniqueViolation as exc:
        raise DictionaryDomainConflictError("Stopword already exists in the target domain") from exc
    log_dictionary_audit(
        entity_type="stopword", entity_id=item_id,
        action="update_domain", before=before, after=after, actor=actor,
    )


def delete_stopword(item_id: int, actor: str = "dashboard-admin") -> None:
    """불용어 항목을 사전에서 삭제하고 감사 로그를 기록한다."""
    before = fetch_stopword_item(item_id)
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM stopword_dict WHERE id = %s", (item_id,))
    log_dictionary_audit(
        entity_type="stopword", entity_id=item_id,
        action="delete", before=before, after=None, actor=actor,
    )


# ── 불용어 후보 ───────────────────────────────────────────────────────────────

def list_stopword_candidates_paged(*, page: int = 1, limit: int = 50, q: str = "", status: str = "", domain: str = "") -> dict[str, Any]:
    """불용어 후보 목록을 상태·도메인 필터로 페이지네이션 조회한다."""
    offset = (page - 1) * limit
    like = f"%{q}%" if q else "%"
    params: list[Any] = [like]
    extra_clauses = ""
    if status and status != "all":
        extra_clauses += " AND status = %s"
        params.append(status)
    if domain and domain != "all":
        extra_clauses += " AND domain = %s"
        params.append(domain)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(f"SELECT COUNT(*) AS cnt FROM stopword_candidates WHERE word ILIKE %s{extra_clauses}", params)
            total = int(cursor.fetchone()["cnt"])
            cursor.execute(
                f"""
                SELECT id, word, domain, language, score, domain_breadth, repetition_rate,
                       trend_stability, cooccurrence_breadth, short_word, frequency,
                       status, first_seen_at, last_seen_at, reviewed_at, reviewed_by
                FROM stopword_candidates
                WHERE word ILIKE %s{extra_clauses}
                ORDER BY score DESC, word ASC
                LIMIT %s OFFSET %s
                """,
                params + [limit, offset],
            )
            items = [_stopword_candidate_to_api(dict(row)) for row in cursor.fetchall()]
    return {"items": items, "total": total, "page": page, "limit": limit}


def approve_stopword_candidate(candidate_id: int, reviewed_by: str) -> None:
    """불용어 후보를 승인하여 불용어 사전에 등록하고 감사 로그를 기록한다."""
    before = fetch_stopword_candidate_item(candidate_id)
    after = db_review_stopword_candidate(candidate_id, "approved", reviewed_by)
    log_dictionary_audit(
        entity_type="stopword_candidate", entity_id=candidate_id,
        action="approved", before=before, after=after, actor=reviewed_by,
    )


def reject_stopword_candidate(candidate_id: int, reviewed_by: str) -> None:
    """불용어 후보를 반려 처리하고 감사 로그를 기록한다."""
    before = fetch_stopword_candidate_item(candidate_id)
    after = db_review_stopword_candidate(candidate_id, "rejected", reviewed_by)
    log_dictionary_audit(
        entity_type="stopword_candidate", entity_id=candidate_id,
        action="rejected", before=before, after=after, actor=reviewed_by,
    )
