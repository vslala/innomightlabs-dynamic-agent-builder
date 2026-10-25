"""Product report tests use synthetic records and mocked AWS only."""
from datetime import UTC, datetime, timedelta
import json

from unittest.mock import Mock

import boto3
from moto import mock_aws
import pytest

from scripts.product_report import FIELDS, build_report, main, parse_time, render_html, scan_metadata

END = datetime(2026, 10, 24, 12, tzinfo=UTC)
START = END - timedelta(days=30)
AT = (END - timedelta(days=1)).isoformat()


def identity(uid="u", **extra):
    return {"pk": f"Identity#{uid}", "sk": "Identity#Metadata", "user_id": uid,
            "name": "Developer", "email": "dev@example.com", "created_at": AT, **extra}


def conversation(cid="c", entity="Conversation", **extra):
    return {"pk": "member", "sk": f"CONVERSATION#{cid}", "entity_type": entity,
            "conversation_id": cid, "created_by": "u", "created_at": AT, **extra}


def message(cid="c", **extra):
    return {"pk": f"CONVERSATION#{cid}", "sk": "MESSAGE#one", "entity_type": "Message",
            "conversation_id": cid, "role": "user", "created_at": AT, **extra}


def report(rows, **kwargs):
    return build_report(rows, start=START, end=END, now=END, **kwargs)


def test_join_is_independent_of_scan_order_and_uses_conversation_actor():
    result = report([message(created_by="wrong"), conversation(), identity()])
    user = result["users"][0]
    assert user["id"] == "platform:u"
    assert [event["kind"] for event in user["events"]] == ["message_sent", "conversation_created"]
    assert sum(event["interactive"] for event in user["events"]) == 1


def test_visitors_and_platform_are_separate_even_when_emails_match():
    rows = [identity()]
    for kind in ("guest", "google"):
        rows += [conversation(kind, "WidgetConversation", visitor_id="u", visitor_kind=kind,
                              visitor_email="dev@example.com", visitor_name=kind), message(kind)]
    result = report(rows)
    assert {user["audience"] for user in result["users"]} == {"platform", "widget_google", "widget_guest"}
    assert all(user["signup"] is None for user in result["users"] if user["audience"] != "platform")


def test_automated_writes_and_tool_audits_do_not_prove_interactive_use():
    rows = [identity(), conversation(entity="AutomationConversation"), message(),
            {"entity_type": "AutomationRun", "created_by": "u", "created_at": AT, "status": "failed"},
            {"entity_type": "Agent", "created_by": "u", "created_at": AT},
            message(kind="tool_audit", role="assistant"), message(sk="AUDIT#old", role="assistant")]
    events = report(rows)["users"][0]["events"]
    assert not any(event["interactive"] for event in events)
    assert sum(event["kind"] == "tool_audit" for event in events) == 2
    assert "automation_run_failed" in [event["kind"] for event in events]


def test_api_and_orphan_messages_are_not_attributed_to_agent_owner():
    result = report([identity(), conversation(entity="ApiConversation"), message(), message("missing")])
    assert not result["users"][0]["events"]
    assert result["quality"]["api_activity_excluded"] == 2
    assert result["quality"]["messages_without_retained_conversation"] == 1


def test_ttl_invalid_timestamps_and_missing_identities_are_visible():
    result = report([identity(), identity("expired", ttl=int(END.timestamp())),
                     identity("bad", ttl="bad"), conversation(created_at="garbage"),
                     {"entity_type": "Agent", "created_by": "deleted", "created_at": AT}])
    assert len(result["users"]) == 1
    assert result["quality"] == {"activity_rows_without_valid_timestamp": 1,
                                 "activity_without_retained_identity": 1,
                                 "expired_rows_excluded": 1, "invalid_ttl": 1}


def test_exclusive_end_and_rolling_30_days_with_short_selected_range():
    result = build_report([identity(), conversation(), message(created_at=END.isoformat()),
                           message(created_at=START.isoformat()),
                           message(created_at=(START - timedelta(microseconds=1)).isoformat())],
                          start=END - timedelta(days=1), end=END, now=END)
    events = result["users"][0]["events"]
    assert sum(event["kind"] == "message_sent" for event in events) == 1
    assert any(event["at"] == START.isoformat() for event in events)


