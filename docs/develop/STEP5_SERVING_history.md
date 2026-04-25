# STEP5 Serving 변경 이력

## 1. 문제 배경

Dashboard에서 키워드 트렌드 차트의 드래그 패닝, 확대/축소, 기간 이동 기능을 구현하면서 다음 문제가 발생했다.

- 기간 변경 시 KPI / keywords / spikes API가 반복 호출됨
- 짧은 시간 내 다수의 backend 요청 발생
- API 응답 대기 동안 UI 상호작용이 끊기는 문제

특히 차트 interaction이 많은 경우 UX가 크게 저하됨.

---

## 2. 초기 구조

초기 구조는 다음과 같았다.

```text
사용자 interaction
→ 기간 변경
→ KPI API 호출
→ keywords API 호출
→ spikes API 호출
→ 결과 렌더링
```

문제:

- 작은 window 이동에도 전체 재조회
- 서버 집계 반복 수행
- 네트워크 latency가 UI에 직접 영향

---

## 3. 해결 전략

핵심 전략:

> "넓은 범위 데이터를 한 번 가져오고, 화면에 필요한 부분만 프론트에서 재집계"

이를 위해 다음을 도입했다.

- `overview-window` 통합 API
- `fetchStartAt / fetchEndAt` 개념
- 프론트 cache 기반 재집계

---

## 4. overview-window 도입

기존:

- KPI / keywords / spikes 각각 호출

변경:

- 하나의 API에서 통합 응답

```text
GET /api/v1/dashboard/overview-window
```

이 API는 다음을 함께 반환한다.

- KPI
- keywords
- spikes
- cache payload (articleBuckets, keywordBuckets, candidateKeywords)

---

## 5. fetch window 개념

두 가지 window 개념을 분리했다.

### (1) 표시 window

- 현재 UI에 보이는 기간

### (2) fetch window

- 서버에서 미리 가져오는 더 넓은 기간

```text
fetch window ⊃ display window
```

프론트는 display window를 이동할 때 fetch window 범위 안이면 API를 다시 호출하지 않는다.

---

## 6. 프론트 재집계 도입

`deriveOverviewFromCache()`를 통해 다음 값을 프론트에서 계산한다.

- KPI
- top keywords
- spike events

입력 데이터:

- articleBuckets
- keywordBuckets
- candidateKeywords

즉:

```text
서버 → 원시 bucket 데이터 제공
프론트 → 현재 window 기준 재집계
```

---

## 7. 백엔드 역할 변화

이 변경은 "집계를 프론트로 옮긴 것"이 아니라 다음과 같은 구조 변경이다.

### 변경 전

- 서버가 모든 window에 대해 집계 수행
- 프론트는 결과만 표시

### 변경 후

- 서버: 넓은 범위의 bucket 데이터 + 1차 집계 제공
- 프론트: 표시 window 기준 2차 집계 수행

즉, 집계 책임이 완전히 이동한 것이 아니라

> "표시 단위 집계만 프론트로 일부 이동"

이다.

---

## 8. 추가 최적화

다음 최적화도 함께 적용됨.

- overview-window 내부 중복 키워드 집계 제거
- sampleSeries 계산 제거
- bucket 기반 집계 통일
- overscan 기반 fetch window 확장

효과:

- 서버 응답 크기 감소
- API 호출 횟수 감소
- UI 반응 속도 개선

---

## 9. 재호출 전략

API는 다음 경우에만 다시 호출된다.

- source 변경
- domain 변경
- search 변경
- fetch window 범위 초과
- auto refresh tick

---

## 10. 결과

- KPI / keywords / spikes 반응 속도 즉시화
- 차트 interaction 시 UX 개선
- backend 호출 횟수 감소
- 서버 부하 감소

---

## 11. 향후 개선

- cache size 관리
- memory usage 최적화
- incremental fetch
- server-side partial aggregation 개선

---

## 12. 메모

- overview-window는 STEP5의 핵심 구조
- 프론트와 백엔드가 협력하는 hybrid aggregation 구조
- design 문서는 "최종 구조"만 남기고 본 문서는 변경 이력 관리
