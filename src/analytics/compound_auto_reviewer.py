"""복합명사 후보 자동 평가 및 보수적 자동 승인.

정책:
    - approved/rejected 후보는 재검증하지 않는다.
    - needs_review 후보만 평가한다.
    - Naver Web Search API 결과에서 공백 제거 후 후보 단어와 완전 일치하는 항목을 외부 근거로 사용한다.
    - high_confidence 후보만 approved 처리하고 compound_noun_dict에 반영한다.
    - 승인 여부와 관계없이 auto_score/auto_evidence/auto_checked_at/auto_decision을 저장한다.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests
from psycopg2.extras import Json, RealDictCursor

from core.config import settings
from core.logger import get_logger
from storage.db import get_connection

logger = get_logger(__name__)

NAVER_WEBKR_URL = "https://openapi.naver.com/v1/search/webkr.json"
DEFAULT_LIMIT = 2000
DEFAULT_THRESHOLD = 85
NAVER_DISPLAY = 10
NAVER_TIMEOUT_SECONDS = 3.0

REVIEWER = "auto-reviewer"
DECISION_HIGH_CONFIDENCE = "high_confidence"
DECISION_NEEDS_MANUAL_REVIEW = "needs_manual_review"
DECISION_LOW_CONFIDENCE = "low_confidence"
DECISION_API_ERROR = "api_error"

_KOREAN_RE = re.compile(r"[가-힣]")
_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")

GENERIC_STOPWORDS = {
    "관련",
    "기반",
    "기술",
    "기업",
    "뉴스",
    "대한",
    "분야",
    "시장",
    "정부",
    "지원",
    "추진",
    "확대",
}


@dataclass(frozen=True)
class Candidate:
    id: int
    word: str
    domain: str
    frequency: int
    doc_count: int
    last_seen_at: datetime | None


def _clean_html(value: str | None) -> str:
    if not value:
        return ""
    return html.unescape(_TAG_RE.sub("", value)).strip()


def _compact(value: str | None) -> str:
    return _SPACE_RE.sub("", _clean_html(value)).lower()


def _fetch_compound_candidates_for_auto_review(limit: int) -> list[Candidate]:
    logger.info("auto_review fetch candidates start | limit=%d", limit)
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                SELECT id, word, domain, frequency, doc_count, last_seen_at
                FROM compound_noun_candidates
                WHERE status = 'needs_review'
                  AND (
                    auto_checked_at IS NULL
                    OR auto_checked_at < NOW() - INTERVAL '7 days'
                    OR last_seen_at > auto_checked_at
                  )
                ORDER BY frequency DESC, doc_count DESC, last_seen_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            logger.info("auto_review fetch candidates done | count=%d", len(rows))
            return [
                Candidate(
                    id=int(row["id"]),
                    word=str(row["word"]),
                    domain=str(row["domain"]),
                    frequency=int(row["frequency"] or 0),
                    doc_count=int(row["doc_count"] or 0),
                    last_seen_at=row.get("last_seen_at"),
                )
                for row in rows
            ]


def _call_naver_webkr(word: str) -> dict[str, Any]:
    started_at = time.monotonic()
    compact_word = _compact(word)
    logger.info("naver_webkr request start | word=%r | compact_word=%r", word, compact_word)

    if not settings.naver_client_id or not settings.naver_client_secret:
        logger.warning("naver_webkr request skipped | word=%r | reason=missing_credentials", word)
        return {
            "ok": False,
            "error": "missing_credentials",
            "total": 0,
            "display": 0,
            "has_exact_compact_match": False,
            "matched_title": None,
            "matched_description": None,
            "matched_link": None,
            "matched_field": None,
            "items": [],
        }

    try:
        response = requests.get(
            NAVER_WEBKR_URL,
            params={"query": word, "display": NAVER_DISPLAY},
            headers={
                "X-Naver-Client-Id": settings.naver_client_id,
                "X-Naver-Client-Secret": settings.naver_client_secret,
            },
            timeout=NAVER_TIMEOUT_SECONDS,
        )
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        if response.status_code != 200:
            logger.warning(
                "naver_webkr request failed | word=%r | status=%d | elapsed_ms=%d",
                word,
                response.status_code,
                elapsed_ms,
            )
            return {
                "ok": False,
                "error": f"http_{response.status_code}",
                "total": 0,
                "display": 0,
                "has_exact_compact_match": False,
                "matched_title": None,
                "matched_description": None,
                "matched_link": None,
                "matched_field": None,
                "items": [],
            }

        data = response.json()
        items = data.get("items") or []
        normalized_items: list[dict[str, str]] = []
        matched_title: str | None = None
        matched_description: str | None = None
        matched_link: str | None = None
        matched_field: str | None = None

        for item in items:
            title = _clean_html(item.get("title"))
            description = _clean_html(item.get("description"))
            link = str(item.get("link") or "")
            compact_title = _compact(title)
            compact_description = _compact(description)
            normalized_items.append(
                {
                    "title": title,
                    "description": description,
                    "link": link,
                    "title_compact": compact_title,
                    "description_compact": compact_description,
                }
            )
            if compact_word and compact_word in compact_title:
                matched_title = title
                matched_description = description
                matched_link = link
                matched_field = "title"
                break
            if compact_word and compact_word in compact_description:
                matched_title = title
                matched_description = description
                matched_link = link
                matched_field = "description"
                break

        has_match = matched_field is not None
        logger.info(
            "naver_webkr request done | word=%r | status=200 | total=%d | items=%d | exact_compact_match=%s | matched_field=%s | elapsed_ms=%d",
            word,
            int(data.get("total") or 0),
            len(items),
            has_match,
            matched_field,
            elapsed_ms,
        )
        return {
            "ok": True,
            "error": None,
            "total": int(data.get("total") or 0),
            "display": int(data.get("display") or len(items)),
            "has_exact_compact_match": has_match,
            "matched_title": matched_title,
            "matched_description": matched_description,
            "matched_link": matched_link,
            "matched_field": matched_field,
            "items": normalized_items[:3],
        }
    except Exception as exc:  # noqa: BLE001 - batch job should keep processing remaining candidates
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
        logger.warning("naver_webkr request error | word=%r | error=%s | elapsed_ms=%d", word, exc, elapsed_ms)
        return {
            "ok": False,
            "error": exc.__class__.__name__,
            "total": 0,
            "display": 0,
            "has_exact_compact_match": False,
            "matched_title": None,
            "matched_description": None,
            "matched_link": None,
            "matched_field": None,
            "items": [],
        }


def build_candidate_evidence(candidate: Candidate) -> dict[str, Any]:
    frequency_per_doc = round(candidate.frequency / max(candidate.doc_count, 1), 2)
    naver_webkr = _call_naver_webkr(candidate.word)
    return {
        "stats": {
            "frequency": candidate.frequency,
            "doc_count": candidate.doc_count,
            "frequency_per_doc": frequency_per_doc,
            "last_seen_at": candidate.last_seen_at.isoformat() if candidate.last_seen_at else None,
        },
        "naver_webkr": naver_webkr,
    }


def score_candidate(candidate: Candidate, evidence: dict[str, Any]) -> tuple[int, dict[str, int]]:
    stats = evidence["stats"]
    webkr = evidence["naver_webkr"]

    frequency_score = min(int(stats["frequency"]), 20)
    doc_count_score = min(int(stats["doc_count"]) * 4, 20)
    recent_score = 5 if candidate.last_seen_at else 0

    external_score = 0
    if int(webkr["total"] or 0) > 0:
        external_score += min(int(webkr["total"]), 10)
    if webkr["has_exact_compact_match"]:
        external_score += 30
    external_score = min(external_score, 40)

    penalty = 0
    if len(candidate.word.strip()) <= 1:
        penalty -= 20
    if len(candidate.word.strip()) == 2:
        penalty -= 5
    if float(stats["frequency_per_doc"]) > 8:
        penalty -= 15
    if candidate.word.strip() in GENERIC_STOPWORDS:
        penalty -= 20
    if not _KOREAN_RE.search(candidate.word):
        penalty -= 10

    total = max(0, min(100, frequency_score + doc_count_score + recent_score + external_score + penalty))
    return total, {
        "frequency": frequency_score,
        "doc_count": doc_count_score,
        "recent_activity": recent_score,
        "external_evidence": external_score,
        "penalty": penalty,
    }


def decide_candidate(candidate: Candidate, evidence: dict[str, Any], score: int, threshold: int) -> str:
    stats = evidence["stats"]
    webkr = evidence["naver_webkr"]

    if not webkr["ok"]:
        return DECISION_API_ERROR
    if score >= threshold and candidate.doc_count >= 3 and candidate.frequency >= 5 and webkr[
        "has_exact_compact_match"
    ] and float(stats["frequency_per_doc"]) <= 8:
        return DECISION_HIGH_CONFIDENCE
    if score < 50:
        return DECISION_LOW_CONFIDENCE
    return DECISION_NEEDS_MANUAL_REVIEW


def _update_compound_candidate_auto_review(
    *,
    candidate_id: int,
    score: int,
    evidence: dict[str, Any],
    decision: str,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_candidates
                SET auto_score = %s,
                    auto_evidence = %s,
                    auto_checked_at = NOW(),
                    auto_decision = %s
                WHERE id = %s
                  AND status = 'needs_review'
                """,
                (score, Json(evidence), decision, candidate_id),
            )
    logger.info(
        "auto_review saved | candidate_id=%d | score=%d | decision=%s",
        candidate_id,
        score,
        decision,
    )


