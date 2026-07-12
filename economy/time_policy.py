from datetime import datetime, timedelta, timezone


JAKARTA = timezone(timedelta(hours=7), name="Asia/Jakarta")


def utc_datetime(value=None):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            raise ValueError("timestamp kosong")
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JAKARTA)
    return parsed.astimezone(timezone.utc)


def utc_iso(value=None):
    return utc_datetime(value).isoformat()


def jakarta_date(value=None):
    return utc_datetime(value).astimezone(JAKARTA).date().isoformat()


def add_seconds(value, seconds):
    return utc_iso(utc_datetime(value) + timedelta(seconds=int(seconds)))


def remaining_seconds(next_eligible_at, now=None):
    if not next_eligible_at:
        return 0
    remaining = (utc_datetime(next_eligible_at) - utc_datetime(now)).total_seconds()
    return max(0, int(remaining))
