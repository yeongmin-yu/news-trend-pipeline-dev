"""복합명사 후보 자동 승인 배치 잡.

compound_noun_candidates 중 검토 대기 항목을 대상으로
네이버 백과사전 API를 호출한다.
 - 검색 결과가 있으면 → approved + compound_noun_dict 에 삽입
 - 검색 결과가 없거나 API 오류이면 → needs_review 유지

참고:
    현재 표준 검토 대기 상태는 ``needs_review``이다.
    과거 DB에 남아 있을 수 있는 legacy ``pending`` 상태도 함께 조회한다.
"""

from __future__ import annotations

from typing import Any

import requests

from core.config import settings
from core.logger import get_logger
from storage.db import get_connection

logger = get_logger(__name__)

NAVER_ENCYC_URL = "https://openapi.naver.com/v1/search/encyc.json"
BATCH_LIMIT = 200
REVIEW_PENDING_STATUSES = ("needs_review", "pending")


def _call_naver_encyc(word: str) -> bool:
    if not settings.naver_client_id or not settings.naver_client_secret:
        logger.warning("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 미설정 — 자동 승인 불가")
        return False
    try:
        resp = requests.get(
            NAVER_ENCYC_URL,
            params={"query": word, "display": 1},
            headers={
                "X-Naver-Client-Id": settings.naver_client_id,
                "X-Naver-Client-Secret": settings.naver_client_secret,
            },
            timeout=3.0,
        )
        if resp.status_code == 200:
            return int(resp.json().get("total", 0)) > 0
        logger.warning("Naver Encyc API HTTP %d for %r", resp.status_code, word)
    except Exception as exc:
        logger.warning("Naver Encyc API error for %r: %s", word, exc)
    return False


def _fetch_pending_candidates() -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, status
                FROM compound_noun_candidates
                WHERE status = ANY(%s)
                ORDER BY frequency DESC
                LIMIT %s
                """,
                (list(REVIEW_PENDING_STATUSES), BATCH_LIMIT),
            )
            return [
                {"id": row[0], "word": row[1], "domain": row[2], "status": row[3]}
                for row in cursor.fetchall()
            ]


def _set_auto_approved(candidate_id: int, word: str, domain: str) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_candidates
                SET status = 'approved',
                    reviewed_at = NOW(),
                    reviewed_by = 'auto-approver'
                WHERE id = %s
                """,
                (candidate_id,),
            )
            cursor.execute(
                """
                INSERT INTO compound_noun_dict (word, domain, source)
                VALUES (%s, %s, 'auto-approved')
                ON CONFLICT (word, domain) DO NOTHING
                """,
                (word, domain),
            )


def _set_needs_review(candidate_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_candidates
                SET status = 'needs_review'
                WHERE id = %s AND status = 'pending'
                """,
                (candidate_id,),
            )


def run_compound_auto_approve() -> dict[str, int]:
    candidates = _fetch_pending_candidates()
    if not candidates:
        logger.info("자동 승인 대상 후보 없음")
        return {"total": 0, "auto_approved": 0, "needs_review": 0}

    auto_approved = 0
    needs_review = 0

    for c in candidates:
        found = _call_naver_encyc(c["word"])
        if found:
            _set_auto_approved(c["id"], c["word"], c["domain"])
            auto_approved += 1
            logger.info("auto_approved: %s", c["word"])
        else:
            _set_needs_review(c["id"])
            needs_review += 1

    logger.info(
        "복합명사 자동 승인 완료 | total=%d | auto_approved=%d | needs_review=%d",
        len(candidates), auto_approved, needs_review,
    )
    return {"total": len(candidates), "auto_approved": auto_approved, "needs_review": needs_review}


if __name__ == "__main__":
    print(run_compound_auto_approve())