def test_widget_contact_metadata_is_from_newest_conversation():
    newer = conversation("new", "WidgetConversation", visitor_id="v", visitor_name="new")
    older = conversation("old", "WidgetConversation", visitor_id="v", visitor_name="old",
                         created_at=(END - timedelta(days=3)).isoformat())
    assert report([newer, older])["users"][0]["name"] == "new"


@pytest.mark.parametrize("value,expected", [("2026-10-24", "2026-10-24T00:00:00+00:00"),
                                             ("2026-10-24T13:00:00+01:00", "2026-10-24T12:00:00+00:00"),
                                             ("bad", None), (None, None)])
def test_parse_time(value, expected):
    result = parse_time(value)
    assert (result.isoformat() if result else None) == expected


def test_scan_paginates_empty_page_and_paces_by_capacity(monkeypatch):
    key = {"pk": "next", "sk": "next"}
    table = Mock()
    table.scan.side_effect = [
        {"Items": [], "ScannedCount": 100, "LastEvaluatedKey": key, "ConsumedCapacity": {"CapacityUnits": 20}},
        {"Items": [identity()], "ScannedCount": 1, "ConsumedCapacity": {"CapacityUnits": 0.5}},
    ]
    sleep = Mock()
    monkeypatch.setattr("scripts.product_report.time.sleep", sleep)
    monkeypatch.setattr("scripts.product_report.time.monotonic", lambda: 0)
    rows, stats = scan_metadata(table)
    assert rows == [identity()]
    assert stats == {"pages": 2, "scanned": 101, "capacity": 20.5}
    sleep.assert_called_once_with(2)
    first, second = [call.kwargs for call in table.scan.call_args_list]
    assert first["ConsistentRead"] is False
    assert "ExclusiveStartKey" not in first
    assert second["ExclusiveStartKey"] == key
    assert set(first["ExpressionAttributeNames"].values()) == set(FIELDS)
    assert not {"content", "config", "password_hash", "encrypted_secrets"}.intersection(FIELDS)
    assert [call[0] for call in table.method_calls] == ["scan", "scan"]


def test_render_escapes_script_injection_and_roundtrips_json():
    result = report([identity(name='</script><script>alert("x")</script>&')])
    html = render_html(result)
    embedded = html.split('<script type="application/json" id="report-data">')[1].split("</script>")[0]
    assert "<" not in embedded
    assert json.loads(embedded) == result
    assert "__REPORT_DATA__" not in html


def test_cli_against_moto_uses_only_scan_and_private_file(tmp_path, monkeypatch):
    output = tmp_path / "report.html"
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        table = resource.create_table(TableName="report-test", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}], AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
        table.put_item(Item={**identity(), "password_hash": "never-export", "content": "private-body"})
        operations = []
        original_session = boto3.Session

        def session(**kwargs):
            instance = original_session(**kwargs)
            instance.events.register("before-call.dynamodb.*", lambda model, **kw: operations.append(model.name))
            return instance

        monkeypatch.setattr("scripts.product_report.boto3.Session", session)
        assert main(["--table", "report-test", "--region", "us-east-1", "--output", str(output)]) == 0
        assert operations == ["Scan"]
    assert output.stat().st_mode & 0o777 == 0o600
    html = output.read_text()
    assert "never-export" not in html and "private-body" not in html


@pytest.mark.parametrize("options", [["--from", "bad"], ["--capacity-per-second", "nan"],
                                     ["--page-size", "0"], ["--to", "2999-01-01"]])
def test_invalid_arguments_fail_before_aws(options, monkeypatch):
    session = Mock()
    monkeypatch.setattr("scripts.product_report.boto3.Session", session)
    with pytest.raises(SystemExit):
        main(["--table", "prod", *options])
    session.assert_not_called()


def test_existing_output_is_never_overwritten(tmp_path):
    output = tmp_path / "report.html"
    output.write_text("existing work")
    with pytest.raises(SystemExit):
        main(["--table", "prod", "--output", str(output)])
    assert output.read_text() == "existing work"
