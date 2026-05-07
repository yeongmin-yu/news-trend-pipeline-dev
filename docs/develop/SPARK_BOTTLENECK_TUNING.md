# Spark Streaming 병목 진단 및 튜닝 기록

> 기준일: 2026-05-06  
> 환경: Docker Desktop + WSL2 기반 로컬 개발 환경  
> 구성: Kafka, Spark standalone, PostgreSQL, Airflow, FastAPI, Dashboard

## 1. 문제 상황

로컬 PC에서 전체 인프라를 한 번에 띄운 상태에서 뉴스 수집 후 Spark 처리가 원활하지 않았다.

겉으로 보인 증상은 다음과 같았다.

- Spark batch가 오래 걸리거나 멈춘 것처럼 보였다.
- Docker Desktop API가 `500 Internal Server Error`를 반환했다.
- Spark 로그에 `Python worker exited unexpectedly`, `Broken pipe`가 발생했다.
- Spark streaming 컨테이너를 멈추는 명령도 바로 먹히지 않을 정도로 Docker Desktop이 흔들렸다.

처음에는 메모리 부족처럼 보였지만, 실제로는 한 번에 처리하려는 데이터 양과 Spark 작업 분할 방식이 현재 PC 자원에 비해 부담스러운 상태였다.

## 2. 병목이 생긴 원인

### 2.1 Kafka backlog가 한 batch에 크게 몰림

수집 DAG가 한 번에 많은 메시지를 Kafka에 넣으면 Spark가 다음 micro-batch에서 그 backlog를 크게 가져가려 한다.

기존 코드에는 `maxOffsetsPerTrigger` 설정이 있었지만, 로컬 compose 실행에서 조절값이 명확히 드러나 있지 않았다. 값이 크거나 checkpoint에 이미 큰 batch가 잡힌 상태에서는 Spark가 한 번에 무거운 작업을 다시 시도한다.

쉽게 말하면, Spark가 밥을 조금씩 먹어야 하는데 한 번에 많이 먹고 체한 상황이다.

### 2.2 한국어 토큰화가 Python UDF에 몰림

Spark 집계 자체보다 기사 본문을 토큰화하는 단계가 무겁다.

현재 파이프라인은 Spark DataFrame에서 Python UDF를 호출해 `processing.preprocessing.tokenize()`를 실행한다. 이 작업이 적은 partition에 몰리면 특정 Python worker가 오래 일하거나 죽을 수 있다.

### 2.3 PostgreSQL JDBC write가 batch 처리 시간을 좌우함

Spark는 최종 테이블에 직접 쓰지 않고 다음 staging table에 먼저 append한다.

- `stg_news_raw`
- `stg_keywords`
- `stg_keyword_trends`
- `stg_keyword_relations`

그 다음 DB 내부 upsert 함수를 호출한다.

관찰 결과, DB upsert 자체는 대부분 빠르게 끝났다. 더 큰 부담은 Spark가 JDBC로 staging table에 데이터를 쓰는 구간이었다. 특히 `stg_news_raw`는 제목, 요약, URL 같은 TEXT 컬럼이 있어 쓰기 비용이 크다.

### 2.4 로컬 PC에서 너무 많은 서비스가 동시에 실행됨

현재 개발 환경은 다음 서비스를 동시에 띄운다.

- Kafka
- Zookeeper
- Spark master
- Spark worker 2개
- Spark streaming driver
- Spark history server
- PostgreSQL
- Airflow API server
- Airflow scheduler
- Airflow dag processor
- Airflow triggerer
- FastAPI
- Dashboard

이 구성은 학습과 시연에는 좋지만, 로컬 PC 자원에서는 CPU 경합이 쉽게 생긴다. Spark만 튜닝해도 Airflow, Kafka, PostgreSQL이 동시에 CPU를 쓰면 전체 Docker Desktop이 버거워질 수 있다.

## 3. 현재 PC 자원 상황

Docker Desktop 기준으로 사용 가능한 메모리 한도는 약 7.7GiB로 관찰됐다.

문제가 있던 시점에는 Spark worker와 Kafka, Airflow dag processor가 동시에 CPU를 크게 사용했다. 특히 큰 checkpoint batch를 재시도할 때는 다음 현상이 있었다.

