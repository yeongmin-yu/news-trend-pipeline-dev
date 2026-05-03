...REPLACE RAW STREAM BLOCK ONLY...

    raw_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap_servers)
        .option("subscribe", settings.kafka_topic)
        .option("startingOffsets", settings.spark_starting_offsets)
        .option("maxOffsetsPerTrigger", settings.spark_max_offsets_per_trigger)
        .load()
    )

...REST OF FILE UNCHANGED...
