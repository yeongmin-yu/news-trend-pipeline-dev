# 장애 대응 및 복구 가이드

Dead Letter Queue 관리, 자동/수동 재처리, 그리고 영구 실패 메시지 대응 방법을 설명합니다.

---

## 1. 핵심 개념

### replay.py의 책임범위

**replay.py는 오직 하나의 역할만 합니다:**
- ✅ **Kafka 전송 실패만 재시도** (이미 수집된 메시지의 Kafka 전송 재시도)

**replay.py가 할 수 없는 것들:**
- ❌ API 네트워크 장애 (NewsAPI/Naver 타임아웃, 연결 끊김)
- ❌ Kafka 브로커 다운 (브로커 자체가 실행 중이 아님)
- ❌ API 키 만료/오류 (인증 실패)
- ❌ 기타 인프라 문제 (Docker 네트워크, 권한 문제)

이런 문제들은 **Airflow 로그에 기록되고, 관리자가 수동으로 원인을 해결**해야 합니다.

### 메시지 상태 흐름

```
API 수집 성공
    ↓
[Kafka 전송 시도]
    ├─ 성공 → news_topic ✅
    └─ 실패 → dead_letter.jsonl (attempt=1)
              ↓
           [auto_replay_dag 또는 수동 replay.py]
              ├─ 성공 → dead_letter_replayed.jsonl ✅
              ├─ 재실패 (attempt: 1→2, 2→3) → dead_letter.jsonl
              └─ 3회 초과 → dead_letter_permanent.jsonl
                           ↓
                      🔔 수동 개입 필요
```

### 파일 위치

```
state/
├── dead_letter.jsonl              # 재시도 가능한 메시지 (attempt ≤ 3)
├── dead_letter_replayed.jsonl     # 재처리 성공한 메시지 ✅
└── dead_letter_permanent.jsonl    # 영구 실패 메시지 (attempt > 3) 🔴
```

---

## 2. 장애 유형별 대응

### A. Kafka 전송 실패 (재시도 가능)

**증상:**
- `KafkaTimeoutError`, `KafkaError` 발생
- 메시지가 `state/dead_letter.jsonl`에 기록됨
- Airflow 로그: "전송 실패 콜백" 또는 "Kafka 타임아웃"

**원인:**
- 일시적 네트워크 지연
- Kafka 브로커의 임시 부하
- Producer 버퍼 오버플로우

**자동 대응:**
`auto_replay_dag`가 15분마다 자동으로 재처리합니다.

**수동 즉시 재처리:**
```bash
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py
```

---

### B. Kafka 브로커 다운

**증상:**
- `NoBrokersAvailable` 또는 `ConnectionRefusedError`
- 모든 메시지 전송 실패
- `dead_letter.jsonl` 급증

**복구 절차:**

**Step 1: 상태 확인**
```bash
docker compose logs kafka | tail -20
```

**Step 2: Kafka 재시작**
```bash
docker compose restart kafka zookeeper
sleep 10
```

**Step 3: Topic 재생성 (필요시)**
```bash
docker compose exec kafka kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --create --if-not-exists \
  --topic news_topic \
  --partitions 2 \
  --replication-factor 1
```

**Step 4: 자동 또는 수동 재처리**
- 자동: `auto_replay_dag`가 다음 15분마다 재처리
- 수동:
  ```bash
  docker compose exec airflow-scheduler \
    python /opt/news-trend-pipeline/ingestion/replay.py
  ```

---

### C. API 네트워크 장애 (재시도 불가)

**증상:**
- API 호출 실패 (타임아웃, 연결 거부)
- Airflow 로그: "API 수집 실패", "ConnectionError", "TimeoutError"
- `news_ingest_dag`의 task 실패

**원인:**
- NewsAPI/Naver 서버 다운 또는 느린 응답
- 네트워크 연결 문제
- API 서버 변경 (DNS 문제)

**대응:**

**Step 1: API 서버 상태 확인**
```bash
# NewsAPI 확인
curl -I https://newsapi.org/v2/everything

# Naver API 확인
curl -I https://openapi.naver.com/v1/search/news.json
```

**Step 2: 원인 파악**
- API 서버 상태 페이지 확인
- 네트워크 연결 상태 확인
  ```bash
  docker compose exec airflow-scheduler ping newsapi.org
  docker compose exec airflow-scheduler ping openapi.naver.com
  ```

**Step 3: 서비스 복구 대기**
- API 서버가 정상화될 때까지 대기
- 이 기간 동안 `news_ingest_dag`는 계속 실패 로그만 기록

**Step 4: 데이터 손실 최소화**
- API 서버 복구 후, `news_ingest_dag`가 자동으로 재시작
- 증분 수집 로직(`last_timestamp`)이 누락 기사를 보완

> **중요**: 이 장애는 **replay.py로 해결 불가능**합니다.  
> replay.py는 이미 수집된 메시지의 Kafka 전송만 재시도하므로, API 수집 자체가 실패하면 메시지가 없습니다.

---

### D. API 키 만료/오류 (재시도 불가)

