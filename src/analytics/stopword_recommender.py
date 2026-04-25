"""불용어 후보 자동 추천 배치 잡.

최근 7일 keyword_trends / keywords / keyword_relations 데이터를 기반으로
다중 신호 스코어를 계산해 stopword_candidates 테이블에 누적한다.

점수 구성 (합계 1.0):
  - domain_breadth      (0.30): 등장 도메인 수 / 전체 도메인 수  →  높을수록 범용어
  - repetition_rate     (0.20): 기사당 평균 반복 횟수 (5회 = 100%) →  높을수록 반복 충전어
  - trend_stability     (0.25): 1 - CV (시간 윈도우 CV 낮을수록 = 안정 = 지루)
  - cooccurrence_breadth(0.15): 공출현 키워드 종류 수 / 50 → 높을수록 범용 연결어
  - short_word          (0.10): 한국어 2글자 이하
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from psycopg2.extras import RealDictCursor

from core.logger import get_logger
from storage.db import get_connection

logger = get_logger(__name__)

WEIGHTS = {
    "domain_breadth": 0.30,
    "repetition_rate": 0.20,
    "trend_stability": 0.25,
    "cooccurrence_breadth": 0.15,
    "short_word": 0.10,
}
SCORE_THRESHOLD = 0.45
MIN_TOTAL_MENTIONS = 10
MAX_CANDIDATES = 500


def _total_domain_count() -> int:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM domain_catalog WHERE is_active = TRUE")
            return max(1, int(cursor.fetchone()[0]))


def _compute_scores(domain_count: int) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(
                """
                WITH base AS (
                    SELECT keyword, domain, SUM(keyword_count) AS total_count
                    FROM keyword_trends
                    WHERE window_start >= NOW() - INTERVAL '7 days'
                    GROUP BY keyword, domain
                    HAVING SUM(keyword_count) >= %(min_mentions)s
                ),
                domain_breadth_cte AS (
                    SELECT keyword,
                        LEAST(1.0, COUNT(DISTINCT domain)::float / %(domain_count)s) AS domain_breadth,
                        SUM(total_count) AS frequency
                    FROM base
                    GROUP BY keyword
                ),
                repetition_cte AS (
                    SELECT k.keyword,
                        LEAST(1.0, AVG(k.keyword_count)::float / 5.0) AS repetition_rate
                    FROM keywords k
                    JOIN domain_breadth_cte d ON d.keyword = k.keyword
                    GROUP BY k.keyword
                ),
                stability_cte AS (
                    SELECT kt.keyword,
                        CASE
                            WHEN AVG(kt.keyword_count) > 0
                            THEN GREATEST(0.0, LEAST(1.0,
                                1.0 - COALESCE(STDDEV(kt.keyword_count), 0) / AVG(kt.keyword_count)
                            ))
                            ELSE 0.0
                        END AS trend_stability
                    FROM keyword_trends kt
                    JOIN domain_breadth_cte d ON d.keyword = kt.keyword
                    WHERE kt.window_start >= NOW() - INTERVAL '7 days'
                    GROUP BY kt.keyword
                ),
                coocc_cte AS (
                    SELECT kw.keyword,
                        LEAST(1.0,
                            COUNT(DISTINCT CASE
                                WHEN kr.keyword_a = kw.keyword THEN kr.keyword_b
                                WHEN kr.keyword_b = kw.keyword THEN kr.keyword_a
                                ELSE NULL
                            END)::float / 50.0
                        ) AS cooccurrence_breadth
                    FROM domain_breadth_cte kw
                    LEFT JOIN keyword_relations kr
                        ON (kr.keyword_a = kw.keyword OR kr.keyword_b = kw.keyword)
                        AND kr.window_start >= NOW() - INTERVAL '7 days'
                    GROUP BY kw.keyword
                )
                SELECT
                    d.keyword,
                    d.frequency,
                    COALESCE(d.domain_breadth, 0) AS domain_breadth,
                    COALESCE(r.repetition_rate, 0) AS repetition_rate,
                    COALESCE(s.trend_stability, 0) AS trend_stability,
                    COALESCE(c.cooccurrence_breadth, 0) AS cooccurrence_breadth,
                    (LENGTH(d.keyword) <= 2) AS short_word
                FROM domain_breadth_cte d
                LEFT JOIN repetition_cte r ON r.keyword = d.keyword
                LEFT JOIN stability_cte s ON s.keyword = d.keyword
                LEFT JOIN coocc_cte c ON c.keyword = d.keyword
                ORDER BY d.domain_breadth DESC
                LIMIT %(max_candidates)s
                """,
                {
                    "min_mentions": MIN_TOTAL_MENTIONS,
                    "domain_count": domain_count,
                    "max_candidates": MAX_CANDIDATES,
                },
            )
            return list(cursor.fetchall())


def _excluded_words() -> set[str]:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT word FROM stopword_dict")
            words = {row[0] for row in cursor.fetchall()}
            cursor.execute("SELECT word FROM stopword_candidates WHERE status IN ('approved', 'rejected')")
            words |= {row[0] for row in cursor.fetchall()}
    return words


def _upsert_candidates(candidates: list[dict[str, Any]]) -> tuple[int, int]:
    now = datetime.now(timezone.utc)
    new_count = 0
    updated_count = 0
    insert_sql = """
        INSERT INTO stopword_candidates
            (word, domain, language, score, domain_breadth, repetition_rate,
             trend_stability, cooccurrence_breadth, short_word, frequency,
             first_seen_at, last_seen_at)
        VALUES (%s, 'all', 'ko', %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (word, domain, language) DO NOTHING
    """
    update_sql = """
        UPDATE stopword_candidates
        SET score = %s, domain_breadth = %s, repetition_rate = %s,
            trend_stability = %s, cooccurrence_breadth = %s,
            short_word = %s, frequency = %s, last_seen_at = %s
        WHERE word = %s AND domain = 'all' AND language = 'ko' AND status = 'needs_review'
    """
    with get_connection() as conn:
        with conn.cursor() as cursor:
            for c in candidates:
                cursor.execute(insert_sql, (
                    c["word"], c["score"],
                    c["domain_breadth"], c["repetition_rate"],
                    c["trend_stability"], c["cooccurrence_breadth"],
                    c["short_word"], c["frequency"], now, now,
                ))
                if cursor.rowcount > 0:
                    new_count += 1
                else:
                    cursor.execute(update_sql, (
                        c["score"], c["domain_breadth"], c["repetition_rate"],
                        c["trend_stability"], c["cooccurrence_breadth"],
                        c["short_word"], c["frequency"], now, c["word"],
                    ))
                    if cursor.rowcount > 0:
                        updated_count += 1
    return new_count, updated_count


def run_stopword_recommender() -> dict[str, int]:
    domain_count = _total_domain_count()
    rows = _compute_scores(domain_count)
    if not rows:
        logger.info("불용어 추천: 분석 대상 키워드 없음")
        return {"total_analyzed": 0, "candidates": 0, "new": 0, "updated": 0}

    excluded = _excluded_words()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        word = str(row["keyword"])
        if word in excluded:
            continue
        db = float(row["domain_breadth"] or 0)
        rr = float(row["repetition_rate"] or 0)
        ts = float(row["trend_stability"] or 0)
        cb = float(row["cooccurrence_breadth"] or 0)
        sw = bool(row["short_word"])
        score = (
            WEIGHTS["domain_breadth"] * db
            + WEIGHTS["repetition_rate"] * rr
            + WEIGHTS["trend_stability"] * ts
            + WEIGHTS["cooccurrence_breadth"] * cb
            + WEIGHTS["short_word"] * (1.0 if sw else 0.0)
        )
        if score >= SCORE_THRESHOLD:
            candidates.append({
                "word": word,
                "score": round(score, 4),
                "domain_breadth": round(db, 4),
                "repetition_rate": round(rr, 4),
                "trend_stability": round(ts, 4),
                "cooccurrence_breadth": round(cb, 4),
                "short_word": sw,
                "frequency": int(row["frequency"] or 0),
            })

    if not candidates:
        logger.info("불용어 추천: 임계값(%.2f) 이상 후보 없음", SCORE_THRESHOLD)
        return {"total_analyzed": len(rows), "candidates": 0, "new": 0, "updated": 0}

    new_count, updated_count = _upsert_candidates(candidates)
    logger.info(
        "불용어 추천 완료 | total_analyzed=%d | candidates=%d | new=%d | updated=%d",
        len(rows), len(candidates), new_count, updated_count,
    )
    return {
        "total_analyzed": len(rows),
        "candidates": len(candidates),
        "new": new_count,
        "updated": updated_count,
    }


if __name__ == "__main__":
    print(run_stopword_recommender())
