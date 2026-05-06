from __future__ import annotations

from time import monotonic

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

from core.config import settings
from core.logger import get_logger
from core.schemas import NormalizedNewsArticle
from processing.preprocessing import tokenize
from storage.db import (
    upsert_from_staging_keyword_relations,
    upsert_from_staging_keyword_trends,
    upsert_from_staging_keywords,
    upsert_from_staging_news_raw,
)


logger = get_logger(__name__)


ARTICLE_SCHEMA = StructType(
    NormalizedNewsArticle.spark_schema().fields[:]
    + [
        StructField("description", StringType()),
        StructField("content", StringType()),
    ]
)


def extract_tokens(text: str | None, domain: str | None = None) -> list[str]:
    return tokenize(text, domain or "all")


def _with_pg_batch_rewrite(jdbc_url: str) -> str:
    if "reWriteBatchedInserts=" in jdbc_url:
        return jdbc_url
    separator = "&" if "?" in jdbc_url else "?"
    return f"{jdbc_url}{separator}reWriteBatchedInserts=true"


def _jdbc_write(df, table: str, jdbc_url: str, jdbc_props: dict) -> None:
    writer_df = df
    if settings.spark_jdbc_num_partitions > 0:
        writer_df = df.repartition(settings.spark_jdbc_num_partitions)

    writer_df.write.jdbc(
        url=_with_pg_batch_rewrite(jdbc_url),
        table=table,
        mode="append",
        properties={**jdbc_props, "batchsize": str(settings.spark_jdbc_batch_size)},
    )


def _log_batch_step(batch_id: int, step: str, started_at: float) -> None:
    logger.info(
        "Spark batch step finished: batch_id=%s step=%s elapsed=%.2fs",
        batch_id,
        step,
        monotonic() - started_at,
    )


def build_spark_session() -> SparkSession:
    builder = (
        SparkSession.builder.appName(settings.spark_app_name)
        .master(settings.spark_master)
        .config("spark.sql.shuffle.partitions", settings.spark_shuffle_partitions)
    )

    builder = builder.config("spark.driver.bindAddress", settings.spark_driver_bind_address)
    if settings.spark_driver_host:
        builder = builder.config("spark.driver.host", settings.spark_driver_host)
    if settings.spark_driver_port:
        builder = builder.config("spark.driver.port", settings.spark_driver_port)
    if settings.spark_block_manager_port:
        builder = builder.config("spark.blockManager.port", settings.spark_block_manager_port)

    builder = builder.config("spark.ui.port", settings.spark_ui_port)

    if settings.spark_event_log_enabled:
        builder = (
            builder.config("spark.eventLog.enabled", "true")
            .config("spark.eventLog.dir", settings.spark_event_log_dir)
        )

    return builder.getOrCreate()


