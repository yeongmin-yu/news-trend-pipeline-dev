"""복합명사 후보 자동 추출 배치 잡.

수집된 뉴스 기사에서 인접한 명사 형태소 시퀀스를 탐색해
일정 빈도 이상 등장한 조합을 compound_noun_candidates 테이블에 누적한다.

실행 흐름:
    run_extraction_job()
        ↓
    fetch_articles_for_extraction()   ← news_raw에서 기사 조회
        ↓
    _extract_candidates()             ← Kiwi 무사전 형태소 분석 + 스팬 인접 조합
        ↓
    upsert_compound_candidates()      ← 신규 INSERT / pending 기존 누적 UPDATE
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from core.config import settings
from core.logger import get_logger
from processing.preprocessing import KOREAN_TOKEN_PATTERN, KOREAN_NOUN_TAGS
from storage.db import (
    fetch_articles_for_extraction,
    fetch_compound_nouns,
    upsert_compound_candidates,
)

try:
    from kiwipiepy import Kiwi
except ImportError:  # pragma: no cover
    Kiwi = None

logger = get_logger(__name__)
DEFAULT_DOMAIN = "all"


def _build_raw_kiwi() -> Any | None:
    """사용자 사전 없이 Kiwi를 초기화한다.

    기존 compound_noun_dict 단어들은 의도적으로 등록하지 않아
    아직 사전에 없는 새 복합명사 후보가 형태소로 분리되도록 한다.
    """
    if Kiwi is None:
        return None
    return Kiwi()


def _clean_for_extraction(text: str) -> str:
    """추출용 텍스트 정제 — 한글과 공백만 남긴다."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\+\d+\s+chars\]", " ", text)
    text = text.lower()
    text = re.sub(r"[^\uAC00-\uD7A3\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_domain(value: Any) -> str:
    domain = str(value or "").strip()
    return domain or DEFAULT_DOMAIN


def _extract_candidates(
    articles: list[dict[str, Any]],
    min_frequency: int,
    min_char_length: int,
    max_morpheme_count: int,
    excluded_words: set[str],
) -> dict[str, dict[str, tuple[int, int]]]:
    """기사 목록에서 domain별 복합명사 후보를 추출한다.

    Returns:
        {domain: {word: (total_count, doc_count)}} — 빈도 조건을 통과한 후보 맵.
    """
    kiwi = _build_raw_kiwi()
    if kiwi is None:
        logger.warning("Kiwi를 사용할 수 없어 복합명사 추출을 건너뜁니다")
        return {}

    total_counts: dict[str, Counter[str]] = defaultdict(Counter)
    doc_counts: dict[str, Counter[str]] = defaultdict(Counter)

    for article in articles:
        domain = _normalize_domain(article.get("domain"))
        text = " ".join(
            part
            for part in (
                article.get("title"),
                article.get("summary"),
            )
            if part
        )
        cleaned = _clean_for_extraction(text)
        if not cleaned:
            continue

        tokens = kiwi.tokenize(cleaned)
        noun_tokens: list[tuple[str, int, int]] = []
        for t in tokens:
            form = unicodedata.normalize("NFC", t.form)
            if t.tag in KOREAN_NOUN_TAGS and re.fullmatch(KOREAN_TOKEN_PATTERN, form):
                noun_tokens.append((form, t.start, t.start + t.len))

        article_words: set[str] = set()
        n = len(noun_tokens)

        for i in range(n):
            for count in range(2, max_morpheme_count + 1):
                if i + count > n:
                    break
                contiguous = all(
                    noun_tokens[j][2] == noun_tokens[j + 1][1]
                    for j in range(i, i + count - 1)
                )
                if not contiguous:
                    break
                compound = "".join(t[0] for t in noun_tokens[i : i + count])
                if len(compound) >= min_char_length and compound not in excluded_words:
                    total_counts[domain][compound] += 1
                    article_words.add(compound)

        for word in article_words:
            doc_counts[domain][word] += 1

    return {
        domain: {
            word: (counts[word], doc_counts[domain][word])
            for word in counts
            if counts[word] >= min_frequency
        }
        for domain, counts in total_counts.items()
    }


def run_extraction_job(
    window_days: int | None = None,
    min_frequency: int | None = None,
    min_char_length: int | None = None,
    max_morpheme_count: int | None = None,
    until: datetime | None = None,
) -> dict[str, int]:
    _window_days = window_days if window_days is not None else settings.compound_extraction_window_days
    _min_freq = min_frequency if min_frequency is not None else settings.compound_extraction_min_frequency
    _min_len = min_char_length if min_char_length is not None else settings.compound_extraction_min_char_length
    _max_morph = max_morpheme_count if max_morpheme_count is not None else settings.compound_extraction_max_morpheme_count

    until_dt = until or datetime.now(timezone.utc)
    since_dt = until_dt - timedelta(days=_window_days)

    logger.info(
        "복합명사 후보 추출 시작 | window=%dd | since=%s | until=%s | min_freq=%d | min_len=%d",
        _window_days,
        since_dt.isoformat(),
        until_dt.isoformat(),
        _min_freq,
        _min_len,
    )

    articles = fetch_articles_for_extraction(since_dt, until_dt)
    if not articles:
        logger.info("분석 대상 기사 없음. 추출을 종료합니다")
        return {"article_count": 0, "candidate_count": 0, "new_count": 0, "updated_count": 0}

    logger.info("분석 대상 기사 %d건", len(articles))

    excluded: set[str] = set(fetch_compound_nouns())

    candidates_by_domain = _extract_candidates(
        articles,
        min_frequency=_min_freq,
        min_char_length=_min_len,
        max_morpheme_count=_max_morph,
        excluded_words=excluded,
    )

    candidate_count = sum(len(candidates) for candidates in candidates_by_domain.values())
    logger.info("추출된 후보 %d건 (빈도 기준 통과)", candidate_count)

    new_count = 0
    updated_count = 0
    for domain, candidates in candidates_by_domain.items():
        if not candidates:
            continue
        domain_new_count, domain_updated_count = upsert_compound_candidates(candidates, domain=domain)
        new_count += domain_new_count
        updated_count += domain_updated_count
        logger.info(
            "domain=%s 후보 반영 완료 | 신규=%d | 빈도누적=%d | 후보=%d",
            domain,
            domain_new_count,
            domain_updated_count,
            len(candidates),
        )

    result = {
        "article_count": len(articles),
        "candidate_count": candidate_count,
        "new_count": new_count,
        "updated_count": updated_count,
    }
    logger.info(
        "추출 완료 | 신규=%d | 빈도누적=%d | 총후보=%d",
        new_count,
        updated_count,
        candidate_count,
    )
    return result


if __name__ == "__main__":
    result = run_extraction_job()
    print(result)
