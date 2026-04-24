from processing.preprocessing import clean_text, merge_compound_nouns


def test_clean_text_removes_html_and_non_korean() -> None:
    text = "<b>AI</b> 2026 혁신!"
    assert clean_text(text) == "혁신"


def test_merge_compound_nouns_prefers_longest_match() -> None:
    tokens = ["인공", "지능", "반도체"]
    merged = merge_compound_nouns(tokens, frozenset({"인공지능", "반도체"}))
    assert merged == ["인공지능", "반도체"]
