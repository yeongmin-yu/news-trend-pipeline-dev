# STEP1 Ingestion History

> STEP 1 설계 변경 과정 기록.  
> 최종 구조 설명은 `docs/design/STEP1_*` 문서에 두고, 여기에는 왜 구조가 바뀌었는지와 중간 변경 포인트만 남긴다.

## 1. 변경 배경

초기 STEP 1 문서는 단일 수집원, 단순 체크포인트, 고정 키워드 기반 설명이 섞여 있었다.  
하지만 현재 프로젝트는 다음 요구를 만족해야 했다.

- 도메인별 분리 수집
- query별 상태 관리
- Kafka 발행 실패 복구
- 후속 처리 단계에서 `domain`, `query`를 그대로 활용할 수 있는 메시지 구조

이 요구 때문에 STEP 1은 단순 API polling 단계에서 운영 가능한 ingestion 계층으로 확장되었다.

## 2. 변경 과정

### 2-1. 쿼리 관리 위치 변경

초기:

- 환경 변수 또는 코드 상수 중심 쿼리 관리

변경:

- `domain_catalog`
- `query_keywords`

효과:

- 수집 정책과 저장 스키마가 같은 기준 키를 사용하게 됨
- 관리자 UI/API와 연결 가능해짐

### 2-2. 체크포인트 구조 변경

초기:

- provider 단위 마지막 시각

문제:

- 다중 query 수집 중 일부 query 실패 시 누락 가능

변경:

- `keyword_timestamps[domain::query]`

효과:

- query별 성공/실패를 분리해서 관리 가능

### 2-3. Naver 병렬 수집 도입

초기:

- 단순 순차 호출 또는 단일 query 설명

변경:

- query 단위 병렬 호출
- query stagger 적용
- page delay 적용

이유:

- 수집량을 확보하면서도 rate limit 리스크를 줄이기 위해서

### 2-4. Kafka partition key 변경

초기:

- provider 기준 분산 설명

변경:

- `url` 우선 key
- `provider` fallback

이유:

- 동일 기사 기준 추적이 쉬워지고 partition skew를 줄이기 위해서

### 2-5. dead letter 운영 흐름 추가

초기:

- 실패 로그 중심

변경:

- `dead_letter.jsonl`
- `dead_letter_replayed.jsonl`
- `dead_letter_permanent.jsonl`
- `auto_replay_dag`

효과:

- 실패를 단순 기록이 아니라 재처리 가능한 운영 객체로 다루게 됨

## 3. 문서 정리 원칙

STEP 1 문서는 다음 기준으로 재정리했다.

- 최종 구조만 `docs/design`에 남김
- 변경 과정과 배경은 `docs/develop`에 분리
- 과거 `NewsAPI` 중심 설명, 단일 query 설명, `description/content` 중심 예시는 제거
- 현재 코드에 없는 task나 topic 전략은 설계 본문에서 제외

## 4. 후속 문서 작업 메모

STEP 1 다음 문서 정리 시 함께 맞춰야 할 연결 지점은 다음과 같다.

- STEP 2 문서에서 Kafka 입력 스키마가 `domain`, `summary`, `metadata.query`를 전제로 설명되는지
- STEP 3 문서에서 `collection_metrics`가 수집 단계 메트릭으로 설명되는지
- STEP 5 문서에서 관리자 기능이 `query_keywords` 기반이라는 점이 반영되는지
