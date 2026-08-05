# Brick office-task review packets

Review each task independently. Do not use generative AI and do not discuss
an unfinished case with another reviewer. Record your answer in
`RESPONSES.csv`; do not edit this packet file.

## Packet 01

Packet ID: `060299705930c07ac88330798e7e63262d242e7056f190d0b12773452559f58d`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [
      "subject=hale.dovetailpreferencelearning4100@office-v2.example status=expired distractor=1 ignore=true",
      "subject=hale.dovetailpreferencelearning4100@office-v2.example status=expired distractor=2 ignore=true"
    ],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": null,
  "subepisode_prompts": [
    "For subject hale.dovetailpreferencelearning4100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_specific_scope and save exactly one memory containing only the selected bundle's applicable facts: subject=hale.dovetailpreferencelearning4100@office-v2.example | duration_minutes=30 | earliest_start=12:00 | location=Studio | weekday=Tuesday.",
    "Schedule exactly one sync with Hale DovetailPreferenceLearning4100 on 2028-10-17. The attendee is hale.dovetailpreferencelearning4100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-10-16"
}
```

## Packet 02

Packet ID: `1000642378d30986ec76cc0262b454a957751978493eac55bfa48fa6098235c1`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-01-22",
        "end": "09:30",
        "id": "busy-0",
        "location": "",
        "start": "09:00",
        "title": "Busy block 1"
      },
      {
        "attendees": [],
        "date": "2028-01-22",
        "end": "10:30",
        "id": "busy-1",
        "location": "",
        "start": "10:00",
        "title": "Busy block 2"
      },
      {
        "attendees": [],
        "date": "2028-01-22",
        "end": "11:30",
        "id": "busy-2",
        "location": "",
        "start": "11:00",
        "title": "Busy block 3"
      },
      {
        "attendees": [],
        "date": "2028-01-22",
        "end": "12:30",
        "id": "busy-3",
        "location": "",
        "start": "12:00",
        "title": "Busy block 4"
      },
      {
        "attendees": [],
        "date": "2028-01-22",
        "end": "13:30",
        "id": "busy-4",
        "location": "",
        "start": "13:00",
        "title": "Busy block 5"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-01-22. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose earliest_free; the preferred start is 13:30. Add exactly one event titled 'Demi LatticeCalFreeslot0200 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-01-17"
}
```

## Packet 03

Packet ID: `17082d6c485eda2cd80aa983442a3452469c4553b7ffec66a3911d3311762004`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "DECISION: selection_key=KEY-18-A; confirmation_code=CONF-18; confirmation_date=2028-05-13.",
        "date": "2028-05-03 10:00",
        "from": "orla.kestrelemailreply1800@office-v2.example",
        "id": "required-decision",
        "subject": "Initiative DovetailEmailReply1800 / REQUIRED /DECISION"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=4; decision_key=KEY-18-A; request_id=attendance-0.",
        "date": "2028-05-04 10:00",
        "from": "jori.fableemailreply1800@office-v2.example",
        "id": "attendance-0",
        "subject": "Initiative DovetailEmailReply1800 / REQUIRED /ATTENDANCE attendance-0"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=9; decision_key=KEY-18-B; request_id=attendance-1.",
        "date": "2028-05-05 10:00",
        "from": "orla.fableemailreply1801@office-v2.example",
        "id": "attendance-1",
        "subject": "Initiative DovetailEmailReply1800 / REQUIRED /ATTENDANCE attendance-1"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=1; decision_key=KEY-18-C; request_id=attendance-2.",
        "date": "2028-05-07 10:00",
        "from": "demi.fableemailreply1802@office-v2.example",
        "id": "attendance-2",
        "subject": "Initiative DovetailEmailReply1800 / REQUIRED /ATTENDANCE attendance-2"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative DovetailEmailReply1800 / REQUIRED /'. Select exactly one request using policy highest_priority. Reply exactly once to that request's sender. Subject must contain 'Initiative DovetailEmailReply1800'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id. Do not reply to any other sender.",
  "subepisode_prompts": [],
  "today": "2028-05-08"
}
```

## Packet 04

Packet ID: `1b4383ee2e7770debb325a207d80419d4284464da5cd5bd631a2fc65994d25bd`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "CANDIDATES: id=offsite-final-a,issued_rank=3,approval_rank=4,consensus=1 | id=offsite-final-b,issued_rank=2,approval_rank=9,consensus=2 | id=offsite-final-c,issued_rank=1,approval_rank=3,consensus=9.",
        "date": "2028-10-28",
        "from": "iris.indigomultioffsite4300@office-v2.example",
        "id": "offsite-index",
        "subject": "OFFSITE SOURCE INDEX Initiative CinderMultiOffsite4300"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative CinderMultiOffsite4300 Summit A; date=2028-11-09; start=09:00; end=15:30; location=FableMultiOffsite4300 Collaboration Hall; facts=2028-11-09 | 09:00-15:30 | FableMultiOffsite4300 Collaboration Hall | business casual | bring identification | lunch provided.",
        "date": "2028-10-27",
        "from": "demi.dovetailmultioffsite4300@office-v2.example",
        "id": "offsite-final-a",
        "subject": "FINAL OFFSITE DETAIL offsite-final-a"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative CinderMultiOffsite4300 Summit B; date=2028-11-10; start=10:00; end=16:30; location=FableMultiOffsite4301 Collaboration Hall; facts=2028-11-10 | 10:00-16:30 | FableMultiOffsite4301 Collaboration Hall | formal | bring identification | lunch provided.",
        "date": "2028-10-28",
        "from": "iris.dovetailmultioffsite4301@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative CinderMultiOffsite4300 Summit C; date=2028-11-11; start=11:00; end=17:30; location=FableMultiOffsite4302 Collaboration Hall; facts=2028-11-11 | 11:00-17:30 | FableMultiOffsite4302 Collaboration Hall | field attire | bring identification | lunch provided.",
        "date": "2028-10-29",
        "from": "niko.dovetailmultioffsite4302@office-v2.example",
        "id": "offsite-final-c",
        "subject": "FINAL OFFSITE DETAIL offsite-final-c"
      },
      {
        "body": "Superseded draft logistics.",
        "date": "2028-10-20",
        "from": "iris.indigomultioffsite4300@office-v2.example",
        "id": "offsite-draft-0",
        "subject": "DRAFT OFFSITE Initiative CinderMultiOffsite4300 00"
      },
      {
        "body": "Superseded draft logistics.",
        "date": "2028-10-19",
        "from": "iris.indigomultioffsite4300@office-v2.example",
        "id": "offsite-draft-1",
        "subject": "DRAFT OFFSITE Initiative CinderMultiOffsite4300 01"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative CinderMultiOffsite4300'. Select one detail source using policy consensus_supported, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_43_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 05

Packet ID: `1b9ab4287bc732ceb3c2595c82045e635488f366f49ff2f9c336ee2b124ee7bb`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "Region: North; Revenue cents: 14749000; Sequence: 1; Status: FINAL.",
        "date": "2028-03-30 09:00",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "approved-region-1",
        "subject": "APPROVED REGION Initiative DovetailPptxFromEmail1300 / 01"
      },
      {
        "body": "Region: South; Revenue cents: 14922000; Sequence: 2; Status: FINAL.",
        "date": "2028-03-31 09:00",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "approved-region-2",
        "subject": "APPROVED REGION Initiative DovetailPptxFromEmail1300 / 02"
      },
      {
        "body": "Region: Central; Revenue cents: 15095000; Sequence: 3; Status: FINAL.",
        "date": "2028-04-01 09:00",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "approved-region-3",
        "subject": "APPROVED REGION Initiative DovetailPptxFromEmail1300 / 03"
      },
      {
        "body": "Region: Online; Revenue cents: 15268000; Sequence: 4; Status: FINAL.",
        "date": "2028-04-02 09:00",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "approved-region-4",
        "subject": "APPROVED REGION Initiative DovetailPptxFromEmail1300 / 04"
      },
      {
        "body": "Preliminary figures. Status: SUPERSEDED.",
        "date": "2028-03-14",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "draft-region-0",
        "subject": "DRAFT REGION Initiative DovetailPptxFromEmail1300 / 01"
      },
      {
        "body": "Preliminary figures. Status: SUPERSEDED.",
        "date": "2028-03-13",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "draft-region-1",
        "subject": "DRAFT REGION Initiative DovetailPptxFromEmail1300 / 02"
      },
      {
        "body": "Preliminary figures. Status: SUPERSEDED.",
        "date": "2028-03-12",
        "from": "demi.dovetailpptxfromemail1300@office-v2.example",
        "id": "draft-region-2",
        "subject": "DRAFT REGION Initiative DovetailPptxFromEmail1300 / 03"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative DovetailPptxFromEmail1300 /'. Then create office_13_regions.pptx with title slide 'Initiative DovetailPptxFromEmail1300 Revenue Review', followed by one slide per approved email ordered by policy sequence_ascending. Use Region as each slide title and include the exact Revenue cents value. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 06

Packet ID: `1c4535776a600c6f1961f23878cab254a28a183da6f14dfd3dcc0881fc877294`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "DECISION: selection_key=KEY-20-A; confirmation_code=CONF-20; confirmation_date=2028-05-27.",
        "date": "2028-05-17 10:00",
        "from": "mara.emberemailreply2000@office-v2.example",
        "id": "required-decision",
        "subject": "Initiative JuniperEmailReply2000 / REQUIRED /DECISION"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=4; decision_key=KEY-20-A; request_id=attendance-0.",
        "date": "2028-05-18 10:00",
        "from": "hale.latticeemailreply2000@office-v2.example",
        "id": "attendance-0",
        "subject": "Initiative JuniperEmailReply2000 / REQUIRED /ATTENDANCE attendance-0"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=9; decision_key=KEY-20-B; request_id=attendance-1.",
        "date": "2028-05-19 10:00",
        "from": "mara.latticeemailreply2001@office-v2.example",
        "id": "attendance-1",
        "subject": "Initiative JuniperEmailReply2000 / REQUIRED /ATTENDANCE attendance-1"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=1; decision_key=KEY-20-C; request_id=attendance-2.",
        "date": "2028-05-21 10:00",
        "from": "bryn.latticeemailreply2002@office-v2.example",
        "id": "attendance-2",
        "subject": "Initiative JuniperEmailReply2000 / REQUIRED /ATTENDANCE attendance-2"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-05-21",
        "from": "kavi.cinderemailreply2000@office-v2.example",
        "id": "unrelated-0",
        "subject": "Initiative JuniperEmailReply2000 FYI 00"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative JuniperEmailReply2000 / REQUIRED /'. Select exactly one request using policy highest_priority. Reply exactly once to that request's sender. Subject must contain 'Initiative JuniperEmailReply2000'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id. Do not reply to any other sender.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 07

Packet ID: `24974410b816d0ad5772baa1202d87f8b318a0db80594e54940d6528d3d7585a`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "CANDIDATES: id=offsite-final-a,issued_rank=3,approval_rank=4,consensus=1 | id=offsite-final-b,issued_rank=2,approval_rank=9,consensus=2 | id=offsite-final-c,issued_rank=1,approval_rank=3,consensus=9.",
        "date": "2028-01-01",
        "from": "bryn.fablemultioffsite0000@office-v2.example",
        "id": "offsite-index",
        "subject": "OFFSITE SOURCE INDEX Initiative LatticeMultiOffsite0000"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative LatticeMultiOffsite0000 Summit A; date=2028-01-13; start=09:00; end=15:30; location=CinderMultiOffsite0000 Collaboration Hall; facts=2028-01-13 | 09:00-15:30 | CinderMultiOffsite0000 Collaboration Hall.",
        "date": "2027-12-31",
        "from": "mara.astermultioffsite0000@office-v2.example",
        "id": "offsite-final-a",
        "subject": "FINAL OFFSITE DETAIL offsite-final-a"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative LatticeMultiOffsite0000 Summit B; date=2028-01-14; start=10:00; end=16:30; location=CinderMultiOffsite0001 Collaboration Hall; facts=2028-01-14 | 10:00-16:30 | CinderMultiOffsite0001 Collaboration Hall.",
        "date": "2028-01-01",
        "from": "bryn.astermultioffsite0001@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative LatticeMultiOffsite0000 Summit C; date=2028-01-15; start=11:00; end=17:30; location=CinderMultiOffsite0002 Collaboration Hall; facts=2028-01-15 | 11:00-17:30 | CinderMultiOffsite0002 Collaboration Hall.",
        "date": "2028-01-02",
        "from": "gaia.astermultioffsite0002@office-v2.example",
        "id": "offsite-final-c",
        "subject": "FINAL OFFSITE DETAIL offsite-final-c"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative LatticeMultiOffsite0000'. Select one detail source using policy latest_issued, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_00_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 08

Packet ID: `25e8a781c557148f362c547b1d50c051ca36468b7623521e8c8f13a3a1eb0541`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [
      {
        "date": "2028-06-13",
        "text": "Existing reminder 1",
        "time": "08:00"
      }
    ],
    "sent_emails": []
  },
  "prompt": "Action items: id=checkpoint-1,due=2028-06-15,priority=5,depends_on=checkpoint-3 | id=checkpoint-2,due=2028-06-16,priority=9,depends_on=checkpoint-1 | id=checkpoint-3,due=2028-06-17,priority=7,depends_on=none | id=checkpoint-4,due=2028-06-18,priority=4,depends_on=checkpoint-2 | id=checkpoint-5,due=2028-06-19,priority=3,depends_on=checkpoint-4 | id=checkpoint-6,due=2028-06-20,priority=2,depends_on=checkpoint-5. Order them using policy priority_descending. Create exactly one reminder at 14:00 on the first ordered item's due date. Required checklist mentions in that order: checkpoint-2 | checkpoint-3 | checkpoint-1 | checkpoint-4 | checkpoint-5 | checkpoint-6. Then send exactly one chat message to Gaia KestrelRemindMsg2300 repeating those mentions in order and committing that the full checklist will be complete by the deadline. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-06-12"
}
```

