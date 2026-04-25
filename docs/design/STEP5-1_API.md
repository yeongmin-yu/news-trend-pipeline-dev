# STEP5-1: API (FastAPI)

## 1. 구현 방식

STEP5 API는 FastAPI 기반으로 구현되었다.

- framework: FastAPI
- 위치: `src/api/app.py`
- 서비스 로직: `src/api/service.py`

## 2. 역할

- PostgreSQL 데이터를 조회
- Dashboard 친화적인 응답 구조 생성
- overview-window 기반 cache 응답 제공

## 3. 핵심 API

### 3.1 overview-window

```text
GET /api/v1/dashboard/overview-window
```

역할:

- KPI, keywords, spikes 통합 조회
- frontend cache용 bucket 데이터 제공

### 3.2 기타 API

- `/dashboard/kpis`
- `/dashboard/keywords`
- `/dashboard/trend-window`
- `/dashboard/spikes`
- `/dashboard/related`
- `/dashboard/articles`

## 4. overview-window 핵심 구조

입력:

- startAt / endAt (표시 구간)
- fetchStartAt / fetchEndAt (확장 구간)

출력:

- summary (kpis, keywords, spikes)
- cache (bucket raw data)

## 5. 설계 포인트

- backend는 raw bucket + 1차 집계 제공
- frontend 재집계를 고려한 응답 구조
- API 호출 최소화

## 6. 한 줄 정리

```text
FastAPI는 dashboard를 위한 cache-friendly 데이터 provider 역할을 한다.
```