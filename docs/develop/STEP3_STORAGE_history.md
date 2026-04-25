# STEP3 Storage History

> STEP 3 문서 정리 과정 기록.

## 1. 정리 배경

기존 STEP 3 문서는 저장 계층 개요와 데이터베이스 상세가 섞여 있었고, 과거 설계 비교와 현재 구현 설명이 함께 남아 있었다.

문서 정리 원칙에 따라 `docs/design`에는 최종 구현만 남기고, 정리 과정과 변경 배경은 이 파일로 분리했다.

## 2. 정리 내용

- `STEP3_STORAGE.md`
  - 저장 계층의 역할, 데이터 범위, staging 기반 적재 구조 중심으로 재작성
- `STEP3-1_DATABASE.md`
  - 실제 `models.sql`, `db.py` 기준으로 스키마/인덱스/upsert/재처리 유틸 정리

## 3. 반영한 구현 기준

- `safe_initialize_database()` 기반 스키마 초기화와 seed
- `provider + domain` 기준 unique key 구조
- `stg_*` 테이블을 통한 Spark 후단 upsert
- `collection_metrics`, `keyword_events` 포함
- 사전 버전 trigger와 감사 로그 테이블 반영
- 일 단위 rebuild 유틸 반영

## 4. 제거한 문서 요소

- Step 2 시절 파일명 기준의 오래된 참조
- 현재 코드에 없는 비교 설명
- design 문서 안에 있던 변경 배경과 개선 메모
