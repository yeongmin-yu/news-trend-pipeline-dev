# DB Migrations (Flyway)

이 디렉터리의 SQL 파일은 [Flyway](https://flywaydb.org/) 가 컨테이너 기동 시 자동
적용한다. 적용 이력은 PG 의 `flyway_schema_history` 테이블에 기록된다.

## 파일 명명 규칙

```
V<버전>__<설명>.sql
```

- `V1__init_schema.sql` — 최초 스키마 + 초기 seed
- `V2__<설명>.sql` — 다음 변경사항
- 버전은 단조 증가. 한 번 적용된 파일은 **수정 금지** (해시 검증 실패).

## 변경 절차

1. `db/migration/V<n+1>__<설명>.sql` 파일을 새로 만든다.
2. 멱등성 보장을 위해 가능하면 `IF NOT EXISTS`, `IF EXISTS`, `ON CONFLICT` 등을 사용.
3. `docker compose up -d flyway` 또는 전체 재기동으로 적용.
4. 실패 시 → SQL 수정 후 `docker compose run --rm flyway repair && docker compose up -d flyway`.

## 로컬에서 직접 실행

```bash
docker compose run --rm flyway info
docker compose run --rm flyway migrate
docker compose run --rm flyway validate
```

## 운영 시 주의

- 파괴적 변경(`DROP COLUMN`, `DROP TABLE`) 은 별도 PR + 다운타임 협의 후.
- 큰 인덱스 생성은 `CREATE INDEX CONCURRENTLY` 권장 (트랜잭션 외부).
- seed 가 자주 바뀌는 데이터(검색어/도메인) 는 별도 변경 V 파일로 분리.

## 파티션 관리 (pg_partman)

V2 부터 `keyword_relations` / `keyword_trends` 의 파티션을 [pg_partman](https://github.com/pgpartman/pg_partman) 이 자동 관리한다.

- premake 3 — 미래 3개월 분량 파티션을 미리 생성
- retention 6개월 — 6개월 경과 파티션 자동 DROP (디스크 회수)
- Airflow `partition_maintenance` DAG 가 매일 새벽 2시 (KST) `partman.run_maintenance_proc()` 호출

설정 변경:
```sql
-- retention 기간 변경 (예: 12개월로 늘리기)
UPDATE partman.part_config
   SET retention = '12 months'
 WHERE parent_table IN ('public.keyword_relations', 'public.keyword_trends');

-- premake 변경 (미래 6개월까지 미리 만들기)
UPDATE partman.part_config
   SET premake = 6
 WHERE parent_table IN ('public.keyword_relations', 'public.keyword_trends');
```

수동 실행 (디버깅):
```bash
docker compose exec app-postgres \
  psql -U postgres -d news_pipeline -c "CALL partman.run_maintenance_proc()"
```
