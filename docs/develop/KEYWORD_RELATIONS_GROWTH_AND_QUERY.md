# keyword_relations 데이터 증가량 & 조회 성능 가이드

> 기준 코드: [`src/processing/spark_job.py`](../../src/processing/spark_job.py),
> [`db/migration/V1__init_schema.sql`](../../db/migration/V1__init_schema.sql),
> [`src/api/service.py`](../../src/api/service.py)
>
> 기준 설정: `relation_keyword_limit = 5`, `keyword_window_duration = 10 minutes`

## 1. 어떤 테이블이 가장 빨리 큰가

### 이론적 비교 (배치당 행 수)

기사 1건당 distinct 토큰 30개, top-5 키워드로 페어 생성 가정.

| 테이블 | 기사 1건당 | 윈도우(10분) 100기사 1 (provider, domain) | 누적 패턴 |
|---|---|---|---|
| `news_raw` | 1행 | 100행 | 기사 수에 비례 |
| `keywords` | ~30행 | ~3,000행 | 기사 × 토큰 |
| `keyword_trends` | — (집계) | ~200~500행 (윈도우 내 unique keyword) | 윈도우 × 도메인 |
| `keyword_relations` | C(5,2)=**10페어** | ~500~800행 (윈도우 내 unique pair) | 윈도우 × 도메인 × 페어 조합 |

6개 도메인 × 2 provider(naver+rss) = 12 × 144 윈도우/day 환산:

| 테이블 | 하루 추가 행 (추정) |
|---|---|
| `news_raw` | ~17,000 |
| `keywords` | ~520,000 |
| `keyword_trends` | ~520,000 |
| `keyword_relations` | **~860,000** (limit=5) / ~2,400,000 (limit=8) |

**`keyword_relations` 가 가장 빠르게 증가한다.** 페어 조합 폭발 때문.

### 왜 그런가

핵심은 **한 단어 → 여러 페어**.

```
기사: "AI 반도체 수출 호조"
키워드: [AI, 반도체, 수출, 호조] (top-5 중 4개)

keyword_trends 행:
  - AI         (1행)
  - 반도체     (1행)
  - 수출       (1행)
  - 호조       (1행)
  → 4행

keyword_relations 행:
  - (AI, 반도체)
  - (AI, 수출)
  - (AI, 호조)
  - (반도체, 수출)
  - (반도체, 호조)
  - (수출, 호조)
  → 6행 (= C(4,2))
```

키워드 N 개일 때:
- `keyword_trends` 는 N행
- `keyword_relations` 는 N(N-1)/2 행

→ N=8 이면 trends 의 3.5배, N=10 이면 4.5배.

### 실측 쿼리

```sql
-- 테이블별 행 수와 디스크 사용량
SELECT
    relname AS table_name,
    n_live_tup AS approx_rows,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid))       AS heap_size,
    pg_size_pretty(pg_indexes_size(relid))        AS index_size
FROM pg_stat_user_tables
WHERE relname IN ('news_raw', 'keywords', 'keyword_trends', 'keyword_relations',
                  'keyword_relations_default')
   OR relname LIKE 'keyword_relations_2%'
ORDER BY pg_total_relation_size(relid) DESC;
```

```sql
-- keyword_relations 의 월별 파티션 분포
SELECT
    inhrelid::regclass AS partition,
    pg_size_pretty(pg_total_relation_size(inhrelid)) AS size,
    (SELECT n_live_tup FROM pg_stat_user_tables WHERE relid = inhrelid) AS approx_rows
FROM pg_inherits
WHERE inhparent = 'keyword_relations'::regclass
ORDER BY pg_total_relation_size(inhrelid) DESC;
```

