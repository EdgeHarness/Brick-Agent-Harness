# Brick office-task review packets

Review each task independently. Do not use generative AI and do not discuss
an unfinished case with another reviewer. Record your answer in
`RESPONSES.csv`; do not edit this packet file.

## Packet 01

Packet ID: `0198c9280414503fc07fe7cc41954112400ea0023da00d4a3997755736780cbf`

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

## Packet 02

Packet ID: `0f3f5bb9796c52c7588205d21ec5623395413afd432dc2370cafb7e56626a63f`

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

## Packet 03

Packet ID: `1dd10acf66625cd41d9701a419107ce5efbbcccec9fc4fffb45498b08fa8af27`

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
  "prompt": "Inspect calendar date 2028-04-01. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose earliest_free. Policy definitions: earliest_free selects the earliest free slot; latest_free selects the latest free slot; closest_to_preferred selects the slot closest to preferred start 13:30, breaking an equal-distance tie toward the earlier slot. Apply only the named policy. Add exactly one event titled 'Gaia KestrelCalFreeslot1200 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-03-27"
}
```

## Packet 04

Packet ID: `2056e137e4b9f16d913e95ad22a02a67e655962b5eda7ff59e998d5d14ea3d17`

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
  "prompt": "Inspect calendar date 2028-09-21. Send exactly one chat message to Iris EmberCalBrief3700. Include, in policy owner_alphabetical order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. Exclude every other title and date. Then send exactly one separate chat message to Gaia CinderCalBrief3700 containing '2028-09-21' and 'priority-count=4'.",
  "subepisode_prompts": [],
  "today": "2028-09-18"
}
```

## Packet 05

Packet ID: `21472f62c0fc487628fe7b8729a4bfb9da3004eb076e67cf73202ef6cfe377b6`

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

## Packet 06

Packet ID: `28bc3720ed03aad0b3c7cf04dba91bda1ed102bb61a112ce198c416e18871b3a`

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

## Packet 07

Packet ID: `39eb567e16dbc62b0a37b84aa9da174e16c48bbc1cb9e998d64efa924f2a6324`

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
  "prompt": "Inspect calendar date 2028-10-21. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose closest_to_preferred. Policy definitions: earliest_free selects the earliest free slot; latest_free selects the latest free slot; closest_to_preferred selects the slot closest to preferred start 13:30, breaking an equal-distance tie toward the earlier slot. Apply only the named policy. Add exactly one event titled 'Amal AsterCalFreeslot4100 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-10-16"
}
```

## Packet 08

Packet ID: `3d5f352819bf99b7fb8f54c2c6af02200337edaa7561d63ebc6923d4c95488ff`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative LatticeEmailReply4700 / REQUIRED /'. Select exactly one request using policy decision_key_match. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative LatticeEmailReply4700'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 09

Packet ID: `4218b82ffb3c8bf6db409719677c75439d5ead806a8b32073be1e9e746609b3b`

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

## Packet 10

Packet ID: `437d71bb8e9c59f3850fc08a4e92eec53b15fd9d730de1800a1055eb8dc8f899`

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
        "date": "2028-08-24",
        "from": "kavi.junipermultioffsite3401@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative IndigoMultiOffsite3400 Summit C; date=2028-09-09; start=11:00; end=17:30; location=LatticeMultiOffsite3402 Collaboration Hall; facts=2028-09-09 | 11:00-17:30 | LatticeMultiOffsite3402 Collaboration Hall | field attire | bring identification.",
        "date": "2028-08-23",
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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative IndigoMultiOffsite3400'. Select one detail source using policy consensus_supported. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_34_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-08-28"
}
```

## Packet 11

Packet ID: `4b1a899c4080cf61cf3a4f240c0fcc6ea71b2f7e6381880d9aa0af041e6f08e2`

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

## Packet 12

