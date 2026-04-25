# STEP4 Analytics 변경 이력

## 개요

이 문서는 STEP4(Analytics) 설계 및 구현 과정에서 발생한 변경 사항과 판단 과정을 기록한다.

`docs/design/STEP4_*` 문서에는 최종 구현만 남기고, 실험/변경 이력은 본 문서에서 관리한다.

---

## 1. 초기 상태

초기 설계에서는 이벤트 탐지를 Spark 처리 단계 또는 API 레이어에서 계산하는 방식이 혼재되어 있었다.

문제점:

- 동일 로직이 여러 위치에 존재
- 재현성 부족
- 대시보드 조회 시 계산 비용 증가

---

## 2. 이벤트 레이어 분리

결정:

- 이벤트 탐지를 별도 단계(STEP4)로 분리
- 결과를 `keyword_events` 테이블로 materialize

효과:

- Dashboard 조회 성능 개선
- 재계산 가능 구조 확보
- Airflow 기반 스케줄링 가능

---

## 3. 배치 방식 채택

초기 후보:

- streaming 기반 이벤트 탐지
- on-demand API 계산

최종 선택:

- Airflow 배치 (15분 주기)

이유:

- 구현 단순성
- 디버깅 용이성
- 재처리 용이성

---

## 4. lookback window 결정

현재:

- 24시간 고정 lookback

논의:

- 더 짧은 window (6h, 12h)
- adaptive window

결론:

- 초기에는 24시간 고정
- 향후 domain별 튜닝 대상

---

## 5. spike 기준 변경 이력

### 초기

- 단순 증가량 기준

### 중간

- growth 비율 기반

### 현재

```text
current >= 5
and growth >= 0.4
```

추가 조건:

```text
current > 0
and (
    spike
    or current >= 5
    or growth >= 0.15
)
```

---

## 6. score 공식 변화

현재 공식:

```text
growth * 45
+ sqrt(count) * 6
+ spike bonus
```

논의 후보:

- TF-IDF 기반 score
- domain weight 반영
- recency decay 반영

현재 상태:

- heuristic 기반 유지
- 추후 고도화 예정

---

## 7. replace 전략 도입

문제:

- append 방식 → 중복/누적 발생

해결:

- 동일 시간 범위 delete 후 insert

효과:

- 멱등성 확보
- 재실행 안정성 확보

---

## 8. API fallback 구조

현재 구조:

- 1순위: keyword_events
- 2순위: keyword_trends 기반 계산

이유:

- 이벤트 테이블 초기 상태 대응
- 특정 필터 조건 대응

---

## 9. 향후 개선 후보

- domain별 threshold 분리
- noise keyword 자동 제거
- event clustering
- 알림 시스템 연동
- dashboard annotation

---

## 10. 메모

- STEP4는 "계산" 단계가 아니라 "분석 결과 생성 단계"로 정의
- Spark와 역할 분리를 명확히 유지
- 설계 문서는 항상 "현재 코드 기준"으로 유지
