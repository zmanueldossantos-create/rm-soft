"""The SAF-T dates are Luanda times: a sale recorded at 23h30 UTC happened at 00h30 the next day in Luanda."""
from datetime import datetime, timezone

from app.services.saf_t_export_service import _local


def test_a_recorded_moment_is_written_in_luanda_time():
    assert _local(datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc)) == datetime(2026, 10, 10, 0, 30)
    assert _local(datetime(2026, 10, 9, 10, 26, 36, tzinfo=timezone.utc)) == datetime(2026, 10, 9, 11, 26, 36)
