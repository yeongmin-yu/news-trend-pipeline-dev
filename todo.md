# TODO

## 1. 프론트 기능 기준으로 필요한 생성 데이터

### 1.1 이미 필요한 데이터

- 도메인별 기사 원천 데이터
  - `news_raw`
- 기사별 키워드 토큰
  - `keywords`
- 시간 bucket별 키워드 빈도
  - `keyword_trends`
- 시간 bucket별 연관 키워드 쌍
  - `keyword_relations`
- 도메인 메타
  - `domain_catalog`
- 도메인별 수집 쿼리
  - `query_keywords`
- 용어 사전 데이터
  - `compound_noun_dict`
  - `compound_noun_candidates`
  - `stopword_dict`

### 1.2 아직 생성이 필요한 데이터

- 기사 중복 클러스터
  - 기사 패널 `duplicates` 값용
- 기사 관련도 점수
  - `latest` 외 `relevance` 정렬 품질 개선용
- query keyword 운영 로그
  - 운영 변경 추적용
- 용어 사전 감사 로그
  - 변경 이력 화면용
- 도메인별 수집 품질 지표
  - 호출 성공률
  - 기사 수
  - 중복률
  - 무의미 키워드 비율

## 2. DB 계획

### 2.1 현재 반영된 테이블

- `domain_catalog`
- `query_keywords`
- `news_raw`
- `keywords`
- `keyword_trends`
- `keyword_relations`
- `compound_noun_dict`
- `compound_noun_candidates`
- `stopword_dict`
- `dictionary_versions`

### 2.2 추가로 설계해야 할 테이블

#### `article_clusters`

- 목적
  - 중복 기사 묶음 생성
- 추천 컬럼
  - `cluster_id`
  - `provider`
  - `domain`
  - `canonical_url`
  - `member_url`
  - `similarity_score`
  - `created_at`

#### `article_keyword_scores`

- 목적
  - relevance 정렬
- 추천 컬럼
  - `provider`
  - `domain`
  - `article_url`
  - `keyword`
  - `score`
  - `title_boost`
  - `recency_score`
  - `updated_at`

#### `dictionary_audit_logs`

- 목적
  - 용어 사전 변경 이력
- 추천 컬럼
  - `entity_type`
  - `entity_id`
  - `action`
  - `before_json`
  - `after_json`
  - `actor`
  - `acted_at`

#### `query_keyword_audit_logs`

- 목적
  - 수집 키워드 변경 기록
- 추천 컬럼
  - `query_keyword_id`
  - `action`
  - `before_json`
  - `after_json`
  - `actor`
  - `acted_at`

#### `collection_metrics`

- 목적
  - 운영 관제
- 추천 컬럼
  - `provider`
  - `domain`
  - `query`
  - `window_start`
  - `window_end`
  - `request_count`
  - `success_count`
  - `article_count`
  - `duplicate_count`
  - `error_count`

## 3. 데이터 생성 작업 TODO

### 3.1 수집

- `query_keywords` 기반으로 Naver 수집기를 완전히 운영 전환
- 쿼리별 기사 수 편차 모니터링
- 비활성 쿼리 자동 감지 기준 정의

### 3.2 전처리/집계

- domain 포함 Spark 집계 정상 검증
- relation 품질이 낮은 일반명사 제거 규칙 보강
- 시간 bucket별 sparse 데이터 보정 전략 검토

### 3.3 서빙

- `domain` 필터가 모든 dashboard API에서 동일하게 동작하는지 확인
- 기사 정렬용 relevance score 추가
- duplicates 계산 API 추가

### 3.4 운영

- 관리자용 query keyword API/UI
- 도메인별 수집 현황 대시보드
- dictionary audit 로그 노출

## 4. 우선순위

1. 도메인별 수집 데이터 누적 안정화
2. relevance/duplicates용 추가 테이블 설계
3. query keyword 운영 API
4. 감사 로그와 운영 지표 UI