```sql
-- 최근 24시간 추가 추이
SELECT 'news_raw'           AS tbl, count(*) FROM news_raw          WHERE ingested_at  > NOW() - INTERVAL '24 hours'
UNION ALL SELECT 'keywords',           count(*) FROM keywords          WHERE processed_at > NOW() - INTERVAL '24 hours'
UNION ALL SELECT 'keyword_trends',     count(*) FROM keyword_trends    WHERE processed_at > NOW() - INTERVAL '24 hours'
UNION ALL SELECT 'keyword_relations',  count(*) FROM keyword_relations WHERE processed_at > NOW() - INTERVAL '24 hours';
```

## 2. keyword_relations 조회 성능

### 대표 조회 쿼리 (API)

[`src/api/service.py:937-953`](../../src/api/service.py:937) 의 "관련 키워드" 쿼리:

```sql
SELECT keyword_b AS related_keyword, SUM(cooccurrence_count) AS weight
FROM keyword_relations
WHERE keyword_a = :keyword
  AND window_start >= :start_at
  AND window_start <  :end_at
  AND (:provider IS NULL OR provider = :provider)
  AND (cardinality(:domain::text[]) = 0 OR domain = ANY(:domain::text[]))
GROUP BY keyword_b
UNION ALL
SELECT keyword_a AS related_keyword, SUM(cooccurrence_count) AS weight
FROM keyword_relations
WHERE keyword_b = :keyword
  AND window_start >= :start_at
  AND window_start <  :end_at
  ...
GROUP BY keyword_a;
```

### 사용되는 인덱스 + 파티션 프루닝

- `idx_keyword_relations_keyword_a_window (keyword_a, window_start)` — UNION 첫 half
- `idx_keyword_relations_keyword_b_window (keyword_b, window_start)` — UNION 두 번째 half
- 파티션 키 `window_start` 의 BETWEEN 조건 → **partition pruning** 으로 해당 월 자식 테이블만 스캔

### 조회 범위별 예상 응답시간

기준: 인기 키워드 (예: "AI", "정부"), 1 (provider, domain) 필터, `LIMIT 100`.

| 조회 범위 | 스캔 파티션 수 | 매칭 행 (추정) | 예상 응답 | 적합 용도 |
|---|---|---|---|---|
| 1시간 | 1 | ~10~50 | <10ms | 실시간 위젯 |
| 24시간 | 1~2 | ~200~1,000 | 10~50ms | 대시보드 기본 뷰 |
| 7일 | 1~2 | ~1,500~7,000 | 50~200ms | **API 권장 상한** |
| 30일 | 1~2 | ~6,000~30,000 | 100~500ms | 대시보드 확장 뷰 |
| 90일 | 3~4 | ~20,000~90,000 | 300ms~1s | ⚠ 경계 — 백그라운드/캐시 권장 |
| 1년 | 12 | ~80,000~360,000 | 1~3s | ✗ 비동기 분석 전용 |
| 2년+ | 24+ | ~160,000~720,000+ | 2~6s+ | ✗ 배치/익스포트 전용 |

### 권장 가이드라인

| 사용 시나리오 | 안전 범위 | 비고 |
|---|---|---|
| **실시간 API (대시보드 위젯)** | **최대 7일** | 응답 200ms 이하 유지 |
| **사용자 인터랙티브 조회** | **최대 30일** | 500ms 이하, LIMIT 필수 |
| **분석 페이지 (필터 변경 빈도 낮음)** | 최대 90일 | 캐시 또는 materialized view 권장 |
| **리포트/익스포트 (비동기)** | 1년 이상 | 백그라운드 잡으로 처리, 결과 파일 다운로드 |

### 응답 시간을 키우는 요인

다음 조건이 겹치면 추정치보다 더 느려진다.

