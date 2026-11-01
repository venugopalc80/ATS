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
