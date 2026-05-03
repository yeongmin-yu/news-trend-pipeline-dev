"""Kafka 클러스터 / 토픽 / consumer group 상태를 일정 주기로 출력하는 모니터.

사용 예::

    python scripts/kafka_monitor.py                       # 5초 간격으로 기본 토픽 모니터
    python scripts/kafka_monitor.py --interval 2          # 2초 간격
    python scripts/kafka_monitor.py --topic news_topic    # 특정 토픽
    python scripts/kafka_monitor.py --once                # 한 번만 출력하고 종료
    python scripts/kafka_monitor.py --groups              # consumer group lag 도 출력

Spark Structured Streaming 은 일반적인 consumer group 을 사용하지 않고
체크포인트로 offset 을 관리하므로, 토픽의 최신 offset 증가량(=produce rate)을
보면 파이프라인 입력 측 흐름을 가늠할 수 있다.
"""
from __future__ import annotations

import argparse
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from kafka import KafkaAdminClient, KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable
from kafka.structs import TopicPartition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.config import settings  # noqa: E402


@dataclass
class PartitionState:
    partition: int
    begin_offset: int
    end_offset: int

    @property
    def message_count(self) -> int:
        return max(0, self.end_offset - self.begin_offset)


@dataclass
class TopicSnapshot:
    topic: str
    timestamp: float
    partitions: list[PartitionState]

    @property
    def total_end(self) -> int:
        return sum(p.end_offset for p in self.partitions)

    @property
    def total_messages(self) -> int:
        return sum(p.message_count for p in self.partitions)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kafka 브로커/토픽/파티션/consumer group 상태를 주기적으로 출력합니다."
    )
    parser.add_argument(
        "--bootstrap-servers",
        default="localhost:9092",
        help="Kafka bootstrap 서버 (기본: 설정값).",
    )
    parser.add_argument(
        "--topic",
        action="append",
        help="모니터링할 토픽. 여러 번 지정 가능. 미지정 시 설정의 기본 토픽 사용.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="새로고침 간격(초). 기본 5.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="한 번만 출력하고 종료.",
    )
    parser.add_argument(
        "--groups",
        action="store_true",
        help="해당 토픽을 구독하는 consumer group 의 lag 도 함께 출력.",
    )
    parser.add_argument(
        "--client-id",
        default="kafka-monitor",
        help="Kafka 클라이언트 식별자.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=10000,
        help="Kafka 요청 타임아웃(ms).",
    )
    return parser.parse_args(argv)


def _open_admin(args: argparse.Namespace) -> KafkaAdminClient:
    return KafkaAdminClient(
        bootstrap_servers=args.bootstrap_servers,
        client_id=args.client_id,
        request_timeout_ms=args.timeout_ms,
    )


def _open_consumer(args: argparse.Namespace) -> KafkaConsumer:
    return KafkaConsumer(
        bootstrap_servers=args.bootstrap_servers,
        client_id=f"{args.client_id}-probe",
        request_timeout_ms=args.timeout_ms,
        consumer_timeout_ms=args.timeout_ms,
        enable_auto_commit=False,
    )


def _fetch_cluster_summary(admin: KafkaAdminClient) -> str:
    try:
        cluster = admin.describe_cluster()
    except KafkaError as exc:
        return f"cluster=unavailable ({exc.__class__.__name__})"
    brokers = cluster.get("brokers") or []
    controller = cluster.get("controller_id")
    cluster_id = cluster.get("cluster_id") or "?"
    broker_lines = ", ".join(
        f"{b.get('node_id')}@{b.get('host')}:{b.get('port')}" for b in brokers
    )
    return (
        f"cluster_id={cluster_id} controller={controller} "
        f"brokers=[{broker_lines}]"
    )


def _snapshot_topic(consumer: KafkaConsumer, topic: str) -> TopicSnapshot | None:
    partitions = consumer.partitions_for_topic(topic)
    if not partitions:
        return None
    tps = [TopicPartition(topic, p) for p in sorted(partitions)]
    begin = consumer.beginning_offsets(tps)
    end = consumer.end_offsets(tps)
    states = [
        PartitionState(
            partition=tp.partition,
            begin_offset=begin.get(tp, 0),
            end_offset=end.get(tp, 0),
        )
        for tp in tps
    ]
    return TopicSnapshot(topic=topic, timestamp=time.time(), partitions=states)


def _format_rate(curr: TopicSnapshot, prev: TopicSnapshot | None) -> str:
    if prev is None or curr.timestamp <= prev.timestamp:
        return "rate=  -    msg/s"
    delta_msgs = curr.total_end - prev.total_end
    delta_t = curr.timestamp - prev.timestamp
    rate = delta_msgs / delta_t if delta_t > 0 else 0.0
    return f"rate={rate:7.2f} msg/s (Δ{delta_msgs:+d} in {delta_t:.1f}s)"


