import pytest
from fastapi import HTTPException

from app.config import Settings
from app.security import require_auth, verify_google_credential


def configured_settings() -> Settings:
    return Settings(
        google_client_id="web-client.apps.googleusercontent.com",
        google_allowed_emails="oshaye@gastrobh.com, Fabio@practiceops.ai",
    )


def claims(email: str = "oshaye@gastrobh.com", **overrides):
    values = {
        "sub": "google-user-123",
        "email": email,
        "email_verified": True,
        "hd": email.rsplit("@", 1)[-1],
        "name": "Omid Shaye",
        "picture": "https://example.com/avatar.png",
    }
    values.update(overrides)
    return values


def mock_google(monkeypatch, returned_claims):
    monkeypatch.setattr("app.security.get_settings", configured_settings)
    verify = lambda credential, request, audience: returned_claims
    monkeypatch.setattr("app.security.google_id_token.verify_oauth2_token", verify)


@pytest.mark.parametrize(
    ("email", "expected_role"),
    [("oshaye@gastrobh.com", "owner"), ("FABIO@practiceops.ai", "chief_of_staff")],
)
def test_approved_google_accounts_are_accepted(monkeypatch, email, expected_role):
    mock_google(monkeypatch, claims(email))

    user = verify_google_credential("signed-google-credential")

    assert user.email == email.lower()
    assert user.role == expected_role


@pytest.mark.parametrize(
    "returned_claims",
    [
        claims("someone@gastrobh.com"),
        claims(email_verified=False),
        claims(hd="evil.example"),
        claims(hd=None),
        claims(sub=None),
    ],
)
def test_unapproved_or_untrusted_accounts_are_rejected(monkeypatch, returned_claims):
    mock_google(monkeypatch, returned_claims)

    with pytest.raises(HTTPException) as error:
        verify_google_credential("signed-google-credential")

    assert error.value.status_code == 403


def test_invalid_google_credential_is_rejected(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", configured_settings)

    def invalid(*args):
        raise ValueError("invalid token")

    monkeypatch.setattr("app.security.google_id_token.verify_oauth2_token", invalid)
    with pytest.raises(HTTPException) as error:
        verify_google_credential("invalid")
    assert error.value.status_code == 401


def test_google_configuration_is_required(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: Settings(google_client_id=""))
    with pytest.raises(HTTPException) as error:
        verify_google_credential("credential")
    assert error.value.status_code == 503


def test_bearer_authorization_is_required(monkeypatch):
    mock_google(monkeypatch, claims())
    with pytest.raises(HTTPException) as error:
        require_auth("Basic credential")
    assert error.value.status_code == 401
    assert require_auth("bearer signed-google-credential").email == "oshaye@gastrobh.com"
