from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def business_date_for(moment: datetime, tz_name: str, day_end: time) -> date:
    """BR-047: before the branch day-end time, sales belong to the previous business day."""
    local = moment.astimezone(ZoneInfo(tz_name))
    if local.time() < day_end:
        return (local - timedelta(days=1)).date()
    return local.date()
