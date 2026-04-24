# STEP3 EVENT

## 개요

STEP3의 목표는 시간대별 키워드 변화를 기반으로 급상승 이벤트를 계산하고, 대시보드/API에서 바로 활용할 수 있는 이벤트 레이어를 만드는 것이다.

2026-04-23 기준으로 STEP3 관련 추가 구현을 완료했다.

## 구현 내용

### 1. 이벤트 저장 테이블 추가

추가 테이블:

- `keyword_events`

컬럼:

- `provider`
- `domain`
- `keyword`
- `event_time`
- `window_start`
- `window_end`
- `current_mentions`
- `prev_mentions`
- `growth`
- `event_score`
- `is_spike`
- `detected_at`

반영 파일:

- [src/storage/models.sql](C:/Project/news-trend-pipeline-v2/src/storage/models.sql)
- [src/storage/db.py](C:/Project/news-trend-pipeline-v2/src/storage/db.py)

### 2. 이벤트 탐지 배치 구현

추가 파일:

- [src/analytics/event_detector.py](C:/Project/news-trend-pipeline-v2/src/analytics/event_detector.py)

동작 방식:

- `keyword_trends`를 최근 24시간 범위로 읽는다.
- `(provider, domain, keyword)` 단위로 시계열을 묶는다.
- 현재 구간 언급량과 직전 구간 언급량을 비교해 성장률을 계산한다.
- 급상승 여부(`is_spike`)와 이벤트 점수(`event_score`)를 계산한다.
- 결과를 `keyword_events`에 교체 적재한다.

### 3. Airflow DAG 추가

추가 파일:

- [airflow/dags/keyword_event_detection_dag.py](C:/Project/news-trend-pipeline-v2/airflow/dags/keyword_event_detection_dag.py)

DAG 정보:

- DAG ID: `keyword_event_detection`
- 스케줄: 15분 주기
- 태그: `event`, `analytics`, `step3`

역할:

- 최근 24시간 키워드 트렌드를 기준으로 이벤트 후보를 재생성한다.
- STEP5 대시보드의 급상승 키워드 데이터 품질을 높인다.

### 4. API 연동

수정 파일:

- [src/api/service.py](C:/Project/news-trend-pipeline-v2/src/api/service.py)

적용 방식:

- 기존 급상승 계산 API는 우선 `keyword_events`를 조회한다.
- 이벤트 테이블 데이터가 없을 때만 기존 `keyword_trends` 기반 폴백 계산을 수행한다.

사용 엔드포인트:

- `GET /api/v1/dashboard/spikes`

## 검증 결과

2026-04-23(Asia/Seoul) 기준 확인 사항:

### DAG 등록

- `airflow dags list`에서 `keyword_event_detection` 등록 확인

### 수동 실행 검증

컨테이너 내부에서 이벤트 탐지 작업을 직접 실행해 아래 결과를 확인했다.

- source rows: `87872`
- event rows: `33301`

### 데이터 적재 확인

- `keyword_events = 33301`

### 대시보드 연동 확인

- STEP5 대시보드 급상승 API는 `keyword_events`를 우선 사용하도록 반영됨

## 현재 판단

STEP3는 “이벤트 저장 레이어 + 배치 계산 + Airflow 스케줄링 + 대시보드 API 연결”까지 구현된 상태다.

남은 개선 포인트는 품질 튜닝 영역이다.

- 도메인별 임계치 분리
- 노이즈 키워드 자동 억제
- 알림/배너 연동
- 이벤트 score 해석 기준 고도화
