"""복합명사 후보 자동 평가 및 보수적 자동 승인.

정책:
    - approved/rejected 후보는 재검증하지 않는다.
    - needs_review 후보만 평가한다.
    - Free Dictionary API entries 존재 여부를 외부 근거로 사용한다.
    - high_confidence 후보만 approved 처리하고 compound_noun_dict에 반영한다.
    - 승인 여부와 관계없이 auto_score/auto_evidence/auto_checked_at/auto_decision을 저장한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests
from psycopg2.extras import Json, RealDictCursor

from core.logger import get_logger
from storage.db import get_connection

logger = get_logger(__name__)

FREE_DICTIONARY_BASE_URL = "https://freedictionaryapi.com/api/v1/entries/ko"
DEFAULT_LIMIT = 2000
DEFAULT_THRESHOLD = 85
DICTIONARY_TIMEOUT_SECONDS = 3.0

REVIEWER = "auto-reviewer"
DECISION_HIGH_CONFIDENCE = "high_confidence"
DECISION_NEEDS_MANUAL_REVIEW = "needs_manual_review"
DECISION_LOW_CONFIDENCE = "low_confidence"
DECISION_API_ERROR = "api_error"

_KOREAN_RE = re.compile(r"[가-힣]")
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


def _normalize_word(value: str) -> str:
    return _SPACE_RE.sub("", value or "").strip().lower()


def _fetch_compound_candidates_for_auto_review(limit: int) -> list[Candidate]:
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
            return [
                Candidate(
                    id=int(row["id"]),
                    word=str(row["word"]),
                    domain=str(row["domain"]),
                    frequency=int(row["frequency"] or 0),
                    doc_count=int(row["doc_count"] or 0),
                    last_seen_at=row.get("last_seen_at"),
                )
                for row in cursor.fetchall()
            ]


def _call_free_dictionary(word: str) -> dict[str, Any]:
    url = f"{FREE_DICTIONARY_BASE_URL}/{quote(word)}"
    try:
        response = requests.get(url, timeout=DICTIONARY_TIMEOUT_SECONDS)
        if response.status_code == 404:
            return {
                "ok": True,
                "error": None,
                "url": url,
                "word": word,
                "entries_count": 0,
                "has_entries": False,
                "parts_of_speech": [],
                "definitions": [],
                "source_url": None,
                "license": None,
            }
        if response.status_code != 200:
            return {
                "ok": False,
                "error": f"http_{response.status_code}",
                "url": url,
                "word": word,
                "entries_count": 0,
                "has_entries": False,
                "parts_of_speech": [],
                "definitions": [],
                "source_url": None,
                "license": None,
            }

        data = response.json()
        entries = data.get("entries") or []
        parts_of_speech = sorted(
            {
                str(entry.get("partOfSpeech"))
                for entry in entries
                if entry.get("partOfSpeech")
            }
        )
        definitions: list[str] = []
        for entry in entries[:3]:
            for sense in entry.get("senses") or []:
                definition = sense.get("definition")
                if definition:
                    definitions.append(str(definition))
                    break
            if len(definitions) >= 3:
                break

        source = data.get("source") or {}
        return {
            "ok": True,
            "error": None,
            "url": url,
            "word": data.get("word") or word,
            "entries_count": len(entries),
            "has_entries": len(entries) > 0,
            "parts_of_speech": parts_of_speech,
            "definitions": definitions,
            "source_url": source.get("url"),
            "license": source.get("license"),
        }
    except Exception as exc:  # noqa: BLE001 - batch job should keep processing remaining candidates
        logger.warning("Free Dictionary API error for %r: %s", word, exc)
        return {
            "ok": False,
            "error": exc.__class__.__name__,
            "url": url,
            "word": word,
            "entries_count": 0,
            "has_entries": False,
            "parts_of_speech": [],
            "definitions": [],
            "source_url": None,
            "license": None,
        }


def build_candidate_evidence(candidate: Candidate) -> dict[str, Any]:
    frequency_per_doc = round(candidate.frequency / max(candidate.doc_count, 1), 2)
    dictionary = _call_free_dictionary(candidate.word)
    return {
        "stats": {
            "frequency": candidate.frequency,
            "doc_count": candidate.doc_count,
            "frequency_per_doc": frequency_per_doc,
            "last_seen_at": candidate.last_seen_at.isoformat() if candidate.last_seen_at else None,
        },
        "free_dictionary": dictionary,
    }


def score_candidate(candidate: Candidate, evidence: dict[str, Any]) -> tuple[int, dict[str, int]]:
    stats = evidence["stats"]
    dictionary = evidence["free_dictionary"]

    frequency_score = min(int(stats["frequency"]), 20)
    doc_count_score = min(int(stats["doc_count"]) * 4, 20)
    recent_score = 5 if candidate.last_seen_at else 0

    external_score = 0
    if dictionary["has_entries"]:
        external_score += 35
    if dictionary["entries_count"] > 1:
        external_score += min(dictionary["entries_count"], 5)
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
    if _normalize_word(candidate.word) != _normalize_word(str(dictionary.get("word") or candidate.word)):
        penalty -= 5

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
    dictionary = evidence["free_dictionary"]

    if not dictionary["ok"]:
        return DECISION_API_ERROR
    if score >= threshold and candidate.doc_count >= 3 and candidate.frequency >= 5 and dictionary[
        "has_entries"
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
                return False

            cursor.execute(
                """
                INSERT INTO compound_noun_dict (word, domain, source)
                VALUES (%s, %s, 'auto-approved')
                ON CONFLICT (word, domain) DO NOTHING
                """,
                (candidate.word, candidate.domain),
            )
            return True


def run_auto_review(limit: int = DEFAULT_LIMIT, threshold: int = DEFAULT_THRESHOLD) -> dict[str, int]:
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

    for candidate in candidates:
        evidence = build_candidate_evidence(candidate)
        score, breakdown = score_candidate(candidate, evidence)
        evidence["score_breakdown"] = breakdown
        evidence["review_policy"] = {
            "threshold": threshold,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "frequency_min": 5,
            "doc_count_min": 3,
            "frequency_per_doc_max": 8,
            "external_evidence": "free_dictionary_entries",
        }
        decision = decide_candidate(candidate, evidence, score, threshold)

        if decision == DECISION_HIGH_CONFIDENCE:
            if _approve_compound_candidate_from_auto_review(
                candidate=candidate,
                score=score,
                evidence=evidence,
            ):
                counts["auto_approved"] += 1
                logger.info("auto_review approved: %s score=%d", candidate.word, score)
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

    logger.info("복합명사 자동 평가 완료: %s", counts)
    return counts


if __name__ == "__main__":
    print(run_auto_review())
