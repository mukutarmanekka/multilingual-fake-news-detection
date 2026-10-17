"""Temporal Utilities — Date normalization and freshness scoring."""

from __future__ import annotations

import re
from datetime import datetime, timezone, timedelta
from typing import Optional

from dateutil import parser as dateparser


def normalize_date(date_str: str) -> Optional[str]:
    """Normalize a date string to ISO 8601 format."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt:
            return dt.strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        pass
    return None


def parse_datetime(date_str: str) -> Optional[datetime]:
    """Parse a date string into a datetime object."""
    if not date_str:
        return None
    try:
        dt = dateparser.parse(date_str)
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, OverflowError):
        return None


def freshness_score(
    published_date: Optional[str],
    reference_date: Optional[datetime] = None,
    max_age_days: int = 365,
) -> float:
    """
    Calculate a freshness score from 0 to 1.

    Newer documents score higher. Documents older than max_age_days get 0.
    """
    if not published_date:
        return 0.3  # Unknown date gets a middling score

    pub_dt = parse_datetime(published_date)
    if not pub_dt:
        return 0.3

    ref = reference_date or datetime.now(timezone.utc)
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=timezone.utc)

    age = ref - pub_dt
    age_days = max(age.total_seconds() / 86400, 0)

    if age_days > max_age_days:
        return 0.0
    if age_days < 1:
        return 1.0

    # Exponential decay — recent articles score much higher
    score = max(0.0, 1.0 - (age_days / max_age_days) ** 0.5)
    return round(score, 3)


def extract_dates_from_text(text: str) -> list[str]:
    """Extract date-like strings from text using patterns."""
    patterns = [
        r'\b\d{4}-\d{2}-\d{2}\b',           # ISO format
        r'\b\d{1,2}/\d{1,2}/\d{4}\b',        # US format
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b',
        r'\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b',
    ]

    dates = []
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            normalized = normalize_date(match)
            if normalized and normalized not in dates:
                dates.append(normalized)

    return dates


def is_time_sensitive(claim_text: str) -> bool:
    """Determine if a claim is time-sensitive (should prefer fresher evidence)."""
    time_indicators = [
        "today", "yesterday", "this week", "this month",
        "just", "recently", "breaking", "latest",
        "announced", "confirmed", "declared", "reported",
        "hours ago", "minutes ago",
    ]
    lower = claim_text.lower()
    return any(ind in lower for ind in time_indicators)
