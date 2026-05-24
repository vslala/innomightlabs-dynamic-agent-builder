from src.agents.image_generation.storage import ConversationMediaStorage


class FakePaginator:
    def paginate(self, **kwargs):
        assert kwargs["Bucket"] == "test-media"
        assert kwargs["Prefix"] == "agents/agent-1/"
        return [
            {"Contents": [{"Key": "agents/agent-1/a.png"}, {"Key": "agents/agent-1/b.png"}]},
            {"Contents": [{"Key": "agents/agent-1/c.png"}]},
        ]


class FakeS3Client:
    def __init__(self):
        self.deleted = []

    def get_paginator(self, name):
        assert name == "list_objects_v2"
        return FakePaginator()

    def delete_objects(self, **kwargs):
        self.deleted.extend(obj["Key"] for obj in kwargs["Delete"]["Objects"])


def test_build_image_key_uses_agent_conversation_message_prefix(monkeypatch):
    monkeypatch.setattr("src.agents.image_generation.storage.settings.conversation_media_bucket", "test-media")
    storage = ConversationMediaStorage()

    key = storage.build_image_key(
        agent_id="agent-1",
        conversation_id="conv-1",
        message_id="msg-1",
        extension="png",
    )

    assert key.startswith("agents/agent-1/conversations/conv-1/messages/msg-1/")
    assert key.endswith(".png")


def test_delete_agent_prefix_paginates_and_batches(monkeypatch):
    fake_client = FakeS3Client()
    monkeypatch.setattr("src.agents.image_generation.storage.settings.conversation_media_bucket", "test-media")
    storage = ConversationMediaStorage()
    storage.client = fake_client

    deleted = storage.delete_agent_prefix("agent-1")

    assert deleted == 3
    assert fake_client.deleted == [
        "agents/agent-1/a.png",
        "agents/agent-1/b.png",
        "agents/agent-1/c.png",
    ]
