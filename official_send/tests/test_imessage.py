from datetime import datetime, timezone

from official_send.imessage import _apple_timestamp_to_datetime


def test_apple_timestamp_to_datetime_supports_nanoseconds() -> None:
    raw = 60 * 1_000_000_000
    dt = _apple_timestamp_to_datetime(raw)
    assert dt.year == 2001
    assert dt.minute == 1


def test_apple_timestamp_to_datetime_fallbacks_now_for_none() -> None:
    dt = _apple_timestamp_to_datetime(None)
    assert dt.tzinfo == timezone.utc
    assert dt <= datetime.now(timezone.utc)
