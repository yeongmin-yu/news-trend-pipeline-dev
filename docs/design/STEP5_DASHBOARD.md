# STEP5-2: Dashboard

## 1. 목적

Dashboard는 뉴스 트렌드 데이터를 시각화하고, 사용자 인터랙션을 통해 빠르게 탐색할 수 있는 UI이다.

## 2. 구현 위치

- `src/dashboard/src/app.tsx`
- `src/dashboard/src/charts.tsx`
- `src/dashboard/src/data.ts`

## 3. 주요 기능

- KPI 카드
- 상위 키워드 리스트
- 트렌드 차트
- 스파이크 heatmap
- 연관 키워드
- 기사 목록

## 4. 최적화 구조 (핵심)

### 문제

- 차트 드래그 / 줌 시 API 반복 호출
- UI 렉 발생

### 해결

- overview-window API 도입
- fetch window 확장
- 프론트 cache 기반 재집계

## 5. 동작 방식

1. 넓은 범위 fetch
2. cache 저장
3. 현재 window 기준 재집계

## 6. 핵심 함수

- `deriveOverviewFromCache()`

역할:

- KPI 재계산
- keywords 재계산
- spikes 재계산

## 7. 결과

- UI 즉시 반응
- API 호출 감소
- UX 개선

## 8. 화면

- `STEP5-1_Screenshot.png`

## 9. 한 줄 정리

```text
Dashboard는 cache 기반 재집계를 통해 고속 인터랙션을 제공한다.
```