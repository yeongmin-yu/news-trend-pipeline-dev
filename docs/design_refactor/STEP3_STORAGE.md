# STEP 3: Storage (PostgreSQL)

## 목적
처리된 데이터를 안정적으로 저장 및 조회 가능하게 구성

## 핵심 스택
- PostgreSQL

## 흐름
1. Spark → staging table write
2. DB 내부 upsert
3. 최종 테이블 반영

## 주요 테이블
- news_raw
- keywords
- keyword_trends
- keyword_relations

## 설계 포인트
- upsert 기반 멱등성 확보
- domain 기반 데이터 분리
- 인덱스 최적화

## 상세
테이블 구조는 STEP2_DATABASE.md 참고
