"""Legacy office date/time argument normalization."""
import datetime
import re


_WEEKDAYS = [
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
]
_MONTHS = {
    month: index + 1
    for index, month in enumerate(
        [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ]
    )
}


def normalize_date(value, today):
    if not isinstance(value, str):
        return value
    text = value.strip().lower()
    if re.match(r"^\d{4}-\d{2}-\d{2}$", text):
        return text
    if text == "today":
        return today.isoformat()
    if text == "tomorrow":
        return (today + datetime.timedelta(days=1)).isoformat()
    match = re.match(r"^(?:next\s+)?([a-z]+day)$", text)
    if match and match.group(1) in _WEEKDAYS:
        delta = (
            _WEEKDAYS.index(match.group(1)) - today.weekday()
        ) % 7 or 7
        return (today + datetime.timedelta(days=delta)).isoformat()
    match = re.match(
        r"^([a-z]+)\.?\s+(\d{1,2})(?:st|nd|rd|th)?"
        r"(?:,?\s*(\d{4}))?$",
        text,
    )
    if match:
        for name, number in _MONTHS.items():
            if name.startswith(match.group(1)):
                year = int(match.group(3)) if match.group(3) else today.year
                return (
                    f"{year:04d}-{number:02d}-{int(match.group(2)):02d}"
                )
    match = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?$", text)
    if match:
        year = int(match.group(3)) if match.group(3) else today.year
        if year < 100:
            year += 2000
        return (
            f"{year:04d}-{int(match.group(1)):02d}-"
            f"{int(match.group(2)):02d}"
        )
    return value


def normalize_time(value):
    if not isinstance(value, str):
        return value
    text = value.strip().lower().replace(".", "")
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", text)
    if not match:
        return value
    hour = int(match.group(1))
    minutes = match.group(2) or "00"
    meridiem = match.group(3)
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or int(minutes) > 59:
        return value
    return f"{hour:02d}:{minutes}"


def normalize_args(name, args, today):
    if not isinstance(args, dict):
        return args
    normalized = dict(args)
    for key in normalized:
        if key == "date":
            normalized[key] = normalize_date(normalized[key], today)
        elif key in ("start_time", "end_time", "time"):
            normalized[key] = normalize_time(normalized[key])
    return normalized
