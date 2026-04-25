# STEP5 DASHBOARD

## 1. 목적

프론트엔드 대시보드는 실시간 뉴스 트렌드 파이프라인의 운영 화면이다. 사용자는 도메인, 소스, 시간 범위를 바꾸며 현재 급상승 키워드와 관련 기사 흐름을 빠르게 확인할 수 있어야 한다.

## 2. 화면 구성

### 2.1 상단 헤더

- 서비스 타이틀
- 메뉴
  - 대시보드
  - 이벤트
  - 키워드
  - 파이프라인
  - 용어 사전
- 실시간 시각 표시
- 자동 새로고침 토글
- 다크/라이트 테마 토글

### 2.2 서브바 필터

- `source`
  - 전체
  - 네이버 뉴스
  - 글로벌 뉴스
- `domain`
  - 전체
  - AI·테크
  - 경제·금융
  - 정치·정책
  - 엔터·문화
- `range`
  - 10분
  - 30분
  - 1시간
  - 6시간
  - 12시간
  - 1일
- 키워드 검색 typeahead
- 조회 기준 시각 표시

### 2.3 좌측 사이드바

- 도메인 요약
- 워치리스트
- 파이프라인 상태
  - Kafka
  - Spark
  - Airflow
  - API
  - DB

### 2.4 메인 패널

- KPI 카드
  - 총 기사 수
  - 고유 키워드 수
  - 급상승 키워드 수
  - 마지막 업데이트
  - 데이터 지연/상태
- 상위 키워드 패널
  - 언급량/증가율 정렬
  - limit 변경
  - 선택 키워드 강조
- 키워드 트렌드 차트
  - 다중 시리즈 라인 차트
  - hover 툴팁
  - bucket 선택
  - 시리즈 숨김
- 급상승 키워드 타임라인
  - heatmap 형태
  - 시간 bucket 선택
- 급상승 목록 테이블
  - 키워드
  - 현재 언급량
  - 증가율
  - 이벤트 점수

### 2.5 우측 상세 패널

- 선택 키워드 요약
  - mentions
  - 증가율
  - event score
- 최근 추이 미니 차트
- 출처 분포
- 연관 키워드
  - 네트워크 뷰
  - 바 차트 뷰
- 관련 기사 목록
  - 최신순/관련도순 정렬
  - 기사 외부 링크 이동

### 2.6 용어 사전 모달

- 복합명사 사전
- 불용어 사전
- 복합명사 후보
- 등록/삭제/승인/반려 액션

## 3. 프론트 상태 모델

### 3.1 전역 수준 UI 상태

- `theme`
- `source`
- `domain`
- `range`
- `search`
- `selectedKeyword`
- `selectedBucket`
- `selectedArticle`
- `articleSort`
- `relatedView`
- `topSort`
- `topLimit`
- `hiddenSeries`
- `autoRefresh`
- `dictionaryOpen`
- `watchlist`

### 3.2 비동기 데이터 상태

- 필터 메타
- KPI
- 키워드 목록
- 트렌드 시리즈
- 스파이크 이벤트
- 연관 키워드
- 기사 목록
- 시스템 상태
- 용어 사전 데이터

## 4. 기능 정의

### 4.1 필터링

- source/domain/range가 바뀌면 메인 데이터 전체를 재조회한다.
- keyword search는 서버 검색과 typeahead 추천에 사용한다.
- 선택한 도메인은 모든 dashboard API에 공통으로 전달한다.

### 4.2 키워드 선택 흐름

- 상위 키워드 목록에서 선택
- 워치리스트에서 선택
- heatmap 셀에서 선택
- 우측 연관 키워드에서 재선택
- 검색 추천에서 선택

선택된 키워드는 다음 영역과 동기화된다.

- 키워드 트렌드
- 우측 상세 패널
- 관련 기사
- 워치리스트 active 상태

### 4.3 상호작용

- 리스트 hover/selected 상태
- 차트 hover 툴팁
- 차트 bucket click
- heatmap click
- 기사 클릭 시 선택 상태 표시
- typeahead 선택
- 워치리스트 추가/삭제
- 용어 사전 CRUD

## 5. 데이터 계약

### 5.1 Dashboard KPI

- 입력
  - source
  - domain
  - range
- 출력
  - totalArticles
  - uniqueKeywords
  - spikeCount
  - growth
  - lastUpdateRelative
  - lastUpdateAbsolute

### 5.2 Top Keywords

- 입력
  - source
  - domain
  - range
  - search
  - limit
- 출력
  - keyword
  - mentions
  - prevMentions
  - growth
  - delta
  - spike
  - eventScore
  - articleCount
  - sourceShareNaver
  - sourceShareGlobal

### 5.3 Trend Series

- 입력
  - source
  - domain
  - range
  - keyword
  - compareLimit
- 출력
  - series[]
    - name
    - color
    - spike
    - points[]

### 5.4 Spike Events

- 입력
  - source
  - domain
  - range
- 출력
  - topKeywords[]
  - events[]
  - range
  - sampleSeries[]

### 5.5 Related Keywords

- 입력
  - source
  - domain
  - range
  - keyword
- 출력
  - keyword
  - weight

### 5.6 Articles

- 입력
  - source
  - domain
  - range
  - keyword
  - sort
- 출력
  - id
  - title
  - summary
  - publisher
  - source
  - domain
  - publishedAt
  - minutesAgo
  - keywords[]
  - primaryKeyword
  - duplicates
  - url

### 5.7 Dictionary

- overview
- compound noun create/delete
- candidate approve/reject
- stopword create/delete

## 6. 프론트에서 기대하는 미구현/추가 데이터


이 항목들은 `todo.md`와 `STEP4_FastAPI_구현.md`에서 별도 계획으로 연결한다.
