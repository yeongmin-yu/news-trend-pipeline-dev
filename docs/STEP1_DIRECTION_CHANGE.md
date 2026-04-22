# STEP1 방향 변경

## 1. 변경 배경

초기 설계는 단일 도메인 중심 수집으로도 대시보드가 충분히 살아날 것으로 가정했다. 실제 운영 관점에서 확인한 결과, 한 종류의 도메인만으로는 기사 볼륨과 키워드 분산이 부족해 실시간 트렌드 화면이 안정적으로 유지되지 않았다.

따라서 파이프라인의 수집 범위를 다음 4개 도메인으로 확장한다.

1. `ai_tech` : AI·테크
2. `economy_finance` : 경제·금융
3. `politics_policy` : 정치·정책
4. `entertainment_culture` : 엔터·문화

각 도메인은 네이버 뉴스 검색 API에 대해 20개의 쿼리 키워드를 사용하며, 도메인당 20회 호출을 수행한다. 총 80개 쿼리를 매 수집 사이클에서 관리한다.

## 2. 핵심 설계 변경

### 2.1 데이터 수집 구조

- 기존: 단일 테마 키워드 집합 기반 수집
- 변경: `도메인 -> 쿼리 키워드 20개 -> 기사 수집` 구조
- 체크포인트 단위도 `provider + domain + query` 단위로 분리
- 중복 제거는 `provider + domain + url` 기준으로 관리

### 2.2 데이터 모델 변경

다음 테이블/필드를 추가 또는 확장한다.

- `domain_catalog`
  - 도메인 마스터
  - `domain_id`, `label`, `sort_order`, `is_active`
- `query_keywords`
  - 네이버 API 쿼리 키워드 관리 테이블
  - `provider`, `domain_id`, `query`, `sort_order`, `is_active`
- `news_raw.domain`
  - 기사 원문 레벨에서 도메인 보관
- `news_raw.query`
  - 어떤 수집 키워드로 유입되었는지 추적
- `keywords.article_domain`
- `keyword_trends.domain`
- `keyword_relations.domain`

### 2.3 API/대시보드 변경

- 모든 대시보드 API는 `domain` 필터를 받는다.
- 프론트는 기존 도메인 선택 UI를 실제 API 필터와 연결한다.
- 메타 필터 API는 DB의 `domain_catalog` 기준으로 도메인 목록을 제공한다.

## 3. 도메인별 네이버 API 추천 쿼리

### 3.1 AI·테크

1. AI
2. 생성형 AI
3. GPT
4. LLM
5. OpenAI
6. Anthropic
7. Claude
8. 엔비디아
9. 반도체
10. AI 반도체
11. HBM
12. 삼성전자
13. TSMC
14. 로봇
15. 로보틱스
16. 자율주행
17. 클라우드
18. 데이터센터
19. 스타트업
20. 빅테크

### 3.2 경제·금융

1. 기준금리
2. 인플레이션
3. 환율
4. 원달러
5. 코스피
6. 코스닥
7. 증시
8. 미국 증시
9. 연준
10. 한국은행
11. 부동산
12. 가계부채
13. 수출
14. 무역수지
15. 실적
16. 기업공개
17. 채권
18. 유가
19. 관세
20. 경기침체

### 3.3 정치·정책

1. 대통령실
2. 국회
3. 정부조직
4. 예산안
5. 추경
6. 여당
7. 야당
8. 총선
9. 지방선거
10. 외교
11. 안보
12. 국방
13. 검찰
14. 사법개혁
15. 교육정책
16. 부동산 정책
17. 세제 개편
18. 복지정책
19. 의료정책
20. 노동정책

### 3.4 엔터·문화

1. K팝
2. 아이돌
3. 콘서트
4. 팬미팅
5. 넷플릭스
6. OTT
7. 드라마
8. 영화
9. 박스오피스
10. 예능
11. 웹툰
12. 게임
13. e스포츠
14. 뮤지컬
15. 전시
16. 축제
17. BTS
18. 블랙핑크
19. 뉴진스
20. 한류

## 4. 구현 원칙

- 기존 축적 데이터는 유지 대상이 아니다.
- 스키마 마이그레이션보다 새 구조 정합성을 우선한다.
- 단, 매 서비스 시작마다 데이터를 삭제하지는 않는다.
- 기존 인덱스/제약 중 새 설계를 방해하는 것은 제거한다.

## 5. 코드 반영 범위

- `storage/models.sql`
  - 도메인/쿼리 테이블 추가
  - fact/staging 테이블에 `domain` 반영
- `storage/db.py`
  - 도메인/쿼리 시드
  - 도메인 포함 upsert/rebuild 로직
- `ingestion/producer.py`
  - DB의 `query_keywords`를 읽어 수집
  - 체크포인트를 `domain::query` 단위로 관리
- `processing/spark_job.py`
  - Spark 집계 경로에 `domain` 전파
- `api/service.py`, `api/app.py`
  - 대시보드 API에 `domain` 필터 반영
- `frontend/src/data.ts`, `frontend/src/app.tsx`
  - 프론트 도메인 선택값을 실제 API 요청에 전달

## 6. 후속 권장 작업

- 관리자 화면에서 `query_keywords`를 편집하는 API/UI 추가
- 도메인별 수집 품질 지표
  - 쿼리별 기사 수
  - 중복률
  - 무효 키워드 탐지
- 글로벌 뉴스 소스 추가 시 `provider + domain` 확장 구조 유지
