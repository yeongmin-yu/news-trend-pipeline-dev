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

## 6. Naver 호출 텀 조정 및 운영 기준값

멀티 도메인 확장 이후 Naver 수집은 `4개 도메인 x 20개 쿼리 = 총 80개 쿼리`를 주기적으로 호출합니다.  
이 구조에서는 "워커 수"만으로 제어하면 특정 시점에 요청이 몰려 `429 Too Many Requests`가 다시 발생할 수 있어, 이번 개편에서는 다음 3개 파라미터를 함께 제어하도록 변경했습니다.

- `NAVER_MAX_WORKERS`
- `NAVER_PAGE_REQUEST_DELAY_SECONDS`
- `NAVER_QUERY_STAGGER_SECONDS`

### 6-1. 파라미터 의미

- `NAVER_MAX_WORKERS`
  - 동시에 실행할 쿼리 작업 수.
  - 값이 너무 크면 서로 다른 키워드가 한꺼번에 시작되며 rate limit에 걸릴 가능성이 커집니다.
- `NAVER_PAGE_REQUEST_DELAY_SECONDS`
  - 같은 키워드 안에서 `page 1 -> page 2 -> page 3` 호출 사이에 두는 대기 시간입니다.
  - 한 키워드가 짧은 시간 안에 연속 호출되는 것을 막아줍니다.
- `NAVER_QUERY_STAGGER_SECONDS`
  - 병렬 워커에 작업을 던질 때 키워드별 시작 시점을 조금씩 밀어주는 간격입니다.
  - 예를 들어 `0.15`면 1번째 쿼리는 즉시, 2번째는 0.15초 후, 3번째는 0.30초 후에 시작합니다.

즉, 이번 조정은 단순히 "워커를 줄였다"가 아니라, "워커 수 + 쿼리 시작 시점 + 페이지 간격"을 같이 조정해 요청 버스트를 완화한 것입니다.

### 6-2. 코드 반영 위치

- `src/news_trend_pipeline/core/config.py`
  - `naver_page_request_delay_seconds`
  - `naver_query_stagger_seconds`
  - `.env` 값이 컨테이너 환경변수를 덮어쓸 수 있도록 `load_dotenv(..., override=True)` 적용
- `src/news_trend_pipeline/ingestion/api_client.py`
  - `fetch_news_parallel()`에 쿼리별 stagger 적용
  - `fetch_news()` 내부 page loop에 configurable delay 적용
- `src/news_trend_pipeline/ingestion/producer.py`
  - 비정상 기사 1건 때문에 전체 producer cycle이 실패하지 않도록 dead letter 처리 보강
- `.env`
  - 운영 기본값 반영
- `docker-compose.yml`
  - `api-server`, `spark-streaming`, Airflow 서비스에 동일한 throttle 환경변수 주입

### 6-3. 테스트 결과

동일한 80개 활성 쿼리를 대상으로 실제 Naver 호출을 수행해 비교했습니다.

| 설정 | 결과 | 소요 시간 | 판단 |
| --- | --- | ---: | --- |
| `workers=8, stagger=0.0, page_delay=0.5` | `ok=8, fail=72` | 약 0.68초 | 너무 공격적, 운영 불가 |
| `workers=4, stagger=0.25, page_delay=0.75` | `ok=80, fail=0` | 약 209.57초 | 안정적이지만 다소 느림 |
| `workers=2, stagger=0.5, page_delay=1.0` | `ok=79, fail=1` | 약 812.41초 | 지나치게 느림 |
| `workers=3, stagger=0.2, page_delay=0.75` | `ok=80, fail=0` | 약 227.88초 | 안정적이나 현재 추천값보다 느림 |
| `workers=4, stagger=0.15, page_delay=0.75` | `ok=80, fail=0` | 약 129.36초 | 현재 기준 최적값 |

추가로 실제 producer 전체 cycle도 동일 조건으로 검증했습니다.

- `ok_queries=80`
- `failed_queries=0`
- `published=18416`

즉, "전체 쿼리 성공률"과 "수집 시간"을 함께 고려하면 현재 운영 기본값은 다음 조합이 가장 균형이 좋습니다.

<details>
<summary>코드</summary>

```env
NAVER_MAX_WORKERS=4
NAVER_PAGE_REQUEST_DELAY_SECONDS=0.75
NAVER_QUERY_STAGGER_SECONDS=0.15
```

</details>

### 6-4. 최종 운영 권장값

현재 프로젝트의 기본값은 아래처럼 유지하는 것을 권장합니다.

- `NAVER_MAX_WORKERS=4`
- `NAVER_PAGE_REQUEST_DELAY_SECONDS=0.75`
- `NAVER_QUERY_STAGGER_SECONDS=0.15`

선정 이유는 다음과 같습니다.

- 80개 쿼리 전체가 실패 없이 끝났습니다.
- 약 2분 남짓한 수준으로, 15분 주기 수집에 충분히 들어옵니다.
- `workers=8`처럼 버스트가 커지지 않아 향후 rate limit 변동에도 상대적으로 안전합니다.
- `workers=2~3`보다 운영 지연이 적습니다.


### 6-6. 일부 기사에서 `title`이 비어 있는 비정상 payload가 발견

이런 1건이 producer cycle 전체를 실패시킬 수 있었는데, 지금은 해당 레코드만 dead letter로 적재하고 나머지 수집은 계속 진행합니다.