**증상:**
- Airflow 로그: "401 Unauthorized", "Invalid API Key", "Authentication failed"
- API 호출 실패
- `news_ingest_dag`의 task 실패

**복구 절차:**

**Step 1: API 키 확인**
```bash
cat .env | grep -E "NEWS_API_KEY|NAVER_CLIENT"
```

**Step 2: API 키 업데이트**
- [NewsAPI](https://newsapi.org/) 또는 [Naver Developer Console](https://developers.naver.com/)에서 신규 키 발급
- `.env` 파일 수정:
  ```bash
  vi .env
  # NEWS_API_KEY=your_new_key
  # NAVER_CLIENT_ID=your_new_id
  # NAVER_CLIENT_SECRET=your_new_secret
  ```

**Step 3: Docker 재시작**
```bash
docker compose down
docker compose up --build -d
```

**Step 4: 영구 실패 메시지 복구 (선택사항)**
API 키 문제로 영구 실패된 메시지들을 재처리하려면:

```bash
# 영구 실패 메시지 확인
cat state/dead_letter_permanent.jsonl | jq '.'

# permanent_fail_at 필드 제거하고 attempt 리셋
cat state/dead_letter_permanent.jsonl | \
  jq 'del(.permanent_fail_at, .last_retry_at) | .attempt=1' \
  > /tmp/restored.jsonl

# dead_letter.jsonl에 추가
cat /tmp/restored.jsonl >> state/dead_letter.jsonl

# 영구 실패 파일 초기화
echo "" > state/dead_letter_permanent.jsonl

# 재처리 실행
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py
```

---

### E. Docker 네트워크 문제

**증상:**
- Airflow ↔ Kafka 통신 실패
- 로그: "kafka: name resolution failed" 또는 "Connection refused"

**복구 절차:**

```bash
# 네트워크 상태 확인
docker network ls
docker network inspect news-trend-pipeline-dev_default

# 네트워크 재설정 (모든 컨테이너 종료)
docker compose down -v  # -v: 볼륨도 함께 제거
docker compose up --build -d
```

> **주의**: `-v` 옵션을 사용하면 데이터베이스 데이터가 삭제됩니다.  
> Postgres 데이터만 보존하려면 `docker compose down` (v 옵션 생략)으로 실행하세요.

---

## 3. 자동 vs 수동 재처리

### 자동 재처리 (auto_replay_dag)

**특징:**
- 15분마다 자동으로 실행
- 사용자 개입 불필요
- 지연: 최대 15분

**활성화:**
1. Airflow UI (`http://localhost:9080`)
2. DAG 목록에서 `auto_replay_dag` 찾기
3. **Toggle** 버튼으로 활성화 (초록색)

**Task 구조:**
```
auto_replay_dag
├─ check_kafka_health           : Kafka 연결 확인
└─ replay_dead_letters          : replay.py 실행
    ├─ summarize_replay_results : 결과 요약
    └─ check_permanent_failures : 영구 실패 감시
```

**로그 확인:**
```bash
# Airflow UI에서 DAG 선택
# → "Logs" 탭 → Task별 로그 확인

# 또는 Docker 로그
docker compose logs airflow-scheduler | grep auto_replay_dag
```

**모니터링 포인트:**
| 항목 | 확인 방법 | 정상 | 문제 |
|------|---------|------|------|
| 실행 여부 | Airflow UI DAG Grid | 15분마다 초록색 | 실행 안 됨/빨강 |
| 재처리 성공 | `summarize_replay_results` 로그 | success > 0 | success = 0 |
| 영구 실패 | `check_permanent_failures` 로그 | 0건 | 1건 이상 🔔 |

### 수동 재처리 (replay.py)

**특징:**
- 즉시 실행 (지연 없음)
- 명확한 결과 확인 가능
- 운영자 개입 필요

**Dry-run으로 먼저 확인:**
```bash
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py --dry-run
```

출력 예시:
```
[1] provider=newsapi url=https://example.com reason=timeout attempt=1
[2] provider=naver url=https://example2.com reason=broker_error attempt=2
[3] provider=newsapi url=https://example3.com reason=timeout attempt=3
    ⚠️ 최대 재시도 횟수(3)에 도달했습니다
```

**실제 재처리 실행:**
```bash
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py
```

출력 예시:
```
=== 재처리 결과 === 성공=2건 | 중복skip=0건 | 재실패=1건 | 영구실패=0건
```

**결과 해석:**
- **성공**: `dead_letter_replayed.jsonl`로 이동 ✅
- **중복skip**: 이미 발행된 URL (중복 방지)
- **재실패**: 아직 재시도 가능 (attempt 증가)
- **영구실패**: attempt > 3으로 이동 불가 🔴

---

## 4. 영구 실패 메시지 처리

영구 실패 메시지(`dead_letter_permanent.jsonl`)는 **자동으로 재처리되지 않으므로 반드시 수동 개입이 필요**합니다.

### Step 1: 원인 파악

```bash
# 최근 10개 영구 실패 메시지 확인
tail -10 state/dead_letter_permanent.jsonl | jq '.'

# 예시 출력:
# {
#   "failed_at": "2026-01-08T10:30:00Z",
#   "reason": "KafkaTimeoutError: ...",
#   "attempt": 4,
#   "payload": { "provider": "newsapi", "url": "...", ... },
#   "permanent_fail_at": "2026-01-08T10:45:00Z"
# }
```

```bash
# Airflow 로그에서 해당 메시지 검색
grep "url=https://example.com" airflow-docker/logs/*/dags/news_ingest_dag/*.log
```

### Step 2: 원인별 대응

**원인이 일시적 Kafka 문제인 경우:**
```bash
# Kafka 정상화 확인
docker compose logs kafka | tail -5

# 메시지 복원 (attempt 리셋)
cat state/dead_letter_permanent.jsonl | \
  jq 'del(.permanent_fail_at, .last_retry_at) | .attempt=1' \
  > /tmp/restored.jsonl

cat /tmp/restored.jsonl >> state/dead_letter.jsonl

# 영구 실패 파일 초기화
echo "" > state/dead_letter_permanent.jsonl

# 재처리
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py
```

**원인이 API 키 만료인 경우:**
[위의 "API 키 만료/오류" 섹션 참조](#d-api-키-만료오류-재시도-불가)

**원인이 Kafka 브로커 설정 오류인 경우:**
```bash
# 브로커 상태 확인
docker compose logs kafka | grep -i error

# Topic 확인
docker compose exec kafka kafka-topics.sh \
  --bootstrap-server kafka:9092 \
  --list

# 필요시 Kafka 재시작 및 topic 재생성
[위의 "Kafka 브로커 다운" 섹션 참조]

# 메시지 복원 및 재처리
```

**원인이 불명확한 경우:**
```bash
# Airflow 로그 확인
docker compose logs airflow-scheduler | grep -A 5 "permanent_fail"

# 네트워크 상태 확인
docker compose exec airflow-scheduler \
  python -c "from kafka import KafkaAdminClient; \
  KafkaAdminClient(bootstrap_servers='kafka:29092')"
```

### Step 3: 복원된 메시지 재처리

```bash
# Dry-run 확인
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py --dry-run

# 실제 재처리
docker compose exec airflow-scheduler \
  python /opt/news-trend-pipeline/ingestion/replay.py
```

---

## 5. 모니터링 체크리스트

### 일일 체크사항

| 항목 | 확인 위치 | 정상 | 경고 |
|------|---------|------|------|
| 수집 현황 | `news_ingest_dag` 실행 | 15분마다 성공 | 실행 실패 |
| Dead Letter 누적 | `state/dead_letter.jsonl` 크기 | 10건 이하 | 100건 이상 |
| 자동 재처리 | `auto_replay_dag` 실행 | 15분마다 실행 | 실행 안 됨 |
| 재처리 성공 | `summarize_replay_results` 로그 | success > 0 | success = 0 계속 |
| **영구 실패 (중요!)** | `state/dead_letter_permanent.jsonl` | 0건 | **1건 이상 🔔** |

### 정기 점검 (주 1회)

```bash
# 1. 재시도 대기 메시지 상태
echo "=== Dead Letter 현황 ==="
wc -l state/dead_letter.jsonl state/dead_letter_replayed.jsonl state/dead_letter_permanent.jsonl

# 2. attempt 분포 확인 (재시도 몇 번까지 갔는지)
echo "=== Attempt 분포 ==="
cat state/dead_letter.jsonl | jq '.attempt' | sort | uniq -c

# 3. 영구 실패 메시지 원인 확인
echo "=== 영구 실패 메시지 원인 ==="
cat state/dead_letter_permanent.jsonl | jq '.reason' | sort | uniq -c
```

### 실시간 모니터링 (권장)

```bash
# 1. Airflow UI에서 두 DAG 나란히 보기
# http://localhost:9080 → DAG 목록
# news_ingest_dag + auto_replay_dag 함께 확인

# 2. 로그 스트리밍
docker compose logs -f airflow-scheduler | grep -E "dead_letter|replay|permanent"

# 3. 파일 변화 감시
watch -n 5 'wc -l state/dead_letter*.jsonl'
```

---


## 6. 요약

| 상황 | 자동 처리 | 수동 개입 | 예상 시간 |
|------|---------|---------|---------|
| Kafka 일시적 지연 | ✅ auto_replay_dag | 불필요 | 15분 |
| Kafka 브로커 다운 | ❌ 불가 | Kafka 재시작 필요 | 5분 + 15분 |
| API 네트워크 장애 | ❌ 불가 | API 서버 복구 대기 | 30분~ |
| API 키 만료 | ❌ 불가 | .env 업데이트 필요 | 5분 |
| 영구 실패 메시지 | ❌ 자동 재처리 안 됨 | 원인 파악 후 수동 복구 | 10분~ |

**핵심 원칙:**
- **일시적 실패** → auto_replay_dag가 자동 재처리
- **인프라 장애** → 관리자가 원인 해결
- **영구 실패** → 즉시 알림 받고 수동 개입
