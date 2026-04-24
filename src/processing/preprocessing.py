from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from functools import lru_cache
from pathlib import Path

try:
    from kiwipiepy import Kiwi
except ImportError:  # pragma: no cover
    Kiwi = None

from core.config import settings
from core.logger import get_logger


# DB를 사용할 수 없는 환경의 fallback 불용어
_KOREAN_STOPWORDS_DEFAULT: frozenset[str] = frozenset({
    "기자",
    "뉴스",
    "이번",
    "지난",
    "통해",
    "대한",
    "관련",
    "위해",
    "대해",
    "경우",
    "이후",
    "이날",
    "오전",
    "오후",
    "사진",
    "정도",
    "가장",
    "때문",
    "지난해",
    "올해",
    "기사",
    "제공",
    "사용",
    "진행",
    "기준",
    "중심",
    "사업",
    "기업",
    "서비스",
    "시장",
    "기술",
    "최근",
    "예정",
    "대표",
    "이상",
    "이하",
    "모든",
    "부분",
    "현장",
    "내용",
    "결과",
    "발표",
    "계획",
    "설명",
})

KOREAN_TOKEN_PATTERN = r"[\uAC00-\uD7A3]+"
KOREAN_NOUN_TAGS = {"NNG", "NNP"}
DEFAULT_DICT_PATH = Path(__file__).resolve().parents[1] / "core" / "korean_user_dict.txt"
KOREAN_USER_DICT_PATH = Path(os.getenv("KOREAN_USER_DICT_PATH", str(DEFAULT_DICT_PATH)))
USER_WORD_SCORE = 5.0
logger = get_logger(__name__)
_DICTIONARY_VERSION_NAMES = ("compound_noun_dict", "stopword_dict")
_dictionary_refresh_lock = threading.Lock()
_cached_dictionary_versions: dict[str, int] | None = None
_last_dictionary_version_check_at = 0.0


# ---------------------------------------------------------------------------
# 사전 로딩 — DB 우선, 실패 시 파일/기본값 fallback
# ---------------------------------------------------------------------------


def _clear_dictionary_caches() -> None:
    get_user_dictionary.cache_clear()
    get_user_dictionary_set.cache_clear()
    _get_max_compound_len.cache_clear()
    get_kiwi.cache_clear()
    _get_stopwords.cache_clear()


def _refresh_dictionary_caches_if_needed(*, force: bool = False) -> None:
    global _cached_dictionary_versions
    global _last_dictionary_version_check_at

    now = time.monotonic()
    refresh_interval = max(settings.dictionary_refresh_interval_seconds, 1)
    if not force and (now - _last_dictionary_version_check_at) < refresh_interval:
        return

    with _dictionary_refresh_lock:
        now = time.monotonic()
        if not force and (now - _last_dictionary_version_check_at) < refresh_interval:
            return

        _last_dictionary_version_check_at = now
        try:
            from storage.db import fetch_dictionary_versions  # noqa: PLC0415

            latest_versions = fetch_dictionary_versions()
        except Exception as exc:  # pragma: no cover
            logger.debug("Dictionary version check skipped: %s", exc)
            return

        normalized_versions = {
            name: int(latest_versions.get(name, 1))
            for name in _DICTIONARY_VERSION_NAMES
        }

        if _cached_dictionary_versions is None:
            _cached_dictionary_versions = normalized_versions
            logger.info("Dictionary versions initialized: %s", normalized_versions)
            return

        if normalized_versions == _cached_dictionary_versions:
            return

        previous_versions = _cached_dictionary_versions
        _clear_dictionary_caches()
        _cached_dictionary_versions = normalized_versions
        logger.info(
            "Dictionary versions changed: %s -> %s. Reloading cached dictionaries.",
            previous_versions,
            normalized_versions,
        )

def _load_user_dictionary_from_file(path: Path = KOREAN_USER_DICT_PATH) -> list[str]:
    """텍스트 파일에서 복합명사 목록을 로드한다 (fallback용)."""
    if not path.exists():
        return []
    words: list[str] = []
    seen: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        normalized = unicodedata.normalize("NFC", line)
        if not re.fullmatch(KOREAN_TOKEN_PATTERN, normalized):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        words.append(normalized)
    return words