- Spark worker CPU가 높게 유지됨
- Spark worker 메모리가 2GiB 이상까지 상승
- Kafka와 Spark가 동시에 CPU를 사용
- Docker API가 컨테이너 상태 조회나 stop 명령에도 실패

새 checkpoint로 복구한 뒤에는 안정적인 batch 처리 상태가 관찰됐다.

예시:

```text
batch_id=1 elapsed=7.73s
batch_id=2 elapsed=7.58s
batch_id=3 elapsed=6.25s
batch_id=4 elapsed=7.92s
batch_id=5 elapsed=10.63s
batch_id=6 elapsed=6.96s
batch_id=7 elapsed=6.56s
batch_id=8 elapsed=6.70s
```

즉 현재 PC에서는 "한 번에 크게 처리"보다 "작은 batch를 꾸준히 처리"하는 방향이 더 안정적이다.

## 4. 개선 방향

이번 개선의 방향은 성능을 무작정 끌어올리는 것이 아니라, 로컬 자원 안에서 처리량을 안정적으로 유지하는 것이다.

### 4.1 Kafka에서 가져오는 양 줄이기

`SPARK_MAX_OFFSETS_PER_TRIGGER`를 명시하고 로컬 기본값을 낮췄다.

```env
SPARK_MAX_OFFSETS_PER_TRIGGER=150
```

의미:

- Spark가 Kafka에서 한 batch에 가져오는 최대 메시지 수를 제한한다.
- backlog가 쌓여도 한 번에 모두 가져오지 않는다.
- batch 하나가 너무 커져 Python worker나 Docker Desktop이 흔들리는 상황을 줄인다.

### 4.2 토큰화 전에 Spark partition 나누기

토큰화 UDF를 실행하기 전에 repartition을 추가했다.

```env
SPARK_PREPROCESS_PARTITIONS=4
```

의미:

- 기사 전처리 작업을 더 작은 조각으로 나눈다.
- 특정 Spark task나 Python worker에 일이 몰리는 것을 완화한다.
- 한국어 토큰화처럼 CPU를 많이 쓰는 작업을 더 안정적으로 실행한다.

### 4.3 PostgreSQL JDBC write 조절

JDBC write batch 크기와 write partition 수를 설정값으로 뺐다.

```env
SPARK_JDBC_BATCH_SIZE=2000
SPARK_JDBC_NUM_PARTITIONS=2
```

의미:

- PostgreSQL에 너무 큰 insert batch를 한 번에 보내지 않는다.
- DB write 병렬도를 현재 로컬 PC와 PostgreSQL이 감당 가능한 수준으로 제한한다.
- 필요하면 운영 환경이나 더 좋은 PC에서 값을 올릴 수 있다.

### 4.4 Spark worker 자원 명시

Spark worker의 코어와 메모리를 환경변수로 조절할 수 있게 했다.

```env
SPARK_WORKER_CORES=1
SPARK_WORKER_MEMORY=2G
```

현재 로컬 안정형 구성은 worker 2개, 각 1 core, 2G 메모리다.

총 Spark executor core는 2개다. 이전에 4 core까지 올려보면 순간 처리량은 올라갈 수 있었지만, 현재 PC에서는 Docker Desktop 전체가 불안정해지는 문제가 있었다. 따라서 기본값은 안정성을 우선한다.

### 4.5 문제 checkpoint 백업 후 새 checkpoint로 시작

기존 Spark checkpoint에는 이미 무거운 batch가 기록되어 있었다.

이 상태에서는 설정을 낮춰도 Spark가 같은 큰 batch를 계속 재시도했다. 그래서 checkpoint를 삭제하지 않고 백업한 뒤 새 checkpoint로 시작했다.

백업 위치:

```text
runtime/checkpoints-backup-20260506-235824
```

이후 Spark는 새 입력부터 작은 batch 단위로 안정적으로 처리했다.

## 5. 변경된 주요 설정

현재 로컬 안정형 기본값은 다음과 같다.

```env
SPARK_WORKER_CORES=1
SPARK_WORKER_MEMORY=2G
SPARK_SHUFFLE_PARTITIONS=8
SPARK_MAX_OFFSETS_PER_TRIGGER=150
SPARK_PREPROCESS_PARTITIONS=4
SPARK_JDBC_BATCH_SIZE=2000
SPARK_JDBC_NUM_PARTITIONS=2
RELATION_KEYWORD_LIMIT=2
```

설정별 역할:

