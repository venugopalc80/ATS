import pytest
from fastapi import HTTPException

from app.auth import is_mfa_verified, require_mfa


@pytest.mark.parametrize(
    "claims",
    [
        {"aal": "aal1"},
        {},
        {"aal": None},
        {"aal": "unknown"},
    ],
)
def test_mfa_is_not_treated_as_verified_without_aal2(claims):
    assert not is_mfa_verified(claims)


def test_mfa_is_verified_only_for_aal2():
    assert is_mfa_verified({"aal": "aal2"})


def test_require_mfa_rejects_single_factor_session():
    with pytest.raises(HTTPException) as error:
        require_mfa({"aal": "aal1"})

    assert error.value.status_code == 403
    assert error.value.detail["code"] == "mfa_required"


def test_require_mfa_accepts_verified_second_factor():
    assert require_mfa({"aal": "aal2"}) == {"aal": "aal2"}

def test_verified_claims_must_match_authenticated_user(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    import app.auth as auth_module

    user_id = uuid4()
    claims = {
        "sub": str(user_id),
        "role": "authenticated",
        "aal": "aal2",
    }

    class FakeAuth:
        def get_claims(self, token):
            assert token == "test-token"
            return SimpleNamespace(claims=claims)

    class FakeClient:
        auth = FakeAuth()

    monkeypatch.setattr(auth_module, "_auth_client", lambda: FakeClient())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")
    assert auth_module.get_current_auth_claims(credentials, user_id) == claims

    with pytest.raises(HTTPException) as error:
        auth_module.get_current_auth_claims(credentials, uuid4())
    assert error.value.status_code == 401


def test_verified_claims_reject_non_authenticated_role(monkeypatch):
    from types import SimpleNamespace
    from uuid import uuid4
    from fastapi import HTTPException
    from fastapi.security import HTTPAuthorizationCredentials
    import app.auth as auth_module

    user_id = uuid4()

    class FakeAuth:
        def get_claims(self, token):
            return SimpleNamespace(claims={
                "sub": str(user_id),
                "role": "anon",
                "aal": "aal2",
            })

    class FakeClient:
        auth = FakeAuth()

    monkeypatch.setattr(auth_module, "_auth_client", lambda: FakeClient())
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-token")

    with pytest.raises(HTTPException) as error:
        auth_module.get_current_auth_claims(credentials, user_id)
    assert error.value.status_code == 401


def test_session_security_response_does_not_return_raw_claims():
    from app.routers.security import current_session_security

    result = __import__("asyncio").run(current_session_security({
        "sub": "user-id",
        "aal": "aal2",
        "iat": 100,
        "exp": 200,
        "amr": [
            {"method": "password", "timestamp": 100},
            {"method": "totp", "timestamp": 110},
        ],
        "email": "private@example.com",
        "user_metadata": {"private": "value"},
    }))

    assert result["assurance_level"] == "aal2"
    assert result["mfa_verified"] is True
    assert result["authentication_methods"] == [
        {"method": "password", "timestamp": 100},
        {"method": "totp", "timestamp": 110},
    ]
    assert "email" not in result
    assert "user_metadata" not in result
    assert "sub" not in result