@lru_cache(maxsize=1)
def get_user_dictionary() -> tuple[str, ...]:
    """DB에서 승인된 복합명사를 로드한다. DB 불가 시 파일 fallback."""
    try:
        # db.py가 preprocessing.py를 import하므로 순환 참조 방지를 위해 lazy import
        from storage.db import fetch_compound_nouns  # noqa: PLC0415
        words = fetch_compound_nouns()
        if words:
            return tuple(words)
    except Exception:
        pass
    return tuple(_load_user_dictionary_from_file())


@lru_cache(maxsize=1)
def get_user_dictionary_set() -> frozenset[str]:
    return frozenset(get_user_dictionary())


@lru_cache(maxsize=1)
def _get_max_compound_len() -> int:
    user_words = get_user_dictionary()
    if not user_words:
        return 0
    max_chars = max(len(word) for word in user_words)
    return min(max(max_chars, 2), 6)


@lru_cache(maxsize=1)
def get_kiwi() -> Kiwi | None:
    if Kiwi is None:
        return None
    kiwi = Kiwi()
    for word in get_user_dictionary():
        try:
            kiwi.add_user_word(word, "NNP", USER_WORD_SCORE)
        except Exception:  # pragma: no cover
            continue
    return kiwi


@lru_cache(maxsize=1)
def _get_stopwords() -> frozenset[str]:
    """DB에서 불용어를 로드한다. DB 불가 시 기본값 fallback."""
    try:
        from storage.db import fetch_stopwords  # noqa: PLC0415
        words = fetch_stopwords(language="ko")
        if words:
            return frozenset(words)
    except Exception:
        pass
    return _KOREAN_STOPWORDS_DEFAULT


# ---------------------------------------------------------------------------
# 복합명사 병합
# ---------------------------------------------------------------------------

def merge_compound_nouns(
    tokens: list[str],
    user_dict: frozenset[str] | None = None,
    spans: list[tuple[int, int]] | None = None,
) -> list[str]:
    if not tokens:
        return tokens
    if user_dict is None:
        user_dict = get_user_dictionary_set()
    if not user_dict:
        return tokens

    max_window = _get_max_compound_len() or 3
    result: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        merged_here = False
        upper = min(max_window, n - i)
        for window_size in range(upper, 1, -1):
            if spans is not None:
                contiguous = all(spans[j][1] == spans[j + 1][0] for j in range(i, i + window_size - 1))
                if not contiguous:
                    continue
            candidate = "".join(tokens[i : i + window_size])
            if candidate in user_dict:
                result.append(candidate)
                i += window_size
                merged_here = True
                break
        if not merged_here:
            result.append(tokens[i])
            i += 1
    return result


# ---------------------------------------------------------------------------
# 텍스트 정제 및 토큰화
# ---------------------------------------------------------------------------

def clean_text(text: str | None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\+\d+\s+chars\]", " ", text)
    text = text.lower()
    text = re.sub(r"[^\uAC00-\uD7A3\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str | None) -> list[str]:
    _refresh_dictionary_caches_if_needed()
    cleaned = clean_text(text)
    stopwords = _get_stopwords()
    kiwi = get_kiwi()
    if kiwi is not None:
        raw_nouns: list[str] = []
        raw_spans: list[tuple[int, int]] = []
        for token in kiwi.tokenize(cleaned):
            normalized = unicodedata.normalize("NFC", token.form)
            if token.tag in KOREAN_NOUN_TAGS and re.fullmatch(KOREAN_TOKEN_PATTERN, normalized):
                raw_nouns.append(normalized)
                raw_spans.append((token.start, token.start + token.len))
        merged = merge_compound_nouns(raw_nouns, get_user_dictionary_set(), spans=raw_spans)
        nouns = [token for token in merged if len(token) > 1 and token not in stopwords]
        if nouns:
            return nouns

    fallback_tokens = [
        token
        for token in cleaned.split()
        if token and token not in stopwords and len(token) > 1 and re.fullmatch(KOREAN_TOKEN_PATTERN, token)
    ]
    merged_fallback = merge_compound_nouns(fallback_tokens, get_user_dictionary_set())
    return [token for token in merged_fallback if len(token) > 1 and token not in stopwords]