| 설정 | 역할 |
|---|---|
| `SPARK_MAX_OFFSETS_PER_TRIGGER` | Kafka에서 한 batch에 가져올 최대 메시지 수 |
| `SPARK_PREPROCESS_PARTITIONS` | 토큰화 전에 데이터를 나누는 partition 수 |
| `SPARK_JDBC_BATCH_SIZE` | PostgreSQL JDBC insert batch 크기 |
| `SPARK_JDBC_NUM_PARTITIONS` | PostgreSQL에 동시에 쓰는 Spark partition 수 |
| `SPARK_WORKER_CORES` | Spark worker 하나가 제공하는 core 수 |
| `SPARK_WORKER_MEMORY` | Spark worker 하나가 제공하는 memory |
| `RELATION_KEYWORD_LIMIT` | 기사별 연관어 조합에 사용할 상위 키워드 수 |

## 6. 개선 후 얻은 점

개선 후 확인된 가장 큰 변화는 batch가 다시 꾸준히 완료된다는 점이다.

이전:

- 큰 batch가 잡히면 수 분 이상 처리
- Python worker crash 발생
- Docker API 500 발생
- 컨테이너 stop 명령도 실패

이후:

- batch가 약 6-10초 수준으로 완료
- `Spark batch finished` 로그가 연속적으로 출력
- 확인 구간에서 Python worker crash 없음
- Spark worker 메모리 사용량이 감당 가능한 범위로 유지
- 문제가 있던 checkpoint batch를 더 이상 재시도하지 않음

결론적으로, 이번 개선은 최대 처리량을 높이는 튜닝이라기보다 로컬 개발 환경에서 파이프라인이 끊기지 않고 계속 흐르게 만드는 안정화 작업이다.

## 7. 앞으로의 운영 기준

정상 범위:

- 일반 batch elapsed: 5-15초
- backlog 처리 중 batch elapsed: 30초 이내면 관찰 가능
- `upsert_*` 단계: 보통 1초 안팎
- `write_stg_*` 단계: 몇 초 수준

주의 기준:

- `Spark batch finished`가 오래 찍히지 않음
- batch elapsed가 60초 이상 반복됨
- `Python worker exited unexpectedly` 발생
- `Broken pipe` 발생
- Docker API가 컨테이너 상태 조회나 stop 명령에 500을 반환

확인 명령:

```powershell
docker compose logs --no-log-prefix --tail=200 spark-streaming |
  Select-String -Pattern "Spark batch|step=|ERROR|Exception|Python worker|Broken pipe"
```

```powershell
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

## 8. 튜닝값을 바꿀 때의 기준

더 안정적으로 낮추고 싶을 때:

```env
SPARK_MAX_OFFSETS_PER_TRIGGER=100
SPARK_PREPROCESS_PARTITIONS=4
SPARK_JDBC_BATCH_SIZE=1000
SPARK_JDBC_NUM_PARTITIONS=1
```

더 빠르게 처리하고 싶을 때:

```env
SPARK_MAX_OFFSETS_PER_TRIGGER=300
SPARK_PREPROCESS_PARTITIONS=4
SPARK_JDBC_BATCH_SIZE=3000
SPARK_JDBC_NUM_PARTITIONS=2
```

단, 현재 PC에서는 worker core를 4개 이상으로 올리는 것은 신중해야 한다. 순간 처리량은 좋아질 수 있지만 Kafka, Airflow, PostgreSQL까지 함께 돌기 때문에 Docker Desktop 전체가 다시 불안정해질 수 있다.

## 9. 핵심 요약

이번 병목의 핵심은 Spark 자체가 느린 것이 아니라, 로컬 PC가 감당하기 어려운 크기의 batch를 Spark가 한 번에 처리하려 했다는 점이다.

따라서 해결 방향은 다음과 같다.

1. Kafka에서 가져오는 데이터를 작게 나눈다.
2. Spark 내부 전처리 작업을 더 잘게 나눈다.
3. PostgreSQL write도 한 번에 너무 크게 보내지 않는다.
4. 문제가 있는 checkpoint는 백업하고 새 checkpoint로 재시작한다.
5. 로컬 환경에서는 최대 처리량보다 안정적인 지속 처리를 우선한다.

## 10. 추가 진단: batch 603 장기 실행

2026-05-07에 Spark job이 오래 끝나지 않는 상황을 추가로 확인했다.

현상:

- Spark UI 기준 `batch = 603` job이 오랫동안 `RUNNING` 상태로 남아 있었다.
- 처음 확인했을 때 executor 목록에는 driver만 있고 worker executor가 없었다.
- Spark master 로그에는 worker heartbeat timeout과 executor lost가 기록되어 있었다.
- 이후 streaming 컨테이너를 재시작하면 executor는 다시 붙었지만, 같은 batch 603에서 Python worker crash가 반복됐다.

확인된 로그 패턴:

```text
Lost executor ... Remote RPC client disassociated
Python worker exited unexpectedly (crashed)
java.io.EOFException
java.net.SocketException: Connection reset
```

batch 603의 Kafka offset 범위는 크지 않았다.

```text
partition 0: 128813 -> 128843  (30 messages)
partition 1: 127640 -> 127668  (28 messages)
total: 약 58 messages
```

즉 이 문제는 큰 backlog 때문이라기보다, 작은 batch 안에서 Spark Python UDF 실행이 불안정해진 문제에 가깝다.

같은 58건을 Spark 이미지 안에서 단독 Python script로 `tokenize()`에 넣었을 때는 모두 성공했다. 따라서 특정 기사 하나가 tokenizer를 즉시 죽인다고 보기는 어렵다. 더 가능성 높은 원인은 Spark executor 안에서 Python worker가 반복 실행되는 과정, Kiwi 사전 로딩, Python worker 재시도, Docker Desktop 자원 압박이 겹친 것이다.

추가로 코드 구조상 비효율도 있었다.

기존 구조:

```text
Kafka read
-> parse
-> tokens 컬럼 생성
-> foreachBatch
   -> stg_news_raw 저장
   -> keyword/trend/relation 저장
