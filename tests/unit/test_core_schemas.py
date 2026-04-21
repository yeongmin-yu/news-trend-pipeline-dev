from news_trend_pipeline.core.schemas import NormalizedNewsArticle


def test_normalized_news_article_to_message_includes_metadata() -> None:
    article = NormalizedNewsArticle.from_dict(
        {
            "provider": "naver",
            "source": "example.com",
            "title": "테스트 기사",
            "summary": "요약",
            "url": "https://example.com/news/1",
            "published_at": "2026-04-21T00:00:00+00:00",
            "ingested_at": "2026-04-21T00:01:00+00:00",
            "_query": "AI",
        }
    )

    message = article.to_message(schema_version="v1")

    assert message["metadata"] == {
        "source": "naver",
        "version": "v1",
        "query": "AI",
    }
    assert message["summary"] == "요약"
    assert "_query" not in message


def test_normalized_news_article_spark_schema_contains_metadata() -> None:
    schema = NormalizedNewsArticle.spark_schema()
    field_names = [field.name for field in schema.fields]

    assert "metadata" in field_names


def test_normalized_news_article_accepts_legacy_description_payload() -> None:
    article = NormalizedNewsArticle.from_dict(
        {
            "provider": "naver",
            "source": "example.com",
            "title": "테스트 기사",
            "description": "레거시 설명",
            "url": "https://example.com/news/2",
            "published_at": "2026-04-21T00:00:00+00:00",
            "ingested_at": "2026-04-21T00:01:00+00:00",
        }
    )

    assert article.summary == "레거시 설명"