## Packet 09

Packet ID: `2c62afcc2af5c977d0674f3a25045e85405fef70e2fe12256f5fb20b7f349640`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [
      {
        "date": "2028-05-23",
        "text": "Existing reminder 1",
        "time": "08:00"
      }
    ],
    "sent_emails": []
  },
  "prompt": "Action items: id=checkpoint-1,due=2028-05-25,priority=5,depends_on=checkpoint-3 | id=checkpoint-2,due=2028-05-26,priority=9,depends_on=checkpoint-1 | id=checkpoint-3,due=2028-05-27,priority=7,depends_on=none. Order them using policy priority_descending. Create exactly one reminder at 14:00 on the first ordered item's due date. Required checklist mentions in that order: checkpoint-2 | checkpoint-3 | checkpoint-1. Then send exactly one chat message to Iris AsterRemindMsg2000 repeating those mentions in order and committing that the full checklist will be complete by the deadline. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 10

Packet ID: `2e36475acc20106e147fa9ff716cbaf1b4f99be47ff16169f697f5e31757957e`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-06-17",
        "end": "09:30",
        "id": "busy-0",
        "location": "",
        "start": "09:00",
        "title": "Busy block 1"
      },
      {
        "attendees": [],
        "date": "2028-06-17",
        "end": "10:30",
        "id": "busy-1",
        "location": "",
        "start": "10:00",
        "title": "Busy block 2"
      },
      {
        "attendees": [],
        "date": "2028-06-17",
        "end": "11:30",
        "id": "busy-2",
        "location": "",
        "start": "11:00",
        "title": "Busy block 3"
      },
      {
        "attendees": [],
        "date": "2028-06-17",
        "end": "12:30",
        "id": "busy-3",
        "location": "",
        "start": "12:00",
        "title": "Busy block 4"
      },
      {
        "attendees": [],
        "date": "2028-06-17",
        "end": "13:30",
        "id": "busy-4",
        "location": "",
        "start": "13:00",
        "title": "Busy block 5"
      },
      {
        "attendees": [],
        "date": "2028-06-17",
        "end": "14:30",
        "id": "busy-5",
        "location": "",
        "start": "14:00",
        "title": "Busy block 6"
      },
      {
        "attendees": [],
        "date": "2028-06-18",
        "end": "11:00",
        "id": "other-day-0",
        "location": "",
        "start": "10:00",
        "title": "Other date 1"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-06-17. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose latest_free; the preferred start is 13:30. Add exactly one event titled 'Gaia GroveCalFreeslot2300 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-06-12"
}
```

## Packet 11

Packet ID: `2f55396d42cee6f508de211652c6ad59878b05e31b2829f58bb997d84378287e`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-06-23",
        "end": "08:30",
        "id": "adjacent-0",
        "location": "",
        "start": "08:00",
        "title": "Existing block 1"
      },
      {
        "attendees": [],
        "date": "2028-06-23",
        "end": "09:00",
        "id": "adjacent-1",
        "location": "",
        "start": "08:30",
        "title": "Existing block 2"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-06-23. Candidate requests: id=candidate-A,title=Iris IndigoCalAdd2400 candidate-A design review,start=10:00,duration=45,priority=5,location=HarborCalAdd2400 Collaboration Hall | id=candidate-B,title=Iris IndigoCalAdd2400 candidate-B design review,start=11:00,duration=60,priority=9,location=HarborCalAdd2401 Collaboration Hall | id=candidate-C,title=Iris IndigoCalAdd2400 candidate-C design review,start=12:30,duration=30,priority=4,location=HarborCalAdd2402 Collaboration Hall. Select one feasible request using policy highest_priority_feasible and add exactly one event with that candidate's exact title, time, location, and these attendees: hale.harborcaladd2400@office-v2.example | mara.harborcaladd2401@office-v2.example | bryn.harborcaladd2402@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-06-19"
}
```

