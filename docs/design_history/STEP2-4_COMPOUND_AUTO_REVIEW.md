# STEP 2-4: Compound Auto Review

## 1. 목적

복합명사 후보 중 자동으로 신뢰도가 높은 항목을 선별해 사전에 반영하기 위한 단계다.

## 2. 처리 흐름

```text
compound_noun_candidates (needs_review)
    ↓
Naver Web Search API 근거 수집
    ↓
auto_score 계산
    ↓
auto_evidence 저장
    ↓
high_confidence만 자동승인
    ↓
compound_noun_dict 반영
    ↓
dictionary_versions 증가
```

## 3. 핵심 동작

- `needs_review` 상태의 후보만 조회한다.
- Naver Web Search API를 통해 외부 근거를 수집한다.
- 내부 통계(frequency, doc_count)와 외부 근거를 기반으로 `auto_score`를 계산한다.
- 판단 근거는 `auto_evidence` JSON으로 저장한다.
- `high_confidence` 후보만 자동승인한다.
- 승인된 후보는 `compound_noun_dict`에 반영한다.
- 사전 변경 시 `dictionary_versions`를 증가시켜 downstream 캐시 갱신을 유도한다.

## 4. 설계 원칙

- 자동승인은 보수적으로 수행한다.
- 낮은 신뢰도 후보는 절대 자동으로 사전에 반영하지 않는다.
- 후보 상태(`approved`, `rejected`)는 자동 로직으로 변경하지 않는다.
- 재실행 시에도 동일 조건에서는 동일 결과를 유지하도록 설계한다.
