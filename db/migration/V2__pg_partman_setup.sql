-- ============================================================================
-- V2__pg_partman_setup.sql
-- pg_partman 으로 keyword_relations / keyword_trends 의 파티션을 자동 관리.
--
-- 동작:
--   1) partman 확장 설치
--   2) V1 이 수동으로 만든 월별 자식 + DEFAULT 파티션 모두 DROP
--      (개발 단계 — 데이터 보존 안 함; 운영 전환 시 별도 마이그레이션 작성 필요)
--   3) partman.create_parent() 로 등록 — premake 3 (3개월 선행 생성)
--   4) retention 6개월: 윈도우 종료 6개월 경과한 파티션은 자동 DROP
--
-- 이후 매일 1회 partman.run_maintenance_proc() 가 실행되어
-- 누락된 미래 파티션 생성 + 만료된 과거 파티션 회수를 수행한다 (Airflow DAG 가 호출).
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS partman;
CREATE EXTENSION IF NOT EXISTS pg_partman SCHEMA partman;

-- ----------------------------------------------------------------------------
-- 기존 자식 파티션 폐기 (V1 이 만든 *_2024_01 ... *_2027_12 + *_default)
-- partman 이 자기 네이밍 규칙으로 새로 만들도록 하기 위함.
-- ----------------------------------------------------------------------------
DO $$
DECLARE
    rec record;
BEGIN
    FOR rec IN
        SELECT inhrelid::regclass AS child
          FROM pg_inherits
         WHERE inhparent IN (
             'public.keyword_relations'::regclass,
             'public.keyword_trends'::regclass
         )
    LOOP
        EXECUTE format('DROP TABLE %s', rec.child);
    END LOOP;
END $$;

-- ----------------------------------------------------------------------------
-- partman 등록
-- ----------------------------------------------------------------------------
-- pg_partman 5.x 시그니처 (p_type 파라미터는 v5 에서 제거됨, 항상 'native')
SELECT partman.create_parent(
    p_parent_table    := 'public.keyword_relations',
    p_control         := 'window_start',
    p_interval        := '1 month',
    p_premake         := 3,
    p_start_partition := to_char(date_trunc('month', NOW() - INTERVAL '1 month'), 'YYYY-MM-DD')
);

SELECT partman.create_parent(
    p_parent_table    := 'public.keyword_trends',
    p_control         := 'window_start',
    p_interval        := '1 month',
    p_premake         := 3,
    p_start_partition := to_char(date_trunc('month', NOW() - INTERVAL '1 month'), 'YYYY-MM-DD')
);

-- ----------------------------------------------------------------------------
-- Retention 정책: 6개월 경과 파티션 자동 DROP
-- (retention_keep_table=false 면 detach 가 아니라 진짜 DROP — 디스크 회수)
-- ----------------------------------------------------------------------------
UPDATE partman.part_config
   SET retention             = '6 months',
       retention_keep_table  = false,
       infinite_time_partitions = true   -- 미래 데이터 들어와도 자동 확장
 WHERE parent_table IN ('public.keyword_relations', 'public.keyword_trends');
