from pathlib import Path

import requests

from ingestion.api_client import RssNewsClient


def test_rss_client_normalizes_items(tmp_path: Path, monkeypatch) -> None:
    catalog = tmp_path / "rss_feeds.csv"
    catalog.write_text(
        "\n".join(
            [
                "publisher,feed_name,domain,url,is_active,source_url,notes",
                "테스트신문,정치,politics,https://example.com/rss.xml,true,https://example.com/rss,fixture",
            ]
        ),
        encoding="utf-8",
    )
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title><![CDATA[테스트 기사]]></title>
      <description><![CDATA[<p>요약</p>]]></description>
      <link>https://example.com/news/1</link>
      <pubDate>Sat, 02 May 2026 03:00:00 +0900</pubDate>
    </item>
  </channel>
</rss>
"""

    class FakeResponse:
        status_code = 200
        content = xml.encode("utf-8")

        def raise_for_status(self) -> None:
            return None

    def fake_get(url: str, **_: object) -> FakeResponse:
        assert url == "https://example.com/rss.xml"
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)

    articles, ok = RssNewsClient(feed_catalog_path=str(catalog)).fetch_news("테스트신문::politics::정치")

    assert ok is True
    assert len(articles) == 1
    assert articles[0]["provider"] == "테스트신문"
    assert articles[0]["domain"] == "politics"
    assert articles[0]["source"] == "테스트신문"
    assert articles[0]["title"] == "테스트 기사"
    assert articles[0]["summary"] == "요약"
    assert articles[0]["url"] == "https://example.com/news/1"
    assert articles[0]["published_at"] == "2026-05-01T18:00:00+00:00"
    assert articles[0]["_query"] == "정치"


def test_rss_client_skips_inactive_feeds(tmp_path: Path) -> None:
    catalog = tmp_path / "rss_feeds.csv"
    catalog.write_text(
        "\n".join(
            [
                "publisher,feed_name,domain,url,is_active,source_url,notes",
                "테스트신문,정치,politics,https://example.com/rss.xml,false,https://example.com/rss,disabled",
                "활성신문,경제,economy,https://example.com/economy.xml,true,https://example.com/rss,active",
            ]
        ),
        encoding="utf-8",
    )

    client = RssNewsClient(feed_catalog_path=str(catalog))

    assert [client._feed_key(feed) for feed in client.feeds] == ["활성신문::economy::경제"]
