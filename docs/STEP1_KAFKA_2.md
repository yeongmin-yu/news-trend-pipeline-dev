# Step 1 - Kafka Ingestion (Rev.2)

[STEP1_KAFKA.md](./STEP1_KAFKA.md)에서 정의한 수집 파이프라인을 개선한 2차 개정 문서입니다.
세 가지 변경(소스 정리, Naver 병렬 호출, Partition Key 개선)이 포함되어 있습니다.

## 1. 변경 목적

### 1-1. NewsAPI 소스 제거

- NewsAPI 무료 Developer 플랜은 `100회/일` 한도로, 현재 15분 주기 스케줄(`96회/일`)만으로도 한도에 근접했습니다.
- 첫 실행 / 상태 유실 / fallback window 탐색이 겹치면 1회 실행에서 최대 5회 호출되어 이론상 `480회/일`까지 치솟을 수 있었습니다.
- 결과적으로 NewsAPI는 구조적으로 충분한 데이터량을 안정적으로 확보할 수 없다고 판단해 소스에서 제외했습니다.

### 1-2. Naver API 병렬 호출 (테마 키워드)

- [DIRECTION.md](./DIRECTION.md)에서 정의한 "도메인(테마) 기반 수집"으로 방향을 맞추기 위해, 단일 OR 쿼리(`인공지능|AI|데이터|기술`) 대신 **테마 키워드 집합**을 독립적으로 호출하는 구조로 변경했습니다.
- AI/기술 도메인 기본 키워드 8개: `AI, 인공지능, 생성형AI, GPT, LLM, 챗GPT, 머신러닝, 딥러닝`
- 키워드별로 별도 HTTP 요청이므로 I/O 바운드이고, `ThreadPoolExecutor` 기반 병렬 호출로 선형에 가까운 수집 시간 단축을 얻을 수 있었습니다.
- Naver 무료 한도(`25,000회/일`) 대비 여유가 크므로 동시에 키워드를 늘려도 호출 한도에 걸리지 않습니다.

### 1-3. Topic Partition Key를 유니크키(URL)로 변경

- 기존 `provider` key는 소스가 2개뿐이라 partition이 2개 이상일 때 hot partition 문제가 있었습니다. 이제 Naver 단일 소스로 줄어들면서 provider key를 유지하면 모든 메시지가 한 partition에 몰려 사실상 병렬성이 사라집니다.
- URL(기사 고유 식별자)을 partition key로 사용하면:
  - kafka-python murmur2 해시가 URL을 고르게 분산시켜 partition 균등 분배
  - 동일 URL(재전송 포함)은 항상 같은 partition으로 라우팅되어 downstream 디버깅/ordering이 쉬워짐
  - 중복/재처리 추적이 단순화됨

---

## 2. 변경된 파이프라인 구성도

```mermaid
flowchart LR
    A["Airflow Scheduler"] --> B["news_ingest_dag"]
    B --> H["check_kafka_health"]
    H --> D["produce_naver Task"]
    D --> P1["테마 키워드 1: AI"]
    D --> P2["테마 키워드 2: 인공지능"]
    D --> P3["테마 키워드 3: 생성형AI"]
    D --> P4["… 최대 8개 병렬 호출"]
    P1 --> M["URL dedup"]
    P2 --> M
    P3 --> M
    P4 --> M
    M --> E["Kafka: news_topic<br/>(partition key = URL)"]
    D -.실패.-> F["state/dead_letter.jsonl"]
    E --> G["consumer_check.py"]
    F --> R["auto_replay_dag<br/>재처리"]
    R -->|성공| G
    R -->|영구실패| I["수동 개입 필요"]
```

기존 파이프라인과의 차이는 다음과 같습니다.

| 항목 | 기존(STEP1_KAFKA.md) | 변경(STEP1_KAFKA_2.md) |
| --- | --- | --- |
| 수집 소스 | NewsAPI + Naver | Naver 단일 |
| Naver 쿼리 방식 | 단일 OR 쿼리 `A\|B\|C\|D` | 테마 키워드 N개 병렬 호출 |
| Airflow Task | `produce_newsapi` + `produce_naver` 병렬 | `produce_naver` 단일 |
| 최대 호출 수(1회 실행) | Naver 최대 3 페이지 × 1 쿼리 = 3 | Naver 최대 3 페이지 × 8 키워드 = 24 |
| Partition Key | `provider` | `url` (유니크키) |
| metadata.query | 환경변수 단일 쿼리 | 수집한 기사별 실제 키워드 |

---

