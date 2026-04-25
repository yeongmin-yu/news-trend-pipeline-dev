# STEP 5: Analytics (Trend & Event Detection)

## 목적
키워드 트렌드 및 이벤트(급상승) 분석

## 입력
- keyword_trends
- keyword_relations

## 흐름
1. 시간 윈도우 기반 집계
2. 이전 구간 대비 변화량 계산
3. 이벤트 점수 계산
4. keyword_events 저장

## 설계 포인트
- window 기반 분석
- domain별 독립 분석
- spike detection 중심

## 상세
이벤트 스코어 계산 로직은 별도 분석 문서로 분리
