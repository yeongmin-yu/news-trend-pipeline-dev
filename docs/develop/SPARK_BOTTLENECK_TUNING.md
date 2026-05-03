# Spark Streaming 병목 진단 & 튜닝 기록

> 일자: 2026-05-03
> 환경: docker-compose 로컬 dev (Postgres + Kafka + Spark 3.5.7 standalone)
> 트리거: RSS 인제스션 DAG 가동 후 첫 큰 배치(3,036 메시지) 처리에 4분 소요

## 1. 증상

- RSS DAG 가동 직후, **batch_id=2 가 239초 (~4분)** 동안 처리됨.
- 사용자 체감: "메모리가 치솟고 Spark 가 막힌 느낌".
- Kafka 적체: news_topic 두 파티션 합 3,036건.

```text
batch_id=1 elapsed=6.63s     ← 작은 배치
batch_id=2 elapsed=239.18s   ← 3,036건 backlog 한 번에
```

## 2. 단계별 elapsed (batch 2)

```text
write_stg_news_raw          112.77s   ← 가장 오래
write_stg_keyword_trends     55.60s
write_stg_keyword_relations  32.32s
write_stg_keywords           19.96s
upsert_keywords               7.89s
upsert_keyword_relations      5.98s
upsert_keyword_trends         4.04s
upsert_news_raw               0.21s
build_*                       <0.5s
─────────────────────────────────────
TOTAL                       239.18s
```

핵심 관찰: **Spark JDBC `write_stg_*` 가 병목** (전체의 90%+). 정작 Postgres 측 `upsert_*` 는 매우 빠름.

## 3. 원인 분석

### 3-1. 메모리는 진짜 원인이 아니었음

| 컨테이너 | 사용량 | 한도 | 비율 |
|---|---|---|---|
| spark-streaming(driver) | 626 MiB | 7.7 GiB | 8% |
| spark-worker-1 | 452 MiB | 7.7 GiB | 6% |
| spark-worker-2 | 525 MiB | 7.7 GiB | 7% |
| Spark executor JVM peak heap | **215 MB** | 2 GB | 11% |

→ 사용자가 본 "메모리 치솟음" 은 **Docker Desktop 의 WSL2 VM 전체 표시** 였음.
   JVM heap 자체는 여유 충분.

### 3-2. 실제 원인 ① — executor 병렬도 부족

```text
spark-worker 설정: --cores 1 --memory 2G    (워커당 1 코어)
spark.sql.shuffle.partitions: 2

→ 클러스터 전체 동시 실행 가능 task 수 = 2개
→ Spark JDBC writer 의 write 병렬도 = DataFrame partition 수 = 2
→ 큰 배치든 작은 배치든 항상 2-way 직렬화
```

Spark UI 에서 본 task 분포 (batch 2):
- executor 1: 28 task / 191s 누적
- executor 0: 10 task / 85s 누적
- 작업 불균형 + 1 코어 직렬화

### 3-3. 실제 원인 ② — `write_stg_news_raw` 가 유난히 느린 이유

stg_news_raw 는 `title`, `summary`, `url` 등 큰 TEXT 컬럼을 가짐. 큰 페이로드를
2개 JDBC 커넥션이 직렬로 전송하는 동안 다른 step 도 병목.

`reWriteBatchedInserts=true` 자체는 이미 적용돼 있었지만, **연결 수가 적어**
batching 효과를 못 살리고 있었음.

### 3-4. 실제 원인 ③ — backlog 폭탄

RSS DAG 가 한 번에 3,036건을 Kafka 에 쏟아 넣은 직후의 **첫 큰 배치**.
Spark Structured Streaming 은 기본 trigger 가 "직전 배치 완료 즉시 다음 배치"
이기에, 한 배치에 모든 backlog 가 몰림.

## 4. 적용한 변경

### ★★★ 1) 워커 코어 수 1 → 2

[docker-compose.yml](../../docker-compose.yml) `spark-worker-1`, `spark-worker-2`:
```diff
- --cores 1 --memory 2G
+ --cores 2 --memory 2G
```
→ 클러스터 총 코어: 2 → **4**

### ★★★ 2) `spark.sql.shuffle.partitions` 2 → 8

[docker-compose.yml](../../docker-compose.yml) `spark-streaming`:
```diff
+ SPARK_SHUFFLE_PARTITIONS: ${SPARK_SHUFFLE_PARTITIONS:-8}
```
→ 셔플 후 task 수가 늘어 4 코어를 잘 활용. 작업 분배 균형도 개선.

