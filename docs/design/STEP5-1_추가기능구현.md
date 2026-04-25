# STEP4 추가 기능 구현

## 개요

2026-04-23 기준으로 STEP4(FastAPI) 추가 구현 범위 중 아래 항목을 완료했다.

- `collection_metrics` 테이블 및 조회 API 구현
- `dictionary_audit_logs` 테이블 및 감사 로그 API 구현
- `query_keyword_audit_logs` 테이블 및 감사 로그 API 구현
- 도메인 수집 키워드 관리 API 구현
- 프론트엔드 `도메인 키워드 관리` 모달 구현

## 구현 범위

### 1. 수집 운영 지표

추가 테이블:

- `collection_metrics`

기록 항목:

- `provider`
- `domain`
- `query`
- `window_start`
- `window_end`
- `request_count`
- `success_count`
- `article_count`
- `duplicate_count`
- `publish_count`
- `error_count`

반영 위치:

- [src/storage/models.sql](C:/Project/news-trend-pipeline-v2/src/storage/models.sql)
- [src/storage/db.py](C:/Project/news-trend-pipeline-v2/src/storage/db.py)
- [src/ingestion/producer.py](C:/Project/news-trend-pipeline-v2/src/ingestion/producer.py)

동작 방식:

- Naver 수집 쿼리 1회 실행마다 쿼리 단위 운영 지표를 적재한다.
- 성공/실패, 기사 건수, 중복 건수, publish 건수를 함께 남긴다.
- 관리자 API에서 최근 시간 범위 기준으로 조회한다.

### 2. 용어 사전 감사 로그

추가 테이블:

- `dictionary_audit_logs`

기록 대상:

- 복합명사 추가/삭제
- 복합명사 후보 승인/반려
- 불용어 추가/삭제

반영 위치:

- [src/storage/models.sql](C:/Project/news-trend-pipeline-v2/src/storage/models.sql)
- [src/storage/db.py](C:/Project/news-trend-pipeline-v2/src/storage/db.py)
- [src/api/service.py](C:/Project/news-trend-pipeline-v2/src/api/service.py)
- [src/api/app.py](C:/Project/news-trend-pipeline-v2/src/api/app.py)

제공 API:

- `GET /api/v1/dictionary`
- `GET /api/v1/dictionary/history`

### 3. 도메인 수집 키워드 변경 로그

추가 테이블:

- `query_keyword_audit_logs`

기록 대상:

- 도메인 수집 키워드 생성
- 도메인 수집 키워드 수정
- 도메인 수집 키워드 삭제

반영 위치:

- [src/storage/models.sql](C:/Project/news-trend-pipeline-v2/src/storage/models.sql)
- [src/storage/db.py](C:/Project/news-trend-pipeline-v2/src/storage/db.py)
- [src/api/service.py](C:/Project/news-trend-pipeline-v2/src/api/service.py)
- [src/api/app.py](C:/Project/news-trend-pipeline-v2/src/api/app.py)

제공 API:

- `GET /api/v1/admin/query-keywords`
- `POST /api/v1/admin/query-keywords`
- `PATCH /api/v1/admin/query-keywords/{item_id}`
- `DELETE /api/v1/admin/query-keywords/{item_id}`

## 프론트엔드 반영

추가 파일:

- [src/dashboard/src/query-keyword-modal.tsx](C:/Project/news-trend-pipeline-v2/src/dashboard/src/query-keyword-modal.tsx)

수정 파일:

- [src/dashboard/src/app.tsx](C:/Project/news-trend-pipeline-v2/src/dashboard/src/app.tsx)
- [src/dashboard/src/data.ts](C:/Project/news-trend-pipeline-v2/src/dashboard/src/data.ts)

UI 반영 내용:

- `용어 사전` 버튼 옆에 `도메인 키워드 관리` 버튼 추가
- 도메인별 쿼리 키워드 조회/검색/생성/수정/활성화/비활성화/삭제
- 수집 운영 지표 탭
- 수집 키워드 변경 로그 탭

## 검증 결과

2026-04-23(Asia/Seoul) 기준으로 아래를 확인했다.

### 빌드/기동

- `docker compose build api-server frontend-server` 성공
- `docker compose up -d --force-recreate api-server frontend-server` 성공
- 프론트 응답: `http://localhost:3000` 정상
- API 헬스체크: `http://localhost:8000/health` 정상

### API 조회

- `GET /api/v1/admin/query-keywords` 정상 응답
- `GET /api/v1/admin/collection-metrics?hours=24` 정상 응답
- `GET /api/v1/dictionary/history` 정상 응답

### 쓰기 검증

테스트 actor: `codex-test`

- 도메인 키워드 생성 성공
- 도메인 키워드 수정 성공
- 도메인 키워드 삭제 성공
- 불용어 생성 성공
- 불용어 삭제 성공

감사 로그 확인:

- `query_keyword_audit_logs = 3`
- `dictionary_audit_logs = 2`

### 운영 지표 데이터 확인

- `collection_metrics = 80`

의미:

- 4개 도메인 x 20개 쿼리 기준으로 수집 1회분 지표가 생성됨

## 비고

- Windows PowerShell 콘솔에서는 한글 JSON이 깨져 보일 수 있으나, 브라우저와 프론트엔드에서는 정상 표시된다.
- `dictionary_audit_logs`는 API까지 완료되었고, 별도 전용 탭 UI는 후속 개선 항목으로 `todo.md`에 남겼다.