def _approve_compound_candidate_from_auto_review(
    *,
    candidate: Candidate,
    score: int,
    evidence: dict[str, Any],
) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE compound_noun_candidates
                SET status = 'approved',
                    reviewed_at = NOW(),
                    reviewed_by = %s,
                    auto_score = %s,
                    auto_evidence = %s,
                    auto_checked_at = NOW(),
                    auto_decision = %s
                WHERE id = %s
                  AND status = 'needs_review'
                """,
                (REVIEWER, score, Json(evidence), DECISION_HIGH_CONFIDENCE, candidate.id),
            )
            if cursor.rowcount == 0:
                logger.info(
                    "auto_review approve skipped | candidate_id=%d | word=%r | reason=status_changed",
                    candidate.id,
                    candidate.word,
                )
                return False

            cursor.execute(
                """
                INSERT INTO compound_noun_dict (word, domain, source)
                VALUES (%s, %s, 'auto-approved')
                ON CONFLICT (word, domain) DO NOTHING
                """,
                (candidate.word, candidate.domain),
            )
            logger.info(
                "auto_review approved and inserted dict | candidate_id=%d | word=%r | domain=%s | score=%d",
                candidate.id,
                candidate.word,
                candidate.domain,
                score,
            )
            return True


def run_auto_review(limit: int = DEFAULT_LIMIT, threshold: int = DEFAULT_THRESHOLD) -> dict[str, int]:
    logger.info("auto_review start | limit=%d | threshold=%d", limit, threshold)
    started_at = time.monotonic()
    candidates = _fetch_compound_candidates_for_auto_review(limit)
    if not candidates:
        logger.info("자동 평가 대상 복합명사 후보 없음")
        return {
            "total": 0,
            "auto_approved": 0,
            "needs_manual_review": 0,
            "low_confidence": 0,
            "api_error": 0,
        }

    counts = {
        "total": len(candidates),
        "auto_approved": 0,
        "needs_manual_review": 0,
        "low_confidence": 0,
        "api_error": 0,
    }

    for index, candidate in enumerate(candidates, start=1):
        logger.info(
            "auto_review candidate start | index=%d/%d | candidate_id=%d | word=%r | domain=%s | frequency=%d | doc_count=%d",
            index,
            len(candidates),
            candidate.id,
            candidate.word,
            candidate.domain,
            candidate.frequency,
            candidate.doc_count,
        )
        candidate_started_at = time.monotonic()
        evidence = build_candidate_evidence(candidate)
        score, breakdown = score_candidate(candidate, evidence)
        evidence["score_breakdown"] = breakdown
        evidence["review_policy"] = {
            "threshold": threshold,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "frequency_min": 5,
            "doc_count_min": 3,
            "frequency_per_doc_max": 8,
            "external_evidence": "naver_webkr_exact_compact_match",
        }
        decision = decide_candidate(candidate, evidence, score, threshold)
        webkr = evidence["naver_webkr"]

        logger.info(
            "auto_review candidate decision | index=%d/%d | candidate_id=%d | word=%r | score=%d | decision=%s | total=%d | exact_compact_match=%s | matched_field=%s | elapsed_ms=%d",
            index,
            len(candidates),
            candidate.id,
            candidate.word,
            score,
            decision,
            webkr["total"],
            webkr["has_exact_compact_match"],
            webkr["matched_field"],
            int((time.monotonic() - candidate_started_at) * 1000),
        )

        if decision == DECISION_HIGH_CONFIDENCE:
            if _approve_compound_candidate_from_auto_review(
                candidate=candidate,
                score=score,
                evidence=evidence,
            ):
                counts["auto_approved"] += 1
            continue

        _update_compound_candidate_auto_review(
            candidate_id=candidate.id,
            score=score,
            evidence=evidence,
            decision=decision,
        )
        if decision == DECISION_API_ERROR:
            counts["api_error"] += 1
        elif decision == DECISION_LOW_CONFIDENCE:
            counts["low_confidence"] += 1
        else:
            counts["needs_manual_review"] += 1

        if index % 50 == 0 or index == len(candidates):
            logger.info("auto_review progress | processed=%d/%d | counts=%s", index, len(candidates), counts)

    logger.info(
        "복합명사 자동 평가 완료 | counts=%s | elapsed_sec=%.2f",
        counts,
        time.monotonic() - started_at,
    )
    return counts


if __name__ == "__main__":
    print(run_auto_review())
