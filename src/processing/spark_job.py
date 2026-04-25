from __future__ import annotations

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
    safe_initialize_database,
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


def _jdbc_write(df, table: str, jdbc_url: str, jdbc_props: dict) -> None:
    df.write.jdbc(url=jdbc_url, table=table, mode="append", properties=jdbc_props)


def build_spark_session() -> SparkSession:
    return (
        SparkSession.builder.appName(settings.spark_app_name)
        .master(settings.spark_master)
        .config("spark.sql.shuffle.partitions", settings.spark_shuffle_partitions)
        .getOrCreate()
    )


def run_streaming_job() -> None:
    spark = build_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    safe_initialize_database()
    tokenize_udf = udf(extract_tokens, ArrayType(StringType())).asNondeterministic()

    jdbc_url = settings.spark_jdbc_url
    jdbc_props = {
        "user": settings.postgres_user,
        "password": settings.postgres_password,
        "driver": "org.postgresql.Driver",
    }

    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.kafka_topic)
        .option("startingOffsets", settings.spark_starting_offsets)
        .load()
    )

    parsed = (
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
        .withColumn("article_text", expr("concat_ws(' ', title, summary)"))
        .withColumn("tokens", tokenize_udf(col("article_text"), col("domain")))
        .dropna(subset=["event_time", "url"])
    )

    def write_to_sinks(batch_df, batch_id: int) -> None:
        if batch_df.isEmpty():
            return

        logger.info("Processing batch %s", batch_id)

        # news_raw
        _jdbc_write(
            batch_df.select("provider", "domain", "query", "source", "title", "summary", "url", "published_at", "ingested_at"),
            "stg_news_raw", jdbc_url, jdbc_props,
        )
        upsert_from_staging_news_raw()

        article_keywords = (
            batch_df.select("provider", "domain", "url", "event_time", explode(col("tokens")).alias("keyword"))
            .groupBy("provider", "domain", "url", "event_time", "keyword")
            .agg(spark_count("*").alias("keyword_count"))
        )

        # keywords (per-article)
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
        upsert_from_staging_keywords()

        # keyword_trends (windowed aggregation)
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
        _jdbc_write(keyword_trends, "stg_keyword_trends", jdbc_url, jdbc_props)
        upsert_from_staging_keyword_trends()

        # keyword_relations (co-occurrence pairs)
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
        _jdbc_write(relation_trends, "stg_keyword_relations", jdbc_url, jdbc_props)
        upsert_from_staging_keyword_relations()

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
