from datetime import datetime, timedelta, timezone

def now(utc_offset: int = 8):
    return datetime.now(tz=timezone(timedelta(hours=utc_offset)))

def now_iso(utc_offset: int = 8):
    return now(utc_offset).isoformat()