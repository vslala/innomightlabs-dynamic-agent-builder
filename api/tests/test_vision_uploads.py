from __future__ import annotations

from datetime import datetime, timedelta, timezone

import boto3
import pytest

from src.config import settings
from src.messages.models import Message
from src.messages.repositories import DynamoDBMessageRepository
from src.vision.errors import ImageInputError
from src.vision.models import VisionSettings
from src.vision.policy import ImageInputUnavailable, image_input_availability
from src.vision.repository import ImageUploadRepository, VisionSettingsRepository
from src.vision.uploads import ImageUploadService
from tests.vision_support import ACCOUNT_ID, create_media_bucket, enable_vision, make_agent, png_bytes

CONVERSATION_ID = "conversation-1"


@pytest.fixture
def service(dynamodb_table) -> ImageUploadService:
    create_media_bucket()
    return ImageUploadService()


def _store(service: ImageUploadService, agent, actor: str = "alice@example.com", name: str = "photo.png"):
    return service.store(
        agent=agent, conversation_id=CONVERSATION_ID, uploaded_by=actor, filename=name, raw=png_bytes()
    )


class TestAvailability:
    def test_off_until_an_admin_turns_it_on(self, dynamodb_table) -> None:
        availability = image_input_availability(make_agent())

        assert availability.reason == ImageInputUnavailable.DISABLED
        assert availability.available is False
        assert availability.limits.max_images_per_message == 4

    def test_enabled_without_the_providers_credentials_is_not_configured(self, dynamodb_table) -> None:
        VisionSettingsRepository().save(
            VisionSettings(account_id=ACCOUNT_ID, enabled=True, provider_name="Anthropic", model_name="m")
        )

        assert image_input_availability(make_agent()).reason == ImageInputUnavailable.NOT_CONFIGURED

    def test_available_when_enabled_and_configured(self, dynamodb_table) -> None:
        enable_vision()

        availability = image_input_availability(make_agent())

        assert availability.available is True
        assert availability.reason is None

    def test_an_agent_without_tools_cannot_read_images(self, dynamodb_table) -> None:
        enable_vision()

        availability = image_input_availability(make_agent(architecture="krishna-mini"))

        assert availability.reason == ImageInputUnavailable.AGENT_UNSUPPORTED

    def test_each_account_has_its_own_setting(self, dynamodb_table) -> None:
        enable_vision(account_id="account-with-vision")

        assert image_input_availability(make_agent(account_id="account-with-vision")).available is True
        assert image_input_availability(make_agent(account_id="another-account")).available is False