1. **인기 키워드** — "AI", "기업" 처럼 매 윈도우 등장하는 키워드는 페어 행이 수십 배 많음.
2. **여러 도메인 동시 조회** — `domain = ANY(['politics','economy',...])` 처럼 여러 도메인 합산 시 매칭 행 수가 도메인 수만큼 증가.
3. **provider 필터 미적용** — naver + rss 합산이면 약 2배.
4. **`LIMIT` 누락** — `GROUP BY` 결과 전체를 정렬하면 비용 폭증. 항상 `ORDER BY weight DESC LIMIT N` 적용.
5. **콜드 캐시** — 컨테이너 재기동 직후 첫 쿼리는 디스크 IO 로 느림. 두 번째부터 캐시 적중으로 빨라짐.
6. **autovacuum 지연** — 인덱스 bloat 누적 시 점진 저하.

### 응답을 빠르게 하는 패턴

#### A. LIMIT 을 항상 적용
```sql
SELECT keyword_b AS related_keyword, SUM(cooccurrence_count) AS weight
FROM keyword_relations
WHERE keyword_a = :keyword
  AND window_start BETWEEN :start AND :end
GROUP BY keyword_b
ORDER BY weight DESC
LIMIT 100;          -- ← 필수
```

#### B. provider/domain 필터 가능하면 명시
```sql
WHERE keyword_a = :keyword
  AND provider = 'naver'           -- ← 추가
  AND domain = 'tech_science'      -- ← 추가
  AND window_start BETWEEN :s AND :e
```
→ 인덱스 스캔 후 추가 필터로 매칭 행 수가 절반~수분의 1 로 감소.

#### C. 시간 범위를 가능한 좁게
사용자가 "최근 1년 트렌드" 를 원해도 실제 표시 단위가 일별이면, 일 단위 집계 테이블을 별도로 두면 더 빠르다 (아래 D 참고).

#### D. 사전 집계 테이블 도입 (장기 대안)

긴 시간 범위 조회가 잦아지면 다음을 고려:

```sql
CREATE TABLE keyword_relations_daily (
    provider           VARCHAR(50),
    domain             VARCHAR(50),
    day                DATE,
    keyword_a          VARCHAR(255),
    keyword_b          VARCHAR(255),
    cooccurrence_count INTEGER,
    PRIMARY KEY (provider, domain, day, keyword_a, keyword_b)
);
```
- 매일 1회 cron 으로 `keyword_relations` → `keyword_relations_daily` 집계
- 1년 조회: 365행/keyword × 도메인/provider — 원본 대비 100배 이상 작아짐

### 운영 체크 쿼리

```sql
-- 특정 키워드의 보유 페어 수 (인기도 가늠)
SELECT count(*) FROM keyword_relations
WHERE keyword_a = '대통령' OR keyword_b = '대통령';

-- 특정 시간 범위의 행 수
SELECT count(*) FROM keyword_relations
WHERE window_start >= NOW() - INTERVAL '7 days';

-- 인덱스 사용 여부 확인 (실제 쿼리 EXPLAIN)
EXPLAIN (ANALYZE, BUFFERS)
SELECT keyword_b, SUM(cooccurrence_count)
FROM keyword_relations
WHERE keyword_a = '대통령'
  AND window_start >= NOW() - INTERVAL '7 days'
GROUP BY keyword_b
ORDER BY SUM(cooccurrence_count) DESC LIMIT 100;
```
- `Index Scan using idx_keyword_relations_keyword_a_window` 가 보여야 정상
- `Seq Scan` 이 뜨면 인덱스 누락 또는 통계 오래됨 → `ANALYZE keyword_relations;`

## 3. 정리

- **현재 가장 데이터가 많이 쌓이는 테이블**: `keyword_relations` (이론적 ≈ 86만 행/day, limit=5 기준)
- **API 안전 조회 범위**: 7일 (실시간), 30일 (인터랙티브 한도), 90일 (캐시 권장), 1년+ (비동기 전용)
- **장기 누적 시 추가 검토 사항**:
  1. `keyword_relations_daily` 사전 집계 테이블 도입
  2. 오래된 월별 파티션 `DROP TABLE` 으로 회수 (예: 6개월 이상 된 월 폐기)
  3. `keyword_trends`, `keywords` 도 동일 패턴으로 파티셔닝 고려