## Packet 12

Packet ID: `3e44bc062a0d8d104d5eda605d54e29ebe6283178b75ab74866e6975361f98f9`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create spreadsheet office_30_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Mara IndigoXlsxBasic3000,Item=Training,Cost=4675 | Owner=Mara IndigoXlsxBasic3000,Item=Equipment,Cost=4800 | Owner=Mara IndigoXlsxBasic3000,Item=Licenses,Cost=4925 | Owner=Mara IndigoXlsxBasic3000,Item=Travel,Cost=5050 | Owner=Mara IndigoXlsxBasic3000,Item=Research,Cost=5175. Row order rule: cost_descending. Add exactly one final Total row using a formula.",
  "subepisode_prompts": [],
  "today": "2028-07-31"
}
```

## Packet 13

Packet ID: `4bfa05d487ad979e4538ce93b675c8729cc0b47a5c20f3efa71a58abb37eabde`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-04-01",
        "end": "09:30",
        "id": "busy-0",
        "location": "",
        "start": "09:00",
        "title": "Busy block 1"
      },
      {
        "attendees": [],
        "date": "2028-04-01",
        "end": "10:30",
        "id": "busy-1",
        "location": "",
        "start": "10:00",
        "title": "Busy block 2"
      },
      {
        "attendees": [],
        "date": "2028-04-01",
        "end": "11:30",
        "id": "busy-2",
        "location": "",
        "start": "11:00",
        "title": "Busy block 3"
      },
      {
        "attendees": [],
        "date": "2028-04-02",
        "end": "11:00",
        "id": "other-day-0",
        "location": "",
        "start": "10:00",
        "title": "Other date 1"
      },
      {
        "attendees": [],
        "date": "2028-04-03",
        "end": "11:00",
        "id": "other-day-1",
        "location": "",
        "start": "10:00",
        "title": "Other date 2"
      },
      {
        "attendees": [],
        "date": "2028-04-04",
        "end": "11:00",
        "id": "other-day-2",
        "location": "",
        "start": "10:00",
        "title": "Other date 3"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-04-01. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose earliest_free; the preferred start is 13:30. Add exactly one event titled 'Gaia KestrelCalFreeslot1200 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-03-27"
}
```

## Packet 14

Packet ID: `4f94bec1d5c1f4a9f4c8a47346cb38e77682dc7eb6db3542d336060b2a9f7f3f`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "PAID RECEIPT: date=2028-08-23,vendor=IndigoXlsxFromEmail3402 Supply Group,amount_cents=9158. STATUS: FINAL.",
        "date": "2028-08-23 16:00",
        "from": "amal.asterxlsxfromemail3400@office-v2.example",
        "id": "paid-receipt-0",
        "subject": "FINAL PAID RECEIPT CASE 34 / 01"
      },
      {
        "body": "PAID RECEIPT: date=2028-08-24,vendor=IndigoXlsxFromEmail3400 Supply Group,amount_cents=9432. STATUS: FINAL.",
        "date": "2028-08-24 16:00",
        "from": "amal.asterxlsxfromemail3400@office-v2.example",
        "id": "paid-receipt-1",
        "subject": "FINAL PAID RECEIPT CASE 34 / 02"
      },
      {
        "body": "PAID RECEIPT: date=2028-08-25,vendor=IndigoXlsxFromEmail3401 Supply Group,amount_cents=9706. STATUS: FINAL.",
        "date": "2028-08-25 16:00",
        "from": "amal.asterxlsxfromemail3400@office-v2.example",
        "id": "paid-receipt-2",
        "subject": "FINAL PAID RECEIPT CASE 34 / 03"
      },
      {
        "body": "PAID RECEIPT: date=2028-08-26,vendor=IndigoXlsxFromEmail3403 Supply Group,amount_cents=9980. STATUS: FINAL.",
        "date": "2028-08-26 16:00",
        "from": "amal.asterxlsxfromemail3400@office-v2.example",
        "id": "paid-receipt-3",
        "subject": "FINAL PAID RECEIPT CASE 34 / 04"
      },
      {
        "body": "PAID RECEIPT: date=2028-08-27,vendor=IndigoXlsxFromEmail3405 Supply Group,amount_cents=10254. STATUS: FINAL.",
        "date": "2028-08-27 16:00",
        "from": "amal.asterxlsxfromemail3400@office-v2.example",
        "id": "paid-receipt-4",
        "subject": "FINAL PAID RECEIPT CASE 34 / 05"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 34 /'. Then create office_34_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: vendor_alphabetical. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-08-28"
}
```

## Packet 15

Packet ID: `5150af6073581d5deafb5889da391d1433025b23d2e8293af30089de03a5e1b0`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "Region: North; Revenue cents: 19593000; Sequence: 1; Status: FINAL.",
        "date": "2028-10-12 09:00",
        "from": "esra.asterpptxfromemail4100@office-v2.example",
        "id": "approved-region-1",
        "subject": "APPROVED REGION Initiative AsterPptxFromEmail4100 / 01"
      },
      {
        "body": "Region: South; Revenue cents: 19766000; Sequence: 2; Status: FINAL.",
        "date": "2028-10-13 09:00",
        "from": "esra.asterpptxfromemail4100@office-v2.example",
        "id": "approved-region-2",
        "subject": "APPROVED REGION Initiative AsterPptxFromEmail4100 / 02"
      },
      {
        "body": "Region: Central; Revenue cents: 19939000; Sequence: 3; Status: FINAL.",
        "date": "2028-10-14 09:00",
        "from": "esra.asterpptxfromemail4100@office-v2.example",
        "id": "approved-region-3",
        "subject": "APPROVED REGION Initiative AsterPptxFromEmail4100 / 03"
      },
      {
        "body": "Region: Online; Revenue cents: 20112000; Sequence: 4; Status: FINAL.",
        "date": "2028-10-15 09:00",
        "from": "esra.asterpptxfromemail4100@office-v2.example",
        "id": "approved-region-4",
        "subject": "APPROVED REGION Initiative AsterPptxFromEmail4100 / 04"
      },
      {
        "body": "Preliminary figures. Status: SUPERSEDED.",
        "date": "2028-09-26",
        "from": "esra.asterpptxfromemail4100@office-v2.example",
        "id": "draft-region-0",
        "subject": "DRAFT REGION Initiative AsterPptxFromEmail4100 / 01"
      },
      {
        "body": "Preliminary figures. Status: SUPERSEDED.",
        "date": "2028-09-25",
        "from": "esra.asterpptxfromemail4100@office-v2.example",
        "id": "draft-region-1",
        "subject": "DRAFT REGION Initiative AsterPptxFromEmail4100 / 02"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative AsterPptxFromEmail4100 /'. Then create office_41_regions.pptx with title slide 'Initiative AsterPptxFromEmail4100 Revenue Review', followed by one slide per approved email ordered by policy region_alphabetical. Use Region as each slide title and include the exact Revenue cents value. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-10-16"
}
```

## Packet 16

