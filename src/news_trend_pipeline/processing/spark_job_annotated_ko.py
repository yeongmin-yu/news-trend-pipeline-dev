from __future__ import annotations

"""
spark_job.py 학습용 주석 버전

이 파일은 원본 spark_job.py와 같은 동작을 유지하면서,
Spark/Python 초보자가 흐름을 이해하기 쉽게 한글 주석을 자세히 추가한 복사본입니다.

주의:
- 실제 운영 실행은 기존 `spark_job.py`를 계속 사용하세요.
- 이 파일은 "설명용"입니다.
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import udf
from pyspark.sql.functions import (
    col,
    coalesce,
    count as spark_count,
    current_timestamp,
    expr,
    explode,
    from_json,
    to_timestamp,
    window,
)
from pyspark.sql.functions import row_number
from pyspark.sql.types import ArrayType, StringType, StructField, StructType
from pyspark.sql.window import Window

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.logger import get_logger
from news_trend_pipeline.core.schemas import NormalizedNewsArticle
from news_trend_pipeline.processing.preprocessing import tokenize
from news_trend_pipeline.storage.db import (
    safe_initialize_database,
    upsert_from_staging_keyword_relations,
    upsert_from_staging_keyword_trends,
    upsert_from_staging_keywords,
    upsert_from_staging_news_raw,
)


logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 1) Kafka JSON 메시지를 Spark DataFrame 컬럼으로 펼치기 위한 스키마
# ---------------------------------------------------------------------------
# NormalizedNewsArticle 기본 스키마 + 과거/외부 입력 호환용 필드(description, content)를 추가합니다.
# summary가 비어 있는 데이터가 들어오면 description/content를 fallback으로 쓰기 위해 넣어둡니다.
ARTICLE_SCHEMA = StructType(
    NormalizedNewsArticle.spark_schema().fields[:]
    + [
        StructField("description", StringType()),
        StructField("content", StringType()),
    ]
)


def extract_tokens(text: str | None) -> list[str]:
    """
    Spark UDF에서 호출할 래퍼 함수.

    왜 별도 함수가 필요한가?
    - Spark UDF는 "파이썬 함수"를 인자로 받아 실행합니다.
    - 전처리 로직은 preprocessing.tokenize에 있으므로 그대로 위임합니다.
    """
    return tokenize(text)


def _jdbc_write(df, table: str, jdbc_url: str, jdbc_props: dict) -> None:
    """
    DataFrame을 JDBC로 PostgreSQL 테이블에 append 저장.

    여기서 핵심:
    - mode='append' 이므로 기존 데이터에 이어 붙입니다.
    - 실제 중복 제어/병합은 이후 DB upsert 함수에서 처리합니다.
    """
    df.write.jdbc(url=jdbc_url, table=table, mode="append", properties=jdbc_props)


def build_spark_session() -> SparkSession:
    """
    SparkSession 생성.

    자주 보는 설정:
    - appName: Spark UI/로그에서 보이는 작업 이름
    - master: local[*] 또는 spark://... 형태
    - spark.sql.shuffle.partitions: groupBy/join 후 셔플 파티션 개수
    """
    return (
        SparkSession.builder.appName(settings.spark_app_name)
        .master(settings.spark_master)
        .config("spark.sql.shuffle.partitions", settings.spark_shuffle_partitions)
        .getOrCreate()
    )


def run_streaming_job() -> None:
    """
    Spark Structured Streaming 메인 진입점.

    전체 흐름 요약:
    1) Kafka에서 JSON 메시지 읽기
    2) 스키마 파싱 + 전처리(tokenize)
    3) foreachBatch에서 배치 단위 저장
       - news_raw 저장
       - keywords 저장
       - keyword_trends(윈도우 집계) 저장
       - keyword_relations(연관 키워드) 저장
    """
    spark = build_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    # DB 테이블/인덱스가 없으면 초기화 시도 (실패해도 워닝만 남기고 계속 진행)
    safe_initialize_database()

    # tokenize 함수(파이썬)를 Spark UDF로 등록
    tokenize_udf = udf(extract_tokens, ArrayType(StringType()))

    # Spark -> PostgreSQL 연결 정보
    jdbc_url = settings.spark_jdbc_url
    jdbc_props = {
        "user": settings.postgres_user,
        "password": settings.postgres_password,
        "driver": "org.postgresql.Driver",
    }

    # -----------------------------------------------------------------------
    # 2) Kafka 스트림 읽기
    # -----------------------------------------------------------------------
    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.kafka_topic)
        .option("startingOffsets", settings.spark_starting_offsets)
        .load()
    )

    # -----------------------------------------------------------------------
    # 3) Kafka value(JSON 문자열) -> 컬럼 파싱 + 전처리용 컬럼 생성
    # -----------------------------------------------------------------------
    parsed = (
        raw_stream.selectExpr("CAST(value AS STRING) AS json_string")
        .select(from_json(col("json_string"), ARTICLE_SCHEMA).alias("data"))
        .select("data.*")
        # summary가 없을 수 있으므로 description/content 순으로 대체
        .withColumn("summary", coalesce(col("summary"), col("description"), col("content")))
        .withColumn("published_at", to_timestamp("published_at"))
        .withColumn("ingested_at", to_timestamp("ingested_at"))
        # 집계 기준 이벤트 시간은 published_at
        .withColumn("event_time", col("published_at"))
        # 제목 + 요약을 합쳐서 토큰화 입력 텍스트 생성
        .withColumn("article_text", expr("concat_ws(' ', title, summary)"))
        .withColumn("tokens", tokenize_udf(col("article_text")))
        # 최소 필수값이 없는 레코드는 제외
        .dropna(subset=["event_time", "url"])
    )

    def write_to_sinks(batch_df, batch_id: int) -> None:
        """
        foreachBatch 콜백 함수.

        Structured Streaming은 내부적으로 micro-batch를 만들고,
        각 배치마다 이 함수를 호출합니다.
        """
        if batch_df.isEmpty():
            return

        logger.info("Processing batch %s", batch_id)

        # -------------------------------------------------------------------
        # A) 원문 기사(news_raw) 저장
        # -------------------------------------------------------------------
        _jdbc_write(
            batch_df.select("provider", "source", "title", "summary", "url", "published_at", "ingested_at"),
            "stg_news_raw", jdbc_url, jdbc_props,
        )
        upsert_from_staging_news_raw()

        # -------------------------------------------------------------------
        # B) 기사별 키워드 빈도(article_keywords) 계산
        # -------------------------------------------------------------------
        # tokens 배열을 explode로 행으로 펼친 뒤, 기사 단위로 count
        article_keywords = (
            batch_df.select("provider", "url", "event_time", explode(col("tokens")).alias("keyword"))
            .groupBy("provider", "url", "event_time", "keyword")
            .agg(spark_count("*").alias("keyword_count"))
        )

        # keywords (기사 단위 키워드 카운트) 저장
        _jdbc_write(
            article_keywords.withColumn("processed_at", current_timestamp())
            .selectExpr("provider as article_provider", "url as article_url", "keyword", "keyword_count", "processed_at"),
            "stg_keywords", jdbc_url, jdbc_props,
        )
        upsert_from_staging_keywords()

        # -------------------------------------------------------------------
        # C) 키워드 트렌드(keyword_trends) 집계
        # -------------------------------------------------------------------
        # event_time 기준 10분(기본값) 윈도우로 provider+keyword 합산
        keyword_trends = (
            article_keywords.groupBy(
                col("provider"),
                window(col("event_time"), settings.keyword_window_duration),
                col("keyword"),
            )
            .agg(expr("sum(keyword_count) as keyword_count"))
            .withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider",
                "window.start as window_start",
                "window.end as window_end",
                "keyword",
                "keyword_count",
                "processed_at",
            )
        )
        _jdbc_write(keyword_trends, "stg_keyword_trends", jdbc_url, jdbc_props)
        upsert_from_staging_keyword_trends()

        # -------------------------------------------------------------------
        # D) 연관 키워드(keyword_relations) 집계
        # -------------------------------------------------------------------
        # 1) 기사별 상위 키워드 N개(기본 8개)를 고릅니다.
        #    - keyword_count 내림차순
        #    - 동률이면 keyword 오름차순
        article_window = Window.partitionBy("provider", "url", "event_time").orderBy(
            col("keyword_count").desc(),
            col("keyword").asc(),
        )
        representative_keywords = (
            article_keywords.withColumn("keyword_rank", row_number().over(article_window))
            .filter(col("keyword_rank") <= settings.relation_keyword_limit)
        )

        # 2) self join으로 같은 기사 안 키워드 쌍을 만듭니다.
        #    keyword_rank < keyword_rank 조건으로 중복(A,B)/(B,A) 제거
        left = representative_keywords.alias("left")
        right = representative_keywords.alias("right")
        relation_pairs = (
            left.join(
                right,
                (col("left.provider") == col("right.provider"))
                & (col("left.url") == col("right.url"))
                & (col("left.event_time") == col("right.event_time"))
                & (col("left.keyword_rank") < col("right.keyword_rank")),
            )
            .select(
                col("left.provider").alias("provider"),
                col("left.event_time").alias("event_time"),
                col("left.keyword").alias("keyword_a"),
                col("right.keyword").alias("keyword_b"),
            )
        )

        # 3) 윈도우 단위로 키워드 쌍 동시출현 횟수(cooccurrence_count) 집계
        relation_trends = (
            relation_pairs.groupBy(
                col("provider"),
                window(col("event_time"), settings.keyword_window_duration),
                "keyword_a",
                "keyword_b",
            )
            .agg(spark_count("*").alias("cooccurrence_count"))
            .withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider",
                "window.start as window_start",
                "window.end as window_end",
                "keyword_a",
                "keyword_b",
                "cooccurrence_count",
                "processed_at",
            )
        )
        _jdbc_write(relation_trends, "stg_keyword_relations", jdbc_url, jdbc_props)
        upsert_from_staging_keyword_relations()

    # -----------------------------------------------------------------------
    # 4) 스트리밍 쿼리 실행
    # -----------------------------------------------------------------------
    query = (
        parsed.writeStream.outputMode("append")
        .foreachBatch(write_to_sinks)
        .option("checkpointLocation", settings.spark_checkpoint_dir)
        .start()
    )
    logger.info("Spark streaming job started")
    query.awaitTermination()


if __name__ == "__main__":
    run_streaming_job()

