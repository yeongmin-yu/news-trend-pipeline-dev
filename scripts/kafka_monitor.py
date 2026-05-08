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
import json
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kafka import KafkaAdminClient, KafkaConsumer
from kafka.errors import KafkaError, NoBrokersAvailable
from kafka.structs import TopicPartition


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from core.config import settings  # noqa: E402


KST = timezone(timedelta(hours=9), "KST")


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


@dataclass
class SparkCheckpointState:
    batch_id: int
    offsets: dict[str, dict[int, int]]
    updated_at: datetime

    def topic_offsets(self, topic: str) -> dict[int, int]:
        return self.offsets.get(topic, {})


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
        "--checkpoint-dir",
        default=str(PROJECT_ROOT / "runtime" / "checkpoints"),
        help="Spark Structured Streaming checkpoint 디렉터리. 기본: runtime/checkpoints.",
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
        return f"클러스터 상태: 확인 실패 ({exc.__class__.__name__})"
    brokers = cluster.get("brokers") or []
    controller = cluster.get("controller_id")
    cluster_id = cluster.get("cluster_id") or "?"
    broker_lines = ", ".join(
        f"{b.get('node_id')}@{b.get('host')}:{b.get('port')}" for b in brokers
    )
    return (
        f"클러스터: ID={cluster_id} / 컨트롤러={controller} / "
        f"브로커={broker_lines or '없음'}"
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


def _numeric_checkpoint_files(path: Path) -> list[Path]:
    if not path.exists() or not path.is_dir():
        return []
    return sorted(
        (child for child in path.iterdir() if child.is_file() and child.name.isdigit()),
        key=lambda child: int(child.name),
    )


def _load_checkpoint_state(checkpoint_dir: str) -> SparkCheckpointState | None:
    checkpoint_path = Path(checkpoint_dir)
    commits_dir = checkpoint_path / "commits"
    offsets_dir = checkpoint_path / "offsets"

    commit_files = _numeric_checkpoint_files(commits_dir)
    if not commit_files:
        return None

    for commit_file in reversed(commit_files):
        batch_id = int(commit_file.name)
        offset_file = offsets_dir / commit_file.name
        if not offset_file.exists():
            continue

        lines = offset_file.read_text(encoding="utf-8").splitlines()
        if not lines:
            continue

        raw_offsets = lines[-1].lstrip("\ufeff\x00")
        try:
            parsed_offsets = json.loads(raw_offsets)
        except json.JSONDecodeError:
            continue

        offsets: dict[str, dict[int, int]] = {}
        for topic, partition_offsets in parsed_offsets.items():
            if not isinstance(partition_offsets, dict):
                continue
            offsets[str(topic)] = {
                int(partition): int(offset)
                for partition, offset in partition_offsets.items()
            }

        updated_at = datetime.fromtimestamp(commit_file.stat().st_mtime, tz=KST)
        return SparkCheckpointState(
            batch_id=batch_id,
            offsets=offsets,
            updated_at=updated_at,
        )

    return None


def _format_rate(curr: TopicSnapshot, prev: TopicSnapshot | None) -> str:
    if prev is None or curr.timestamp <= prev.timestamp:
        return "초당 유입량: 계산 대기 중"
    delta_msgs = curr.total_end - prev.total_end
    delta_t = curr.timestamp - prev.timestamp
    rate = delta_msgs / delta_t if delta_t > 0 else 0.0
    return f"초당 유입량: {rate:,.2f}건/s ({delta_t:.1f}초 동안 {delta_msgs:+,d}건)"


def _format_int(value: int) -> str:
    return f"{value:,}"


def _print_topic_block(snapshot: TopicSnapshot, prev: TopicSnapshot | None) -> None:
    print()
    print(f"토픽: {snapshot.topic}")
    print(f"  파티션 수: {len(snapshot.partitions)}개")
    print(f"  현재 끝 offset 합계: {_format_int(snapshot.total_end)}")
    print(f"  보관 중인 메시지 수: {_format_int(snapshot.total_messages)}")
    print(f"  {_format_rate(snapshot, prev)}")
    print()
    print("  파티션별 상태")
    print("  - 시작 offset: Kafka에 아직 보관되어 있는 가장 오래된 메시지 위치")
    print("  - 끝 offset: 다음에 들어올 메시지 위치")
    print("  - 보관 메시지: 현재 Kafka에 남아 있는 메시지 수")
    print(f"  {'파티션':>6} {'시작 offset':>14} {'끝 offset':>14} {'보관 메시지':>12}")
    for part in snapshot.partitions:
        print(
            f"  {part.partition:>6} {_format_int(part.begin_offset):>14} "
            f"{_format_int(part.end_offset):>14} {_format_int(part.message_count):>12}"
        )


def _print_spark_checkpoint_block(
    snapshot: TopicSnapshot,
    checkpoint: SparkCheckpointState | None,
) -> None:
    if checkpoint is None:
        print()
        print("  Spark 처리 상태: checkpoint를 찾지 못했습니다.")
        print("  - --checkpoint-dir 값이 올바른지 확인하세요.")
        return

    topic_offsets = checkpoint.topic_offsets(snapshot.topic)
    if not topic_offsets:
        print()
        print(f"  Spark 처리 상태: checkpoint에 '{snapshot.topic}' offset이 없습니다.")
        return

    total_processed = 0
    total_unread = 0
    updated_at = checkpoint.updated_at.strftime("%Y-%m-%d %H:%M:%S %Z")

    print()
    print(f"  Spark 처리 상태: batch {checkpoint.batch_id}까지 완료 ({updated_at})")
    print("  - 처리 완료 offset: Spark가 checkpoint에 저장한 다음 읽을 위치")
    print("  - 처리 완료 메시지: 현재 Kafka 보관 구간 안에서 Spark가 처리한 메시지 수")
    print("  - 아직 안 읽은 메시지: Kafka 끝 offset - 처리 완료 offset")
    print(
        f"  {'파티션':>6} {'처리 완료 offset':>16} "
        f"{'처리 완료 메시지':>16} {'아직 안 읽음':>14}"
    )
    for part in snapshot.partitions:
        processed_offset = topic_offsets.get(part.partition)
        if processed_offset is None:
            processed_count = 0
            unread_count = part.message_count
            processed_display = "-"
        else:
            processed_count = max(0, min(processed_offset, part.end_offset) - part.begin_offset)
            unread_count = max(0, part.end_offset - processed_offset)
            processed_display = _format_int(processed_offset)
        total_processed += processed_count
        total_unread += unread_count
        print(
            f"  {part.partition:>6} {processed_display:>16} "
            f"{_format_int(processed_count):>16} {_format_int(unread_count):>14}"
        )
    print(
        f"  합계: 처리 완료 메시지 {_format_int(total_processed)}건 / "
        f"아직 안 읽은 메시지 {_format_int(total_unread)}건"
    )


def _print_consumer_groups(
    admin: KafkaAdminClient, snapshot: TopicSnapshot
) -> None:
    try:
        groups = admin.list_consumer_groups()
    except KafkaError as exc:
        print(f"  Consumer group 조회 실패: {exc.__class__.__name__}: {exc}")
        return
    if not groups:
        print("  Consumer group: 등록된 group 없음")
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
        print(f"  Consumer group: '{snapshot.topic}'를 구독하는 group 없음")
        return

    print()
    print("  Consumer group lag")
    print("  - 처리 완료 offset: 해당 group이 마지막으로 처리했다고 기록한 위치")
    print("  - 지연 메시지: 끝 offset과 처리 완료 offset의 차이")
    for group_id, topic_offsets in relevant:
        total_lag = 0
        lines: list[str] = []
        for tp, committed in sorted(topic_offsets.items(), key=lambda x: x[0].partition):
            end = end_by_partition.get(tp.partition, 0)
            lag = max(0, end - committed) if committed >= 0 else end
            total_lag += lag
            lines.append(
                f"    {tp.partition:>6} {_format_int(committed):>16} "
                f"{_format_int(end):>14} {_format_int(lag):>12}"
            )
        print(f"  group: {group_id} / 전체 지연 메시지: {_format_int(total_lag)}")
        print(f"    {'파티션':>6} {'처리 완료 offset':>16} {'끝 offset':>14} {'지연 메시지':>12}")
        for line in lines:
            print(line)


def _emit_tick(
    args: argparse.Namespace,
    admin: KafkaAdminClient,
    consumer: KafkaConsumer,
    topics: list[str],
    previous: dict[str, TopicSnapshot],
) -> dict[str, TopicSnapshot]:
    now = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z")
    print("=" * 88)
    print(f"Kafka 모니터링 시각: {now}")
    print(f"접속 서버: {args.bootstrap_servers}")
    print(_fetch_cluster_summary(admin))
    checkpoint = _load_checkpoint_state(args.checkpoint_dir)

    next_state: dict[str, TopicSnapshot] = {}
    for topic in topics:
        snapshot = _snapshot_topic(consumer, topic)
        if snapshot is None:
            print()
            print(f"토픽: {topic}")
            print("  상태: 메타데이터 없음 또는 토픽 미존재")
            continue
        _print_topic_block(snapshot, previous.get(topic))
        _print_spark_checkpoint_block(snapshot, checkpoint)
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
