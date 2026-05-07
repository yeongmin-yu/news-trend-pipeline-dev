# STEP 4-1: Event Storage Layer

## 1. 목적

STEP4-1은 이벤트 탐지 결과를 저장하고 조회 가능한 형태로 유지하는 저장 레이어다.

이 문서는 최종 구현 기준만 설명하며, 구현 과정이나 검증 로그는 포함하지 않는다.

## 2. 역할

- `analytics.event_detector`가 계산한 이벤트 결과를 저장한다.
- 동일 시간 범위에 대해 재계산 시 기존 데이터를 교체한다.
- FastAPI와 Dashboard가 직접 조회하는 분석 결과 테이블을 제공한다.

## 3. 이벤트 생성 흐름

```text
keyword_trends / keywords / news_raw
    ↓
최근 window 기반 급상승 판단
    ↓
keyword_events에 replace / upsert 저장
    ↓
중복 이벤트 방지
```

- 입력 데이터는 `keyword_trends`, `keywords`, `news_raw`이다.
- 최근 window(예: 10~15분)를 기준으로 급상승 여부를 판단한다.
- 동일 window에 대해 재실행 시 기존 데이터를 교체(replace)한다.
- unique key 기준으로 upsert하여 중복 이벤트를 방지한다.
- Airflow DAG `keyword_event_detection`은 15분 주기로 실행된다.

## 4. 테이블: `keyword_events`

이벤트 저장을 위한 핵심 테이블이다.

### 주요 컬럼

| 컬럼 | 설명 |
| --- | --- |
| `provider` | 뉴스 제공자 |
| `domain` | 도메인 ID |
| `keyword` | 이벤트 대상 키워드 |
| `event_time` | 이벤트 기준 시각 (`window_end`) |
| `window_start` | 분석 윈도우 시작 |
| `window_end` | 분석 윈도우 종료 |
| `current_mentions` | 현재 윈도우 언급량 |
| `prev_mentions` | 직전 윈도우 언급량 |
| `growth` | 증가율 |
| `event_score` | 이벤트 점수 |
| `is_spike` | 급상승 여부 |
| `detected_at` | 탐지 시각 |

### 인덱스 및 제약

- `(provider, domain, keyword, window_start)` unique
- 조회 성능을 위해 `(provider, domain, event_time DESC, event_score DESC)` 인덱스 사용

## 5. 적재 방식

이벤트는 append 방식이 아니라 **범위 교체(replace)** 방식으로 적재된다.

동작:

1. 특정 시간 범위의 기존 이벤트 삭제
2. 동일 범위의 신규 이벤트 insert
3. 동일 키 충돌 시 upsert

이 방식은 다음을 보장한다.

- 재실행 시 중복 누적 방지
- 동일 조건 실행 시 동일 결과

## 6. 데이터 생성 주체

이 테이블은 다음 컴포넌트에 의해 생성된다.

- `src/analytics/event_detector.py`
- Airflow DAG `keyword_event_detection`

Spark나 API에서 직접 insert하지 않는다.

## 7. 조회 방식

주요 사용 API:

- `GET /api/v1/dashboard/spikes`
- `GET /api/v1/dashboard/kpis`

FastAPI는 `keyword_events`를 우선 조회한다.

데이터가 없거나 특정 조건에서만 `keyword_trends` 기반 fallback 계산이 수행된다.

## 8. 설계 포인트

- 이벤트 테이블은 분석 결과 캐시 역할을 한다.
- window 기반 집계를 그대로 저장하여 재계산 비용을 줄인다.
- domain 단위로 분리된 이벤트를 유지한다.
- API 조회 성능을 고려해 필요한 필드를 사전에 계산해 저장한다.

## 9. 현재 구현 기준 메모

- 이벤트 탐지 로직은 STEP4 본문에서 정의된다.
- 본 문서는 저장 구조만 다룬다.
- 임계치, score 공식, 실험 이력은 `docs/develop` 문서에서 관리한다.