## 3. 코드/설정 변경 상세

### 3-1. `common/config.py`

- 제거된 설정:
  - `news_api_key`, `news_api_url`, `news_query`, `news_language`, `news_page_size`, `news_max_pages`
  - `naver_news_query` (단일 OR 쿼리)
- 추가된 설정:
  - `naver_theme_keywords` — 콤마 구분. 기본값 `AI, 인공지능, 생성형AI, GPT, LLM, 챗GPT, 머신러닝, 딥러닝` (DIRECTION.md의 AI/기술 도메인 풀).
  - `naver_max_workers` — 병렬 호출 워커 수. 기본값 8.
- `news_providers` 기본값을 `newsapi,naver` → `naver` 로 변경.

### 3-2. `ingestion/api_client.py`

- `NewsAPIClient` 클래스 전체 제거.
- `NaverNewsClient`에 병렬 수집 메서드 추가:

```python
def fetch_news_parallel(
    self,
    queries: Iterable[str] | None = None,
    from_timestamp: str | None = None,
    page_size: int | None = None,
    max_workers: int | None = None,
) -> list[dict[str, Any]]:
    """테마 키워드 집합에 대해 ThreadPoolExecutor로 병렬 API 호출."""
```

- 수집된 각 기사에 `_query` 내부 필드를 붙여 **"이 기사가 어떤 키워드로 수집되었는지"**를 전파합니다. 최종 Kafka 메시지에는 `metadata.query` 로 옮겨지고, 원본 `_query`는 제거됩니다 (underscore prefix 규약으로 외부 노출 방지).
- 중복 제거는 `provider::url` 기준으로 집합 전체에 대해 1회 수행합니다. 여러 키워드에서 동일 기사가 잡히는 경우에도 메시지는 1회만 발행됩니다.

### 3-3. `ingestion/producer.py`

- `_build_clients()`: NewsAPI 분기 제거. 현재는 `naver`만 지원합니다.
- `_collect_articles()` 헬퍼 추가: Naver 클라이언트는 `fetch_news_parallel(queries=settings.naver_theme_keywords, ...)` 호출, 그 외 프로바이더는 기존 단일 `fetch_news()` 호출.
- `_resolve_partition_key()` 헬퍼 추가: URL이 있으면 URL을 key로, 예외 상황(URL 누락)에만 `provider`로 폴백.
- `build_message()` 수정: `_` prefix 내부 필드는 Kafka 메시지에 포함하지 않고, `_query` 를 `metadata.query` 로 이동.

### 3-4. `ingestion/replay.py`

- Dead Letter 재전송 시에도 동일한 `url` 기반 partition key를 사용하도록 업데이트해 원본 파이프라인과 라우팅을 일치시킵니다.

### 3-5. `batch/dags/news_ingest_dag.py`

- `produce_newsapi` task 제거.
- `produce_naver` 단일 task만 남김. Task 내부에서 병렬 호출이 일어나므로 Airflow 단에서는 별도 병렬 구성이 필요 없습니다.
- `task_summarize_results` 가 더 이상 `newsapi_count`를 조회하지 않도록 정리.

### 3-6. `.env` / `.env.example`

- 제거: `NEWS_API_KEY`, `NEWS_API_URL`, `NEWS_QUERY`, `NEWS_LANGUAGE`, `NEWS_PAGE_SIZE`, `NEWS_MAX_PAGES`, `NAVER_NEWS_QUERY`.
- 추가: `NAVER_THEME_KEYWORDS`, `NAVER_MAX_WORKERS`.
- 변경: `NEWS_PROVIDERS=naver`.

---

## 4. 결과

### 4-1. 수집량

- 1회 실행 기준 이론상 최대 수집량: `100(display) × 3(페이지) × 8(키워드) = 2,400건` (dedup 전).
- 실제로는 키워드 간 기사 중복이 많고 `last_timestamp` 기반 증분 필터가 적용되므로, 도메인/시간대에 따라 수백~천 건 수준으로 안정적으로 수집됩니다.
- 이전 단일 OR 쿼리 방식(`최대 300건`) 대비 수집량이 크게 증가했습니다.

### 4-2. 데이터 품질

- 각 메시지가 **자신을 수집하게 만든 키워드**(`metadata.query`)를 포함하므로, downstream 집계 단계에서 키워드-기사 매핑이 그대로 유지됩니다.
- DIRECTION.md의 "도메인 기반 키워드 추출" 전략과 정합성이 높아졌습니다.

### 4-3. Kafka Partition 분산