Packet ID: `56dca134dbf0c5e55910738f0e6fc3a654e13c4f82eeccb7818365ab3a505792`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-10-12,priority=5,depends_on=none | id=checkpoint-2,due=2028-10-13,priority=9,depends_on=none | id=checkpoint-3,due=2028-10-14,priority=7,depends_on=checkpoint-1. Order them using policy dependency_order. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Kavi GroveRemindMsg4000 repeating the same full ordered ID list in order and committing that the full checklist will be complete by 2028-10-13, which is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-10-09"
}
```

## Packet 13

Packet ID: `586565946e2b326a361724f7890f1fc782bfff998ba065dc0d305f6f5e04306a`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-06-15,priority=5,depends_on=none | id=checkpoint-2,due=2028-06-16,priority=9,depends_on=none | id=checkpoint-3,due=2028-06-17,priority=7,depends_on=checkpoint-1 | id=checkpoint-4,due=2028-06-18,priority=4,depends_on=checkpoint-3 | id=checkpoint-5,due=2028-06-19,priority=3,depends_on=checkpoint-4 | id=checkpoint-6,due=2028-06-20,priority=2,depends_on=checkpoint-5. Order them using policy priority_descending. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Gaia KestrelRemindMsg2300 repeating the same full ordered ID list in order and committing that the full checklist will be complete by 2028-06-16, which is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-06-12"
}
```

## Packet 14

Packet ID: `612138ab09e945467aa1eb5e4af509dff31d631f3d089b6e05c2c6f4e4c42692`

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

## Packet 15

Packet ID: `62c772e828cfe3eb15677f705bf55323b0447f0a0244bea643d63f131351cda2`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 24 /'. Then create office_24_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: amount_descending. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-06-19"
}
```

## Packet 16

Packet ID: `652e9d972eaf4562fbc0bac4762d91be5f45e157fee36a11dd27deb55df4b28e`

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
        "date": "2028-10-26",
        "from": "iris.dovetailmultioffsite4301@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative CinderMultiOffsite4300 Summit C; date=2028-11-11; start=11:00; end=17:30; location=FableMultiOffsite4302 Collaboration Hall; facts=2028-11-11 | 11:00-17:30 | FableMultiOffsite4302 Collaboration Hall | field attire | bring identification | lunch provided.",
        "date": "2028-10-25",
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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative CinderMultiOffsite4300'. Select one detail source using policy consensus_supported. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_43_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 17

Packet ID: `6d70249e4abe444101e1397c8c8865e5fcc3579bc6606d58d5e863d168846e91`

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

## Packet 18

Packet ID: `6d770a6c26e444a617b900c4232f58ea3d4e07f5361deed8a7dc23e72dbd73be`

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
    "For subject hale.dovetailpreferencelearning4100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_specific_scope and save exactly one memory containing only the selected bundle's applicable facts: subject=hale.dovetailpreferencelearning4100@office-v2.example | duration_minutes=30 | earliest_start=12:00 | location=Studio | title_prefix=Priority:.",
    "Schedule exactly one sync with Hale DovetailPreferenceLearning4100 on 2028-10-17. The attendee is hale.dovetailpreferencelearning4100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-10-16"
}
```

## Packet 19

Packet ID: `71ff266e51a8493bcd20fa9fa5f29cacaf188ab559d8d48bec399f76a9532275`

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

## Packet 20

Packet ID: `80338d605d6345b42a92830c643bb90f266915699a2acbb18af789e55f57652a`

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

## Packet 21

Packet ID: `8cf4353562350101ae8c724a8c5cc12033b19f0a3e8e39eabacb53056a8a3202`

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

## Packet 22

Packet ID: `9203a8e40384a3ab177d4f0e1dab409e84138a00427c6432e23a185d665cd68c`

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
  "prompt": "Inspect calendar date 2028-06-17. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose latest_free. Policy definitions: earliest_free selects the earliest free slot; latest_free selects the latest free slot; closest_to_preferred selects the slot closest to preferred start 13:30, breaking an equal-distance tie toward the earlier slot. Apply only the named policy. Add exactly one event titled 'Gaia GroveCalFreeslot2300 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-06-12"
}
```

## Packet 23

Packet ID: `9267e941d3a22b9056a64a9c26309fa5bd2b872b9c125f6089338b9f78c54256`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 00 /'. Then create office_00_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: date_ascending. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 24

Packet ID: `9e4c13cd4fe1d8a247361718793211780c1db49a8adff648c280d45b0410f328`

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
    "For subject kavi.kestrelpreferencelearning0100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_recent and save exactly one memory containing only the selected bundle's applicable facts: subject=kavi.kestrelpreferencelearning0100@office-v2.example | duration_minutes=20 | earliest_start=10:00 | location=Video | title_prefix=Focus:.",
    "Schedule exactly one sync with Kavi KestrelPreferenceLearning0100 on 2028-01-11. The attendee is kavi.kestrelpreferencelearning0100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-01-10"
}
```