```

이 구조에서는 원문 저장(`stg_news_raw`)에는 토큰이 필요 없는데도, Spark lineage 상 토큰화 UDF가 함께 끌려올 수 있었다.

개선 구조:

```text
Kafka read
-> parse
-> foreachBatch
   -> stg_news_raw 저장
   -> 그 다음에만 tokens 컬럼 생성
   -> article_keywords persist
   -> keyword/trend/relation 저장
   -> article_keywords unpersist
```

수정 후 확인된 효과:

```text
write_stg_news_raw before: 104.34s
write_stg_news_raw after :   2.83s
```

즉 원문 저장 단계가 토큰화 lineage에 끌려 느려지는 문제는 개선됐다. 다만 `write_stg_keywords` 단계에서 Python worker crash가 계속 발생했으므로, batch 603 자체는 여전히 위험한 checkpoint batch로 남아 있다.

현재 판단:

- `write_stg_news_raw` 병목은 코드 구조 개선으로 완화됐다.
- 남은 병목은 Spark Python UDF 토큰화 실행 안정성이다.
- batch 603을 계속 재시도하면 Docker Desktop이 다시 500 응답을 낼 수 있다.
- 실시간 처리 복구가 우선이면 checkpoint를 백업하고 새 checkpoint로 시작하는 것이 현실적이다.

## 11. Checkpoint 설명

Spark Structured Streaming의 checkpoint는 단순한 임시 파일이 아니다. 스트리밍 잡이 어디까지 처리했는지 기억하는 복구 상태다.

이 프로젝트의 checkpoint 위치:

```env
SPARK_CHECKPOINT_DIR=./runtime/checkpoints
```

checkpoint 안에는 주로 다음 정보가 들어간다.

| 디렉터리/파일 | 의미 |
|---|---|
| `offsets/` | batch별 Kafka offset. 각 batch가 어디까지 읽었는지 기록 |
| `commits/` | batch 처리 완료 여부 |
| `sources/` | Kafka source 관련 metadata |
| `metadata` | streaming query 식별 정보 |

예를 들어 batch 603의 offset이 다음과 같다면:

```text
{"news_topic":{"1":127668,"0":128843}}
```

Spark는 batch 603에서 Kafka `news_topic`의 partition 1은 offset 127668까지, partition 0은 offset 128843까지 읽는 작업을 하려 했다는 뜻이다.

중요한 점은 다음이다.

> batch가 실패하면 Spark는 다음 재시작 때 같은 batch를 다시 시도한다.

그래서 batch 603이 Python worker crash로 끝나지 못하면, streaming 컨테이너를 재시작해도 Spark는 batch 604로 넘어가지 않고 batch 603을 다시 실행한다. 이 동작은 데이터 유실을 막기 위한 정상적인 복구 방식이다.

하지만 로컬 개발 환경에서는 이 특성이 문제를 만들 수 있다.

- 실패하는 batch가 계속 재시도됨
- 같은 Python worker crash가 반복됨
- executor가 lost 됨
- Docker Desktop 전체가 다시 불안정해짐

이럴 때 checkpoint를 백업하고 새 checkpoint로 시작하면 Spark는 이전 실패 batch를 더 이상 재시도하지 않는다. 대신 그 batch의 Kafka 메시지는 Spark 처리 관점에서는 건너뛴다.

따라서 checkpoint 초기화는 데이터 정합성과 운영 복구 사이의 선택이다.

## 12. 파티셔닝을 바꾸면 checkpoint를 리셋해야 하나?

항상 리셋해야 하는 것은 아니다.

하지만 다음 경우에는 checkpoint 백업 후 새로 시작하는 것이 안전하다.

1. 기존 checkpoint가 실패 batch를 계속 재시도하는 경우
2. streaming query의 구조를 크게 바꾼 경우
3. source, sink, schema, stateful 연산 구조가 바뀐 경우
4. Spark가 checkpoint 안의 과거 설정을 계속 적용하는 경우
5. `spark.sql.shuffle.partitions` 같은 실행 설정 변경이 실제 실행에 반영되지 않는 경우

이번 프로젝트에서 실제로 관찰한 현상:

```text
WARN OffsetSeqMetadata:
Updating the value of conf 'spark.sql.shuffle.partitions'
in current session from '8' to '2'.
```

이 메시지는 새 실행 설정은 8인데, checkpoint에 남아 있던 이전 batch metadata 때문에 Spark가 현재 세션 값을 다시 2로 맞췄다는 뜻이다.

즉 `.env`나 `docker-compose.yml`에서 partition 값을 바꿔도, 기존 checkpoint를 이어서 실행하면 Spark가 과거 설정을 따라갈 수 있다.

정리하면:

| 변경 내용 | checkpoint 리셋 필요성 |
|---|---|
| `SPARK_MAX_OFFSETS_PER_TRIGGER` 변경 | 보통 불필요. 다음 batch부터 적용 가능 |
| `SPARK_JDBC_BATCH_SIZE` 변경 | 보통 불필요. foreachBatch 내부 write 설정 |
| `SPARK_JDBC_NUM_PARTITIONS` 변경 | 보통 불필요. 단, 실패 batch가 있으면 재시도 영향 있음 |
| `SPARK_PREPROCESS_PARTITIONS` 변경 | 보통 불필요. 단, 같은 실패 batch를 계속 물고 있으면 새 checkpoint 권장 |
| `SPARK_SHUFFLE_PARTITIONS` 변경 | 기존 checkpoint가 과거 값을 복원할 수 있어 새 checkpoint 권장 |
| Kafka topic, source, checkpoint path 변경 | 새 checkpoint 필요 |
| output sink 구조 변경 | 새 checkpoint 권장 |
| streaming aggregation/state 구조 변경 | 새 checkpoint 필요 가능성 큼 |

운영 관점 권장:

- 단순 튜닝값 변경이면 먼저 기존 checkpoint로 재시작해본다.
- 로그에 과거 설정 복원 경고가 나오거나 같은 batch가 계속 실패하면 checkpoint를 백업한다.
- 백업 후 `runtime/checkpoints`를 비우고 새 checkpoint로 시작한다.
- 데이터 유실이 걱정되면 백업된 checkpoint의 offset 구간을 별도 Python batch로 재처리한다.

안전한 checkpoint 백업 방식:

```powershell
docker stop news-trend-develop-spark-streaming-1

$backup = ".\runtime\checkpoints-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss")
New-Item -ItemType Directory -Path $backup -Force | Out-Null
Get-ChildItem .\runtime\checkpoints -Force |
  Where-Object { $_.Name -ne ".gitkeep" } |
  Move-Item -Destination $backup

docker compose up -d spark-streaming
```

핵심은 checkpoint를 바로 삭제하지 않고 백업해두는 것이다. 그래야 나중에 어떤 Kafka offset batch가 문제였는지 추적하거나 별도 재처리할 수 있다.