class TestStore:
    def test_stores_a_pending_image_under_the_conversation(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()

        upload = _store(service, agent)

        assert upload.status == "pending"
        assert upload.s3_key.startswith(f"agents/{agent.agent_id}/conversations/{CONVERSATION_ID}/uploads/")
        assert upload.filename == "photo.png"
        assert (upload.width, upload.height) == (40, 30)
        stored = service.open_bytes(conversation_id=CONVERSATION_ID, image_id=upload.image_id)
        assert stored.content_type == "image/png"
        tags = boto3.client("s3", region_name=settings.conversation_media_region).get_object_tagging(
            Bucket=settings.conversation_media_bucket, Key=upload.s3_key
        )["TagSet"]
        assert tags == [{"Key": "retention", "Value": "pending-upload"}]

    def test_pasted_images_get_a_meaningful_name(self, service: ImageUploadService) -> None:
        enable_vision()

        upload = _store(service, make_agent(), name="image.png")

        assert upload.filename.startswith("pasted-")
        assert upload.filename.endswith(".png")

    def test_refuses_while_the_feature_is_off(self, service: ImageUploadService) -> None:
        with pytest.raises(ImageInputError) as refused:
            _store(service, make_agent())

        assert (refused.value.code, refused.value.status_code) == ("image_input_disabled", 403)

    def test_refuses_something_that_is_not_an_image(self, service: ImageUploadService) -> None:
        enable_vision()

        with pytest.raises(ImageInputError) as refused:
            service.store(
                agent=make_agent(), conversation_id=CONVERSATION_ID, uploaded_by="a", filename="x.png", raw=b"nope"
            )

        assert refused.value.code == "image_unreadable"


class TestAttach:
    def test_binds_the_actors_pending_images_and_retags_them(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()
        first, second = _store(service, agent), _store(service, agent, name="other.png")

        attachments = service.attach(
            agent=agent, conversation_id=CONVERSATION_ID, actor_id="alice@example.com",
            image_ids=[second.image_id, first.image_id, second.image_id],
        )

        assert [a.image_id for a in attachments] == [second.image_id, first.image_id]
        assert attachments[0].analysis is None
        row = ImageUploadRepository().find(CONVERSATION_ID, first.image_id)
        assert row is not None and row.status == "attached"
        raw_row = service.repository.table.get_item(Key={"pk": row.pk, "sk": row.sk})["Item"]
        assert "ttl" not in raw_row
        tags = boto3.client("s3", region_name=settings.conversation_media_region).get_object_tagging(
            Bucket=settings.conversation_media_bucket, Key=first.s3_key
        )["TagSet"]
        assert tags == [{"Key": "retention", "Value": "conversation"}]

    def test_an_image_can_be_sent_once(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()
        upload = _store(service, agent)
        service.attach(agent=agent, conversation_id=CONVERSATION_ID, actor_id="alice@example.com", image_ids=[upload.image_id])

        with pytest.raises(ImageInputError) as refused:
            service.attach(agent=agent, conversation_id=CONVERSATION_ID, actor_id="alice@example.com", image_ids=[upload.image_id])

        assert refused.value.code == "image_not_found"

    def test_someone_elses_image_is_not_found(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()
        upload = _store(service, agent, actor="alice@example.com")

        with pytest.raises(ImageInputError) as refused:
            service.attach(agent=agent, conversation_id=CONVERSATION_ID, actor_id="mallory@example.com", image_ids=[upload.image_id])

        assert refused.value.code == "image_not_found"

    def test_another_conversations_image_is_not_found(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()
        upload = _store(service, agent)

        with pytest.raises(ImageInputError) as refused:
            service.attach(agent=agent, conversation_id="conversation-2", actor_id="alice@example.com", image_ids=[upload.image_id])

        assert refused.value.code == "image_not_found"

    def test_an_expired_upload_is_not_found_even_before_dynamodb_deletes_it(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()
        upload = _store(service, agent)
        service.repository.table.update_item(
            Key={"pk": upload.pk, "sk": upload.sk},
            UpdateExpression="SET #ttl = :past",
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={":past": int((datetime.now(timezone.utc) - timedelta(hours=1)).timestamp())},
        )

        with pytest.raises(ImageInputError) as refused:
            service.attach(agent=agent, conversation_id=CONVERSATION_ID, actor_id="alice@example.com", image_ids=[upload.image_id])

        assert refused.value.code == "image_not_found"

    def test_too_many_images_in_one_message(self, service: ImageUploadService) -> None:
        enable_vision()
        agent = make_agent()
        uploads = [_store(service, agent, name=f"{n}.png") for n in range(5)]

        with pytest.raises(ImageInputError) as refused:
            service.attach(
                agent=agent, conversation_id=CONVERSATION_ID, actor_id="alice@example.com",
                image_ids=[u.image_id for u in uploads],
            )

        assert refused.value.code == "too_many_images"

    def test_no_images_needs_no_settings_lookup(self, service: ImageUploadService) -> None:
        assert service.attach(agent=make_agent(), conversation_id=CONVERSATION_ID, actor_id="a", image_ids=[]) == []

    def test_attaching_while_the_feature_is_off_is_refused(self, service: ImageUploadService) -> None:
        with pytest.raises(ImageInputError) as refused:
            service.attach(agent=make_agent(), conversation_id=CONVERSATION_ID, actor_id="a", image_ids=["x"])

        assert refused.value.code == "image_input_disabled"


def test_deleting_the_conversation_removes_the_upload_ledger_rows(service: ImageUploadService) -> None:
    enable_vision()
    upload = _store(service, make_agent())
    messages = DynamoDBMessageRepository()
    messages.save(Message(conversation_id=CONVERSATION_ID, role="user", content="hello"))

    messages.delete_by_conversation(CONVERSATION_ID)

    assert ImageUploadRepository().find(CONVERSATION_ID, upload.image_id) is None
