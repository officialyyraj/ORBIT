from datetime import datetime, timezone
import math
from app.config import get_settings

def retention_value(last_updated: datetime | None, now: datetime | None = None) -> float:
    if last_updated is None:
        return 1.0
    now = now or datetime.now(timezone.utc)
    if last_updated.tzinfo is None:
        last_updated = last_updated.replace(tzinfo=timezone.utc)
    days = max(0.0, (now - last_updated).total_seconds() / 86400)
    return math.exp(-math.log(2) * days / get_settings().retention_half_life_days)

def retention_penalty(last_updated: datetime | None, now: datetime | None = None) -> float:
    if last_updated is None:
        return 0.0
    retention = retention_value(last_updated, now)
    threshold = get_settings().retention_threshold
    return max(0.0, min(1.0, (threshold - retention) / threshold))