## Packet 25

Packet ID: `9fc6eef435f8d4e998e004cf60aa9a1495b76f4321496faee945f24159aa35ac`

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
  "prompt": "Inspect calendar date 2028-05-11. Send exactly one chat message to Perrin LatticeCalBrief1800. Include, in policy severity_descending order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. Exclude every other title and date. Then send exactly one separate chat message to Niko JuniperCalBrief1800 containing '2028-05-11' and 'priority-count=5'.",
  "subepisode_prompts": [],
  "today": "2028-05-08"
}
```

## Packet 26

Packet ID: `a4742240beaac7a188dafdabcddef3f638e4f0ca150ff8700401f68f7dbc6194`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 34 /'. Then create office_34_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: vendor_alphabetical. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-08-28"
}
```

## Packet 27

Packet ID: `a56fe7abd3fff4a8677220a4afdadd64b6956a5b7aee51847867f1c4d772229a`

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
    "For subject iris.asterpreferencelearning0200@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_recent and save exactly one memory containing only the selected bundle's applicable facts: subject=iris.asterpreferencelearning0200@office-v2.example | duration_minutes=20 | earliest_start=10:00 | location=Video | title_prefix=Focus: | weekday=Tuesday.",
    "Schedule exactly one sync with Iris AsterPreferenceLearning0200 on 2028-01-18. The attendee is iris.asterpreferencelearning0200@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-01-17"
}
```

## Packet 28

Packet ID: `aa0250dd924f44170ddb7f0e4c8b0450183402ba94b43d4594cdda270f3a5618`

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
    "For subject iris.asterpreferencelearning3100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy highest_priority and save exactly one memory containing only the selected bundle's applicable facts: subject=iris.asterpreferencelearning3100@office-v2.example | duration_minutes=25 | earliest_start=11:00 | location=Cedar room | title_prefix=Deep: | weekday=Tuesday | sole_attendee=iris.asterpreferencelearning3100@office-v2.example.",
    "Schedule exactly one sync with Iris AsterPreferenceLearning3100 on 2028-08-08. The attendee is iris.asterpreferencelearning3100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle; the winning start, duration, location, and optional title prefix are not repeated here."
  ],
  "today": "2028-08-07"
}
```

## Packet 29

Packet ID: `b70164c6b3357d473b925534b0fecfcad4db25d0160a5138ec717050ff0642e3`

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
  "prompt": "Inspect calendar date 2028-05-25. Send exactly one chat message to Fint BirchCalBrief2000. Include, in policy severity_descending order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. Exclude every other title and date. Then send exactly one separate chat message to Demi LatticeCalBrief2000 containing '2028-05-25' and 'priority-count=3'.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 30

Packet ID: `b75e7bd71282fadd9b1d5a4effcf8f6099fb6191ecc25bb7e4330b60ccbc56b5`

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

## Packet 31

Packet ID: `b92f168fb1e52e65a05bc5caee6a144b4eab322682da21671732b50f05f71ab7`

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
        "date": "2028-03-23",
        "from": "jori.embermultioffsite1201@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative DovetailMultiOffsite1200 Summit C; date=2028-04-08; start=11:00; end=17:30; location=GroveMultiOffsite1202 Collaboration Hall; facts=2028-04-08 | 11:00-17:30 | GroveMultiOffsite1202 Collaboration Hall.",
        "date": "2028-03-22",
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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative DovetailMultiOffsite1200'. Select one detail source using policy latest_issued. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_12_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-03-27"
}
```

## Packet 32

Packet ID: `bcc7625685b4af5d62ee2e3d3b33f8adf4ba62813d62026131bcbc7272daf1dd`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 30 /'. Then create office_30_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: amount_descending. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row using a formula. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-07-31"
}
```

## Packet 33

Packet ID: `c51bbf655145e69ac10b34296cfc9c87bd5505cc31b31f0fa288977df713a5d2`

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

## Packet 34

