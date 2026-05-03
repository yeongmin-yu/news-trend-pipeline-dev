from __future__ import annotations

import hashlib
import os
import re
import time
from datetime import UTC, datetime
from typing import Any

import requests

from storage.db import (
    create_query_keyword as db_create_query_keyword,
    delete_query_keyword as db_delete_query_keyword,
    fetch_all_query_keywords,
    fetch_collection_metrics_summary,
    fetch_domain_catalog,
    fetch_query_keyword_audit_logs,
    update_query_keyword as db_update_query_keyword,
)
from services._utils import AirflowTriggerError


# ── 직렬화 헬퍼 ───────────────────────────────────────────────────────────────

def _query_keyword_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "provider": row.get("provider"),
        "domainId": row.get("domain_id"),
        "domainLabel": row.get("domain_label"),
        "query": row.get("query"),
        "sortOrder": row.get("sort_order"),
        "isActive": row.get("is_active"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _audit_log_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "queryKeywordId": row.get("query_keyword_id"),
        "action": row.get("action"),
        "beforeJson": row.get("before_json"),
        "afterJson": row.get("after_json"),
        "actor": row.get("actor"),
        "actedAt": row.get("acted_at"),
    }


def _collection_metric_to_api(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": row.get("provider"),
        "domain": row.get("domain"),
        "query": row.get("query"),
        "requestCount": row.get("request_count"),
        "successCount": row.get("success_count"),
        "articleCount": row.get("article_count"),
        "duplicateCount": row.get("duplicate_count"),
        "publishCount": row.get("publish_count"),
        "errorCount": row.get("error_count"),
        "lastSeenAt": row.get("last_seen_at"),
    }


# ── 공개 서비스 함수 ──────────────────────────────────────────────────────────

def get_query_keyword_admin_overview() -> dict[str, Any]:
    """도메인·쿼리 키워드·감사 로그·수집 메트릭을 한 번에 반환한다."""
    return {
        "domains": fetch_domain_catalog(),
        "queryKeywords": [_query_keyword_to_api(dict(row)) for row in fetch_all_query_keywords(provider="naver")],
        "auditLogs": [_audit_log_to_api(dict(row)) for row in fetch_query_keyword_audit_logs(limit=100)],
        "collectionMetrics": [_collection_metric_to_api(dict(row)) for row in fetch_collection_metrics_summary(hours=24, provider="naver")],
    }


def get_collection_metrics_overview(hours: int = 24) -> dict[str, Any]:
    """최근 N시간 동안의 소스별 뉴스 수집 메트릭을 반환한다."""
    return {
        "items": [_collection_metric_to_api(dict(row)) for row in fetch_collection_metrics_summary(hours=hours, provider="naver")]
    }


def create_query_keyword(domain_id: str, query: str, sort_order: int, actor: str) -> dict[str, Any]:
    """특정 도메인에 새 뉴스 수집용 검색 키워드를 추가한다."""
    return db_create_query_keyword(provider="naver", domain_id=domain_id, query=query, sort_order=sort_order, actor=actor)


def update_query_keyword(item_id: int, domain_id: str, query: str, sort_order: int, is_active: bool, actor: str) -> dict[str, Any]:
    """기존 쿼리 키워드의 내용·도메인·정렬 순서·활성화 여부를 변경한다."""
    return db_update_query_keyword(item_id=item_id, domain_id=domain_id, query=query, sort_order=sort_order, is_active=is_active, actor=actor)


def delete_query_keyword(item_id: int, actor: str) -> None:
    """뉴스 수집 대상에서 해당 검색 키워드를 제거한다."""
    db_delete_query_keyword(item_id=item_id, actor=actor)


def trigger_compound_auto_approve() -> dict[str, int]:
    """승인 기준을 통과한 복합명사 후보를 일괄 자동 승인한다."""
    from analytics.compound_auto_approver import run_compound_auto_approve
    return run_compound_auto_approve()


def trigger_stopword_recommender() -> dict[str, int]:
    """최신 키워드 데이터를 분석하여 불용어 후보를 새로 생성한다."""
    from analytics.stopword_recommender import run_stopword_recommender
    return run_stopword_recommender()


def trigger_compound_keyword_backfill_dag(
    *,
    word: str,
    domain: str,
    since: str,
    until: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Airflow compound_keyword_backfill DAG을 트리거하여 과거 키워드 집계를 재처리한다."""
    normalized_word = word.strip()
    normalized_domain = (domain or "all").strip() or "all"
    if not normalized_word:
        raise ValueError("word is required")
    if not since.strip() or not until.strip():
        raise ValueError("since and until are required")

    dag_id = "compound_keyword_backfill"
    airflow_base_url = os.getenv("AIRFLOW_API_BASE_URL", "http://airflow-apiserver:8080").rstrip("/")
    username = os.getenv("AIRFLOW_API_USERNAME", os.getenv("_AIRFLOW_WWW_USER_USERNAME", "airflow"))
    password = os.getenv("AIRFLOW_API_PASSWORD", os.getenv("_AIRFLOW_WWW_USER_PASSWORD", "airflow"))

    # Airflow run_id는 ^[A-Za-z0-9_.~:+-]+$ 형식을 요구하므로 한글 등 비ASCII 문자를 해시로 대체
    safe_word = re.sub(r"[^A-Za-z0-9_.~:+-]", "", normalized_word)
    word_hash = hashlib.sha1(normalized_word.encode("utf-8")).hexdigest()[:8]
    word_slug = f"{safe_word[:32]}_{word_hash}" if safe_word else word_hash
    dag_run_id = f"compound-backfill-{int(time.time())}-{word_slug}"
    logical_date = datetime.now(UTC).isoformat()
    conf = {"word": normalized_word, "domain": normalized_domain, "since": since.strip(), "until": until.strip(), "dry_run": dry_run}
    payload = {"dag_run_id": dag_run_id, "logical_date": logical_date, "conf": conf}
    endpoints = [
        f"{airflow_base_url}/api/v2/dags/{dag_id}/dagRuns",
        f"{airflow_base_url}/api/v1/dags/{dag_id}/dagRuns",
    ]

    headers: dict[str, str] = {}
    try:
        token_response = requests.post(
            f"{airflow_base_url}/auth/token",
            json={"username": username, "password": password},
            timeout=10,
        )
        if token_response.status_code in {200, 201}:
            token = token_response.json().get("access_token")
            if token:
                headers["Authorization"] = f"Bearer {token}"
    except requests.RequestException:
        headers = {}

    last_error = ""
    for endpoint in endpoints:
        try:
            auth = None if headers else (username, password)
            response = requests.post(endpoint, json=payload, headers=headers, auth=auth, timeout=10)
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
        if response.status_code in {200, 201}:
            data = response.json()
            return {
                "status": "triggered",
                "dagId": dag_id,
                "dagRunId": data.get("dag_run_id") or data.get("dagRunId") or dag_run_id,
                "conf": conf,
            }
        last_error = f"{response.status_code} {response.text[:500]}"
        if response.status_code != 404:
            break

    raise AirflowTriggerError(f"Airflow DAG trigger failed: {last_error}")