Packet ID: `54a859b0c87eb3d5097366eb3fca7a95adb8c30ddbb34b02f9c1ecf38798891a`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "PAID RECEIPT: date=2027-12-31,vendor=GroveXlsxFromEmail0002 Supply Group,amount_cents=4500. STATUS: FINAL.",
        "date": "2027-12-31 16:00",
        "from": "gaia.kestrelxlsxfromemail0000@office-v2.example",
        "id": "paid-receipt-0",
        "subject": "FINAL PAID RECEIPT CASE 00 / 01"
      },
      {
        "body": "PAID RECEIPT: date=2028-01-01,vendor=GroveXlsxFromEmail0000 Supply Group,amount_cents=4774. STATUS: FINAL.",
        "date": "2028-01-01 16:00",
        "from": "gaia.kestrelxlsxfromemail0000@office-v2.example",
        "id": "paid-receipt-1",
        "subject": "FINAL PAID RECEIPT CASE 00 / 02"
      },
      {
        "body": "PAID RECEIPT: date=2028-01-02,vendor=GroveXlsxFromEmail0001 Supply Group,amount_cents=5048. STATUS: FINAL.",
        "date": "2028-01-02 16:00",
        "from": "gaia.kestrelxlsxfromemail0000@office-v2.example",
        "id": "paid-receipt-2",
        "subject": "FINAL PAID RECEIPT CASE 00 / 03"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 00 /'. Then create office_00_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: date_ascending. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 17

Packet ID: `57a716962ae0e39530e36f370df78bd7438d18dd26ed77138778062cbd9b7641`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create spreadsheet office_24_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Amal AsterXlsxBasic2400,Item=Training,Cost=3925 | Owner=Amal AsterXlsxBasic2400,Item=Equipment,Cost=4050 | Owner=Amal AsterXlsxBasic2400,Item=Licenses,Cost=4175. Row order rule: cost_descending. Add exactly one final Total row using a formula.",
  "subepisode_prompts": [],
  "today": "2028-06-19"
}
```

## Packet 18

Packet ID: `593630bed574d4a6b6a2cf15b2259f3cd21d49e21218afc74fa64a0d79e7ed9a`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [
      "subject=iris.asterpreferencelearning3100@office-v2.example status=expired distractor=1 ignore=true",
      "subject=iris.asterpreferencelearning3100@office-v2.example status=expired distractor=2 ignore=true",
      "subject=iris.asterpreferencelearning3100@office-v2.example status=expired distractor=3 ignore=true"
    ],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": null,
  "subepisode_prompts": [
    "For subject iris.asterpreferencelearning3100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy highest_priority and save exactly one memory containing only the selected bundle's applicable facts: subject=iris.asterpreferencelearning3100@office-v2.example | duration_minutes=25 | earliest_start=11:00 | location=Cedar room | weekday=Tuesday | title_prefix=Deep: | sole_attendee=iris.asterpreferencelearning3100@office-v2.example.",
    "Schedule exactly one sync with Iris AsterPreferenceLearning3100 on 2028-08-08. The attendee is iris.asterpreferencelearning3100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-08-07"
}
```

## Packet 19

Packet ID: `5e4e6cc2979c19e6b1786920165271e92e16b02bc677d7abc14bbda3301edc0e`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-05-11",
        "end": "09:30",
        "id": "priority-0",
        "location": "",
        "owner": "Owner-C",
        "severity": 5,
        "start": "09:00",
        "title": "Priority: session 1"
      },
      {
        "attendees": [],
        "date": "2028-05-11",
        "end": "10:30",
        "id": "priority-1",
        "location": "",
        "owner": "Owner-A",
        "severity": 4,
        "start": "10:00",
        "title": "Priority: session 2"
      },
      {
        "attendees": [],
        "date": "2028-05-11",
        "end": "11:30",
        "id": "priority-2",
        "location": "",
        "owner": "Owner-B",
        "severity": 6,
        "start": "11:00",
        "title": "Priority: session 3"
      },
      {
        "attendees": [],
        "date": "2028-05-11",
        "end": "12:30",
        "id": "priority-3",
        "location": "",
        "owner": "Owner-D",
        "severity": 3,
        "start": "12:00",
        "title": "Priority: session 4"
      },
      {
        "attendees": [],
        "date": "2028-05-11",
        "end": "13:30",
        "id": "priority-4",
        "location": "",
        "owner": "Owner-E",
        "severity": 2,
        "start": "13:00",
        "title": "Priority: session 5"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-05-11. Send exactly one chat message to Perrin LatticeCalBrief1800. Include, in policy severity_descending order, only event titles beginning 'Priority:' and each start time. Exclude every other title and date. Then send exactly one separate chat message to Niko JuniperCalBrief1800 containing '2028-05-11' and 'priority-count=5'.",
  "subepisode_prompts": [],
  "today": "2028-05-08"
}
```

## Packet 20

Packet ID: `62829279a9733330b3c7b0f505c594e1a95de5ed1354c613a0484e60bd67b3ea`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-05-25",
        "end": "09:30",
        "id": "priority-0",
        "location": "",
        "owner": "Owner-C",
        "severity": 5,
        "start": "09:00",
        "title": "Priority: session 1"
      },
      {
        "attendees": [],
        "date": "2028-05-25",
        "end": "10:30",
        "id": "priority-1",
        "location": "",
        "owner": "Owner-A",
        "severity": 4,
        "start": "10:00",
        "title": "Priority: session 2"
      },
      {
        "attendees": [],
        "date": "2028-05-25",
        "end": "11:30",
        "id": "priority-2",
        "location": "",
        "owner": "Owner-B",
        "severity": 6,
        "start": "11:00",
        "title": "Priority: session 3"
      },
      {
        "attendees": [],
        "date": "2028-05-25",
        "end": "12:00",
        "id": "nonpriority-0",
        "location": "",
        "start": "11:30",
        "title": "Routine: unrelated 1"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-05-25. Send exactly one chat message to Fint BirchCalBrief2000. Include, in policy severity_descending order, only event titles beginning 'Priority:' and each start time. Exclude every other title and date. Then send exactly one separate chat message to Demi LatticeCalBrief2000 containing '2028-05-25' and 'priority-count=3'.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 21

Packet ID: `682b46d87710c4ec9463b27d013f8e8436c9b427166150d2e50802a80f39530a`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "DECISION: selection_key=KEY-13-A; confirmation_code=CONF-13; confirmation_date=2028-04-08.",
        "date": "2028-03-29 10:00",
        "from": "amal.emberemailreply1300@office-v2.example",
        "id": "required-decision",
        "subject": "Initiative JuniperEmailReply1300 / REQUIRED /DECISION"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=4; decision_key=KEY-13-A; request_id=attendance-0.",
        "date": "2028-03-30 10:00",
        "from": "lumi.latticeemailreply1300@office-v2.example",
        "id": "attendance-0",
        "subject": "Initiative JuniperEmailReply1300 / REQUIRED /ATTENDANCE attendance-0"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=9; decision_key=KEY-13-B; request_id=attendance-1.",
        "date": "2028-03-31 10:00",
        "from": "amal.latticeemailreply1301@office-v2.example",
        "id": "attendance-1",
        "subject": "Initiative JuniperEmailReply1300 / REQUIRED /ATTENDANCE attendance-1"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=1; decision_key=KEY-13-C; request_id=attendance-2.",
        "date": "2028-04-02 10:00",
        "from": "fint.latticeemailreply1302@office-v2.example",
        "id": "attendance-2",
        "subject": "Initiative JuniperEmailReply1300 / REQUIRED /ATTENDANCE attendance-2"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-04-02",
        "from": "orla.cinderemailreply1300@office-v2.example",
        "id": "unrelated-0",
        "subject": "Initiative JuniperEmailReply1300 FYI 00"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-04-02",
        "from": "demi.cinderemailreply1301@office-v2.example",
        "id": "unrelated-1",
        "subject": "Initiative JuniperEmailReply1300 FYI 01"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-04-02",
        "from": "iris.cinderemailreply1302@office-v2.example",
        "id": "unrelated-2",
        "subject": "Initiative JuniperEmailReply1300 FYI 02"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative JuniperEmailReply1300 / REQUIRED /'. Select exactly one request using policy latest_request. Reply exactly once to that request's sender. Subject must contain 'Initiative JuniperEmailReply1300'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id. Do not reply to any other sender.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 22

Packet ID: `68534d1828bc58dc413c5ef3bee9c3f105d1303f62977535b844522212a830f1`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create presentation office_43_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative HarborPptxBasic4300-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative HarborPptxBasic4300-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative HarborPptxBasic4300-approved-fact-3 | section=Decision,sequence=4,risk=3,owner=Owner-D,fact=Initiative HarborPptxBasic4300-approved-fact-4 | section=Owners,sequence=6,risk=2,owner=Owner-E,fact=Initiative HarborPptxBasic4300-approved-fact-5 | section=Next Steps,sequence=5,risk=1,owner=Owner-F,fact=Initiative HarborPptxBasic4300-approved-fact-6. Order section slides by policy owner_alphabetical. Use exactly 7 slides: one title slide named 'Initiative HarborPptxBasic4300 Review', then one slide per section. Use each section name as its slide title and include that section's exact fact as a bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 23

Packet ID: `6c0726035ac4c9a1ba6c86314ff709344ca9b115d2bbd2961dec20270ff6c4f2`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create presentation office_35_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative FablePptxBasic3500-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative FablePptxBasic3500-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative FablePptxBasic3500-approved-fact-3 | section=Decision,sequence=4,risk=3,owner=Owner-D,fact=Initiative FablePptxBasic3500-approved-fact-4 | section=Owners,sequence=6,risk=2,owner=Owner-E,fact=Initiative FablePptxBasic3500-approved-fact-5 | section=Next Steps,sequence=5,risk=1,owner=Owner-F,fact=Initiative FablePptxBasic3500-approved-fact-6. Order section slides by policy owner_alphabetical. Use exactly 7 slides: one title slide named 'Initiative FablePptxBasic3500 Review', then one slide per section. Use each section name as its slide title and include that section's exact fact as a bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-09-04"
}
```

