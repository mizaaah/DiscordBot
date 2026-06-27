import re
from datetime import timedelta

DURATION_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
UNIT_LABELS = {"s": "seconde(s)", "m": "minute(s)", "h": "heure(s)", "d": "jour(s)", "w": "semaine(s)"}


def parse_duration(duration_str: str) -> tuple[int, timedelta]:
    """Parse a duration string like '10m', '2h', '1d' into (seconds, timedelta)."""
    match = re.fullmatch(r"(\d+)([smhdw])", duration_str.lower())
    if not match:
        raise ValueError("Format invalide. Utilisez: `10s`, `5m`, `2h`, `1d`, `1w`")
    value, unit = int(match.group(1)), match.group(2)
    if value <= 0:
        raise ValueError("La durée doit être supérieure à 0.")
    seconds = value * DURATION_UNITS[unit]
    return seconds, timedelta(seconds=seconds)


def duration_to_str(duration_str: str) -> str:
    """Convert a duration string to a human-readable French string."""
    match = re.fullmatch(r"(\d+)([smhdw])", duration_str.lower())
    if not match:
        return duration_str
    value, unit = int(match.group(1)), match.group(2)
    return f"{value} {UNIT_LABELS[unit]}"


def xp_for_level(level: int) -> int:
    """XP needed to reach a given level (MEE6-style formula)."""
    return 5 * (level ** 2) + 50 * level + 100


def total_xp_for_level(level: int) -> int:
    """Total XP accumulated to reach a given level."""
    return sum(xp_for_level(i) for i in range(level))
