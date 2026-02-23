from datetime import UTC, datetime

import pytest

from backend.services.cron_utils import next_run_datetime, validate_cron_expression


def test_validate_cron_expression_accepts_valid_expression():
    validate_cron_expression("*/15 9-17 * * 1-5")


@pytest.mark.parametrize(
    "expression",
    [
        "",
        "* * * *",
        "61 * * * *",
        "* 24 * * *",
        "* * 0 * *",
        "* * * 13 *",
        "* * * * 9",
    ],
)
def test_validate_cron_expression_rejects_invalid_expression(expression: str):
    with pytest.raises(ValueError):
        validate_cron_expression(expression)


def test_next_run_datetime_for_daily_midnight():
    now = datetime(2026, 2, 16, 23, 59, 30, tzinfo=UTC)
    next_run = next_run_datetime(now, "0 0 * * *")
    assert next_run == datetime(2026, 2, 17, 0, 0, 0, tzinfo=UTC)