## Packet 24

Packet ID: `6ca05466109e2a0ec47058b58744396941369061b28f1212096ad31a4f8ab3db`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "Region: North; Revenue cents: 15960000; Sequence: 1; Status: FINAL.",
        "date": "2028-05-19 09:00",
        "from": "esra.indigopptxfromemail2000@office-v2.example",
        "id": "approved-region-1",
        "subject": "APPROVED REGION Initiative IndigoPptxFromEmail2000 / 01"
      },
      {
        "body": "Region: South; Revenue cents: 16133000; Sequence: 2; Status: FINAL.",
        "date": "2028-05-20 09:00",
        "from": "esra.indigopptxfromemail2000@office-v2.example",
        "id": "approved-region-2",
        "subject": "APPROVED REGION Initiative IndigoPptxFromEmail2000 / 02"
      },
      {
        "body": "Region: Central; Revenue cents: 16306000; Sequence: 3; Status: FINAL.",
        "date": "2028-05-21 09:00",
        "from": "esra.indigopptxfromemail2000@office-v2.example",
        "id": "approved-region-3",
        "subject": "APPROVED REGION Initiative IndigoPptxFromEmail2000 / 03"
      },
      {
        "body": "Preliminary figures. Status: SUPERSEDED.",
        "date": "2028-05-02",
        "from": "esra.indigopptxfromemail2000@office-v2.example",
        "id": "draft-region-0",
        "subject": "DRAFT REGION Initiative IndigoPptxFromEmail2000 / 01"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative IndigoPptxFromEmail2000 /'. Then create office_20_regions.pptx with title slide 'Initiative IndigoPptxFromEmail2000 Revenue Review', followed by one slide per approved email ordered by policy revenue_descending. Use Region as each slide title and include the exact Revenue cents value. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 25

Packet ID: `6ea8fb0581074fc6331053e95602c30d688156d586b2f82db571859733488433`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "PAID RECEIPT: date=2028-07-26,vendor=JuniperXlsxFromEmail3002 Supply Group,amount_cents=8610. STATUS: FINAL.",
        "date": "2028-07-26 16:00",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "paid-receipt-0",
        "subject": "FINAL PAID RECEIPT CASE 30 / 01"
      },
      {
        "body": "PAID RECEIPT: date=2028-07-27,vendor=JuniperXlsxFromEmail3000 Supply Group,amount_cents=8884. STATUS: FINAL.",
        "date": "2028-07-27 16:00",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "paid-receipt-1",
        "subject": "FINAL PAID RECEIPT CASE 30 / 02"
      },
      {
        "body": "PAID RECEIPT: date=2028-07-28,vendor=JuniperXlsxFromEmail3001 Supply Group,amount_cents=9158. STATUS: FINAL.",
        "date": "2028-07-28 16:00",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "paid-receipt-2",
        "subject": "FINAL PAID RECEIPT CASE 30 / 03"
      },
      {
        "body": "PAID RECEIPT: date=2028-07-29,vendor=JuniperXlsxFromEmail3003 Supply Group,amount_cents=9432. STATUS: FINAL.",
        "date": "2028-07-29 16:00",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "paid-receipt-3",
        "subject": "FINAL PAID RECEIPT CASE 30 / 04"
      },
      {
        "body": "PAID RECEIPT: date=2028-07-30,vendor=JuniperXlsxFromEmail3005 Supply Group,amount_cents=9706. STATUS: FINAL.",
        "date": "2028-07-30 16:00",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "paid-receipt-4",
        "subject": "FINAL PAID RECEIPT CASE 30 / 05"
      },
      {
        "body": "Quote or duplicate; not a paid final receipt.",
        "date": "2028-07-21",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "receipt-draft-0",
        "subject": "DRAFT RECEIPTS 00"
      },
      {
        "body": "Quote or duplicate; not a paid final receipt.",
        "date": "2028-07-20",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "receipt-draft-1",
        "subject": "DRAFT RECEIPTS 01"
      },
      {
        "body": "Quote or duplicate; not a paid final receipt.",
        "date": "2028-07-19",
        "from": "jori.birchxlsxfromemail3000@office-v2.example",
        "id": "receipt-draft-2",
        "subject": "DRAFT RECEIPTS 02"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 30 /'. Then create office_30_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: amount_descending. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-07-31"
}
```

## Packet 26

Packet ID: `73b8f1897b0aaf21ec9348a551ff86c8abe8de059ca74deeb76573598a171a29`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create presentation office_22_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative KestrelPptxBasic2200-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative KestrelPptxBasic2200-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative KestrelPptxBasic2200-approved-fact-3 | section=Decision,sequence=4,risk=3,owner=Owner-D,fact=Initiative KestrelPptxBasic2200-approved-fact-4 | section=Owners,sequence=6,risk=2,owner=Owner-E,fact=Initiative KestrelPptxBasic2200-approved-fact-5. Order section slides by policy risk_descending. Use exactly 6 slides: one title slide named 'Initiative KestrelPptxBasic2200 Review', then one slide per section. Use each section name as its slide title and include that section's exact fact as a bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-06-05"
}
```

## Packet 27

