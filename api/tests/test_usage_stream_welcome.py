from unittest.mock import Mock

import pytest
from boto3.dynamodb.types import TypeSerializer

from lambdas.usage_stream_handler import handler as usage_handler


@pytest.mark.parametrize("sk", ["Identity#Metadata", "User#Metadata"])
def test_identity_insert_does_not_send_a_second_welcome(monkeypatch, dynamodb_table, sk):
    send = Mock()
    monkeypatch.setattr(usage_handler, "send_email", send)
    serializer = TypeSerializer()
    image = {
        "pk": "Identity#new-user",
        "sk": sk,
        "entity_type": "Identity",
        "email": "new.user@example.com",
        "name": "New User",
    }
    record = {
        "eventName": "INSERT",
        "eventID": "new-user-event",
        "dynamodb": {"NewImage": {key: serializer.serialize(value) for key, value in image.items()}},
    }

    # Stream delivery can be repeated; neither delivery should send an email.
    for _ in range(2):
        assert usage_handler.handler({"Records": [record]}, context=None) == {"status": "ok"}

    send.assert_not_called()
    assert not any(
        item.get("event_type") == "welcome"
        for item in dynamodb_table.scan()["Items"]
    )