def _print_topic_block(snapshot: TopicSnapshot, prev: TopicSnapshot | None) -> None:
    header = (
        f"  topic={snapshot.topic}  partitions={len(snapshot.partitions)}  "
        f"end_total={snapshot.total_end}  retained={snapshot.total_messages}  "
        f"{_format_rate(snapshot, prev)}"
    )
    print(header)
    print(f"    {'part':>4} {'begin':>12} {'end':>12} {'retained':>10}")
    for part in snapshot.partitions:
        print(
            f"    {part.partition:>4} {part.begin_offset:>12} "
            f"{part.end_offset:>12} {part.message_count:>10}"
        )


def _print_consumer_groups(
    admin: KafkaAdminClient, snapshot: TopicSnapshot
) -> None:
    try:
        groups = admin.list_consumer_groups()
    except KafkaError as exc:
        print(f"    [groups] 조회 실패: {exc.__class__.__name__}: {exc}")
        return
    if not groups:
        print("    [groups] 등록된 consumer group 없음")
        return

    end_by_partition = {p.partition: p.end_offset for p in snapshot.partitions}
    relevant: list[tuple[str, dict[TopicPartition, int]]] = []
    for group_id, _proto in groups:
        try:
            offsets = admin.list_consumer_group_offsets(group_id)
        except KafkaError as exc:
            print(f"    [groups] {group_id} offset 조회 실패: {exc}")
            continue
        topic_offsets = {
            tp: meta.offset for tp, meta in offsets.items() if tp.topic == snapshot.topic
        }
        if topic_offsets:
            relevant.append((group_id, topic_offsets))

    if not relevant:
        print(f"    [groups] '{snapshot.topic}' 를 구독하는 group 없음")
        return

    for group_id, topic_offsets in relevant:
        total_lag = 0
        lines: list[str] = []
        for tp, committed in sorted(topic_offsets.items(), key=lambda x: x[0].partition):
            end = end_by_partition.get(tp.partition, 0)
            lag = max(0, end - committed) if committed >= 0 else end
            total_lag += lag
            lines.append(
                f"      part={tp.partition:>3} committed={committed:>12} "
                f"end={end:>12} lag={lag:>10}"
            )
        print(f"    [group] {group_id}  total_lag={total_lag}")
        for line in lines:
            print(line)


def _emit_tick(
    args: argparse.Namespace,
    admin: KafkaAdminClient,
    consumer: KafkaConsumer,
    topics: list[str],
    previous: dict[str, TopicSnapshot],
) -> dict[str, TopicSnapshot]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("=" * 88)
    print(f"[{now}] bootstrap={args.bootstrap_servers}")
    print(f"  {_fetch_cluster_summary(admin)}")

    next_state: dict[str, TopicSnapshot] = {}
    for topic in topics:
        snapshot = _snapshot_topic(consumer, topic)
        if snapshot is None:
            print(f"  topic={topic}  (메타데이터 없음 / 토픽 미존재)")
            continue
        _print_topic_block(snapshot, previous.get(topic))
        if args.groups:
            _print_consumer_groups(admin, snapshot)
        next_state[topic] = snapshot
    sys.stdout.flush()
    return next_state


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv if argv is not None else sys.argv[1:])
    topics = args.topic or [settings.kafka_topic]

    try:
        admin = _open_admin(args)
        consumer = _open_consumer(args)
    except NoBrokersAvailable as exc:
        print(f"[kafka_monitor] Kafka 연결 실패: {exc}", file=sys.stderr)
        return 1
    except KafkaError as exc:
        print(f"[kafka_monitor] Kafka 초기화 오류: {exc}", file=sys.stderr)
        return 1

    stop = {"flag": False}

    def _handle_signal(signum, _frame):  # noqa: ANN001 - signal 핸들러 시그니처
        stop["flag"] = True
        print(f"\n[kafka_monitor] 신호 수신({signum}), 종료 중...")

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    previous: dict[str, TopicSnapshot] = {}
    try:
        while not stop["flag"]:
            try:
                previous = _emit_tick(args, admin, consumer, topics, previous)
            except KafkaError as exc:
                print(f"[kafka_monitor] 일시 오류: {exc}", file=sys.stderr)
            if args.once:
                break
            # 짧은 슬립으로 잘게 쪼개 SIGINT 응답성 확보
            slept = 0.0
            while slept < args.interval and not stop["flag"]:
                step = min(0.5, args.interval - slept)
                time.sleep(step)
                slept += step
    finally:
        try:
            consumer.close()
        except Exception:
            pass
        try:
            admin.close()
        except Exception:
            pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
