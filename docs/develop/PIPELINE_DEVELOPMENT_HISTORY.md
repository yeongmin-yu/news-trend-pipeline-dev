# 파이프라인 개발 이력 통합 정리

이 문서는 `docs/develop` 안에 흩어져 있던 단계별 history 문서를 하나로 합친 개발 이력 문서입니다.

정리 기준은 다음과 같습니다.

- `docs/design_history`: 과거 단계별 설계 문서 원본을 보관합니다.
- `docs/design_final`: 최종 발표/설계 문서를 보관합니다.
- `docs/develop`: 실제 개발 중 결정한 이유, 장애 대응, 튜닝, 운영 메모만 보관합니다.

따라서 `develop` 폴더에 있던 `STEP1_INGESTION_history.md`, `STEP2_PROCESSING_history.md`, `STEP3_STORAGE.md`, `STEP3_STORAGE_history.md`, `STEP4_ANALYTICS.md`, `STEP4_ANALYTICS_history.md`, `STEP5_SERVING_history.md`는 이 문서로 통합했습니다.

---

## 1. STEP1 Ingestion 개발 이력

초기 수집 구조는 단일 검색어와 단순 API 호출 중심이었습니다. 실제 수집량을 확인하면서 다음 문제가 드러났습니다.

- 도메인별 기사량이 부족했습니다.
- 특정 검색어에 데이터가 편중되었습니다.
- 검색어별 성공/실패 상태를 따로 추적하기 어려웠습니다.
- Kafka 발행 실패 시 재처리 흐름이 부족했습니다.

변경된 방향은 다음과 같습니다.

| 변경 | 이유 |
| --- | --- |
| `domain_catalog`, `query_keywords` 도입 | 도메인별 검색어를 DB에서 관리하고 대시보드/API와 연결하기 위해 |
| checkpoint 단위를 `domain::query`로 변경 | 일부 검색어 실패가 전체 수집 상태를 망치지 않도록 하기 위해 |
| Naver API 병렬 호출과 query stagger 적용 | 수집 속도를 확보하면서 rate limit(호출 제한) 위험을 낮추기 위해 |
| Kafka partition key를 `url` 중심으로 변경 | 동일 기사 추적과 partition skew(특정 파티션 쏠림)를 줄이기 위해 |
| dead letter 파일과 `auto_replay_dag` 추가 | Kafka 발행 실패 메시지를 버리지 않고 재처리하기 위해 |

추가로 News API 무료 사용량과 검색어 기반 수집의 한계 때문에 RSS 수집을 보완했습니다. RSS는 언론사가 제공하는 최신 기사 피드라 검색어에 걸리지 않는 기사까지 일부 보완할 수 있습니다.

자세한 수집 방향 변경과 도메인/검색어 확장 과정은 `docs/develop/STEP1_DIRECTION_CHANGE_history.md`와 `docs/develop/RSS_INGESTION_PLAN_RESULT.md`에 남깁니다.

---

## 2. STEP2 Processing 개발 이력

초기 STEP2 문서에는 Spark 처리 흐름, 전처리 아이디어, DB 스키마 변경, 향후 개선 방향이 섞여 있었습니다.

정리하면서 다음 기준으로 분리했습니다.

- 최종 Spark 처리 구조는 `docs/design_final/Q1_SPARK_PROCESSING.md`에 둡니다.
- 과거 상세 설계 원본은 `docs/design_history/STEP2_*`에 둡니다.
- 실제 병목과 튜닝 결과는 `docs/develop/SPARK_BOTTLENECK_TUNING.md`에 둡니다.
- 한국어 전처리 상세 메모는 `docs/develop/STEP2-2_PREPROCESSING.md`에 둡니다.

핵심 개발 결정은 다음과 같습니다.

| 결정 | 이유 |
| --- | --- |
| Spark Structured Streaming 사용 | Kafka 입력, micro-batch(작은 묶음 처리), 시간 구간 집계가 자연스럽기 때문 |
| Kiwi 형태소 분석 사용 | 한국어 명사 추출과 사용자 사전 적용이 필요했기 때문 |
| 복합명사/불용어 사전을 DB로 관리 | 운영 중 대시보드에서 단어를 수정하고 변경 이력을 남기기 위해 |
| Python UDF 비용을 별도 튜닝 대상으로 분리 | 한국어 토큰화 단계가 Spark 작업 중 가장 무거운 구간이기 때문 |

Spark 처리 병목은 Kafka backlog(처리 대기 메시지), Python UDF, partition 설정, JDBC 저장 방식이 함께 영향을 주었습니다. 현재 튜닝 방향은 Kafka에서 한 번에 가져오는 양을 줄이고, Spark 내부 작업 조각과 DB 저장 batch를 로컬 PC 자원에 맞추는 것입니다.

---

## 3. STEP3 Storage 개발 이력

초기 Storage 문서는 저장 단계 개요와 DB 상세 설계가 섞여 있었습니다. 이후 저장 책임을 다음처럼 분리했습니다.

