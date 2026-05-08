export type PipelineNodeId = "airflow" | "kafka" | "spark" | "db";

export interface AirflowDag {
  id: string;
  name: string;
  schedule: string;
  lastRun: string;
  duration: string;
  status: "success" | "running" | "failed";
  runs: number[];
}

export interface KafkaTopic {
  name: string;
  partitions: number;
  replication: number;
  retentionHr: number;
  lag: number;
  msgRate: number;
  sizeGB: number;
  offsetNewest: number;
  status: "healthy" | "lag" | "warn";
}

export interface SparkJob {
  id: string;
  app: string;
  worker: string;
  startedAt: string;
  duration: string;
  stage: string;
  tasks: string;
  shuffle: string;
  status: "succeeded" | "running" | "failed";
}

export interface SparkWorker {
  id: string;
  host: string;
  cores: number;
  coresUsed: number;
  memGB: number;
  memUsedGB: number;
  jobs: number;
  status: "alive" | "busy";
}

export interface DbTable {
  name: string;
  rows: number;
  sizeGB: number;
  lastWrite: string;
  writeRate: number;
  status: "ok" | "warn";
}

export type PipelineNodeMeta =
  | { kind: "airflow"; dags: number; running: number; failed: number; success: number; nextIn: string; status: string }
  | { kind: "kafka"; topics: number; totalLag: number; msgRate: number; sizeGB: number; status: string }
  | { kind: "spark"; workers: number; running: number; failed: number; coreUsed: number; coreMax: number; status: string }
  | { kind: "db"; tables: number; totalGB: number; writeRate: number; status: string };

export interface PipelineNodeDef {
  id: PipelineNodeId;
  label: string;
  sub: string;
  meta: PipelineNodeMeta;
  color: string;
  icon: string;
}

export interface PipelineEdgeDef {
  from: PipelineNodeId;
  to: PipelineNodeId;
  label: string;
  rate: string;
  latency: string;
  color: string;
}