(설정 자체는 [src/core/config.py](../../src/core/config.py) 의
`spark_shuffle_partitions` 가 읽어 [build_spark_session](../../src/processing/spark_job.py) 에서 적용됨)

## 5. 적용 후 측정

같은 RSS 데이터 흐름 + 평소 ingestion 양 기준.

| batch | before (cores=1, shuffle=2) | after (cores=2, shuffle=8) |
|---|---|---|
| 첫 backlog (3,036건) | **239.18s** | n/a |
| 일반 배치 #3 | — | 6.23s |
| 일반 배치 #4 | — | 7.15s |
| 일반 배치 #5 | — | 9.28s |
| 일반 배치 #6 | — | 4.40s |

after 의 step 별 분해 (batch_id=5):
```text
write_stg_news_raw            5.96s   (이전 112.77s의 1/19)
write_stg_keywords            0.99s
write_stg_keyword_trends      0.87s
write_stg_keyword_relations   1.22s
upsert_*                      <0.05s 각각
TOTAL                         9.28s   (이전 batch 2 의 1/26)
```

→ **약 26~36배 단축**. 일반 배치는 5~10초로 안정.

## 6. 추가 권장 (★★, 아직 미적용)

상시 인입량이 더 커지거나, RSS DAG 같은 일괄 backlog 를 매번 처리해야 할 때 검토.

| # | 조치 | 대상 | 효과 | 적용 방법 |
|---|---|---|---|---|
| ★★ | `maxOffsetsPerTrigger=500` (혹은 1000) | Kafka source | 한 배치당 행수 캡 → backlog 도 균등 분할 처리 | [spark_job.py](../../src/processing/spark_job.py) 의 `readStream` 옵션에 추가 |
| ★★ | 워커 메모리 2G → 3G | spark-worker 컨테이너 | shuffle/cache 시 OOM 안전 마진 | `--memory 2G` → `3G` |
| ★ | JDBC writer `numPartitions` 명시 (예: 4) | `_jdbc_write` | 큰 TEXT 가 있는 테이블에서 더 분산된 동시 INSERT | `df.repartition(4).write.option("numPartitions", "4")...` |
| ★ | `spark.streaming.backpressure.enabled=true` | streaming conf | 처리량 자동 조정 | `build_spark_session` 에 1줄 |

## 7. 운영 가이드 — 평상시 관찰 지표

**정상 범위 (RSS 만 가동, naver 비활성)**:
- 배치 간격: ~10초~수십초 (Spark 자체 trigger 주기)
- 배치 elapsed: 5~15초
- 배치당 행 수: 5~50건 (10분 윈도우 안에 수집된 수)

**경보 기준**:
- 배치 elapsed > 60초가 연속 → 인입량 급증 또는 PG/네트워크 병목
- step 중 `upsert_*` 가 1초 이상 → PG 인덱스/락 문제 의심
- step 중 `write_stg_*` 가 10초 이상 → JDBC writer 병렬도 부족 또는 큰 페이로드

## 8. 다시 측정하려면

```bash
# 모든 배치 elapsed 보기
docker compose logs --no-log-prefix spark-streaming 2>&1 | grep "Spark batch finished"

# step 별 분해 (특정 batch_id)
docker compose logs --no-log-prefix spark-streaming 2>&1 | grep "batch_id=5 step="

# 현재 executor 자원
curl -s http://localhost:4040/api/v1/applications/$(curl -s http://localhost:4040/api/v1/applications | jq -r '.[0].id')/executors \
  | jq '.[] | {id, cores: .totalCores, peakHeapMB: (.peakMemoryMetrics.JVMHeapMemory/1024/1024)}'
```

## 9. 학습 포인트

1. **체감이 메모리 문제 같아도 실제는 CPU 병렬도** 일 수 있음. 항상 stat 으로 검증.
2. **Spark JDBC writer 의 동시성** = DataFrame partition 수. 셔플 안 된 source 라면 source partition 수가 캡.
3. **Backlog 첫 배치는 항상 비대해짐** — `maxOffsetsPerTrigger` 로 보호하는 게 운영 안정.
4. **단계별 elapsed 로깅** ([spark_job.py](../../src/processing/spark_job.py) `_log_batch_step`) 이 결정적이었음. 도입 안 했으면 어디가 느린지 못 찾았을 것.
