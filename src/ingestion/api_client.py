from __future__ import annotations

import html
import re
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Iterable, Mapping
from urllib.parse import urlparse

import requests

from core.config import settings
from core.logger import get_logger


logger = get_logger(__name__)

# fetch_news() 반환 타입: (수집된 기사 목록, ok 플래그).
#   ok=True  → 모든 페이지를 예외 없이 순회 완료(조기 중단 포함, 정상 종료).
#   ok=False → 페이지네이션 중 네트워크/HTTP/파싱 오류 발생.
#              → 호출자는 체크포인트(last_timestamp)를 전진시키지 말고
#                다음 실행에서 같은 from_timestamp 로 재시도해야 합니다.
FetchResult = tuple[list[dict[str, Any]], bool]


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
    ) -> FetchResult:
        """단일 키워드 수집 결과를 (articles, ok) 튜플로 반환합니다.

        ok=False 인 경우, 호출자는 해당 키워드의 체크포인트를 전진시키지 말고
        다음 실행에서 동일한 from_timestamp 로 재시도해야 합니다.
        """
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
    ) -> FetchResult:
        """단일 키워드로 Naver 뉴스 페이지네이션 수집을 수행합니다.

        반환값은 (articles, ok) 튜플입니다.
          - ok=True  : 모든 페이지를 정상 순회 완료 (threshold 조기 중단 포함).
          - ok=False : 페이지 중 하나라도 네트워크/HTTP/파싱 오류가 발생해 루프를 중단.
                       → 호출자는 이 키워드의 체크포인트를 **전진시키지 않아야** 합니다.

        병렬 호출 시에는 fetch_news_parallel()을 사용합니다. 단, 병렬 호출도
        내부적으로 이 함수를 그대로 사용합니다.
        """
        effective_query = query or (
            settings.naver_theme_keywords[0] if settings.naver_theme_keywords else "AI"
        )
        display = min(page_size or settings.naver_news_display, 100)
        start_positions = [1 + page * display for page in range(settings.naver_news_max_pages)]
        articles: list[dict[str, Any]] = []
        threshold = self._parse_timestamp(from_timestamp) if from_timestamp else None
        # ok 플래그: 기본 True, 페이지 루프에서 예외가 발생하면 False 로 전환.
        ok = True

        logger.info(
            "Naver API 호출 시작 — query=%r from=%s display=%d max_pages=%d",
            effective_query,
            from_timestamp or "없음",
            display,
            settings.naver_news_max_pages,
        )

        for page_index, start in enumerate(start_positions):
            # 첫 페이지는 즉시 호출, 두 번째 페이지부터 설정된 지연 후 호출.
            # `break`로 조기 중단되는 경우 남은 sleep이 없도록 요청 직전에 대기합니다.
            if page_index > 0:
                time.sleep(settings.naver_page_request_delay_seconds)
            try:
                payload = self._request_news(query=effective_query, display=display, start=start)
            except requests.HTTPError as exc:
                # 4xx/5xx 응답. 429(rate limit) 포함. 부분 성공으로 보고.
                logger.warning(
                    "Naver API HTTP 오류 query=%r start=%d: %s",
                    effective_query,
                    start,
                    exc,
                )
                ok = False
                break
            except (requests.Timeout, requests.ConnectionError) as exc:
                # 타임아웃/네트워크 단절. 재시도 가능한 일시 장애로 간주.
                logger.warning(
                    "Naver API 네트워크 오류 query=%r start=%d: %s",
                    effective_query,
                    start,
                    exc,
                )
                ok = False
                break
            except ValueError as exc:
                # response.json() 파싱 실패. 응답이 손상된 상태이므로 중단.
                logger.error(
                    "Naver API 응답 파싱 실패 query=%r start=%d: %s",
                    effective_query,
                    start,
                    exc,
                )
                ok = False
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
                # 최신순(sort=date)으로 내려온다는 전제 하에, 마지막 아이템(페이지 내 최고참)이
                # threshold 이하라면 그 뒤 페이지는 모두 이미 처리된 기사이므로 조기 종료.
                # 이 경로는 정상 종료이므로 ok=True 를 유지합니다.
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
            "Naver API 수집 완료 — query=%r articles=%d ok=%s",
            effective_query,
            len(unique_articles),
            ok,
        )
        return unique_articles, ok

    # ── 다중 키워드 병렬 수집 ─────────────────────────────────────────────────
    def fetch_news_parallel(
        self,
        queries: Iterable[str] | None = None,
        from_timestamps: Mapping[str, str | None] | None = None,
        page_size: int | None = None,
        max_workers: int | None = None,
    ) -> dict[str, FetchResult]:
        """테마 키워드 집합에 대해 ThreadPoolExecutor로 병렬 API 호출.

        키워드별로 독립된 체크포인트(`from_timestamps[keyword]`)를 받아
        각 키워드의 (articles, ok) 결과를 {keyword: (articles, ok)} dict로 반환합니다.

        설계 포인트:
          - 한 키워드의 부분 실패가 다른 키워드의 체크포인트 전진에 영향을 주지 않도록,
            키워드 단위로 ok 플래그를 그대로 노출합니다.
          - 스레드 내부 예외(fetch_news 본체가 완전히 터진 경우)는 ok=False + 빈 articles
            로 정규화하여 호출자 쪽 분기를 단순하게 유지합니다.
          - Naver 검색 API는 키워드별 독립 호출이라 I/O 대기가 커 GIL 영향이 적고,
            스레드 기반 병렬화로 선형에 가까운 속도 향상을 얻습니다.

        Parameters
        ----------
        queries:
            대상 키워드 목록. None 이면 settings.naver_theme_keywords 사용.
        from_timestamps:
            키워드별 증분 기준 시각 매핑. 누락된 키워드는 None(=증분 필터 없음)으로 취급.
        page_size, max_workers:
            기존 시그니처와 동일.
        """
        keyword_list = [q for q in (queries or settings.naver_theme_keywords) if q]
        if not keyword_list:
            logger.warning("Naver 병렬 호출 대상 키워드가 비어 있습니다. NAVER_THEME_KEYWORDS 확인.")
            return {}

        # 키워드별 from_timestamp 매핑. 입력이 None 이면 전 키워드에 대해 None 적용.
        timestamp_map: dict[str, str | None] = {
            keyword: (from_timestamps.get(keyword) if from_timestamps else None)
            for keyword in keyword_list
        }

        effective_workers = max(
            1,
            min(max_workers or settings.naver_max_workers, len(keyword_list)),
        )
        logger.info(
            "Naver 병렬 호출 시작 — keywords=%d workers=%d per_keyword_from=%s",
            len(keyword_list),
            effective_workers,
            {k: (v or "없음") for k, v in timestamp_map.items()},
        )

        # 결과 컨테이너는 dict: 키워드 -> (articles, ok).
        # 각 키워드의 체크포인트를 호출자가 독립적으로 갱신할 수 있도록 분리 보관.
        results: dict[str, FetchResult] = {keyword: ([], False) for keyword in keyword_list}

        with ThreadPoolExecutor(max_workers=effective_workers) as executor:
            def _fetch_with_stagger(keyword: str, start_delay: float) -> FetchResult:
                if start_delay > 0:
                    time.sleep(start_delay)
                return self.fetch_news(
                    keyword,
                    timestamp_map[keyword],
                    page_size,
                )

            future_to_query = {
                executor.submit(
                    _fetch_with_stagger,
                    keyword,
                    index * settings.naver_query_stagger_seconds,
                ): keyword
                for index, keyword in enumerate(keyword_list)
            }
            for future in as_completed(future_to_query):
                keyword = future_to_query[future]
                try:
                    articles, ok = future.result()
                except Exception as exc:  # noqa: BLE001
                    # fetch_news 본체에서 예상치 못한 예외가 올라온 경우 — 체크포인트 보존용으로 ok=False.
                    logger.error("Naver 병렬 호출 실패 query=%r: %s", keyword, exc)
                    results[keyword] = ([], False)
                    continue
                logger.info(
                    "Naver 병렬 수집 완료 — query=%r articles=%d ok=%s",
                    keyword,
                    len(articles),
                    ok,
                )
                results[keyword] = (articles, ok)

        total_articles = sum(len(a) for a, _ in results.values())
        ok_count = sum(1 for _, ok in results.values() if ok)
        logger.info(
            "Naver 병렬 호출 종합 — keywords=%d ok=%d partial_or_fail=%d raw=%d",
            len(keyword_list),
            ok_count,
            len(keyword_list) - ok_count,
            total_articles,
        )
        return results

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
        summary = strip_html_tags(item.get("description"))
        title = strip_html_tags(item.get("title"))
        published_at = self._normalize_pub_date(item.get("pubDate"))
        article: dict[str, Any] = {
            "provider": self.provider,
            "source": publisher,
            "title": title,
            "summary": summary,
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
