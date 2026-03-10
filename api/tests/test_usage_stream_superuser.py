from lambdas.usage_stream_handler import handler as usage_handler


def test_usage_stream_still_tracks_superuser_analytics(monkeypatch):
    user_email = "varunshrivastava007@gmail.com"
    calls: list[tuple[str, str, int]] = []

    class DummyTable:
        def put_item(self, **_kwargs):
            return {}

    class DummyDynamo:
        def Table(self, _name):
            return DummyTable()

    class FakeUsageRepo:
        def adjust_active_agents(self, _user_email: str, _delta: int):
            return None

        def increment_messages(self, tracked_user: str, period_key: str, count: int):
            calls.append((tracked_user, period_key, count))
            return None

        def increment_kb_pages(self, _user_email: str, _period_key: str, _count: int):
            return None

    monkeypatch.setattr(usage_handler.settings, "superuser_emails", [user_email])
    monkeypatch.setattr(usage_handler, "get_dynamodb_resource", lambda: DummyDynamo())
    monkeypatch.setattr(usage_handler, "_deserialize", lambda image: image or {})
    monkeypatch.setattr(usage_handler, "_dedupe_event", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(usage_handler, "UsageRepository", FakeUsageRepo)

    event = {
        "Records": [
            {
                "eventName": "INSERT",
                "eventID": "event-1",
                "dynamodb": {
                    "NewImage": {
                        "entity_type": "Message",
                        "created_by": user_email,
                        "created_at": "2026-03-10T00:00:00+00:00",
                    }
                },
            }
        ]
    }

    result = usage_handler.handler(event, context=None)
    assert result["status"] == "ok"
    assert len(calls) == 1
    assert calls[0][0] == user_email
    assert calls[0][2] == 1
