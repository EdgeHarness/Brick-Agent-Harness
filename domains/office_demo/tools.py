"""Office-demo tool specifications."""
from . import office_files


def office_specs():
    return {
        "list_emails": {
            "desc": "List all emails in the inbox (id, from, date, subject). Newest first.",
            "params": {},
            "example": {"tool": "list_emails", "args": {}},
            "run": lambda c, a: c.world.list_emails(),
        },
        "read_email": {
            "desc": "Read the full body of one email by its id.",
            "params": {"id": ("string, an email id like 'e3'", True)},
            "example": {"tool": "read_email", "args": {"id": "e2"}},
            "run": lambda c, a: c.world.read_email(a["id"]),
        },
        "send_email": {
            "desc": "Send an email.",
            "params": {
                "to": ("string, recipient address", True),
                "subject": ("string", True),
                "body": ("string", True),
            },
            "example": {
                "tool": "send_email",
                "args": {
                    "to": "dana@corp.com",
                    "subject": "Re: numbers",
                    "body": "Got it, thanks!",
                },
            },
            "run": lambda c, a: c.world.send_email(
                a["to"], a.get("subject", ""), a.get("body", "")
            ),
        },
        "list_events": {
            "desc": "List calendar events, optionally only for one date.",
            "params": {
                "date": (
                    "string YYYY-MM-DD, optional - omit for all events",
                    False,
                )
            },
            "example": {
                "tool": "list_events",
                "args": {"date": "2026-07-22"},
            },
            "run": lambda c, a: c.world.list_events(a.get("date")),
        },
        "add_event": {
            "desc": "Add an event to the calendar.",
            "params": {
                "title": ("string", True),
                "date": ("string YYYY-MM-DD", True),
                "start_time": ("string 24h HH:MM", True),
                "end_time": ("string 24h HH:MM", True),
                "attendees": ("list of email strings, optional", False),
                "location": ("string, optional", False),
            },
            "example": {
                "tool": "add_event",
                "args": {
                    "title": "Budget review",
                    "date": "2026-07-21",
                    "start_time": "13:00",
                    "end_time": "14:00",
                    "attendees": ["sam@corp.com"],
                },
            },
            "run": lambda c, a: c.world.add_event(
                a["title"],
                a["date"],
                a["start_time"],
                a["end_time"],
                a.get("attendees"),
                a.get("location"),
            ),
        },
        "send_message": {
            "desc": "Send a chat/instant message to a person.",
            "params": {
                "to": ("string, contact name", True),
                "text": ("string, the message", True),
            },
            "example": {
                "tool": "send_message",
                "args": {"to": "sam", "text": "Running 5 min late."},
            },
            "run": lambda c, a: c.world.send_message(a["to"], a["text"]),
        },
        "set_reminder": {
            "desc": "Set a reminder for yourself at a specific date and time.",
            "params": {
                "text": ("string, what to be reminded of", True),
                "date": ("string YYYY-MM-DD", True),
                "time": ("string 24h HH:MM", True),
            },
            "example": {
                "tool": "set_reminder",
                "args": {
                    "text": "send invoice",
                    "date": "2026-07-22",
                    "time": "09:00",
                },
            },
            "run": lambda c, a: c.world.set_reminder(
                a["text"], a["date"], a["time"]
            ),
        },
        "create_presentation": {
            "desc": "Create a real .pptx PowerPoint file. Each slide is an object with a "
                    "'title' and an optional 'bullets' list. A first slide without bullets "
                    "becomes a title slide.",
            "params": {
                "filename": ("string ending in .pptx", True),
                "slides": (
                    'list of {"title": str, "bullets": [str, ...]}',
                    True,
                ),
            },
            "example": {
                "tool": "create_presentation",
                "args": {
                    "filename": "plan.pptx",
                    "slides": [
                        {"title": "2027 Plan"},
                        {
                            "title": "Goals",
                            "bullets": ["Grow 20%", "Ship v2", "Hire 3"],
                        },
                    ],
                },
            },
            "run": lambda c, a: office_files.create_presentation(
                c.world.files_dir, a["filename"], a["slides"]
            ),
        },
        "create_spreadsheet": {
            "desc": "Create a real .xlsx Excel file from a list of rows (first row is usually "
                    "headers). A cell string starting with '=' becomes a formula.",
            "params": {
                "filename": ("string ending in .xlsx", True),
                "rows": (
                    "list of rows, each row a list of cell values",
                    True,
                ),
                "sheet_name": ("string, optional", False),
            },
            "example": {
                "tool": "create_spreadsheet",
                "args": {
                    "filename": "costs.xlsx",
                    "rows": [
                        ["Item", "Cost"],
                        ["Chairs", 400],
                        ["Desks", 900],
                        ["Total", "=SUM(B2:B3)"],
                    ],
                },
            },
            "run": lambda c, a: office_files.create_spreadsheet(
                c.world.files_dir,
                a["filename"],
                a["rows"],
                a.get("sheet_name"),
            ),
        },
        "read_spreadsheet": {
            "desc": "Read back the cell contents of an existing .xlsx file.",
            "params": {"filename": ("string ending in .xlsx", True)},
            "example": {
                "tool": "read_spreadsheet",
                "args": {"filename": "costs.xlsx"},
            },
            "run": lambda c, a: office_files.read_spreadsheet(
                c.world.files_dir, a["filename"]
            ),
        },
    }


OFFICE_EFFECTS = {
    "list_emails": "read",
    "read_email": "read",
    "send_email": "state_write",
    "list_events": "read",
    "add_event": "state_write",
    "send_message": "state_write",
    "set_reminder": "state_write",
    "create_presentation": "state_write",
    "create_spreadsheet": "state_write",
    "read_spreadsheet": "read",
}
