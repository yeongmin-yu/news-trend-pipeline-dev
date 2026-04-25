# STEP2 Processing History

> STEP 2 설계 변경 과정 기록.

## 1. 변경 배경

STEP 2 문서는 초기에 Spark 처리, 전처리 개선 아이디어, DB 스키마 변화 설명이 한 문서 안에 섞여 있었다.  
정리 원칙에 맞춰 `docs/design`에는 현재 구현만 남기고, 여기에는 변경 과정과 문서 분리 배경만 기록한다.

## 2. 정리한 항목

- Spark 처리 흐름과 전처리 세부 내용을 분리함
- 과거 파일명과 맞지 않는 참조를 제거함
- 개선 방향, 향후 아이디어, 예전 스키마 비교를 design 문서에서 제거함
- 사전 계층 문서를 현재 구현 범위에 맞춰 복합명사/불용어/후보 추천 중심으로 재정리함

## 3. 문서 분리 결과

- `STEP2_PROCESSING.md`
  - STEP 2 전체 처리 흐름
- `STEP2-1_SPARK.md`
  - Spark streaming 적재와 집계
- `STEP2-2_PREPROCESSING.md`
  - 텍스트 정제와 토큰화
- `STEP2-3_DICTIONARY.md`
  - 사전 적용과 후보 관리

## 4. 후속 정리 메모

- STEP 3에서는 staging/upsert 구조와 최종 테이블 책임을 더 명확히 연결할 필요가 있다.
- STEP 4에서는 `keyword_events`가 `keyword_trends`를 입력으로 삼는 점을 중심으로 문서를 맞추면 된다.
