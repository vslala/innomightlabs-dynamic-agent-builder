from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.widget.guests import GuestSessionEnded, GuestSessionRepository
from src.widget.sessions import create_guest_session, rotate_refresh_token, _hash


@pytest.fixture
def repository(dynamodb_table):
    return GuestSessionRepository()


def create(repository, **kwargs):
    return repository.create(agent_id="agent", key_id="key", email="a@gmail.com",
                             session_timeout_minutes=kwargs.pop("session_timeout_minutes", 60), **kwargs)


def test_timeout_default_and_lifetime_cap(repository):
    now = datetime.now(timezone.utc)
    guest = create(repository, session_timeout_minutes=0, now=now)
    assert guest.session_ends_at == now + timedelta(minutes=settings.widget_guest_default_session_minutes)
    # A continuously active guest may reach the cap, but never extend beyond it.
    repository.table.update_item(Key={"pk": guest.pk, "sk": guest.sk},
        UpdateExpression="SET session_ends_at = :end", ExpressionAttributeValues={":end": guest.max_ends_at.isoformat()})
    guest = repository.get(guest.visitor_id)
    repository.touch(guest, guest.max_ends_at - timedelta(minutes=1))
    assert repository.get(guest.visitor_id).session_ends_at == guest.max_ends_at


@pytest.mark.parametrize("state", ["expired", "closing", "deleted", "ended"])
def test_stale_touch_never_resurrects(repository, state):
    now = datetime.now(timezone.utc)
    guest = create(repository, now=now)
    if state == "expired":
        now = guest.session_ends_at
    elif state == "deleted":
        repository.table.delete_item(Key={"pk": guest.pk, "sk": guest.sk})
    elif state == "ended":
        repository.end(guest, now)
    else:
        repository.end(guest, now)
        assert repository.claim(guest, now)
    with pytest.raises(GuestSessionEnded):
        repository.touch(guest, now)
    if state == "deleted":
        assert repository.get(guest.visitor_id) is None


def test_binding_and_expiration(repository):
    now = datetime.now(timezone.utc)
    guest = create(repository, now=now)
    assert repository.require_active(guest.visitor_id, "agent", "key", now)
    for aid, kid, at in [("other", "key", now), ("agent", "other", now), ("agent", "key", guest.session_ends_at)]:
        with pytest.raises(GuestSessionEnded):
            repository.require_active(guest.visitor_id, aid, kid, at)


def test_turn_lease_excludes_closer_even_after_explicit_end(repository):
    now = datetime.now(timezone.utc)
    guest = create(repository, now=now)
    repository.touch(guest, now, turn_id="turn")
    repository.end(guest, now)
    assert repository.claim(guest, now) is None
    repository.finish_turn(guest, "turn")
    claimed = repository.claim(guest, now)
    assert claimed.status == "closing"
    assert repository.claim(guest, now) is None
    repository.release(claimed)
    assert repository.get(guest.visitor_id).status == "closing"
    assert repository.claim(guest, now)


def test_guest_refresh_rotation_and_key_binding(repository):
    session = create_guest_session(agent_id="agent", key_id="key", email="a@gmail.com",
                                  session_timeout_minutes=60, origin="", ip="127.0.0.1")
    assert rotate_refresh_token(session.refresh_token, "agent", "wrong-key") is None
    rotated = rotate_refresh_token(session.refresh_token, "agent", "key")
    assert rotated is not None
    assert repository.get(session.visitor.visitor_id).refresh_hash == _hash(rotated.refresh_token)
    assert rotate_refresh_token(session.refresh_token, "agent", "key") is None
    repository.end(repository.get(session.visitor.visitor_id))
    assert rotate_refresh_token(rotated.refresh_token, "agent", "key") is None


def test_refresh_loses_race_to_closer_without_orphan_token(repository, monkeypatch):
    session = create_guest_session(agent_id="agent", key_id="key", email="a@gmail.com",
                                  session_timeout_minutes=60, origin="", ip="127.0.0.1")
    original = GuestSessionRepository.require_active
    def close_after_read(self, *args, **kwargs):
        guest = original(self, *args, **kwargs)
        self.end(guest)
        assert self.claim(guest, datetime.now(timezone.utc))
        return guest
    monkeypatch.setattr(GuestSessionRepository, "require_active", close_after_read)
    assert rotate_refresh_token(session.refresh_token, "agent", "key") is None
    tokens = [row for row in repository.table.scan()["Items"] if row["pk"].startswith("WidgetRefresh#")]
    assert len(tokens) == 1
    assert tokens[0]["pk"] == "WidgetRefresh#" + _hash(session.refresh_token)


def test_two_refreshes_only_one_wins(repository, monkeypatch):
    session = create_guest_session(agent_id="agent", key_id="key", email="a@gmail.com",
                                  session_timeout_minutes=60, origin="", ip="127.0.0.1")
    original = GuestSessionRepository.require_active
    winner = []
    def rotate_after_read(self, *args, **kwargs):
        guest = original(self, *args, **kwargs)
        monkeypatch.setattr(GuestSessionRepository, "require_active", original)
        winner.append(rotate_refresh_token(session.refresh_token, "agent", "key"))
        return guest
    monkeypatch.setattr(GuestSessionRepository, "require_active", rotate_after_read)
    assert rotate_refresh_token(session.refresh_token, "agent", "key") is None
    assert winner[0] is not None
    tokens = [row for row in repository.table.scan()["Items"] if row["pk"].startswith("WidgetRefresh#")]
    assert len(tokens) == 1
    assert repository.get(session.visitor.visitor_id).refresh_hash == _hash(winner[0].refresh_token)


def test_missing_session_cannot_be_recreated_by_refresh(repository):
    session = create_guest_session(agent_id="agent", key_id="key", email="a@gmail.com",
                                  session_timeout_minutes=60, origin="", ip="127.0.0.1")
    guest = repository.get(session.visitor.visitor_id)
    repository.table.delete_item(Key={"pk": guest.pk, "sk": guest.sk})
    assert rotate_refresh_token(session.refresh_token, "agent", "key") is None
    assert repository.get(guest.visitor_id) is None
