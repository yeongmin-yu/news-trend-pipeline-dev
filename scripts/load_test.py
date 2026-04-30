# scripts/load_test.py 예시 구조
# 실제 구현 시 프로젝트의 config/schema와 Kafka producer 유틸을 재사용한다.

import argparse
import json
import time
from datetime import datetime, timezone
from uuid import uuid4

from kafka import KafkaProducer


def build_message(index: int, domain: str) -> dict:
    return {
        "provider": "load_test",
        "domain": domain,
        "url": f"https://example.com/load-test/{index}-{uuid4()}",
        "title": f"로드 테스트 뉴스 제목 {index}",
        "summary": "Kafka-Spark-PostgreSQL 처리량 검증용 더미 메시지입니다.",
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bootstrap-servers", default="localhost:9092")
    parser.add_argument("--topic", default="news_topic")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--rate", type=int, default=100, help="messages per second")
    parser.add_argument("--domain", default="technology")
    args = parser.parse_args()

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap_servers,
        value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
        acks="all",
        retries=3,
    )

    interval = 1 / args.rate if args.rate > 0 else 0
    success = 0
    failed = 0
    started_at = time.time()

    for index in range(args.count):
        message = build_message(index, args.domain)
        try:
            producer.send(args.topic, message).get(timeout=10)
            success += 1
        except Exception:
            failed += 1
        if interval:
            time.sleep(interval)

    producer.flush()
    elapsed = time.time() - started_at
    print({
        "count": args.count,
        "success": success,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_msg_per_sec": round(success / elapsed, 2) if elapsed > 0 else 0,
    })


if __name__ == "__main__":
    main()