| 영역 | 역할 |
| --- | --- |
| staging table | Spark가 처리 결과를 임시로 append(추가 저장)하는 공간 |
| upsert 함수 | staging 데이터를 운영 테이블로 정리해 반영하는 DB 함수 |
| analysis table | 대시보드와 분석 작업이 조회하는 최종 테이블 |
| rebuild 함수 | 날짜 단위 재처리와 복구를 위한 보조 함수 |

staging 구조를 둔 이유는 Spark worker가 운영 테이블에 동시에 upsert할 때 생길 수 있는 DB lock 경합을 줄이기 위해서입니다.

반영된 주요 기준은 다음과 같습니다.

- `provider + domain + url` 중심의 중복 제어
- `stg_*` 테이블을 통한 Spark 결과 완충
- `news_raw`, `keywords`, `keyword_trends`, `keyword_relations`, `keyword_events` 운영 테이블 분리
- `collection_metrics`로 수집 상태 추적
- 사전 변경 이력과 버전 관리를 위한 audit/version 테이블 유지

현재 DB 설계 원본과 ERD는 `docs/design_history/STEP3-1_DATABASE.md`, `docs/design_history/STEP3-1_ERD.md`를 참고합니다.

---

## 4. STEP4 Analytics 개발 이력

초기에는 급상승 이벤트를 Spark streaming 내부나 API 요청 시점에 계산하는 방안도 검토했습니다.

최종적으로는 별도 Analytics 단계로 분리했습니다.

| 결정 | 이유 |
| --- | --- |
| `keyword_events` 테이블 materialize | 대시보드 조회 때마다 무거운 계산을 반복하지 않기 위해 |
| Airflow 배치로 15분 주기 실행 | 구현과 운영이 단순하고 재처리가 쉽기 때문 |
| 24시간 lookback 적용 | 늦게 들어온 기사로 과거 window 값이 바뀌는 상황을 보정하기 위해 |
| delete 후 insert 방식 | 같은 시간 범위를 재처리해도 중복이 누적되지 않도록 하기 위해 |

현재 spike 조건은 언급 수와 증가율을 함께 봅니다.

```text
mentions >= threshold
and growth >= threshold
```

점수는 growth(증가율), mentions(언급 수), spike bonus(급상승 가산점)를 조합하는 휴리스틱(경험 기반 계산식)입니다.

향후에는 domain weight(도메인별 가중치), recency decay(최신성 가중치 감소), TF-IDF(흔한 단어를 낮게 보는 통계 기법) 기반 점수를 검토할 수 있습니다.

---

## 5. STEP5 Serving 개발 이력

대시보드에서는 기간 이동, 확대/축소, 드래그 같은 interaction(사용자 조작)이 많습니다.

초기 구조는 KPI, keywords, spikes API를 각각 호출하는 방식이었습니다. 이 방식은 기간이 조금만 바뀌어도 여러 API를 다시 호출해야 해서 UI 반응성이 떨어졌습니다.

해결 방향은 `overview-window` 통합 API였습니다.

| 개념 | 설명 |
| --- | --- |
| display window | 현재 화면에서 사용자가 보고 있는 시간 범위 |
| fetch window | 서버가 미리 넓게 내려주는 시간 범위 |
| frontend cache | 브라우저가 보관하는 bucket 데이터 |
| deriveOverviewFromCache | 캐시 데이터를 현재 화면 기준으로 재집계하는 프론트엔드 함수 |

이 구조 덕분에 사용자가 차트를 조금 이동해도 fetch window 안에 있으면 API를 다시 호출하지 않고 브라우저에서 즉시 재집계할 수 있습니다.

트레이드오프는 프론트엔드 상태 관리가 복잡해진다는 점입니다. 서버와 프론트엔드가 같은 bucket 단위와 시간 범위를 공유해야 하므로, cache metadata를 함께 관리해야 합니다.

최종 Serving 설계는 `docs/design_final/Q5_SERVING.md`를 참고합니다.

---

## 6. 정리 후 문서 배치

정리 후 문서 역할은 다음과 같습니다.

| 위치 | 역할 |
| --- | --- |
| `docs/design_final/FINAL_DEMO_AND_REVIEW.md` | 최종 데모, 설계 이유, 트레이드오프, 회고 |
| `docs/design_final/Q*.md` | 최종 단계별 발표/설계 문서 |
| `docs/design_history/STEP*.md` | 이전 단계별 설계 원본 |
| `docs/develop/PIPELINE_DEVELOPMENT_HISTORY.md` | 단계별 개발 이력 통합본 |
| `docs/develop/SPARK_BOTTLENECK_TUNING.md` | Spark 병목과 튜닝 기록 |
| `docs/develop/RSS_INGESTION_PLAN_RESULT.md` | RSS 수집 추가 배경과 결과 |
| `docs/develop/KAFKA_HEALTH_RECOVERY.md` | Kafka 장애 복구 |
| `docs/develop/FULL_RESET_AND_REBOOTSTRAP_GUIDE.md` | 전체 초기화와 재부트스트랩 |

앞으로 새 문서를 추가할 때는 다음 기준을 따릅니다.

- 최종 발표/설계에 들어갈 내용이면 `docs/design_final`
- 과거 설계 원본 보관이면 `docs/design_history`
- 장애, 튜닝, 실험, 의사결정 이력이면 `docs/develop`