Packet ID: `7aa2697e7d4e0a9ba5984e80dadb19d5d1e23a3d0f9b81c4321cdeae66c1cd8a`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "DECISION: selection_key=KEY-47-A; confirmation_code=CONF-47; confirmation_date=2028-12-02.",
        "date": "2028-11-22 10:00",
        "from": "cato.groveemailreply4700@office-v2.example",
        "id": "required-decision",
        "subject": "Initiative LatticeEmailReply4700 / REQUIRED /DECISION"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=4; decision_key=KEY-47-A; request_id=attendance-0.",
        "date": "2028-11-23 10:00",
        "from": "niko.birchemailreply4700@office-v2.example",
        "id": "attendance-0",
        "subject": "Initiative LatticeEmailReply4700 / REQUIRED /ATTENDANCE attendance-0"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=9; decision_key=KEY-47-B; request_id=attendance-1.",
        "date": "2028-11-24 10:00",
        "from": "cato.birchemailreply4701@office-v2.example",
        "id": "attendance-1",
        "subject": "Initiative LatticeEmailReply4700 / REQUIRED /ATTENDANCE attendance-1"
      },
      {
        "body": "ATTENDANCE REQUEST: priority=1; decision_key=KEY-47-C; request_id=attendance-2.",
        "date": "2028-11-26 10:00",
        "from": "hale.birchemailreply4702@office-v2.example",
        "id": "attendance-2",
        "subject": "Initiative LatticeEmailReply4700 / REQUIRED /ATTENDANCE attendance-2"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-11-26",
        "from": "amal.emberemailreply4700@office-v2.example",
        "id": "unrelated-0",
        "subject": "Initiative LatticeEmailReply4700 FYI 00"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-11-26",
        "from": "fint.emberemailreply4701@office-v2.example",
        "id": "unrelated-1",
        "subject": "Initiative LatticeEmailReply4700 FYI 01"
      },
      {
        "body": "Informational mention; no attendance request.",
        "date": "2028-11-26",
        "from": "kavi.emberemailreply4702@office-v2.example",
        "id": "unrelated-2",
        "subject": "Initiative LatticeEmailReply4700 FYI 02"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative LatticeEmailReply4700 / REQUIRED /'. Select exactly one request using policy decision_key_match. Reply exactly once to that request's sender. Subject must contain 'Initiative LatticeEmailReply4700'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id. Do not reply to any other sender.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 28

Packet ID: `7bb13f0ad2c2a4d812b8fd7254cc372f5550ce1cd40290451c43fdbba7312c1d`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-10-20",
        "end": "08:30",
        "id": "adjacent-0",
        "location": "",
        "start": "08:00",
        "title": "Existing block 1"
      },
      {
        "attendees": [],
        "date": "2028-10-20",
        "end": "09:00",
        "id": "adjacent-1",
        "location": "",
        "start": "08:30",
        "title": "Existing block 2"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-10-20. Candidate requests: id=candidate-A,title=Fint JuniperCalAdd4100 candidate-A design review,start=10:00,duration=45,priority=5,location=IndigoCalAdd4100 Collaboration Hall | id=candidate-B,title=Fint JuniperCalAdd4100 candidate-B design review,start=11:00,duration=60,priority=9,location=IndigoCalAdd4101 Collaboration Hall | id=candidate-C,title=Fint JuniperCalAdd4100 candidate-C design review,start=12:30,duration=30,priority=4,location=IndigoCalAdd4102 Collaboration Hall. Select one feasible request using policy shortest_duration_feasible and add exactly one event with that candidate's exact title, time, location, and these attendees: esra.indigocaladd4100@office-v2.example | jori.indigocaladd4101@office-v2.example | orla.indigocaladd4102@office-v2.example | demi.indigocaladd4103@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-10-16"
}
```

## Packet 29

Packet ID: `7f53ec163e126f5501e0a2545f0711a9f1bcc2de0930e92e4d2d2ba55e6159ec`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": null,
  "subepisode_prompts": [
    "For subject iris.asterpreferencelearning0200@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_recent and save exactly one memory containing only the selected bundle's applicable facts: subject=iris.asterpreferencelearning0200@office-v2.example | duration_minutes=20 | earliest_start=10:00 | location=Video | weekday=Tuesday | title_prefix=Focus:.",
    "Schedule exactly one sync with Iris AsterPreferenceLearning0200 on 2028-01-18. The attendee is iris.asterpreferencelearning0200@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-01-17"
}
```

## Packet 30

Packet ID: `87d04c7ce84155fc742966a56f44b7f6c81fed334c04cd515bcecc1b59ed9c90`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-05-26",
        "end": "08:30",
        "id": "adjacent-0",
        "location": "",
        "start": "08:00",
        "title": "Existing block 1"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-05-26. Candidate requests: id=candidate-A,title=Hale LatticeCalAdd2000 candidate-A design review,start=10:00,duration=45,priority=5,location=KestrelCalAdd2000 Collaboration Hall | id=candidate-B,title=Hale LatticeCalAdd2000 candidate-B design review,start=11:00,duration=60,priority=9,location=KestrelCalAdd2001 Collaboration Hall | id=candidate-C,title=Hale LatticeCalAdd2000 candidate-C design review,start=12:30,duration=30,priority=4,location=KestrelCalAdd2002 Collaboration Hall. Select one feasible request using policy highest_priority_feasible and add exactly one event with that candidate's exact title, time, location, and these attendees: gaia.kestrelcaladd2000@office-v2.example | lumi.kestrelcaladd2001@office-v2.example | amal.kestrelcaladd2002@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 31

Packet ID: `8c87e9e7718feeefacbf08eaf88cd61b52713cfbc18e0ce537e655d3dc88ccdb`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [
      {
        "date": "2028-10-10",
        "text": "Existing reminder 1",
        "time": "08:00"
      },
      {
        "date": "2028-10-11",
        "text": "Existing reminder 2",
        "time": "08:00"
      }
    ],
    "sent_emails": []
  },
  "prompt": "Action items: id=checkpoint-1,due=2028-10-12,priority=5,depends_on=checkpoint-3 | id=checkpoint-2,due=2028-10-13,priority=9,depends_on=checkpoint-1 | id=checkpoint-3,due=2028-10-14,priority=7,depends_on=none. Order them using policy dependency_order. Create exactly one reminder at 14:00 on the first ordered item's due date. Required checklist mentions in that order: checkpoint-3 | checkpoint-1 | checkpoint-2. Then send exactly one chat message to Kavi GroveRemindMsg4000 repeating those mentions in order and committing that the full checklist will be complete by the deadline. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-10-09"
}
```

## Packet 32

Packet ID: `9409d47b31ffd248ce918d978c55cb89f61935bac35f493853e7f1999a22b90d`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "CANDIDATES: id=offsite-final-a,issued_rank=3,approval_rank=4,consensus=1 | id=offsite-final-b,issued_rank=2,approval_rank=9,consensus=2 | id=offsite-final-c,issued_rank=1,approval_rank=3,consensus=9.",
        "date": "2028-03-25",
        "from": "jori.junipermultioffsite1200@office-v2.example",
        "id": "offsite-index",
        "subject": "OFFSITE SOURCE INDEX Initiative DovetailMultiOffsite1200"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative DovetailMultiOffsite1200 Summit A; date=2028-04-06; start=09:00; end=15:30; location=GroveMultiOffsite1200 Collaboration Hall; facts=2028-04-06 | 09:00-15:30 | GroveMultiOffsite1200 Collaboration Hall.",
        "date": "2028-03-24",
        "from": "esra.embermultioffsite1200@office-v2.example",
        "id": "offsite-final-a",
        "subject": "FINAL OFFSITE DETAIL offsite-final-a"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative DovetailMultiOffsite1200 Summit B; date=2028-04-07; start=10:00; end=16:30; location=GroveMultiOffsite1201 Collaboration Hall; facts=2028-04-07 | 10:00-16:30 | GroveMultiOffsite1201 Collaboration Hall.",
        "date": "2028-03-25",
        "from": "jori.embermultioffsite1201@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative DovetailMultiOffsite1200 Summit C; date=2028-04-08; start=11:00; end=17:30; location=GroveMultiOffsite1202 Collaboration Hall; facts=2028-04-08 | 11:00-17:30 | GroveMultiOffsite1202 Collaboration Hall.",
        "date": "2028-03-26",
        "from": "orla.embermultioffsite1202@office-v2.example",
        "id": "offsite-final-c",
        "subject": "FINAL OFFSITE DETAIL offsite-final-c"
      },
      {
        "body": "Superseded draft logistics.",
        "date": "2028-03-17",
        "from": "jori.junipermultioffsite1200@office-v2.example",
        "id": "offsite-draft-0",
        "subject": "DRAFT OFFSITE Initiative DovetailMultiOffsite1200 00"
      },
      {
        "body": "Superseded draft logistics.",
        "date": "2028-03-16",
        "from": "jori.junipermultioffsite1200@office-v2.example",
        "id": "offsite-draft-1",
        "subject": "DRAFT OFFSITE Initiative DovetailMultiOffsite1200 01"
      },
      {
        "body": "Superseded draft logistics.",
        "date": "2028-03-15",
        "from": "jori.junipermultioffsite1200@office-v2.example",
        "id": "offsite-draft-2",
        "subject": "DRAFT OFFSITE Initiative DovetailMultiOffsite1200 02"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative DovetailMultiOffsite1200'. Select one detail source using policy latest_issued, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_12_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-03-27"
}
```

## Packet 33