- URL 기반 해싱으로 2개 partition에 메시지가 거의 균등하게 분산됩니다.
- 동일 URL은 항상 같은 partition으로 라우팅되므로, 재처리/디버깅 시 offset 추적이 용이합니다.

### 4-4. API 호출량

- 15분 주기 × 96회/일 × 최대 8 keyword × 3 page = `최대 2,304회/일` (극단치).
- Naver 무료 한도 `25,000회/일` 대비 약 9% 수준으로 여유가 큽니다.

### 4-5. Airflow DAG 단순화

- NewsAPI task 제거로 DAG dependency 그래프가 단순해졌고, produce 병렬 단계가 1개로 줄어 XCom 집계 로직도 가벼워졌습니다.

---

## 5. 예시 메시지

테마 키워드 "GPT"로 수집된 기사의 최종 Kafka payload 예시입니다.

```json
{
  "provider": "naver",
  "source": "it.chosun.com",
  "author": null,
  "title": "OpenAI, 차세대 GPT 모델 공개",
  "description": "OpenAI가 차세대 GPT 모델을 공개하고…",
  "content": "OpenAI가 차세대 GPT 모델을 공개하고…",
  "url": "https://it.chosun.com/site/data/html_dir/2026/04/20/2026042000123.html",
  "published_at": "2026-04-20T09:15:00+00:00",
  "ingested_at": "2026-04-20T09:20:03+00:00",
  "metadata": {
    "source": "naver",
    "version": "v1",
    "query": "GPT"
  }
}
```

`metadata.query` 필드는 이제 **이 기사가 실제로 수집된 테마 키워드**를 담습니다.

---

## 6. 기존 문서와의 연결

- 기본 수집 흐름, Dead Letter 처리, 자동 재처리(`auto_replay_dag`), `consumer_check.py` 사용법 등 변경되지 않은 부분은 [STEP1_KAFKA.md](./STEP1_KAFKA.md) 를 계속 참조합니다.
- 장애 대응 및 복구 절차는 [DISASTER_RECOVERY.md](./DISASTER_RECOVERY.md) 를 참조합니다.
- 도메인(테마) 기반 수집의 배경과 키워드 풀은 [DIRECTION.md](./DIRECTION.md) 를 참조합니다.

---

## 7. 프로젝트 구조 리팩토링 (src layout)

앞 절의 코드 변경과 함께, 이후 단계(Spark 집계/Analytics/API/Dashboard)를 고려해 프로젝트 구조를 src layout으로 정리했습니다. 본 절은 `news-trend-pipeline-v2/` 디렉토리에 반영된 내용을 정리한 기록입니다.

### 7-1. 변경 목적

- 단일 `common/`, `ingestion/` 최상위 모듈을 유지하면 이후 `processing/`, `analytics/`, `api/`, `dashboard/` 추가 시 루트에 평평하게 쌓이게 됩니다.
- 패키지 경계를 `src/news_trend_pipeline/` 한 곳으로 모아 **import 경로를 `news_trend_pipeline.*` 로 통일**하고, 테스트/외부 스크립트에서 같은 방식으로 접근하도록 정리했습니다.
- Airflow 설정, Docker 이미지, 런타임 산출물(state/logs)이 코드와 섞여 있던 문제를 **`infra/`, `runtime/` 로 분리**해 운영 환경과 개발 환경 모두에서 파일 성격을 명확히 했습니다.
- `pyproject.toml` 을 도입해 `pip install -e .` 로 editable install이 가능하도록 했습니다.

### 7-2. 디렉토리 이동 표

| 기존 경로 | 새 경로 | 비고 |
| --- | --- | --- |
| `common/` | `src/news_trend_pipeline/core/` | import: `from news_trend_pipeline.core.config import settings` |
| `ingestion/` | `src/news_trend_pipeline/ingestion/` | import: `from news_trend_pipeline.ingestion.producer import ...` |
| — | `src/news_trend_pipeline/{processing,analytics,api,dashboard}/` | 빈 패키지 placeholder (`__init__.py`) |
| `batch/dags/` | `airflow/dags/` | `batch/` 네임스페이스 제거, Airflow 전용 최상위 디렉토리로 분리 |
| `airflow-docker/Dockerfile.airflow` | `infra/airflow/Dockerfile.airflow` | Docker 이미지 관련 산출물을 infra 아래로 이동 |
| `airflow-docker/config/` | `infra/airflow/config/` | `airflow.cfg` |
| `airflow-docker/plugins/` | `infra/airflow/plugins/` | |
| `airflow-docker/logs/` | `runtime/logs/` | 런타임 산출물은 `runtime/` 로 일원화 |
| `state/` | `runtime/state/` | dead_letter.jsonl, last_timestamp.json 등 |
| `scripts/` | `scripts/` | 경로 유지, 내부 sys.path를 `src/` 로 변경 |

