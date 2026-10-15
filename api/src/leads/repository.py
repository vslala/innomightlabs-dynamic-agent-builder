"""DynamoDB access for leads. Everything sits in the account's partition.

Key structure:
    Account#{account_id} / LeadForm#{form_id}                  a form; `capture_count` is kept by captures
    Account#{account_id} / LeadFormSlug#{slug}                 makes slugs unique; points at the form
    Account#{account_id} / LeadSettings                        the account's statuses (absent: the defaults)
    Account#{account_id} / Capture#{created_at}#{capture_id}   a capture, newest first by key
    Account#{account_id} / CaptureId#{capture_id}              makes captures idempotent; points at the capture
    Account#{account_id} / LeadUsage#{yyyy-mm}                 captures counted towards the plan that month
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from boto3.dynamodb.conditions import Attr, ConditionBase, Key
from botocore.exceptions import ClientError

from src.common.pagination import decode_cursor, encode_cursor
from src.config import settings
from src.db import get_dynamodb_resource
from src.leads.models import Capture, CaptureFilters, LeadForm, LeadSettings
from src.utils.dynamodb import convert_floats_to_decimals


class SlugTaken(Exception):
    """Another form in the account already uses this slug."""


class FormHasCaptures(Exception):
    """A form is only deleted while nothing refers to it; archive it instead."""


class DuplicateCapture(Exception):
    """This capture was saved before (a retried or repeated call)."""


class LeadsRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    # Forms

    def create_form(self, form: LeadForm) -> LeadForm:
        try:
            self._transact([
                {"Put": {"Item": form.to_dynamo_item(), "ConditionExpression": "attribute_not_exists(pk)"}},
                {"Put": {"Item": _slug_item(form), "ConditionExpression": "attribute_not_exists(pk)"}},
            ])
        except ClientError as error:
            if _cancelled(error):
                raise SlugTaken(form.slug) from error
            raise
        return form

    def find_form(self, account_id: str, form_id: str) -> LeadForm | None:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": f"LeadForm#{form_id}"}).get("Item")
        return LeadForm.from_dynamo_item(item) if item else None

    def find_form_by_slug(self, account_id: str, slug: str) -> LeadForm | None:
        guard = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": f"LeadFormSlug#{slug}"}).get("Item")
        return self.find_form(account_id, guard["form_id"]) if guard else None

    def list_forms(self, account_id: str) -> list[LeadForm]:
        items = self._query_all(Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("LeadForm#"))
        forms = [LeadForm.from_dynamo_item(item) for item in items]
        return sorted(forms, key=lambda form: form.created_at, reverse=True)

    def update_form(self, form: LeadForm) -> LeadForm:
        """Writes the editable fields only, so a capture counted at the same moment is never lost."""
        values = convert_floats_to_decimals(form.model_dump(mode="json", include={
            "name", "purpose", "form_inputs", "version", "status", "updated_at",
        }))
        self.table.update_item(
            Key={"pk": form.pk, "sk": form.sk},
            UpdateExpression="SET " + ", ".join(f"#{field} = :{field}" for field in values),
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={f"#{field}": field for field in values},
            ExpressionAttributeValues={f":{field}": value for field, value in values.items()},
        )
        return form

    def delete_form(self, form: LeadForm) -> None:
        try:
            self._transact([
                {"Delete": {"Key": {"pk": form.pk, "sk": form.sk},
                            "ConditionExpression": "attribute_not_exists(capture_count) OR capture_count = :zero",
                            "ExpressionAttributeValues": {":zero": 0}}},
                {"Delete": {"Key": {"pk": form.pk, "sk": f"LeadFormSlug#{form.slug}"}}},
            ])
        except ClientError as error:
            if _cancelled(error):
                raise FormHasCaptures(form.form_id) from error
            raise

    # Settings

    def find_settings(self, account_id: str) -> LeadSettings:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": "LeadSettings"}).get("Item")
        return LeadSettings.from_dynamo_item(item) if item else LeadSettings(account_id=account_id)

    def save_settings(self, lead_settings: LeadSettings) -> LeadSettings:
        self.table.put_item(Item=lead_settings.to_dynamo_item())
        return lead_settings

    # Captures

    def find_capture(self, account_id: str, capture_id: str) -> Capture | None:
        guard = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": f"CaptureId#{capture_id}"}).get("Item")
        if not guard:
            return None
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": guard["capture_sk"]}).get("Item")
        return Capture.from_dynamo_item(item) if item else None

    def count_towards_plan(self, account_id: str, month: str) -> int:
        """The next number in the month's count. Taken before saving; a capture that turns out to be a racing
        duplicate leaves a gap, which can only ever let one fewer capture through that month."""
        response = self.table.update_item(
            Key={"pk": f"Account#{account_id}", "sk": f"LeadUsage#{month}"},
            UpdateExpression="SET captures = if_not_exists(captures, :zero) + :one, entity_type = :type",
            ExpressionAttributeValues={":zero": 0, ":one": 1, ":type": "LeadUsage"},
            ReturnValues="UPDATED_NEW",
        )
        return int(response["Attributes"]["captures"])

    def monthly_counts(self, account_id: str) -> dict[str, int]:
        items = self._query_all(Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("LeadUsage#"))
        return {item["sk"].removeprefix("LeadUsage#"): int(item["captures"]) for item in items}

    def save_capture(self, capture: Capture) -> Capture:
        """The capture, its idempotency guard and its form's count, all or nothing."""
        writes: list[dict[str, Any]] = [
            {"Put": {"Item": _capture_guard_item(capture), "ConditionExpression": "attribute_not_exists(pk)"}},
            {"Put": {"Item": capture.to_dynamo_item()}},
        ]
        if capture.form_id:
            writes.append({"Update": {
                "Key": {"pk": capture.pk, "sk": f"LeadForm#{capture.form_id}"},
                "UpdateExpression": "SET capture_count = if_not_exists(capture_count, :zero) + :one",
                "ConditionExpression": "attribute_exists(pk)",
                "ExpressionAttributeValues": {":zero": 0, ":one": 1},
            }})
        try:
            self._transact(writes)
        except ClientError as error:
            # The guard is the first write: its condition failing means the capture exists already
            if _cancelled(error) and _reasons(error)[:1] == ["ConditionalCheckFailed"]:
                raise DuplicateCapture(capture.capture_id) from error
            raise
        return capture

    def update_capture_status(self, capture: Capture, status: str) -> Capture:
        now = datetime.now(timezone.utc)
        self.table.update_item(
            Key={"pk": capture.pk, "sk": capture.sk},
            UpdateExpression="SET #status = :status, updated_at = :updated_at",
            ConditionExpression="attribute_exists(pk)",
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={":status": status, ":updated_at": now.isoformat()},
        )
        return capture.model_copy(update={"status": status, "updated_at": now})

    def delete_capture(self, capture: Capture) -> None:
        writes: list[dict[str, Any]] = [
            {"Delete": {"Key": {"pk": capture.pk, "sk": capture.sk}}},
            {"Delete": {"Key": {"pk": capture.pk, "sk": f"CaptureId#{capture.capture_id}"}}},
        ]
        if capture.form_id:
            writes.append({"Update": {
                "Key": {"pk": capture.pk, "sk": f"LeadForm#{capture.form_id}"},
                "UpdateExpression": "SET capture_count = capture_count - :one",
                "ConditionExpression": "capture_count > :zero",
                "ExpressionAttributeValues": {":zero": 0, ":one": 1},
            }})
        self._transact(writes)

    def list_captures(
        self,
        account_id: str,
        filters: CaptureFilters,
        *,
        monthly_limit: int,
        limit: int,
        cursor: str | None = None,
    ) -> tuple[list[Capture], str | None]:
        """Newest first. The date range is part of the key; everything else filters the pages read, so the
        repository keeps reading until it has `limit` captures. The cursor is the last capture returned."""
        since = filters.since.isoformat() if filters.since else ""
        until = filters.until.isoformat() if filters.until else "~"
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{account_id}")
            & Key("sk").between(f"Capture#{since}", f"Capture#{until}~"),
            "ScanIndexForward": False,
            "Limit": max(limit, 25),
        }
        filter_expression = _capture_filter(filters, monthly_limit)
        if filter_expression is not None:
            query["FilterExpression"] = filter_expression
        start_key = decode_cursor(cursor)
        if start_key:
            query["ExclusiveStartKey"] = start_key

        captures: list[Capture] = []
        while len(captures) < limit:
            response = self.table.query(**query)
            for item in response.get("Items", []):
                captures.append(Capture.from_dynamo_item(item))
                if len(captures) == limit:
                    last = captures[-1]
                    return captures, encode_cursor({"pk": last.pk, "sk": last.sk})
            if "LastEvaluatedKey" not in response:
                return captures, None
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return captures, None

    def captures_with_status(self, account_id: str, status: str) -> Iterator[Capture]:
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("Capture#"),
            "FilterExpression": Attr("status").eq(status),
        }
        while True:
            response = self.table.query(**query)
            for item in response.get("Items", []):
                yield Capture.from_dynamo_item(item)
            if "LastEvaluatedKey" not in response:
                return
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def _query_all(self, key_condition: ConditionBase) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"KeyConditionExpression": key_condition}
        items: list[dict[str, Any]] = []
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                return items
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]

    def _transact(self, writes: list[dict[str, Any]]) -> None:
        for write in writes:
            next(iter(write.values()))["TableName"] = self.table.name
        self.table.meta.client.transact_write_items(TransactItems=writes)