def run_streaming_job() -> None:
    spark = build_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    tokenize_udf = udf(extract_tokens, ArrayType(StringType())).asNondeterministic()

    jdbc_url = settings.spark_jdbc_url
    jdbc_props = {
        "user": settings.postgres_user,
        "password": settings.postgres_password,
        "driver": "org.postgresql.Driver",
    }

    stream_reader = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.kafka_topic)
        .option("startingOffsets", settings.spark_starting_offsets)
    )
    if settings.spark_max_offsets_per_trigger > 0:
        stream_reader = stream_reader.option(
            "maxOffsetsPerTrigger",
            settings.spark_max_offsets_per_trigger,
        )
    raw_stream = stream_reader.load()

    parsed_base = (
        raw_stream.selectExpr("CAST(value AS STRING) AS json_string")
        .select(from_json(col("json_string"), ARTICLE_SCHEMA).alias("data"))
        .select("data.*")
        .withColumn("provider", coalesce(col("provider"), expr("'naver'")))
        .withColumn("domain", coalesce(col("domain"), expr("'ai_tech'")))
        .withColumn("query", col("metadata.query"))
        .withColumn("summary", coalesce(col("summary"), col("description"), col("content")))
        .withColumn("published_at", to_timestamp("published_at"))
        .withColumn("ingested_at", to_timestamp("ingested_at"))
        .withColumn("event_time", col("published_at"))
        .withColumn(
            "article_text",
            expr(
                """
                CASE
                  WHEN summary IS NULL OR trim(summary) = '' THEN title
                  WHEN summary = title THEN title
                  ELSE concat_ws(' ', title, summary)
                END
                """
            ),
        )
        .dropna(subset=["event_time", "url"])
    )
    if settings.spark_preprocess_partitions > 0:
        parsed_base = parsed_base.repartition(settings.spark_preprocess_partitions)
    parsed = parsed_base.withColumn("tokens", tokenize_udf(col("article_text"), col("domain")))

    def write_to_sinks(batch_df, batch_id: int) -> None:
        if batch_df.isEmpty():
            logger.info("Spark batch skipped: batch_id=%s reason=empty", batch_id)
            return

        batch_started_at = monotonic()
        logger.info("Spark batch started: batch_id=%s", batch_id)

        step_started_at = monotonic()
        _jdbc_write(
            batch_df.select("provider", "domain", "query", "source", "title", "summary", "url", "published_at", "ingested_at"),
            "stg_news_raw", jdbc_url, jdbc_props,
        )
        _log_batch_step(batch_id, "write_stg_news_raw", step_started_at)
        step_started_at = monotonic()
        upsert_from_staging_news_raw()
        _log_batch_step(batch_id, "upsert_news_raw", step_started_at)

        step_started_at = monotonic()
        article_keywords = (
            batch_df.select("provider", "domain", "url", "event_time", explode(col("tokens")).alias("keyword"))
            .filter(col("keyword").isNotNull())
            .filter(expr("length(keyword) >= 2"))
            .groupBy("provider", "domain", "url", "event_time", "keyword")
            .agg(spark_count("*").alias("keyword_count"))
        )
        _log_batch_step(batch_id, "build_article_keywords", step_started_at)

        step_started_at = monotonic()
        _jdbc_write(
            article_keywords.withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider as article_provider",
                "domain as article_domain",
                "url as article_url",
                "keyword",
                "keyword_count",
                "processed_at",
            ),
            "stg_keywords", jdbc_url, jdbc_props,
        )
        _log_batch_step(batch_id, "write_stg_keywords", step_started_at)
        step_started_at = monotonic()
        upsert_from_staging_keywords()
        _log_batch_step(batch_id, "upsert_keywords", step_started_at)

        step_started_at = monotonic()
        keyword_trends = (
            article_keywords.groupBy(
                col("provider"),
                col("domain"),
                window(col("event_time"), settings.keyword_window_duration),
                col("keyword"),
            )
            .agg(expr("sum(keyword_count) as keyword_count"))
            .withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider",
                "domain",
                "window.start as window_start",
                "window.end as window_end",
                "keyword",
                "keyword_count",
                "processed_at",
            )
        )
        _log_batch_step(batch_id, "build_keyword_trends", step_started_at)
        step_started_at = monotonic()
        _jdbc_write(keyword_trends, "stg_keyword_trends", jdbc_url, jdbc_props)
        _log_batch_step(batch_id, "write_stg_keyword_trends", step_started_at)
        step_started_at = monotonic()
        upsert_from_staging_keyword_trends()
        _log_batch_step(batch_id, "upsert_keyword_trends", step_started_at)

        step_started_at = monotonic()
        article_window = Window.partitionBy("provider", "domain", "url", "event_time").orderBy(
            col("keyword_count").desc(),
            col("keyword").asc(),
        )
        representative_keywords = (
            article_keywords.withColumn("keyword_rank", row_number().over(article_window))
            .filter(col("keyword_rank") <= settings.relation_keyword_limit)
        )
        left = representative_keywords.alias("left")
        right = representative_keywords.alias("right")
        relation_pairs = (
            left.join(
                right,
                (col("left.provider") == col("right.provider"))
                & (col("left.domain") == col("right.domain"))
                & (col("left.url") == col("right.url"))
                & (col("left.event_time") == col("right.event_time"))
                & (col("left.keyword_rank") < col("right.keyword_rank")),
            )
            .select(
                col("left.provider").alias("provider"),
                col("left.domain").alias("domain"),
                col("left.event_time").alias("event_time"),
                col("left.keyword").alias("keyword_a"),
                col("right.keyword").alias("keyword_b"),
            )
        )
        relation_trends = (
            relation_pairs.groupBy(
                col("provider"),
                col("domain"),
                window(col("event_time"), settings.keyword_window_duration),
                "keyword_a",
                "keyword_b",
            )
            .agg(spark_count("*").alias("cooccurrence_count"))
            .withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider",
                "domain",
                "window.start as window_start",
                "window.end as window_end",
                "keyword_a",
                "keyword_b",
                "cooccurrence_count",
                "processed_at",
            )
        )
        _log_batch_step(batch_id, "build_keyword_relations", step_started_at)
        step_started_at = monotonic()
        _jdbc_write(relation_trends, "stg_keyword_relations", jdbc_url, jdbc_props)
        _log_batch_step(batch_id, "write_stg_keyword_relations", step_started_at)
        step_started_at = monotonic()
        upsert_from_staging_keyword_relations()
        _log_batch_step(batch_id, "upsert_keyword_relations", step_started_at)
        logger.info(
            "Spark batch finished: batch_id=%s elapsed=%.2fs",
            batch_id,
            monotonic() - batch_started_at,
        )

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
