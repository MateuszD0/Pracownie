"""User-selected local scan time, separate from historical report deadlines."""
from datetime import time

PRIMARY_START = time(9)
BACKUP_START = time(10, 30)
READINESS_CHECK = time(10, 50)
START_TIME_EFFECTIVE_DAY = '2026-11-20'


def publication_deadline(day: str) -> time | None:
    # From 20 November the request is a 09:00 start, not a publication deadline.
    # Keep old reports' original delivery goal rather than rewriting history.
    return time(8) if day < START_TIME_EFFECTIVE_DAY else None
