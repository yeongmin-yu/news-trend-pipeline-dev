from __future__ import annotations

import html
import re
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable
from urllib.parse import urlparse

import requests

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.logger import get_logger


logger = get_logger(__name__)

# Naver 검색 API는 초당 호출 제한이 있어, 동일 키워드의 페이지네이션 호출 사이에
# 짧은 지연을 두어 429(Too Many Requests)를 예방합니다.
_NAVER_PAGE_REQUEST_DELAY_SECONDS = 0.5


def strip_html_tags(text: str | None) -> str | None:
    if not text:
        return text
    return re.sub(r"<[^>]+>", "", html.unescape(text)).strip()


class BaseNewsClient(ABC):
    provider: str

    @abstractmethod
    def fetch_news(
        self,
        query: str | None = None,
        from_timestamp: str | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError


class NaverNewsClient(BaseNewsClient):
    provider = "naver"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None) -> None:
        self.client_id = client_id or settings.naver_client_id
        self.client_secret = client_secret or settings.naver_client_secret
        if not self.client_id or not self.client_secret:
            raise ValueError(
                "NAVER_CLIENT_ID 또는 NAVER_CLIENT_SECRET이 없습니다. Naver 호출 전에 .env에서 설정하세요."
            )

    # ── 단일 키워드 수집 ─────────────────────────────────────────────────────
    def fetch_news(
        self,
        query: str | None = None,
        from_timestamp: str | None = None,
        page_size: int | None = None,
    ) -> list[dict[str, Any]]:
        # 단일 키워드 호출. 병렬 호출 시에는 fetch_news_parallel()을 사용합니다.
        effective_query = query or (
            settings.naver_theme_keywords[0] if settings.naver_theme_keywords else "AI"
        )
        display = min(page_size or settings.naver_news_display, 100)
        start_positions = [1 + page * display for page in range(settings.naver_news_max_pages)]
        articles: list[dict[str, Any]] = []
        threshold = self._parse_timestamp(from_timestamp) if from_timestamp else None

        logger.info(
            "Naver API 호출 시작 — query=%r from=%s display=%d max_pages=%d",
            effective_query,
            from_timestamp or "없음",
            display,
            settings.naver_news_max_pages,
        )

        for page_index, start in enumerate(start_positions):
            # 첫 페이지는 즉시 호출, 두 번째 페이지부터 0.5초 지연 후 호출.
            # `break`로 조기 중단되는 경우 남은 sleep이 없도록 요청 직전에 대기합니다.
            if page_index > 0:
                time.sleep(_NAVER_PAGE_REQUEST_DELAY_SECONDS)
            try:
                payload = self._request_news(query=effective_query, display=display, start=start)
            except requests.HTTPError as exc:
                logger.warning(
                    "Naver API 요청 실패 query=%r start=%d: %s",
                    effective_query,
                    start,
                    exc,
                )
                break

            items = payload.get("items", [])
            normalized_batch = [self._normalize_article(item, effective_query) for item in items]
            if threshold:
                before = len(normalized_batch)
                normalized_batch = [
                    item
                    for item in normalized_batch
                    if self._parse_timestamp(item.get("published_at"))
                    and self._parse_timestamp(item.get("published_at")) > threshold
                ]
                logger.info(
                    "Naver API query=%r start=%d — raw=%d threshold_filtered=%d passed=%d",
                    effective_query,
                    start,
                    before,
                    before - len(normalized_batch),
                    len(normalized_batch),
                )
            else:
                logger.info(
                    "Naver API query=%r start=%d — raw=%d (threshold 없음)",
                    effective_query,
                    start,
                    len(items),
                )
            articles.extend(normalized_batch)

            if threshold and items:
                oldest_item = self._normalize_article(items[-1], effective_query)
                oldest_timestamp = self._parse_timestamp(oldest_item.get("published_at"))
                if oldest_timestamp and oldest_timestamp <= threshold:
                    logger.info(
                        "Naver API 조기 중단: query=%r start=%d oldest=%s <= threshold=%s",
                        effective_query,
                        start,
                        oldest_timestamp.isoformat(),
                        threshold.isoformat(),
                    )
                    break

        unique_articles = self._deduplicate_articles(articles)
        logger.info(
            "Naver API 수집 완료 — query=%r articles=%d",
            effective_query,
            len(unique_articles),
        )
        return unique_articles

    # ── 다중 키워드 병렬 수집 ─────────────────────────────────────────────────
    def fetch_news_parallel(
        self,
        queries: Iterable[str] | None = None,
        from_timestamp: str | None = None,
        page_size: int | None = None,
        max_workers: int | None = None,
    ) -> list[dict[str, Any]]:
        """테마 키워드 집합에 대해 ThreadPoolExecutor로 병렬 API 호출.

        Naver 검색 API는 키워드별 독립 호출이므로 I/O 대기가 크고 GIL 영향이 적어
        스레드 기반 병렬화로 선형에 가까운 속도 향상을 얻을 수 있습니다.
        """
        keyword_list = [q for q in (queries or settings.naver_theme_keywords) if q]
        if not keyword_list:
            logger.warning("Naver 병렬 호출 대상 키워드가 비어 있습니다. NAVER_THEME_KEYWORDS 확인.")
            return []

        effective_workers = max(
            1,
            min(max_workers or settings.naver_max_workers, len(keyword_list)),
        )
        logger.info(
            "Naver 병렬 호출 시작 — keywords=%d workers=%d from=%s",
            len(keyword_list),
            effective_workers,
            from_timestamp or "없음",
        )

        collected: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            future_to_query = {
                executor.submit(
                    self.fetch_news,
                    keyword,
                    from_timestamp,
                    page_size,
                ): keyword
                for keyword in keyword_list
            }
            for future in as_completed(future_to_query):
                keyword = future_to_query[future]
                try:
                    batch = future.result()
                except Exception as exc:  # noqa: BLE001
                    logger.error("Naver 병렬 호출 실패 query=%r: %s", keyword, exc)
                    continue
                logger.info("Naver 병렬 수집 완료 — query=%r articles=%d", keyword, len(batch))
                collected.extend(batch)

        unique_articles = self._deduplicate_articles(collected)
        logger.info(
            "Naver 병렬 호출 종합 — keywords=%d raw=%d unique=%d",
            len(keyword_list),
            len(collected),
            len(unique_articles),
        )
        return unique_articles

    # ── HTTP / 정규화 ────────────────────────────────────────────────────────
    def _request_news(self, query: str, display: int, start: int) -> dict[str, Any]:
        params = {
            "query": query,
            "display": display,
            "start": start,
            "sort": settings.naver_news_sort,
        }
        headers = {
            "X-Naver-Client-Id": self.client_id,
            "X-Naver-Client-Secret": self.client_secret,
        }
        response = requests.get(
            settings.naver_news_api_url,
            params=params,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def _normalize_article(self, item: dict[str, Any], query: str | None = None) -> dict[str, Any]:
        publisher_url = item.get("originallink") or item.get("link") or ""
        publisher = urlparse(publisher_url).netloc or "Naver News"
        description = strip_html_tags(item.get("description"))
        title = strip_html_tags(item.get("title"))
        published_at = self._normalize_pub_date(item.get("pubDate"))
        article: dict[str, Any] = {
            "provider": self.provider,
            "source": publisher,
            "author": None,
            "title": title,
            "description": description,
            "content": description,
            "url": publisher_url or item.get("link"),
            "published_at": published_at,
            "ingested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }
        # `_query`는 내부 전파용 필드로, build_message()에서 metadata로 옮기며 제거됩니다.
        if query is not None:
            article["_query"] = query
        return article

    @staticmethod
    def _normalize_pub_date(value: str | None) -> str | None:
        if not value:
            return None
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()

    @staticmethod
    def _parse_timestamp(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduplicated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for article in articles:
            unique_key = f"{article.get('provider')}::{article.get('url')}"
            if not article.get("url") or unique_key in seen:
                continue
            seen.add(unique_key)
            deduplicated.append(article)
        return deduplicated
