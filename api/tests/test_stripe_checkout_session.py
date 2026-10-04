"""A checkout session id from the success URL is never a credential."""

from fastapi.testclient import TestClient

from tests.mock_data import TEST_USER_EMAIL

SESSION = {"id": "cs_1", "payment_status": "paid", "customer_email": TEST_USER_EMAIL}


def _stripe_returns(monkeypatch, session: dict) -> None:
    class FakeStripe:
        async def get(self, path: str) -> dict:
            assert path == f"/checkout/sessions/{session['id']}"
            return session

    monkeypatch.setattr("src.payments.stripe.router.StripeClient", FakeStripe)


def test_the_payer_sees_their_session_without_getting_a_token(test_client: TestClient, auth_headers, monkeypatch):
    _stripe_returns(monkeypatch, SESSION)

    response = test_client.get("/payments/stripe/session/cs_1", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {"email": TEST_USER_EMAIL, "subscription_status": None}


def test_the_session_needs_a_signed_in_user(test_client: TestClient, monkeypatch):
    _stripe_returns(monkeypatch, SESSION)

    assert test_client.get("/payments/stripe/session/cs_1").status_code == 401


def test_someone_elses_session_is_not_found(test_client: TestClient, auth_headers, monkeypatch):
    _stripe_returns(monkeypatch, {**SESSION, "customer_email": "victim@example.com"})

    assert test_client.get("/payments/stripe/session/cs_1", headers=auth_headers).status_code == 404