def get_leads_repository() -> LeadsRepository:
    return LeadsRepository()


def _slug_item(form: LeadForm) -> dict[str, Any]:
    return {"pk": form.pk, "sk": f"LeadFormSlug#{form.slug}", "form_id": form.form_id, "entity_type": "LeadFormSlug"}


def _capture_guard_item(capture: Capture) -> dict[str, Any]:
    return {"pk": capture.pk, "sk": f"CaptureId#{capture.capture_id}", "capture_sk": capture.sk,
            "entity_type": "LeadCaptureId"}


def _capture_filter(filters: CaptureFilters, monthly_limit: int) -> ConditionBase | None:
    conditions: list[ConditionBase] = []
    if filters.agent_id:
        conditions.append(Attr("agent_id").eq(filters.agent_id))
    if filters.form_slug:
        conditions.append(Attr("form_slug").eq(filters.form_slug))
    if filters.status:
        conditions.append(Attr("status").eq(filters.status))
    if not filters.include_tests:
        conditions.append(Attr("source").ne("dashboard"))
    if monthly_limit > 0:
        # Locked captures stay hidden until the account upgrades (Capture.is_locked)
        conditions.append(Attr("month_seq").not_exists() | Attr("month_seq").lte(monthly_limit))
    if not conditions:
        return None
    combined = conditions[0]
    for condition in conditions[1:]:
        combined = combined & condition
    return combined


def _cancelled(error: ClientError) -> bool:
    return error.response["Error"]["Code"] == "TransactionCanceledException"


def _reasons(error: ClientError) -> list[str]:
    return [reason.get("Code", "") for reason in error.response.get("CancellationReasons", [])]