Packet ID: `c5b3ff32755e20052e037898547139b57579b85659d441e9532710ea254c411d`

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
  "prompt": "Inspect calendar date 2028-01-22. Between 09:00 and 17:00, find 30-minute slots aligned to 30 minutes and choose earliest_free. Policy definitions: earliest_free selects the earliest free slot; latest_free selects the latest free slot; closest_to_preferred selects the slot closest to preferred start 13:30, breaking an equal-distance tie toward the earlier slot. Apply only the named policy. Add exactly one event titled 'Demi LatticeCalFreeslot0200 focus block' in that slot, with no attendees and location 'Focus room'. Ignore other dates.",
  "subepisode_prompts": [],
  "today": "2028-01-17"
}
```

## Packet 35

Packet ID: `ca6a1e71f0f43265f20e7e4081483bf847ff2117611b7aa5b73aebc84347019a`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative DovetailEmailReply1800 / REQUIRED /'. Select exactly one request using policy highest_priority. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative DovetailEmailReply1800'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-05-08"
}
```

## Packet 36

Packet ID: `cb9f1a4ccc05643a86344f7794938b6712bdfcdfdfc95e90e974709ddb084612`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-05-25,priority=5,depends_on=none | id=checkpoint-2,due=2028-05-26,priority=9,depends_on=none | id=checkpoint-3,due=2028-05-27,priority=7,depends_on=checkpoint-1. Order them using policy priority_descending. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Iris AsterRemindMsg2000 repeating the same full ordered ID list in order and committing that the full checklist will be complete by 2028-05-26, which is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 37

Packet ID: `df3f548adbf1454befd715974c3f1c08693fd8035c78b549836a67a2a318fa26`

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
  "prompt": "Inspect calendar date 2028-11-30. Send exactly one chat message to Orla CinderCalBrief4700. Include, in policy owner_alphabetical order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. Exclude every other title and date. Then send exactly one separate chat message to Mara AsterCalBrief4700 containing '2028-11-30' and 'priority-count=6'.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 38

Packet ID: `e6c8b30540e879d8dd8e436acebde533f2d607d6c82b4efb52caab67a79021dc`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative JuniperEmailReply1300 / REQUIRED /'. Select exactly one request using policy latest_request. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative JuniperEmailReply1300'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 39

Packet ID: `e7db2bbabf692e422fe1e6f9a11612529bb81f06acf064906bc952c4fbda3159`

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

## Packet 40

Packet ID: `ea4e0d36bdeabd9567222b898d8c9163623f88c48447046e4e699dcab60de377`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative JuniperEmailReply2000 / REQUIRED /'. Select exactly one request using policy highest_priority. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative JuniperEmailReply2000'. Body must confirm attendance and include the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 41

Packet ID: `ebec46e700b1ef52547a7188ac88591052aa1cdef254bf108cff0984bfdce079`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-01-20,priority=5,depends_on=none | id=checkpoint-2,due=2028-01-21,priority=9,depends_on=none | id=checkpoint-3,due=2028-01-22,priority=7,depends_on=checkpoint-1 | id=checkpoint-4,due=2028-01-23,priority=4,depends_on=checkpoint-3 | id=checkpoint-5,due=2028-01-24,priority=3,depends_on=checkpoint-4. Order them using policy due_date_ascending. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Orla GroveRemindMsg0200 repeating the same full ordered ID list in order and committing that the full checklist will be complete by 2028-01-20, which is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-01-17"
}
```

## Packet 42

Packet ID: `effbcadad09a5e06423e64e57d0b7554fb1c9461ed85a9667f7b7b36fdb28453`

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

## Packet 43

Packet ID: `fccb0c78f96683aa3f62986e5519c94b11e28bde979f1d2ba322731def22ea8e`

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

## Packet 44

Packet ID: `fced9859a973319ab967970660bcc2ebc75e1e9f78ce8bf23c592127b2e6e04c`

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
        "date": "2027-12-30",
        "from": "bryn.astermultioffsite0001@office-v2.example",
        "id": "offsite-final-b",
        "subject": "FINAL OFFSITE DETAIL offsite-final-b"
      },
      {
        "body": "FINAL OFFSITE: event=Initiative LatticeMultiOffsite0000 Summit C; date=2028-01-15; start=11:00; end=17:30; location=CinderMultiOffsite0002 Collaboration Hall; facts=2028-01-15 | 11:00-17:30 | CinderMultiOffsite0002 Collaboration Hall.",
        "date": "2027-12-29",
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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative LatticeMultiOffsite0000'. Select one detail source using policy latest_issued. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly, reply to its sender confirming attendance, and create office_00_offsite.pptx with exactly one slide titled for the event and bullets containing every listed fact in order. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```
