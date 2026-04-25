# STEP 2: Processing (Spark)

## 목적
Kafka 메시지를 실시간 처리하여 분석 가능한 형태로 변환

## 핵심 스택
- Spark Structured Streaming

## 흐름
1. Kafka 메시지 consume
2. JSON parsing
3. 텍스트 전처리 (tokenize)
4. 키워드 추출
5. window aggregation

## 설계 포인트
- streaming 기반 near real-time 처리
- 상태 관리 (checkpoint)
- 사전 기반 토큰 처리 (복합명사/불용어)

## 상세
전처리 세부 로직은 STEP2_PREPROCESSING 문서 참고
