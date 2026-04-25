from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings
from core.logger import get_logger
from core.schemas import NormalizedNewsArticle
from core.utils import ensure_dir, read_json, utc_now_iso
from ingestion.producer import NewsKafkaProducer, build_message


logger = get_logger(__name__)

STATE_FILE = Path(settings.state_dir) / "producer_state.json"
DEAD_LETTER_FILE = Path(settings.state_dir) / "dead_letter.jsonl"
REPLAYED_FILE = Path(settings.state_dir) / "dead_letter_replayed.jsonl"
PERMANENTLY_FAILED_FILE = Path(settings.state_dir) / "dead_letter_permanent.jsonl"
MAX_RETRY_ATTEMPTS = 3


def _load_seen_urls() -> set[str]:
    """이미 발행한 URL 집합을 상태 파일에서 읽습니다."""
    state = read_json(STATE_FILE, {"providers": {}})
    seen: set[str] = set()
    for provider_state in state.get("providers", {}).values():
        seen.update(provider_state.get("published_urls", []))
    return seen


def _read_dead_letters() -> list[dict[str, Any]]:
    """Dead Letter 파일의 모든 레코드를 읽습니다."""
    if not DEAD_LETTER_FILE.exists():
        return []

    records: list[dict[str, Any]] = []
    with DEAD_LETTER_FILE.open(encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Dead Letter 파일 %d번째 줄 파싱 실패: %s", line_number, exc)
    return records


def _rewrite_dead_letter(remaining: list[dict[str, Any]]) -> None:
    """재시도 대상만 남도록 Dead Letter 파일을 다시 씁니다."""
    ensure_dir(DEAD_LETTER_FILE.parent)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=DEAD_LETTER_FILE.parent, suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as file:
            for record in remaining:
                file.write(json.dumps(record, ensure_ascii=False) + "\n")
        Path(tmp_path).replace(DEAD_LETTER_FILE)
    except OSError:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _append_replayed(record: dict[str, Any]) -> None:
    """재전송 성공 레코드를 별도 파일에 남깁니다."""
    ensure_dir(REPLAYED_FILE.parent)
    record_copy = {**record, "replayed_at": utc_now_iso()}
    with REPLAYED_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record_copy, ensure_ascii=False) + "\n")


def _append_permanent_failed(records: list[dict[str, Any]]) -> None:
    """영구 실패 레코드를 별도 파일에 남깁니다."""
    if not records:
        return

    ensure_dir(PERMANENTLY_FAILED_FILE.parent)
    with PERMANENTLY_FAILED_FILE.open("a", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_replay(dry_run: bool = False) -> dict[str, int] | None:
    """Dead Letter 메시지를 다시 Kafka로 전송합니다."""
    records = _read_dead_letters()
    if not records:
        logger.info("재전송할 Dead Letter 메시지가 없습니다.")
        return None

    logger.info("Dead Letter %d건을 읽었습니다.", len(records))

    if dry_run:
        logger.info("[DRY-RUN] 실제 전송 없이 대상만 확인합니다.")
        for index, record in enumerate(records, start=1):
            payload = record.get("payload", {})
            attempt = record.get("attempt", 1)
            logger.info(
                "[%d] provider=%s url=%s reason=%s attempt=%d",
                index,
                payload.get("provider"),
                payload.get("url"),
                record.get("reason"),
                attempt,
            )
        return {
            "success": 0,
            "skip": 0,
            "retry_fail": len(records),
            "permanent_fail": 0,
            "total_processed": len(records),
        }

    seen_urls = _load_seen_urls()
    producer = NewsKafkaProducer()

    success_count = 0
    skip_count = 0
    permanent_fail_count = 0
    remaining: list[dict[str, Any]] = []
    permanent_failed: list[dict[str, Any]] = []

    for record in records:
        payload = record.get("payload", {})
        try:
            article = NormalizedNewsArticle.from_dict(payload)
        except ValueError as exc:
            logger.error("잘못된 Dead Letter payload 영구 실패 처리: error=%s payload=%s", exc, payload)
            permanent_failed.append(
                {
                    **record,
                    "error": str(exc),
                    "permanent_fail_at": utc_now_iso(),
                }
            )
            permanent_fail_count += 1
            continue

        url = article.url
        provider = article.provider
        unique_key = f"{provider}::{url}"
        attempt = record.get("attempt", 1) + 1

        if attempt > MAX_RETRY_ATTEMPTS:
            logger.error(
                "영구 실패 처리: url=%s attempt=%d max=%d",
                url,
                attempt - 1,
                MAX_RETRY_ATTEMPTS,
            )
            permanent_failed.append(
                {**record, "attempt": attempt - 1, "permanent_fail_at": utc_now_iso()}
            )
            permanent_fail_count += 1
            continue

        if unique_key in seen_urls:
            logger.info("중복 URL로 재전송 건너뜀: %s", url)
            skip_count += 1
            continue

        try:
            message = build_message(article)
            partition_key = url or provider
            future = producer.producer.send(
                settings.kafka_topic,
                value=message,
                key=partition_key,
            )
            future.get(timeout=30)
            seen_urls.add(unique_key)
            _append_replayed(record)
            success_count += 1
            logger.info("재전송 성공: url=%s attempt=%d", url, attempt)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "재전송 실패: url=%s error=%s attempt=%d/%d",
                url,
                exc,
                attempt,
                MAX_RETRY_ATTEMPTS,
            )
            remaining.append({**record, "attempt": attempt, "last_retry_at": utc_now_iso()})

    _rewrite_dead_letter(remaining)
    _append_permanent_failed(permanent_failed)

    logger.info(
        "재전송 결과: 성공=%d 중복=%d 재시도대기=%d 영구실패=%d",
        success_count,
        skip_count,
        len(remaining),
        permanent_fail_count,
    )

    return {
        "success": success_count,
        "skip": skip_count,
        "retry_fail": len(remaining),
        "permanent_fail": permanent_fail_count,
        "total_processed": success_count + skip_count + len(remaining) + permanent_fail_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Dead Letter 메시지 재전송 스크립트")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 전송 없이 재전송 대상만 확인합니다.",
    )
    args = parser.parse_args()
    run_replay(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
