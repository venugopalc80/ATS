from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.routers.audit import validate_security_event_window


@pytest.mark.parametrize("field_name", ["since", "until"])
def test_security_event_window_rejects_timezone_naive_timestamps(field_name):
    values = {"since": None, "until": None}
    values[field_name] = datetime(2026, 10, 26, 12, 0, 0)

    with pytest.raises(HTTPException) as error:
        validate_security_event_window(values["since"], values["until"])

    assert error.value.status_code == 422
    assert field_name in error.value.detail


def test_security_event_window_accepts_timezone_aware_timestamps():
    validate_security_event_window(
        datetime(2026, 10, 26, 12, tzinfo=timezone.utc),
        datetime(2026, 10, 26, 13, tzinfo=timezone.utc),
    )


def test_security_event_window_rejects_inverted_range():
    with pytest.raises(HTTPException) as error:
        validate_security_event_window(
            datetime(2026, 10, 26, 13, tzinfo=timezone.utc),
            datetime(2026, 10, 26, 12, tzinfo=timezone.utc),
        )

    assert error.value.status_code == 422
    assert "earlier than or equal" in error.value.detail