export const AIRFLOW_DAGS: AirflowDag[] = [
  { id: "ntp_news_ingest",     name: "news_ingest",        schedule: "*/5 * * * *",  lastRun: "2026-05-08 14:40", duration: "00:01:12", status: "success", runs: [1,1,1,1,1,1,1,0,1,1,1,1,1,1,1,1,1,1,0,1] },
  { id: "ntp_keyword_extract", name: "keyword_extract",    schedule: "*/10 * * * *", lastRun: "2026-05-08 14:40", duration: "00:02:44", status: "success", runs: [1,1,1,0,1,1,1,1,1,1,1,1,1,0,1,1,1,1,1,1] },
  { id: "ntp_trend_aggregate", name: "trend_aggregate",    schedule: "*/10 * * * *", lastRun: "2026-05-08 14:30", duration: "00:03:18", status: "running", runs: [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,2] },
  { id: "ntp_related_build",   name: "related_kw_build",   schedule: "0 * * * *",    lastRun: "2026-05-08 14:00", duration: "00:05:02", status: "success", runs: [1,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
  { id: "ntp_spike_detect",    name: "spike_detect",       schedule: "*/5 * * * *",  lastRun: "2026-05-08 14:40", duration: "00:00:48", status: "success", runs: [1,1,1,1,1,1,1,1,1,1,1,1,0,1,1,1,1,1,1,1] },
  { id: "ntp_dedup",           name: "article_dedup",      schedule: "*/15 * * * *", lastRun: "2026-05-08 14:30", duration: "00:01:55", status: "success", runs: [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
  { id: "ntp_dict_reindex",    name: "dict_reindex",       schedule: "0 3 * * *",    lastRun: "2026-05-08 03:00", duration: "00:12:31", status: "success", runs: [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
  { id: "ntp_report_daily",    name: "daily_report",       schedule: "0 8 * * *",    lastRun: "2026-05-08 08:00", duration: "00:04:10", status: "failed",  runs: [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,0] },
  { id: "ntp_cleanup",         name: "storage_cleanup",    schedule: "0 2 * * *",    lastRun: "2026-05-08 02:00", duration: "00:08:22", status: "success", runs: [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
  { id: "ntp_model_eval",      name: "model_eval",         schedule: "0 6 * * *",    lastRun: "2026-05-08 06:00", duration: "00:18:44", status: "success", runs: [1,1,0,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1] },
];

export const KAFKA_TOPICS: KafkaTopic[] = [
  { name: "ntp.raw.naver",       partitions: 12, replication: 3, retentionHr: 72,  lag: 142,  msgRate: 1840, sizeGB: 18.4, offsetNewest: 48291002, status: "healthy" },
  { name: "ntp.raw.global",      partitions: 8,  replication: 3, retentionHr: 72,  lag: 88,   msgRate: 1210, sizeGB: 12.1, offsetNewest: 31204400, status: "healthy" },
  { name: "ntp.parsed.articles", partitions: 12, replication: 3, retentionHr: 48,  lag: 0,    msgRate: 2980, sizeGB: 24.8, offsetNewest: 78210001, status: "healthy" },
  { name: "ntp.keywords.raw",    partitions: 6,  replication: 3, retentionHr: 24,  lag: 2841, msgRate: 4120, sizeGB: 8.2,  offsetNewest: 22100440, status: "lag"     },
  { name: "ntp.keywords.agg",    partitions: 6,  replication: 3, retentionHr: 168, lag: 0,    msgRate: 320,  sizeGB: 4.4,  offsetNewest: 9812001,  status: "healthy" },
  { name: "ntp.spikes",          partitions: 4,  replication: 3, retentionHr: 168, lag: 0,    msgRate: 48,   sizeGB: 0.8,  offsetNewest: 1280041,  status: "healthy" },
  { name: "ntp.related",         partitions: 4,  replication: 3, retentionHr: 168, lag: 0,    msgRate: 14,   sizeGB: 0.3,  offsetNewest: 420088,   status: "healthy" },
  { name: "ntp.dlq",             partitions: 3,  replication: 3, retentionHr: 168, lag: 18,   msgRate: 2,    sizeGB: 0.1,  offsetNewest: 18812,    status: "warn"    },
];

export const SPARK_JOBS: SparkJob[] = [
  { id: "job-4812", app: "keyword-extractor",  worker: "worker-01", startedAt: "14:39:02", duration: "00:01:14", stage: "4/4", tasks: "320/320", shuffle: "2.1 GB",  status: "succeeded" },
  { id: "job-4811", app: "trend-aggregator",   worker: "worker-02", startedAt: "14:29:10", duration: "running",  stage: "2/5", tasks: "180/320", shuffle: "0.8 GB",  status: "running"   },
  { id: "job-4810", app: "spike-detector",     worker: "worker-03", startedAt: "14:39:08", duration: "00:00:44", stage: "2/2", tasks: "64/64",   shuffle: "0.4 GB",  status: "succeeded" },
  { id: "job-4809", app: "article-dedup",      worker: "worker-01", startedAt: "14:28:55", duration: "00:01:58", stage: "3/3", tasks: "128/128", shuffle: "1.2 GB",  status: "succeeded" },
  { id: "job-4808", app: "related-kw-builder", worker: "worker-04", startedAt: "13:59:12", duration: "00:05:04", stage: "6/6", tasks: "512/512", shuffle: "5.8 GB",  status: "succeeded" },
  { id: "job-4807", app: "keyword-extractor",  worker: "worker-02", startedAt: "14:29:01", duration: "00:01:18", stage: "4/4", tasks: "320/320", shuffle: "2.0 GB",  status: "succeeded" },
  { id: "job-4806", app: "daily-report",       worker: "worker-03", startedAt: "08:00:04", duration: "00:04:10", stage: "2/6", tasks: "80/320",  shuffle: "0.3 GB",  status: "failed"    },
  { id: "job-4805", app: "trend-aggregator",   worker: "worker-04", startedAt: "14:19:08", duration: "00:03:22", stage: "5/5", tasks: "320/320", shuffle: "2.9 GB",  status: "succeeded" },
  { id: "job-4804", app: "spike-detector",     worker: "worker-01", startedAt: "14:34:11", duration: "00:00:51", stage: "2/2", tasks: "64/64",   shuffle: "0.4 GB",  status: "succeeded" },
  { id: "job-4803", app: "model-eval",         worker: "worker-02", startedAt: "06:00:01", duration: "00:18:44", stage: "8/8", tasks: "640/640", shuffle: "12.4 GB", status: "succeeded" },
  { id: "job-4802", app: "article-dedup",      worker: "worker-03", startedAt: "14:13:44", duration: "00:02:01", stage: "3/3", tasks: "128/128", shuffle: "1.1 GB",  status: "succeeded" },
  { id: "job-4801", app: "keyword-extractor",  worker: "worker-04", startedAt: "14:19:00", duration: "00:01:22", stage: "4/4", tasks: "320/320", shuffle: "2.2 GB",  status: "succeeded" },
];

export const SPARK_WORKERS: SparkWorker[] = [
  { id: "worker-01", host: "10.0.1.11", cores: 16, coresUsed: 8,  memGB: 64, memUsedGB: 28.4, jobs: 312, status: "alive" },
  { id: "worker-02", host: "10.0.1.12", cores: 16, coresUsed: 12, memGB: 64, memUsedGB: 44.1, jobs: 298, status: "alive" },
  { id: "worker-03", host: "10.0.1.13", cores: 16, coresUsed: 4,  memGB: 64, memUsedGB: 18.2, jobs: 305, status: "alive" },
  { id: "worker-04", host: "10.0.1.14", cores: 16, coresUsed: 16, memGB: 64, memUsedGB: 58.8, jobs: 287, status: "busy"  },
];

export const DB_TABLES: DbTable[] = [
  { name: "kw_mentions",     rows: 48291002, sizeGB: 22.4, lastWrite: "14:42:01", writeRate: 1840, status: "ok"   },
  { name: "kw_trends",       rows: 12840100, sizeGB: 8.1,  lastWrite: "14:40:10", writeRate: 320,  status: "ok"   },
  { name: "kw_related",      rows:  4200880, sizeGB: 3.2,  lastWrite: "14:00:04", writeRate: 14,   status: "ok"   },
  { name: "spike_events",    rows:   128044, sizeGB: 0.4,  lastWrite: "14:42:08", writeRate: 48,   status: "ok"   },
  { name: "articles_parsed", rows: 78210001, sizeGB: 54.8, lastWrite: "14:41:55", writeRate: 2980, status: "ok"   },
  { name: "articles_dedup",  rows: 71204100, sizeGB: 48.2, lastWrite: "14:41:55", writeRate: 2820, status: "ok"   },
  { name: "dict_compound",   rows:       10, sizeGB: 0.0,  lastWrite: "14:10:00", writeRate: 0,    status: "ok"   },
  { name: "dict_stopword",   rows:       12, sizeGB: 0.0,  lastWrite: "14:10:00", writeRate: 0,    status: "ok"   },
  { name: "pipeline_log",    rows:  1820044, sizeGB: 1.8,  lastWrite: "14:42:08", writeRate: 12,   status: "ok"   },
  { name: "dead_letter",     rows:      188, sizeGB: 0.0,  lastWrite: "13:55:00", writeRate: 0,    status: "warn" },
];

export function statusVar(s: string): string {
  if (s === "ok") return "var(--up)";
  if (s === "warn") return "var(--warn)";
  return "var(--down)";
}
