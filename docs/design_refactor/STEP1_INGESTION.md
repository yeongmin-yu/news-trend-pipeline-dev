# STEP 1: Ingestion (Airflow + Kafka)

## 목적
외부 뉴스 데이터를 안정적으로 수집하고 Kafka로 전달

## 핵심 스택
- Airflow (스케줄링)
- Kafka (메시지 큐)

## 흐름
1. Airflow DAG 실행
2. 도메인별 query_keyword 조회
3. Naver API 호출
4. URL dedup
5. Kafka topic publish

## 설계 포인트
- 수집과 처리 분리
- idempotent 설계 (URL 기준)
- domain 기반 수집 구조

## 상세
전처리/필터링 로직은 별도 문서 참조
