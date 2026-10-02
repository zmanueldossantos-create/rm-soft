"""The AGT rule for the year of a series: the current year, and the next one too after 15 December."""
from datetime import date

from app.services.document_series_service import allowed_series_years


def test_from_january_to_15_december_only_the_current_year():
    assert allowed_series_years(date(2026, 1, 1)) == [2026]
    assert allowed_series_years(date(2026, 12, 15)) == [2026]


def test_after_15_december_the_next_year_too():
    assert allowed_series_years(date(2026, 12, 16)) == [2026, 2027]
    assert allowed_series_years(date(2026, 12, 31)) == [2026, 2027]
