from processing.preprocessing import clean_text, merge_compound_nouns, tokenize


def test_clean_text_removes_html_and_digits_but_keeps_english() -> None:
    text = "<b>AI</b> 2026 혁신!"
    assert clean_text(text) == "ai 혁신"


def test_tokenize_keeps_english_keywords() -> None:
    text = "OpenAI GPT 모델과 AI 반도체"
    tokens = tokenize(text)

    assert "openai" in tokens
    assert "gpt" in tokens
    assert "ai" in tokens


def test_merge_compound_nouns_prefers_longest_match() -> None:
    tokens = ["인공", "지능", "반도체"]
    merged = merge_compound_nouns(tokens, frozenset({"인공지능", "반도체"}))
    assert merged == ["인공지능", "반도체"]


def test_merge_compound_nouns_allows_whitespace_between_parts() -> None:
    tokens = ["데이터", "센터", "투자"]
    spans = [(0, 3), (4, 6), (7, 9)]

    merged = merge_compound_nouns(
        tokens,
        frozenset({"데이터센터"}),
        spans=spans,
        text="데이터 센터 투자",
    )

    assert merged == ["데이터센터", "투자"]
