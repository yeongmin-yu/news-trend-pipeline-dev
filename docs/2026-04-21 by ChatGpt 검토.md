문제

현재 구조:

Spark → collect() → Python → DB insert

→ 병목: 드라이버, 메모리, DB round-trip
→ Spark 병렬성 거의 못 씀

목표
Spark → DB (bulk) → DB에서 upsert
1. collect() 제거 (가장 중요)
절대 Python으로 모으지 말 것
Spark DataFrame 그대로 DB로 저장
2. staging 테이블 도입

예:

stg_news_raw
stg_keyword_trends
stg_keyword_relations

흐름:

Spark → staging append → DB에서 upsert → 본 테이블
3. upsert 구조 필수
news_raw
키: (provider, url)
ON CONFLICT:
DO NOTHING 또는
DO UPDATE (권장)
keyword_trends

고유키 추가:

(provider, window_start, window_end, keyword)
keyword_relations

고유키:

(provider, window_start, window_end, keyword_a, keyword_b)
4. 집계 테이블은 append 금지

→ 중복 발생

대신:

ON CONFLICT DO UPDATE
5. keywords 테이블 활성화 (중요)

용도:

기사별 키워드 저장
재처리
복합명사 후보
이벤트 근거

구조:

(article_provider, article_url, keyword)
6. 최종 구조
news_raw        ← 원문
keywords        ← 기사 단위
keyword_trends  ← 윈도우 집계
relations       ← 관계
7. 최소 변경 vs 권장
최소
collect 제거
JDBC write
upsert 추가
권장
staging
keywords 테이블
unique key
결론

Spark 결과를 Python으로 모으지 말고
DB에 직접 bulk write + upsert로 처리해야 한다.
