"""Utilities for validating and evaluating 5-field cron expressions."""

from __future__ import annotations

from datetime import datetime, timedelta


def validate_cron_expression(expression: str) -> None:
    """Validate a standard 5-field cron expression.

    Supported syntax per field:
    - `*`
    - `*/n`
    - `a`
    - `a-b`
    - `a,b,c`
    - combinations with `/step` for ranges and wildcard.
    """
    _parse_cron(expression)


def cron_matches(dt: datetime, expression: str) -> bool:
    minute_set, hour_set, dom_set, month_set, dow_set = _parse_cron(expression)
    return (
        dt.minute in minute_set
        and dt.hour in hour_set
        and dt.day in dom_set
        and dt.month in month_set
        and _python_weekday_to_cron(dt.weekday()) in dow_set
    )


def next_run_datetime(now: datetime, expression: str) -> datetime:
    """Return the next datetime (minute precision) matching the cron expression."""
    if now.tzinfo is None:
        raise ValueError("`now` must be timezone-aware")

    candidate = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    # Search up to 366 days ahead, minute by minute.
    max_steps = 366 * 24 * 60
    for _ in range(max_steps):
        if cron_matches(candidate, expression):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError("Could not find next run for cron expression within one year")


def seconds_until_next_run(now: datetime, expression: str) -> float:
    next_run = next_run_datetime(now, expression)
    return (next_run - now).total_seconds()


def _parse_cron(expression: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    parts = expression.strip().split()
    if len(parts) != 5:
        raise ValueError("Cron expression must have 5 fields: minute hour day month weekday")

    minute = _parse_field(parts[0], 0, 59)
    hour = _parse_field(parts[1], 0, 23)
    day_of_month = _parse_field(parts[2], 1, 31)
    month = _parse_field(parts[3], 1, 12)
    day_of_week = _parse_field(parts[4], 0, 7)
    if 7 in day_of_week:
        day_of_week.add(0)
        day_of_week.remove(7)
    return minute, hour, day_of_month, month, day_of_week


def _parse_field(field: str, min_value: int, max_value: int) -> set[int]:
    values: set[int] = set()
    for token in field.split(","):
        token = token.strip()
        if not token:
            raise ValueError(f"Invalid cron token in field: {field}")
        values.update(_parse_token(token, min_value, max_value))
    if not values:
        raise ValueError(f"Field produced no values: {field}")
    return values


def _parse_token(token: str, min_value: int, max_value: int) -> set[int]:
    if "/" in token:
        base, step_raw = token.split("/", 1)
        step = _parse_int(step_raw, min_value=1, max_value=max_value - min_value + 1)
        base_values = (
            set(range(min_value, max_value + 1))
            if base == "*"
            else _parse_token(base, min_value, max_value)
        )
        start = min(base_values)
        return {v for v in sorted(base_values) if (v - start) % step == 0}

    if token == "*":
        return set(range(min_value, max_value + 1))

    if "-" in token:
        start_raw, end_raw = token.split("-", 1)
        start = _parse_int(start_raw, min_value=min_value, max_value=max_value)
        end = _parse_int(end_raw, min_value=min_value, max_value=max_value)
        if start > end:
            raise ValueError(f"Invalid range '{token}'")
        return set(range(start, end + 1))

    value = _parse_int(token, min_value=min_value, max_value=max_value)
    return {value}


def _parse_int(raw: str, min_value: int, max_value: int) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"Invalid integer '{raw}'") from exc
    if not min_value <= value <= max_value:
        raise ValueError(f"Value '{value}' outside range [{min_value}, {max_value}]")
    return value


def _python_weekday_to_cron(python_weekday: int) -> int:
    # Python: Monday=0..Sunday=6; Cron: Sunday=0..Saturday=6
    return (python_weekday + 1) % 7

