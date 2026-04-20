from __future__ import annotations

"""Dead Letter 재처리 스크립트 (replay.py)

dead_letter.jsonl에 쌓인 실패 메시지를 Kafka에 재전송합니다.

사용법:
    # 실제 재처리
    python ingestion/replay.py

    # 테스트 실행 (전송 없이 대상 건수만 출력)
    python ingestion/replay.py --dry-run

동작 방식:
  1. dead_letter.jsonl을 한 줄씩 읽어 재전송 시도
  2. 성공한 레코드는 dead_letter_replayed.jsonl로 이동
  3. 재전송 실패한 레코드는 dead_letter.jsonl에 그대로 남김 (attempt 카운트 증가)
  4. 중복 체크: producer_state.json의 published_urls Set과 대조
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.logger import get_logger
from news_trend_pipeline.core.utils import ensure_dir, read_json, utc_now_iso
from news_trend_pipeline.ingestion.producer import NewsKafkaProducer, build_message

logger = get_logger(__name__)

STATE_FILE = Path(settings.state_dir) / "producer_state.json"
DEAD_LETTER_FILE = Path(settings.state_dir) / "dead_letter.jsonl"
REPLAYED_FILE = Path(settings.state_dir) / "dead_letter_replayed.jsonl"
PERMANENTLY_FAILED_FILE = Path(settings.state_dir) / "dead_letter_permanent.jsonl"
MAX_RETRY_ATTEMPTS = 3  # 최대 재시도 횟수


def _load_seen_urls() -> set[str]:
    """producer_state.json에서 이미 발행된 URL Set을 로드합니다."""
    state = read_json(STATE_FILE, {"providers": {}})
    seen: set[str] = set()
    for provider_state in state.get("providers", {}).values():
        seen.update(provider_state.get("published_urls", []))
    return seen


def _read_dead_letters() -> list[dict[str, Any]]:
    """dead_letter.jsonl의 모든 레코드를 읽어 반환합니다."""
    if not DEAD_LETTER_FILE.exists():
        return []
    records: list[dict[str, Any]] = []
    with DEAD_LETTER_FILE.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                logger.warning("Dead Letter 파일 %d번째 줄 파싱 실패 (skip): %s", line_no, exc)
    return records


def _rewrite_dead_letter(remaining: list[dict[str, Any]]) -> None:
    """남은 레코드로 dead_letter.jsonl을 원자적으로 덮어씁니다."""
    ensure_dir(DEAD_LETTER_FILE.parent)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=DEAD_LETTER_FILE.parent, suffix=".tmp")
    try:
        with open(tmp_fd, "w", encoding="utf-8") as f:
            for record in remaining:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        Path(tmp_path).replace(DEAD_LETTER_FILE)
    except OSError:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _append_replayed(record: dict[str, Any]) -> None:
    """재처리 성공한 레코드를 dead_letter_replayed.jsonl에 기록합니다."""
    ensure_dir(REPLAYED_FILE.parent)
    record_copy = {**record, "replayed_at": utc_now_iso()}
    with REPLAYED_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record_copy, ensure_ascii=False) + "\n")


def run_replay(dry_run: bool = False) -> dict[str, int]:
    """Dead Letter 재처리 메인 로직.

    Args:
        dry_run: True면 전송 없이 재처리 대상 건수만 출력합니다.

    Returns:
        재처리 결과를 담은 딕셔너리:
        {
            'success': int,           # 성공한 메시지 건수
            'skip': int,              # 중복으로 건너뛴 메시지 건수
            'retry_fail': int,        # 재시도했으나 실패한 메시지 건수
            'permanent_fail': int,    # 영구 실패로 처리된 메시지 건수
            'total_processed': int,   # 처리한 메시지 총 건수
        }
    """
    records = _read_dead_letters()
    if not records:
        logger.info("Dead Letter 파일이 비어 있거나 없습니다. 재처리할 메시지가 없습니다.")
        return

    logger.info("Dead Letter 총 %d건 로드 완료.", len(records))

    if dry_run:
        logger.info("[DRY-RUN] 실제 전송 없이 대상 건수만 출력합니다.")
        for i, record in enumerate(records, start=1):
            payload = record.get("payload", {})
            attempt = record.get("attempt", 1)
            logger.info(
                "  [%d] provider=%s url=%s reason=%s attempt=%d",
                i,
                payload.get("provider"),
                payload.get("url"),
                record.get("reason"),
                attempt,
            )
            # 최대 재시도 횟수 초과 경고
            if attempt >= MAX_RETRY_ATTEMPTS:
                logger.warning("    ⚠️ 최대 재시도 횟수(%d)에 도달했습니다", MAX_RETRY_ATTEMPTS)
        logger.info("[DRY-RUN] 재처리 대상: %d건", len(records))
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
        payload: dict[str, Any] = record.get("payload", {})
        url: str | None = payload.get("url")
        provider: str = payload.get("provider", "unknown")
        unique_key = f"{provider}::{url}"
        attempt: int = record.get("attempt", 1) + 1

        # 최대 재시도 횟수 초과 확인
        if attempt > MAX_RETRY_ATTEMPTS:
            logger.error(
                "영구 실패: url=%s (attempt=%d, 최대=%d)",
                url,
                attempt - 1,
                MAX_RETRY_ATTEMPTS,
            )
            permanent_failed.append(
                {**record, "attempt": attempt - 1, "permanent_fail_at": utc_now_iso()}
            )
            permanent_fail_count += 1
            continue

        # 이미 발행된 URL 중복 체크
        if not url or unique_key in seen_urls:
            logger.info("중복 skip: url=%s", url)
            skip_count += 1
            continue

        # 재전송 시도
        try:
            message = build_message(payload)
            # URL을 partition key로 사용 (원본 producer와 동일한 라우팅 유지).
            partition_key = url or provider
            future = producer.producer.send(
                settings.kafka_topic,
                value=message,
                key=partition_key,
            )
            future.get(timeout=30)  # 동기 대기로 성공 여부 즉시 확인
            seen_urls.add(unique_key)
            _append_replayed(record)
            success_count += 1
            logger.info("재처리 성공: url=%s (attempt=%d)", url, attempt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("재처리 실패: url=%s error=%s (attempt=%d/%d)", url, exc, attempt, MAX_RETRY_ATTEMPTS)
            updated_record = {**record, "attempt": attempt, "last_retry_at": utc_now_iso()}
            remaining.append(updated_record)

    # 남은 실패 레코드로 dead_letter.jsonl 갱신
    _rewrite_dead_letter(remaining)

    # 영구 실패 레코드 저장
    if permanent_failed:
        ensure_dir(PERMANENTLY_FAILED_FILE.parent)
        with PERMANENTLY_FAILED_FILE.open("a", encoding="utf-8") as f:
            for record in permanent_failed:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    logger.info(
        "=== 재처리 결과 === 성공=%d건 | 중복skip=%d건 | 재실패=%d건 | 영구실패=%d건",
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
    parser = argparse.ArgumentParser(description="Dead Letter 메시지 재처리 스크립트")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 전송 없이 재처리 대상 건수만 출력합니다.",
    )
    args = parser.parse_args()
    run_replay(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
