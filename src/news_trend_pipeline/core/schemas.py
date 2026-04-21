from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_required_text(value: Any, field_name: str) -> str:
    text = _normalize_optional_text(value)
    if not text:
        raise ValueError(f"{field_name} is required")
    return text


def _normalize_timestamp(value: Any, *, field_name: str, required: bool) -> str | None:
    if value is None or value == "":
        if required:
            raise ValueError(f"{field_name} is required")
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ArticleMetadata:
    source: str
    version: str
    query: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any] | None) -> ArticleMetadata | None:
        if not payload:
            return None
        return cls(
            source=_normalize_required_text(payload.get("source"), "metadata.source"),
            version=_normalize_required_text(payload.get("version"), "metadata.version"),
            query=str(payload.get("query", "") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "version": self.version,
            "query": self.query,
        }


@dataclass(frozen=True)
class NormalizedNewsArticle:
    provider: str
    source: str | None
    author: str | None
    title: str
    description: str | None
    content: str | None
    url: str
    published_at: str | None
    ingested_at: str
    metadata: ArticleMetadata | None = None
    query: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> NormalizedNewsArticle:
        metadata = ArticleMetadata.from_dict(payload.get("metadata"))
        query = _normalize_optional_text(payload.get("_query"))
        if query is None and metadata is not None:
            query = metadata.query or None

        return cls(
            provider=_normalize_required_text(payload.get("provider", "unknown"), "provider"),
            source=_normalize_optional_text(payload.get("source")),
            author=_normalize_optional_text(payload.get("author")),
            title=_normalize_required_text(payload.get("title"), "title"),
            description=_normalize_optional_text(payload.get("description")),
            content=_normalize_optional_text(payload.get("content")),
            url=_normalize_required_text(payload.get("url"), "url"),
            published_at=_normalize_timestamp(
                payload.get("published_at"),
                field_name="published_at",
                required=False,
            ),
            ingested_at=_normalize_timestamp(
                payload.get("ingested_at"),
                field_name="ingested_at",
                required=True,
            ),
            metadata=metadata,
            query=query,
        )

    def to_dict(self, *, include_internal: bool = False, include_metadata: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "provider": self.provider,
            "source": self.source,
            "author": self.author,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "url": self.url,
            "published_at": self.published_at,
            "ingested_at": self.ingested_at,
        }
        if include_metadata and self.metadata is not None:
            payload["metadata"] = self.metadata.to_dict()
        if include_internal and self.query:
            payload["_query"] = self.query
        return payload

    def to_message(self, *, schema_version: str) -> dict[str, Any]:
        metadata = self.metadata or ArticleMetadata(
            source=self.provider,
            version=schema_version,
            query=self.query or "",
        )
        return {
            **self.to_dict(include_internal=False, include_metadata=False),
            "metadata": metadata.to_dict(),
        }

    @classmethod
    def spark_schema(cls):
        from pyspark.sql.types import StringType, StructField, StructType

        return StructType(
            [
                StructField("provider", StringType()),
                StructField("source", StringType()),
                StructField("author", StringType()),
                StructField("title", StringType()),
                StructField("description", StringType()),
                StructField("content", StringType()),
                StructField("url", StringType()),
                StructField("published_at", StringType()),
                StructField("ingested_at", StringType()),
                StructField(
                    "metadata",
                    StructType(
                        [
                            StructField("source", StringType()),
                            StructField("version", StringType()),
                            StructField("query", StringType()),
                        ]
                    ),
                ),
            ]
        )
