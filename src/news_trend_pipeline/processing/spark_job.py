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
    lit,
    to_timestamp,
    window,
)
from pyspark.sql.functions import row_number
from pyspark.sql.types import ArrayType, StringType
from pyspark.sql.window import Window

from news_trend_pipeline.core.config import settings
from news_trend_pipeline.core.logger import get_logger
from news_trend_pipeline.core.schemas import NormalizedNewsArticle
from news_trend_pipeline.processing.preprocessing import tokenize
from news_trend_pipeline.storage.db import (
    insert_keyword_relations,
    insert_keyword_trends,
    insert_news_raw,
    safe_initialize_database,
)


logger = get_logger(__name__)


ARTICLE_SCHEMA = NormalizedNewsArticle.spark_schema()


def extract_tokens(text: str | None, provider: str | None) -> list[str]:
    return tokenize(text, provider=provider)


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
    tokenize_udf = udf(extract_tokens, ArrayType(StringType()))

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
        .withColumn("provider", coalesce(col("provider"), lit("newsapi")))
        .withColumn("event_time", to_timestamp("published_at"))
        .withColumn("article_text", expr("concat_ws(' ', title, description, content)"))
        .withColumn("tokens", tokenize_udf(col("article_text"), col("provider")))
        .dropna(subset=["event_time", "url"])
    )

    def write_to_sinks(batch_df, batch_id: int) -> None:
        if batch_df.isEmpty():
            return

        raw_rows = [
            row.asDict()
            for row in batch_df.select(
                "provider",
                "source",
                "author",
                "title",
                "description",
                "content",
                "url",
                "published_at",
                "ingested_at",
            ).collect()
        ]
        if raw_rows:
            logger.info("Persisting %s raw article rows from batch %s", len(raw_rows), batch_id)
            insert_news_raw(raw_rows)

        article_keywords = (
            batch_df.select("provider", "url", "event_time", explode(col("tokens")).alias("keyword"))
            .groupBy("provider", "url", "event_time", "keyword")
            .agg(spark_count("*").alias("keyword_count"))
        )

        keyword_trends = (
            article_keywords.groupBy(
                col("provider"),
                window(col("event_time"), settings.keyword_window_duration),
                col("keyword"),
            )
            .agg(expr("sum(keyword_count) as count"))
            .withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider",
                "window.start as window_start",
                "window.end as window_end",
                "keyword",
                "count",
                "processed_at",
            )
        )

        trend_rows = [row.asDict() for row in keyword_trends.collect()]
        if trend_rows:
            logger.info("Persisting %s keyword trend rows from batch %s", len(trend_rows), batch_id)
            insert_keyword_trends(trend_rows)

        article_window = Window.partitionBy("provider", "url", "event_time").orderBy(
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

        relation_trends = (
            relation_pairs.groupBy(
                col("provider"),
                window(col("event_time"), settings.keyword_window_duration),
                "keyword_a",
                "keyword_b",
            )
            .count()
            .withColumn("processed_at", current_timestamp())
            .selectExpr(
                "provider",
                "window.start as window_start",
                "window.end as window_end",
                "keyword_a",
                "keyword_b",
                "count",
                "processed_at",
            )
        )

        relation_rows = [row.asDict() for row in relation_trends.collect()]
        if relation_rows:
            logger.info("Persisting %s keyword relation rows from batch %s", len(relation_rows), batch_id)
            insert_keyword_relations(relation_rows)

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