Packet ID: `9a327ec2d22b4dbf280224b2bbe860120287bcdd9503e8a4dc0f9c04504d5e7b`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "Region: North; Revenue cents: 18555000; Sequence: 1; Status: FINAL.",
        "date": "2028-08-29 09:00",
        "from": "jori.juniperpptxfromemail3500@office-v2.example",
        "id": "approved-region-1",
        "subject": "APPROVED REGION Initiative JuniperPptxFromEmail3500 / 01"
      },
      {
        "body": "Region: South; Revenue cents: 18728000; Sequence: 2; Status: FINAL.",
        "date": "2028-08-30 09:00",
        "from": "jori.juniperpptxfromemail3500@office-v2.example",
        "id": "approved-region-2",
        "subject": "APPROVED REGION Initiative JuniperPptxFromEmail3500 / 02"
      },
      {
        "body": "Region: Central; Revenue cents: 18901000; Sequence: 3; Status: FINAL.",
        "date": "2028-08-31 09:00",
        "from": "jori.juniperpptxfromemail3500@office-v2.example",
        "id": "approved-region-3",
        "subject": "APPROVED REGION Initiative JuniperPptxFromEmail3500 / 03"
      },
      {
        "body": "Region: Online; Revenue cents: 19074000; Sequence: 4; Status: FINAL.",
        "date": "2028-09-01 09:00",
        "from": "jori.juniperpptxfromemail3500@office-v2.example",
        "id": "approved-region-4",
        "subject": "APPROVED REGION Initiative JuniperPptxFromEmail3500 / 04"
      },
      {
        "body": "Region: Partner; Revenue cents: 19247000; Sequence: 5; Status: FINAL.",
        "date": "2028-09-02 09:00",
        "from": "jori.juniperpptxfromemail3500@office-v2.example",
        "id": "approved-region-5",
        "subject": "APPROVED REGION Initiative JuniperPptxFromEmail3500 / 05"
      },
      {
        "body": "Region: Public; Revenue cents: 19420000; Sequence: 6; Status: FINAL.",
        "date": "2028-09-03 09:00",
        "from": "jori.juniperpptxfromemail3500@office-v2.example",
        "id": "approved-region-6",
        "subject": "APPROVED REGION Initiative JuniperPptxFromEmail3500 / 06"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative JuniperPptxFromEmail3500 /'. Then create office_35_regions.pptx with title slide 'Initiative JuniperPptxFromEmail3500 Revenue Review', followed by one slide per approved email ordered by policy region_alphabetical. Use Region as each slide title and include the exact Revenue cents value. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-09-04"
}
```

## Packet 34

Packet ID: `a2aa150b9b947de6aa218984c88084f3d48c0f030b3537fc2aa6236fbf55c442`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create spreadsheet office_43_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Niko BirchXlsxBasic4300,Item=Training,Cost=6300 | Owner=Niko BirchXlsxBasic4300,Item=Equipment,Cost=6425 | Owner=Niko BirchXlsxBasic4300,Item=Licenses,Cost=6550 | Owner=Niko BirchXlsxBasic4300,Item=Travel,Cost=6675 | Owner=Niko BirchXlsxBasic4300,Item=Research,Cost=6800 | Owner=Niko BirchXlsxBasic4300,Item=Facilities,Cost=6925. Row order rule: item_alphabetical. Add exactly one final Total row using a formula.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 35

Packet ID: `a4d19c969ccaaa6f68c4f4c655325057c2eaabc2511d7a9bddf0c35a9ce3ecbd`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-09-21",
        "end": "09:30",
        "id": "priority-0",
        "location": "",
        "owner": "Owner-C",
        "severity": 5,
        "start": "09:00",
        "title": "Priority: session 1"
      },
      {
        "attendees": [],
        "date": "2028-09-21",
        "end": "10:30",
        "id": "priority-1",
        "location": "",
        "owner": "Owner-A",
        "severity": 4,
        "start": "10:00",
        "title": "Priority: session 2"
      },
      {
        "attendees": [],
        "date": "2028-09-21",
        "end": "11:30",
        "id": "priority-2",
        "location": "",
        "owner": "Owner-B",
        "severity": 6,
        "start": "11:00",
        "title": "Priority: session 3"
      },
      {
        "attendees": [],
        "date": "2028-09-21",
        "end": "12:30",
        "id": "priority-3",
        "location": "",
        "owner": "Owner-D",
        "severity": 3,
        "start": "12:00",
        "title": "Priority: session 4"
      },
      {
        "attendees": [],
        "date": "2028-09-21",
        "end": "12:00",
        "id": "nonpriority-0",
        "location": "",
        "start": "11:30",
        "title": "Routine: unrelated 1"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-09-21. Send exactly one chat message to Iris EmberCalBrief3700. Include, in policy owner_alphabetical order, only event titles beginning 'Priority:' and each start time. Exclude every other title and date. Then send exactly one separate chat message to Gaia CinderCalBrief3700 containing '2028-09-21' and 'priority-count=4'.",
  "subepisode_prompts": [],
  "today": "2028-09-18"
}
```

## Packet 36

Packet ID: `af402aca2da6d0ba834654f0d28d54e17dacdfa63130f04bd787566593d67e05`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create presentation office_00_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative FablePptxBasic0000-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative FablePptxBasic0000-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative FablePptxBasic0000-approved-fact-3. Order section slides by policy brief_sequence. Use exactly 4 slides: one title slide named 'Initiative FablePptxBasic0000 Review', then one slide per section. Use each section name as its slide title and include that section's exact fact as a bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 37

Packet ID: `b3b9e97dc62be3d1c414263938a8612691124b01883a486db0e3f941e0b13034`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": null,
  "subepisode_prompts": [
    "For subject kavi.kestrelpreferencelearning0100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_recent and save exactly one memory containing only the selected bundle's applicable facts: subject=kavi.kestrelpreferencelearning0100@office-v2.example | duration_minutes=20 | earliest_start=10:00 | location=Video | weekday=Tuesday.",
    "Schedule exactly one sync with Kavi KestrelPreferenceLearning0100 on 2028-01-11. The attendee is kavi.kestrelpreferencelearning0100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-01-10"
}
```

## Packet 38

Packet ID: `cb8c91132236ab8c7d829581a020224dc13a7def6621528435d7792c7d74b95d`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "09:30",
        "id": "priority-0",
        "location": "",
        "owner": "Owner-C",
        "severity": 5,
        "start": "09:00",
        "title": "Priority: session 1"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "10:30",
        "id": "priority-1",
        "location": "",
        "owner": "Owner-A",
        "severity": 4,
        "start": "10:00",
        "title": "Priority: session 2"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "11:30",
        "id": "priority-2",
        "location": "",
        "owner": "Owner-B",
        "severity": 6,
        "start": "11:00",
        "title": "Priority: session 3"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "12:30",
        "id": "priority-3",
        "location": "",
        "owner": "Owner-D",
        "severity": 3,
        "start": "12:00",
        "title": "Priority: session 4"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "13:30",
        "id": "priority-4",
        "location": "",
        "owner": "Owner-E",
        "severity": 2,
        "start": "13:00",
        "title": "Priority: session 5"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "14:30",
        "id": "priority-5",
        "location": "",
        "owner": "Owner-F",
        "severity": 1,
        "start": "14:00",
        "title": "Priority: session 6"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "12:00",
        "id": "nonpriority-0",
        "location": "",
        "start": "11:30",
        "title": "Routine: unrelated 1"
      },
      {
        "attendees": [],
        "date": "2028-12-02",
        "end": "12:00",
        "id": "nonpriority-1",
        "location": "",
        "start": "11:30",
        "title": "Routine: unrelated 2"
      },
      {
        "attendees": [],
        "date": "2028-11-30",
        "end": "12:00",
        "id": "nonpriority-2",
        "location": "",
        "start": "11:30",
        "title": "Routine: unrelated 3"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-11-30. Send exactly one chat message to Orla CinderCalBrief4700. Include, in policy owner_alphabetical order, only event titles beginning 'Priority:' and each start time. Exclude every other title and date. Then send exactly one separate chat message to Mara AsterCalBrief4700 containing '2028-11-30' and 'priority-count=6'.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 39

Packet ID: `d5cfa60a945227ca710efd8d170d94b47e33e12ce7a5b43ecb9ede7bff268c6f`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Action items: id=checkpoint-1,due=2028-01-20,priority=5,depends_on=checkpoint-3 | id=checkpoint-2,due=2028-01-21,priority=9,depends_on=checkpoint-1 | id=checkpoint-3,due=2028-01-22,priority=7,depends_on=none | id=checkpoint-4,due=2028-01-23,priority=4,depends_on=checkpoint-2 | id=checkpoint-5,due=2028-01-24,priority=3,depends_on=checkpoint-4. Order them using policy due_date_ascending. Create exactly one reminder at 14:00 on the first ordered item's due date. Required checklist mentions in that order: checkpoint-1 | checkpoint-2 | checkpoint-3 | checkpoint-4 | checkpoint-5. Then send exactly one chat message to Orla GroveRemindMsg0200 repeating those mentions in order and committing that the full checklist will be complete by the deadline. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-01-17"
}
```

