from datetime import datetime
from typing import Optional


def current_time_hms() -> str:
    """Get current local timestamp in HH:MM:SS format."""
    return datetime.now().strftime("%H:%M:%S")


def format_updated_at(raw_timestamp: Optional[str]) -> str:
    """Format an ISO-like timestamp for UI display in HH:MM:SS."""
    if not raw_timestamp:
        return current_time_hms()

    normalized = raw_timestamp.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%H:%M:%S")
    except ValueError:
        return raw_timestamp
