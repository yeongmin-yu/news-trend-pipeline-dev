from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

try:
    from kiwipiepy import Kiwi
except ImportError:  # pragma: no cover
    Kiwi = None

try:
    import spacy
except ImportError:  # pragma: no cover
    spacy = None


ENGLISH_STOPWORDS = {
    "a",
    "about",
    "after",
    "all",
    "also",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "been",
    "before",
    "being",
    "but",
    "by",
    "can",
    "could",
    "do",
    "does",
    "even",
    "for",
    "from",
    "has",
    "have",
    "he",
    "her",
    "here",
    "his",
    "how",
    "http",
    "https",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "like",
    "may",
    "more",
    "most",
    "new",
    "news",
    "not",
    "of",
    "on",
    "one",
    "only",
    "or",
    "our",
    "out",
    "over",
    "reuters",
    "s",
    "said",
    "says",
    "she",
    "should",
    "so",
    "some",
    "that",
    "the",
    "their",
    "them",
    "there",
    "these",
    "they",
    "this",
    "those",
    "to",
    "up",
    "us",
    "using",
    "via",
    "was",
    "we",
    "were",
    "what",
    "will",
    "with",
    "would",
    "www",
    "you",
    "your",
}

KOREAN_STOPWORDS = {
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
}

KOREAN_TOKEN_PATTERN = r"[\uAC00-\uD7A3]+"
KOREAN_NOUN_TAGS = {"NNG", "NNP"}
ENGLISH_NOUN_TAGS = {"NOUN", "PROPN"}
DEFAULT_DICT_PATH = Path(__file__).resolve().parents[1] / "core" / "korean_user_dict.txt"
KOREAN_USER_DICT_PATH = Path(os.getenv("KOREAN_USER_DICT_PATH", str(DEFAULT_DICT_PATH)))
SPACY_MODEL_NAME = os.getenv("SPACY_MODEL_NAME", "en_core_web_sm")
USER_WORD_SCORE = 5.0


def _load_user_dictionary(path: Path = KOREAN_USER_DICT_PATH) -> list[str]:
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
    return tuple(_load_user_dictionary())


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
def get_spacy_nlp():
    if spacy is None:
        return None
    try:
        return spacy.load(
            SPACY_MODEL_NAME,
            disable=["parser", "lemmatizer", "ner", "textcat"],
        )
    except Exception:  # pragma: no cover
        return None


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


def clean_text(text: str | None, provider: str | None = None) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"http\S+", " ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\[\+\d+\s+chars\]", " ", text)
    if provider == "naver":
        text = text.lower()
        text = re.sub(r"[^\uAC00-\uD7A3\s]", " ", text)
    else:
        text = re.sub(r"[^A-Za-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str | None, provider: str | None = None) -> list[str]:
    cleaned = clean_text(text, provider=provider)
    if provider == "naver":
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
            nouns = [token for token in merged if len(token) > 1 and token not in KOREAN_STOPWORDS]
            if nouns:
                return nouns

        fallback_tokens = [
            token
            for token in cleaned.split()
            if token and token not in KOREAN_STOPWORDS and len(token) > 1 and re.fullmatch(KOREAN_TOKEN_PATTERN, token)
        ]
        merged_fallback = merge_compound_nouns(fallback_tokens, get_user_dictionary_set())
        return [token for token in merged_fallback if len(token) > 1 and token not in KOREAN_STOPWORDS]

    nlp = get_spacy_nlp()
    if nlp is not None:
        nouns = [
            token.text.lower()
            for token in nlp(cleaned)
            if token.pos_ in ENGLISH_NOUN_TAGS
            and token.text
            and token.text.lower() not in ENGLISH_STOPWORDS
            and len(token.text) > 1
            and not token.text.isdigit()
            and re.search(r"[a-z]", token.text.lower())
        ]
        if nouns:
            return nouns

    return [
        token.lower()
        for token in cleaned.split()
        if token
        and token.lower() not in ENGLISH_STOPWORDS
        and len(token) > 1
        and not token.isdigit()
        and re.search(r"[a-z]", token.lower())
    ]
