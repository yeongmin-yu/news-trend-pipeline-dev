# STEP 4: Dictionary (Compound Noun & Stopword)

## 목적
텍스트 품질 향상을 위한 사전 기반 처리

## 구성
- compound_noun_dict
- stopword_dict
- compound_noun_candidates

## 흐름
1. 뉴스 데이터 분석
2. 후보 추출
3. 관리자 검토
4. 사전 등록
5. Spark 처리 반영

## 설계 포인트
- DB 기반 사전 관리
- version 관리 (dictionary_versions)
- 자동 추천 + 수동 승인 구조

## 상세
복합명사 추출 로직은 analytics 모듈 참고