## Packet 40

Packet ID: `d7afee160e35ffd8eab6cdd2eeb5b7ab1af4d52e1c5b989390e90d8d2ec6c17a`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-11-17",
        "end": "08:30",
        "id": "adjacent-0",
        "location": "",
        "start": "08:00",
        "title": "Existing block 1"
      },
      {
        "attendees": [],
        "date": "2028-11-17",
        "end": "09:00",
        "id": "adjacent-1",
        "location": "",
        "start": "08:30",
        "title": "Existing block 2"
      },
      {
        "attendees": [],
        "date": "2028-11-17",
        "end": "09:30",
        "id": "adjacent-2",
        "location": "",
        "start": "09:00",
        "title": "Existing block 3"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-11-17. Candidate requests: id=candidate-A,title=Niko JuniperCalAdd4500 candidate-A design review,start=10:00,duration=45,priority=5,location=IndigoCalAdd4500 Collaboration Hall | id=candidate-B,title=Niko JuniperCalAdd4500 candidate-B design review,start=11:00,duration=60,priority=9,location=IndigoCalAdd4501 Collaboration Hall | id=candidate-C,title=Niko JuniperCalAdd4500 candidate-C design review,start=12:30,duration=30,priority=4,location=IndigoCalAdd4502 Collaboration Hall. Select one feasible request using policy shortest_duration_feasible and add exactly one event with that candidate's exact title, time, location, and these attendees: mara.indigocaladd4500@office-v2.example | bryn.indigocaladd4501@office-v2.example | gaia.indigocaladd4502@office-v2.example | lumi.indigocaladd4503@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-11-13"
}
```

## Packet 41

Packet ID: `d816197695813ba1e78062ccc24ed5c71661eafe12a7512f206e0db9aae13a14`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "CANDIDATES: id=offsite-final-a,issued_rank=3,approval_rank=4,consensus=1 | id=offsite-final-b,issued_rank=2,approval_rank=9,consensus=2 | id=offsite-final-c,issued_rank=1,approval_rank=3,consensus=9.",
        "date": "2028-08-26",
        "from": "kavi.cindermultioffsite3400@office-v2.example",
        "id": "offsite-index",
        "subject": "OFFSITE SOURCE INDEX Initiative IndigoMultiOffsite3400"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative IndigoMultiOffsite3400 Summit A; date=2028-09-07; start=09:00; end=15:30; location=LatticeMultiOffsite3400 Collaboration Hall; facts=2028-09-07 | 09:00-15:30 | LatticeMultiOffsite3400 Collaboration Hall | business casual | bring identification.",
        "date": "2028-08-25",
        "from": "fint.junipermultioffsite3400@office-v2.example",
        "id": "offsite-final-a",
        "subject": "FINAL OFFSITE DETAIL offsite-final-a"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative IndigoMultiOffsite3400 Summit B; date=2028-09-08; start=10:00; end=16:30; location=LatticeMultiOffsite3401 Collaboration Hall; facts=2028-09-08 | 10:00-16:30 | LatticeMultiOffsite3401 Collaboration Hall | formal | bring identification.",
        "date": "2028-08-26",
        "from": "kavi.junipermultioffsite3401@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative IndigoMultiOffsite3400 Summit C; date=2028-09-09; start=11:00; end=17:30; location=LatticeMultiOffsite3402 Collaboration Hall; facts=2028-09-09 | 11:00-17:30 | LatticeMultiOffsite3402 Collaboration Hall | field attire | bring identification.",
        "date": "2028-08-27",
        "from": "perrin.junipermultioffsite3402@office-v2.example",
        "id": "offsite-final-c",
        "subject": "FINAL OFFSITE DETAIL offsite-final-c"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative IndigoMultiOffsite3400'. Select one detail source using policy consensus_supported, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_34_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-08-28"
}
```

## Packet 42

Packet ID: `e99252e8b45c3ea710e3262731b7bc3c599151b92b023e478878f6771d16ddfe`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Create spreadsheet office_13_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Hale DovetailXlsxBasic1300,Item=Training,Cost=2550 | Owner=Hale DovetailXlsxBasic1300,Item=Equipment,Cost=2675 | Owner=Hale DovetailXlsxBasic1300,Item=Licenses,Cost=2800 | Owner=Hale DovetailXlsxBasic1300,Item=Travel,Cost=2925. Row order rule: source_order. Add exactly one final Total row using a formula.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 43

Packet ID: `f2d3c0831cc05ee03c9545af8d807a221c2c372af2e79eb140715482d4875b36`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [],
    "events": [
      {
        "attendees": [],
        "date": "2028-10-21",
        "end": "09:30",
        "id": "busy-0",
        "location": "",
        "start": "09:00",
        "title": "Busy block 1"
      },
      {
        "attendees": [],
        "date": "2028-10-21",
        "end": "10:30",
        "id": "busy-1",
        "location": "",
        "start": "10:00",
        "title": "Busy block 2"
      },
      {
        "attendees": [],
        "date": "2028-10-21",
        "end": "11:30",
        "id": "busy-2",
        "location": "",
        "start": "11:00",
        "title": "Busy block 3"
      },
      {
        "attendees": [],
        "date": "2028-10-21",
        "end": "12:30",
        "id": "busy-3",
        "location": "",
        "start": "12:00",
        "title": "Busy block 4"
      },
      {
        "attendees": [],
        "date": "2028-10-22",
        "end": "11:00",
        "id": "other-day-0",
        "location": "",
        "start": "10:00",
        "title": "Other date 1"
      },
      {
        "attendees": [],
        "date": "2028-10-23",
        "end": "11:00",
        "id": "other-day-1",
        "location": "",
        "start": "10:00",
        "title": "Other date 2"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-10-21. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose closest_to_preferred; the preferred start is 13:30. Add exactly one event titled 'Amal AsterCalFreeslot4100 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-10-16"
}
```

## Packet 44

Packet ID: `f8b9f6714b77bfacdc937539da476e3adb148f76f575fdc91bd5c70ba5e618b6`

```json
{
  "available_tools": [
    "list_emails",
    "read_email",
    "send_email",
    "list_events",
    "add_event",
    "send_message",
    "set_reminder",
    "create_presentation",
    "create_spreadsheet",
    "read_spreadsheet",
    "think",
    "save_memory",
    "recall_memories",
    "done"
  ],
  "initial_state": {
    "artifacts": [],
    "emails": [
      {
        "body": "PAID RECEIPT: date=2028-06-16,vendor=LatticeXlsxFromEmail2402 Supply Group,amount_cents=7788. STATUS: FINAL.",
        "date": "2028-06-16 16:00",
        "from": "hale.dovetailxlsxfromemail2400@office-v2.example",
        "id": "paid-receipt-0",
        "subject": "FINAL PAID RECEIPT CASE 24 / 01"
      },
      {
        "body": "PAID RECEIPT: date=2028-06-17,vendor=LatticeXlsxFromEmail2400 Supply Group,amount_cents=8062. STATUS: FINAL.",
        "date": "2028-06-17 16:00",
        "from": "hale.dovetailxlsxfromemail2400@office-v2.example",
        "id": "paid-receipt-1",
        "subject": "FINAL PAID RECEIPT CASE 24 / 02"
      },
      {
        "body": "PAID RECEIPT: date=2028-06-18,vendor=LatticeXlsxFromEmail2401 Supply Group,amount_cents=8336. STATUS: FINAL.",
        "date": "2028-06-18 16:00",
        "from": "hale.dovetailxlsxfromemail2400@office-v2.example",
        "id": "paid-receipt-2",
        "subject": "FINAL PAID RECEIPT CASE 24 / 03"
      },
      {
        "body": "Quote or duplicate; not a paid final receipt.",
        "date": "2028-06-09",
        "from": "hale.dovetailxlsxfromemail2400@office-v2.example",
        "id": "receipt-draft-0",
        "subject": "DRAFT RECEIPTS 00"
      },
      {
        "body": "Quote or duplicate; not a paid final receipt.",
        "date": "2028-06-08",
        "from": "hale.dovetailxlsxfromemail2400@office-v2.example",
        "id": "receipt-draft-1",
        "subject": "DRAFT RECEIPTS 01"
      }
    ],
    "events": [],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 24 /'. Then create office_24_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: amount_descending. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-06-19"
}
```
