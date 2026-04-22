# TODO

## 완료된 항목

이번 라운드에서 아래 항목은 완료되어 별도 TODO 대상에서 제거했다.

- `collection_metrics` 테이블 및 운영 지표 API
- `dictionary_audit_logs` 테이블 및 감사 로그 API
- `query_keyword_audit_logs` 테이블 및 감사 로그 API
- 도메인 수집 키워드 관리 UI/API
- STEP3 이벤트 적재 테이블, 탐지 배치, Airflow DAG

## README 기준 잔여 과제

### 1. 글로벌 뉴스 소스 추가

- README에는 Naver와 글로벌 뉴스 소스(예: NewsAPI/Google News) 이중 소스 방향이 남아 있다.
- 현재 실제 운영 구현은 `naver` 단일 소스 중심이다.
- `source=global` 또는 다중 공급원 비교를 실제로 지원하려면 별도 수집기와 정규화 로직이 더 필요하다.

### 2. 용어 사전 감사 로그 UI

- 백엔드 API와 DB 적재는 완료되었다.
- 현재 프론트에는 용어 사전 변경 이력을 전용 탭으로 보여주는 UI가 없다.
- 운영자 사용성을 위해 `용어 사전` 모달 내 `변경 이력` 탭을 추가하는 것이 좋다.

### 3. 기사 관련도 정렬 고도화

- 현재 기사 목록은 `latest` 중심으로는 충분히 동작한다.
- 하지만 `relevance` 품질을 높이려면 제목 가중치, 최근성 decay, 키워드 일치율 등을 반영한 별도 점수 레이어가 필요하다.

선택 과제:

- `article_keyword_scores`

설명:

- 지금은 단순 정렬로도 대시보드 사용은 가능하다.
- 다만 `관련도순` 품질이 중요해지면 별도 점수 테이블 또는 materialized view가 필요하다.

### 4. 유사 기사 묶음

선택 과제:

- `article_clusters`

설명:

- 현재 STEP1, STEP2의 중복 제거는 `provider + domain + url` 기준의 저장 중복 방지다.
- `article_clusters`는 URL이 달라도 사실상 같은 기사, 재배포 기사, 제목만 조금 바뀐 기사들을 UI에서 한 묶음으로 보여주기 위한 기능이다.
- 대시보드에 `duplicates` 표시나 대표 기사 1건만 노출하는 요구가 생길 때 추진하면 된다.

### 5. 수집 운영 자동화

- `collection_metrics`는 이미 적재/조회 가능하다.
- 다음 단계는 운영 자동화다.

후속 과제:

- 실패율이 높은 쿼리 자동 감지
- 비효율 쿼리 비활성화 추천
- 도메인별 성공률/중복률 경고 배너
- 일정 기간 무수집 쿼리 알림

### 6. 이벤트 품질 튜닝

- STEP3 배치와 저장 구조는 준비되었다.
- 현재는 공통 규칙 기반 점수 계산이라, 도메인마다 노이즈 특성이 다를 수 있다.

후속 과제:

- 도메인별 spike threshold 분리
- 저빈도 노이즈 키워드 억제 규칙
- 이벤트 점수 해석 기준 표준화
- 이벤트 알림/배너 정책 정의

### 7. 통합 테스트 자동화

- 수동 검증은 완료했지만, 회귀를 막으려면 자동화가 필요하다.

후속 과제:

- 관리자 API CRUD 테스트
- dictionary audit 로그 테스트
- query keyword audit 로그 테스트
- collection_metrics 적재 테스트
- keyword_events 탐지 및 API 폴백 테스트
- 프론트 API 계약 테스트
