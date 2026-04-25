# STEP 5: Serving Overview

## 1. 목적

STEP5는 분석 결과를 FastAPI를 통해 제공하고, Dashboard에서 빠르게 탐색할 수 있도록 하는 서빙 계층이다.

이 단계는 다음 두 영역으로 구성된다.

- STEP5-1: API (FastAPI)
- STEP5-2: Dashboard (Frontend)

## 2. 전체 구조

```mermaid
flowchart LR
    A[PostgreSQL] --> B[FastAPI]
    B --> C[overview-window API]
    C --> D[Dashboard Cache]
    D --> E[Frontend Aggregation]
    E --> F[UI Rendering]
```

## 3. 핵심 특징

- FastAPI 기반 REST API
- overview-window 기반 통합 조회
- frontend cache + 재집계 구조
- low-latency UI interaction 지원

## 4. 세부 문서

- `STEP5_API.md` → FastAPI 구현 및 API 구조
- `STEP5_DASHBOARD.md` → Dashboard UI 및 프론트 로직

## 5. 한 줄 정리

```text
STEP5는 FastAPI와 Dashboard가 결합된 hybrid serving layer이다.
```