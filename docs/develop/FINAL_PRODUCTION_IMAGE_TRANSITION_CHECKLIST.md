# Final Production Image Transition Checklist

개발 단계에서는 `docker-compose.yml`에서 필요한 폴더만 bind mount 하도록 구성해 두었다.
운영 단계로 전환할 때는 이미지가 자기완결적으로 동작하도록 `COPY` 중심 구조로 바꾸는 것을 권장한다.

이 문서는 최종 단계에서 점검하거나 조치해야 할 항목을 모아둔 체크리스트다.

## 목적

- 개발 편의용 bind mount 의존성 제거
- 이미지 태그만으로 실행 코드 버전 고정
- 운영 환경 재현성 향상
- 호스트 파일 상태에 따른 오동작 가능성 축소

## 현재 개발용 마운트 전략

현재 compose는 전체 프로젝트를 mount 하지 않고, 서비스별 필요한 경로만 mount 한다.

- Airflow
  - `./src -> /opt/news-trend-pipeline/src`
  - `./runtime/state -> /opt/news-trend-pipeline/runtime/state`
  - `./airflow/dags -> /opt/airflow/dags`
  - `./runtime/logs -> /opt/airflow/logs`
  - `./infra/airflow/config -> /opt/airflow/config`
  - `./infra/airflow/plugins -> /opt/airflow/plugins`
- Spark
  - `./src -> /opt/news-trend-pipeline/src`
  - `./scripts -> /opt/news-trend-pipeline/scripts`
  - `./runtime/checkpoints -> /opt/news-trend-pipeline/runtime/checkpoints`
  - `./runtime/spark-events -> /tmp/spark-events`

이 구성은 개발 중 코드 변경을 빠르게 반영하기 위한 것이다.

## 운영 전환 시 해야 할 일

### 1. Airflow 이미지에 앱 코드 포함

현재 `infra/airflow/Dockerfile.airflow`는 requirements만 설치하고 앱 코드는 이미지에 넣지 않는다.
운영 전환 시 아래 경로를 이미지에 포함해야 한다.

- `src/`
- 필요 시 `scripts/`

권장 방향:

- `COPY src /opt/news-trend-pipeline/src`
- 필요 시 `COPY scripts /opt/news-trend-pipeline/scripts`

Airflow DAG 자체는 계속 별도 mount 할지, 이미지에 포함할지 결정이 필요하다.

권장안:

- 운영에서는 DAG도 이미지에 포함하거나, 배포 파이프라인에서 별도 artifact로 관리

### 2. Spark 이미지에 개발용 mount 의존 제거

현재 `infra/spark/Dockerfile.spark`는 이미 프로젝트 전체를 `COPY`하고 있다.
운영 전환 시 compose에서 아래 개발용 mount 를 제거하는 방향이 적절하다.

- `./src:/opt/news-trend-pipeline/src`
- `./scripts:/opt/news-trend-pipeline/scripts`

Spark는 이미지 내부 코드만 사용하고, runtime 데이터 디렉터리만 외부에 남기는 구성이 권장된다.

### 3. runtime 디렉터리만 외부 유지

운영에서 외부 보존이 필요한 것은 코드가 아니라 런타임 산출물이다.

보존 대상:

- `runtime/state`
- `runtime/checkpoints`
- `runtime/logs`
- `runtime/spark-events`

운영에서는 bind mount 대신 named volume 또는 명시적 영속 스토리지를 검토한다.

### 4. compose에서 제거 또는 유지할 mount 정리

운영 전환 시 제거 후보:

- Airflow의 `src` bind mount
- Spark의 `src` bind mount
- Spark의 `scripts` bind mount

운영에서 유지 후보:

- Airflow logs
- runtime/state
- runtime/checkpoints
- runtime/spark-events

### 5. Airflow init 권한 처리 재점검

현재 `airflow-init`은 bind mount 된 디렉터리 기준으로 `mkdir`/`chown` 한다.
운영에서 mount 구성이 바뀌면 아래 항목을 다시 맞춰야 한다.

- `mkdir -p` 대상 경로
- `chown` 대상 경로
- 실행 유저 권한

특히 bind mount가 줄어들면 `/opt/news-trend-pipeline` 전체에 대한 권한 조정은 불필요할 수 있다.

### 6. 문서 경로와 예제 명령 정리

운영 전환 시 아래 문서/예제에서 host mount 전제를 제거해야 한다.

- `README.md`
- `docs/STEP1_KAFKA.md`
- `docs/STEP1_KAFKA_2.md`
- `docs/DISASTER_RECOVERY.md`
- 기타 `/opt/news-trend-pipeline/...` 직접 경로 예시

특히 subprocess 실행 예제가 이미지 포함 구조와 맞는지 확인한다.

### 7. 빌드/배포 기준 확정

운영 전환 전에 아래 정책을 결정한다.

- 이미지 태그 정책
- 배포 시점의 DAG 배포 방식
- 환경변수 주입 방식
- 런타임 데이터 백업 정책
- 롤백 기준

## 권장 최종 운영 구조

### Airflow

- 이미지에 `src` 포함
- 필요 시 `scripts` 포함
- DAG는 이미지 포함 또는 별도 배포 artifact
- 외부 mount 또는 volume은 logs/state 위주만 유지

### Spark

- 이미지에 `src`, `scripts` 포함
- 외부 mount 또는 volume은 checkpoints/spark-events 위주만 유지

## 최종 전환 전 체크 항목

- Airflow 컨테이너가 host `src` 없이도 DAG import 가능한가
- replay 관련 task가 host `scripts` 없이도 정상 실행되는가
- spark-streaming이 host `src` 없이도 정상 집계되는가
- checkpoint 복구가 volume 기준으로 유지되는가
- dead letter/state 파일이 운영 보존 정책에 맞게 백업되는가
- compose에서 개발용 bind mount 제거 후도 전체 파이프라인이 동작하는가

## 메모

개발 단계에서는 빠른 반복이 중요하므로 bind mount 전략이 맞다.
다만 운영 전환 직전에는 반드시 mount 의존을 제거하고, 이미지 단독 실행 기준으로 한 번 전체 검증하는 단계를 둬야 한다.
