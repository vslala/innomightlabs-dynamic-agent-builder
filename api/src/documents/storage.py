"""The documents bucket: a document's original and everything read from it, under one prefix per document.

    {prefix}original/{filename}
    {prefix}document.md
    {prefix}structured.json      (Docling)
    {prefix}outline.json         (headings, pages with little text, tables)
    {prefix}tables/{n}.csv       (1-based, in reading order)
    {prefix}pages/{n}.md, {n}.png
"""

import csv
import io
import json
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from src.config import settings
from src.documents.models import Document, ParsedDocument
from src.documents.outline import describe_reading

#: Everything under a prefix except the original: what a new reading replaces.
READING_PARTS = ("document.md", "structured.json", "outline.json", "tables/", "pages/")


class DocumentStorage:
    def __init__(self, s3_client: Any = None) -> None:
        self.bucket = settings.documents_bucket
        self.client = s3_client or boto3.client("s3", region_name=settings.documents_region)

    def put_original(self, document: Document, data: bytes) -> None:
        self._put(document.original_key, data, document.content_type or "application/octet-stream")

    def original(self, document: Document) -> bytes:
        data = self._get(document.original_key)
        if data is None:
            raise FileNotFoundError(f"The original of document {document.document_id} is missing")
        return data

    def put_reading(self, document: Document, reading: ParsedDocument) -> None:
        """Replace the previous reading (a re-parse can have fewer tables or pages) with this one."""
        for part in READING_PARTS:
            self._delete_prefix(document.prefix + part)
        self._put(f"{document.prefix}document.md", reading.markdown.encode(), "text/markdown; charset=utf-8")
        self._put(f"{document.prefix}outline.json", json.dumps(describe_reading(reading)).encode(), "application/json")
        if reading.structured is not None:
            self._put(f"{document.prefix}structured.json", json.dumps(reading.structured).encode(), "application/json")
        for number, table in enumerate(reading.tables, start=1):
            buffer = io.StringIO()
            csv.writer(buffer).writerows(table.rows)
            self._put(f"{document.prefix}tables/{number}.csv", buffer.getvalue().encode(), "text/csv; charset=utf-8")
        for page in reading.pages:
            self._put(f"{document.prefix}pages/{page.number}.md", page.markdown.encode(), "text/markdown; charset=utf-8")
            if page.image:
                self._put(f"{document.prefix}pages/{page.number}.png", page.image, "image/png")

    def markdown(self, document: Document) -> str:
        return (self._get(f"{document.prefix}document.md") or b"").decode()

    def outline(self, document: Document) -> Optional[dict[str, Any]]:
        """What `describe_reading` kept; None for a document read before outlines were kept."""
        data = self._get(f"{document.prefix}outline.json")
        outline: Optional[dict[str, Any]] = json.loads(data) if data is not None else None
        return outline

    def table(self, document: Document, number: int) -> Optional[list[list[str]]]:
        data = self._get(f"{document.prefix}tables/{number}.csv")
        return list(csv.reader(io.StringIO(data.decode()))) if data is not None else None

    def page_markdown(self, document: Document, number: int) -> Optional[str]:
        data = self._get(f"{document.prefix}pages/{number}.md")
        return data.decode() if data is not None else None

    def page_image(self, document: Document, number: int) -> Optional[bytes]:
        return self._get(f"{document.prefix}pages/{number}.png")

    def delete(self, document: Document) -> None:
        self._delete_prefix(document.prefix)

    def _put(self, key: str, body: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)

    def _get(self, key: str) -> Optional[bytes]:
        try:
            body: bytes = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        return body

    def _delete_prefix(self, prefix: str) -> None:
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            objects = [{"Key": obj["Key"]} for obj in page.get("Contents", [])]
            if objects:
                self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": objects, "Quiet": True})
