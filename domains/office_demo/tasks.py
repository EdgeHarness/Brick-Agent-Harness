"""Frozen prompts and capability labels for the 12 synthetic office tasks.

Executable graders live in ``strict_graders`` and are bound by ``pack``. Task
metadata intentionally contains no live-world scoring callback.
"""


TASKS = [
    {"id": "pptx_basic", "caps": ["powerpoint"],
     "prompt": "Create a PowerPoint file named q3_review.pptx with exactly 5 slides in this order: "
               "(1) a title slide 'Q3 Business Review', (2) 'Agenda', (3) 'Sales', (4) 'Marketing', "
               "(5) 'Next Steps'. Slides 2 through 5 must each have at least 3 bullet points."},
    {"id": "pptx_from_email", "caps": ["powerpoint", "email"],
     "prompt": "Dana emailed me the final Q3 sales numbers. Create sales_summary.pptx with a title "
               "slide, then one slide per region (West, East, Online), each showing that region's "
               "revenue as a bullet point."},
    {"id": "xlsx_basic", "caps": ["excel"],
     "prompt": "Create budget.xlsx with two columns, Item and Cost, containing: Laptops 3200, "
               "Software licenses 1150, Training 800, Travel 2400. Add a final Total row with the sum."},
    {"id": "xlsx_from_email", "caps": ["excel", "email"],
     "prompt": "Find the three purchase receipts in my inbox and create expenses.xlsx with columns "
               "Date, Vendor, Amount - one row per receipt - plus a final Total row."},
    {"id": "email_reply", "caps": ["email"],
     "prompt": "Look through my inbox for the most recent email about the Northwind project and "
               "send a reply to its sender confirming that I will attend the kickoff."},
    {"id": "cal_add", "caps": ["calendar_write"],
     "prompt": "Add a meeting called 'Design sync' to my calendar on Tuesday July 21 from 2pm to 3pm "
               "with attendees alice@corp.com and bob@corp.com."},
    {"id": "cal_freeslot", "caps": ["calendar_write", "thinking"],
     "prompt": "Find a free one-hour slot in my calendar on Thursday July 23 between 9:00 and 17:00 "
               "and book it as 'Deep work'."},
    {"id": "cal_brief", "caps": ["calendar_read", "messaging", "thinking"],
     "prompt": "Check my calendar for Wednesday July 22 and send Jordan a chat message summarizing "
               "my meetings that day in chronological order."},
    {"id": "remind_msg", "caps": ["reminders", "messaging"],
     "prompt": "Set a reminder for Friday July 24 at 3pm to submit the TPS report, and send Casey a "
               "message letting them know the TPS report will be done by end of day Friday."},
    {"id": "learn_store", "caps": ["learning"],
     "prompt": "Please remember these preferences for all future scheduling: I like meetings to be "
               "25 minutes long, and I never schedule anything before 10am."},
    {"id": "learn_use", "caps": ["learning", "calendar_write"],
     "prompt": "Book a quick sync with Priya tomorrow morning."},
    {"id": "multi_offsite", "caps": ["email", "calendar_write", "powerpoint"],
     "prompt": "The CEO emailed about the summer offsite. Add it to my calendar, reply to confirm "
               "I'll be there, and create a one-slide offsite.pptx titled 'Summer Offsite' with the "
               "date, time, and location as bullet points."},
]
