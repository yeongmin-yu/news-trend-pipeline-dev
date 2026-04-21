from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable


# src layout: scripts/<this>.py → parents[1] = project root → ./src 를 sys.path 앞에 추가
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.schemas import NormalizedNewsArticle


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kafka에서 메시지를 읽어 producer 출력을 검증합니다."
    )
    parser.add_argument(
        "--topic",
        default=settings.kafka_topic,
        help="소비할 Kafka 토픽.",
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=settings.kafka_bootstrap_servers,
        help="Kafka 부트스트랩 서버.",
    )
    parser.add_argument(
        "--max-messages",
        type=int,
        default=5,
        help="종료 전 출력할 메시지 개수.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])

    try:
        consumer = KafkaConsumer(
            args.topic,
            bootstrap_servers=args.bootstrap_servers,
            auto_offset_reset="earliest",
            enable_auto_commit=False,
            consumer_timeout_ms=10000,
            value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        )
    except NoBrokersAvailable as exc:
        print(f"[consumer_check] Kafka 연결 실패: {exc}", file=sys.stderr)
        return 1

    count = 0
    for message in consumer:
        count += 1
        article = NormalizedNewsArticle.from_dict(message.value)
        print(
            json.dumps(
                {
                    "topic": message.topic,
                    "partition": message.partition,
                    "offset": message.offset,
                    "value": article.to_dict(include_metadata=True),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if count >= args.max_messages:
            break

    consumer.close()

    if count == 0:
        print("[consumer_check] 메시지를 받지 못했습니다.")
        return 1

    print(f"[consumer_check] {args.topic}에서 {count}개의 메시지를 읽었습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