### 7-3. 코드/설정 변경 포인트

- **`src/news_trend_pipeline/core/config.py`**
  - `BASE_DIR = Path(__file__).resolve().parents[3]` — src layout에 맞춰 `core → news_trend_pipeline → src → <project root>` 로 3단계 위를 가리킵니다.
  - `state_dir` 기본값을 `BASE_DIR / "runtime" / "state"` 로 변경.
- **`src/news_trend_pipeline/ingestion/*.py`**
  - 모든 `from common.*` → `from news_trend_pipeline.core.*`.
  - `from ingestion.*` → `from news_trend_pipeline.ingestion.*`.
- **`airflow/dags/news_ingest_dag.py`, `airflow/dags/auto_replay_dag.py`**
  - 각 Task 함수 안에서 `sys.path`에 **프로젝트 루트가 아닌 `<project_root>/src`** 를 추가합니다 (`_ensure_src_on_syspath` 헬퍼).
  - import를 `news_trend_pipeline.*` 로 갱신.
  - `auto_replay_dag`의 replay 호출을 `python ingestion/replay.py` 대신 **`python -m news_trend_pipeline.ingestion.replay`** 모듈 실행으로 변경하고, `PYTHONPATH`에 `src/` 를 주입합니다.
- **`scripts/consumer_check.py`**
  - `PROJECT_ROOT / "src"` 를 sys.path 앞에 삽입.
  - `from common.config` → `from news_trend_pipeline.core.config`.
- **`docker-compose.yml`**
  - `build.dockerfile: airflow-docker/...` → `infra/airflow/Dockerfile.airflow`.
  - `PYTHONPATH: /opt/news-trend-pipeline` → `/opt/news-trend-pipeline/src`.
  - `STATE_DIR=/opt/news-trend-pipeline/runtime/state` 환경변수 추가.
  - volume 매핑:
    - `./batch/dags → /opt/airflow/dags` → `./airflow/dags → /opt/airflow/dags`
    - `./airflow-docker/logs → /opt/airflow/logs` → `./runtime/logs → /opt/airflow/logs`
    - `./airflow-docker/config → /opt/airflow/config` → `./infra/airflow/config → /opt/airflow/config`
    - `./airflow-docker/plugins → /opt/airflow/plugins` → `./infra/airflow/plugins → /opt/airflow/plugins`
- **`pyproject.toml`** 신규 생성 — setuptools src layout (`where = ["src"]`, `include = ["news_trend_pipeline*"]`).
- **`.env` / `.env.example`**
  - `STATE_DIR=/opt/news-trend-pipeline/state` → `.../runtime/state`.
  - `.env.example`의 로컬 기본값도 `./runtime/state` 로 변경.
- **`.gitignore` / `.dockerignore`**
  - 기존 `state/`, `airflow-docker/logs/` 제외 규칙을 `runtime/state/*`, `runtime/logs/*` 로 교체.
  - `build/`, `dist/`, `*.egg-info/` 등 packaging 산출물 제외 규칙 추가.

### 7-4. 이후 단계 연동

- Spark 집계(`processing/`), 이벤트 분석(`analytics/`), API(`api/`), 대시보드(`dashboard/`) 모두 동일한 패키지 규약(`news_trend_pipeline.<subpackage>`) 으로 붙이기만 하면 됩니다.
- 테스트는 `tests/unit`, `tests/integration` 에 위치시키고, `pip install -e .[dev]` 로 pytest 환경을 준비합니다.
- Airflow DAG 파일을 늘릴 때도 `airflow/dags/` 한 곳에서만 관리되고, 패키지 코드와 분리되어 있어 DAG 로딩 시 무거운 import가 발생하지 않습니다.

### 7-5. 마이그레이션 메모

기존 `news-trend-pipeline-dev/` 에 있던 런타임 state 파일(`state/last_timestamp.json`, `state/dead_letter*.jsonl` 등)은 **`runtime/state/`** 아래로 그대로 옮기면 기존 증분 수집 커서와 Dead Letter 기록을 이어서 사용할 수 있습니다. `airflow-docker/logs/` 의 과거 DAG 로그를 보존하고 싶다면 `runtime/logs/` 로 옮겨주세요.
