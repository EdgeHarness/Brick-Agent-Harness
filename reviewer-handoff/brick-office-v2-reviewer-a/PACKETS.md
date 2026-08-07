# Brick office-task review packets

Review each task independently. Do not use generative AI and do not discuss
an unfinished case with another reviewer. Record your answer in
`RESPONSES.csv`; do not edit this packet file.

## Packet 01

Packet ID: `0138646e2a195985b930137f663c3dc920a4a290fb643bcff06bc76287fa6eb6`

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

## Packet 02

Packet ID: `07bb7faad122e7a9ec4c9d52fbcaa8d68cc07ae7c11e9e43c89a133f137d2dd3`

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
  "prompt": "Create presentation office_22_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative KestrelPptxBasic2200-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative KestrelPptxBasic2200-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative KestrelPptxBasic2200-approved-fact-3 | section=Decision,sequence=4,risk=3,owner=Owner-D,fact=Initiative KestrelPptxBasic2200-approved-fact-4 | section=Owners,sequence=6,risk=2,owner=Owner-E,fact=Initiative KestrelPptxBasic2200-approved-fact-5. Order section slides by policy risk_descending. Policy definitions: brief_sequence sorts by the smallest sequence value first; risk_descending sorts by the largest risk value first, breaking ties by section name; owner_alphabetical sorts by owner then section name alphabetically. Apply only the named policy. Use exactly 6 slides: one title slide named 'Initiative KestrelPptxBasic2200 Review' with no body text, then one slide per section. Use each section name as its exact slide title. Each section slide's only bullet must be exactly that section's fact value, with no label and no additional bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-06-05"
}
```

## Packet 03

Packet ID: `0f0675729685dfb7c2731b130dc2a8511c2b78364e0788f7cb0f4f8046f62bed`

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
  "prompt": "Create presentation office_35_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative FablePptxBasic3500-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative FablePptxBasic3500-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative FablePptxBasic3500-approved-fact-3 | section=Decision,sequence=4,risk=3,owner=Owner-D,fact=Initiative FablePptxBasic3500-approved-fact-4 | section=Owners,sequence=6,risk=2,owner=Owner-E,fact=Initiative FablePptxBasic3500-approved-fact-5 | section=Next Steps,sequence=5,risk=1,owner=Owner-F,fact=Initiative FablePptxBasic3500-approved-fact-6. Order section slides by policy owner_alphabetical. Policy definitions: brief_sequence sorts by the smallest sequence value first; risk_descending sorts by the largest risk value first, breaking ties by section name; owner_alphabetical sorts by owner then section name alphabetically. Apply only the named policy. Use exactly 7 slides: one title slide named 'Initiative FablePptxBasic3500 Review' with no body text, then one slide per section. Use each section name as its exact slide title. Each section slide's only bullet must be exactly that section's fact value, with no label and no additional bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-09-04"
}
```

## Packet 04

Packet ID: `13a742a0406ef0e6284bd8a80eb5be570f7a1d49778ee1823e69da205c3b9ea4`

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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative IndigoMultiOffsite3400'. Select one detail source using policy consensus_supported. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly with no attendees. Reply to its sender with the exact body 'I will attend.' Create office_34_offsite.pptx with exactly one slide whose title is exactly the selected event name. Its bullets must be exactly the listed facts, one fact per bullet in the listed order, with no labels and no additional bullet. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-08-28"
}
```

## Packet 05

Packet ID: `186cfc91a8d5a99e70443fda627da3bbb7b496353c8b376b94c9f56e39509e02`

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

## Packet 06

Packet ID: `1900d4585c74c36fc0cf17f7d857b189210aa7578e22520500d2ee77966b3a8b`

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
        "end": "09:00",
        "id": "candidate-feasibility-blocker",
        "location": "",
        "start": "08:30",
        "title": "Protected focus block"
      },
      {
        "attendees": [],
        "date": "2028-05-26",
        "end": "06:30",
        "id": "adjacent-0",
        "location": "",
        "start": "06:00",
        "title": "Existing block 1"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-05-26. Candidate requests: id=candidate-A,title=Hale LatticeCalAdd2000 candidate-A design review,start=10:00,duration=45,priority=5,location=KestrelCalAdd2000 Collaboration Hall | id=candidate-B,title=Hale LatticeCalAdd2000 candidate-B design review,start=11:00,duration=60,priority=9,location=KestrelCalAdd2001 Collaboration Hall | id=candidate-C,title=Hale LatticeCalAdd2000 candidate-C design review,start=12:30,duration=30,priority=4,location=KestrelCalAdd2002 Collaboration Hall | id=candidate-D,title=Hale LatticeCalAdd2000 candidate-D design review,start=08:30,duration=15,priority=99,location=KestrelCalAdd2003 Collaboration Hall. A candidate is feasible only when its complete interval does not overlap any existing event on that date. Select one feasible request using policy highest_priority_feasible. Policy definitions: earliest_feasible selects the feasible request with the earliest start; highest_priority_feasible selects the feasible request with the largest numeric priority value; shortest_duration_feasible selects the feasible request with the shortest duration. Apply only the named policy. Add exactly one event with that candidate's exact title, time, location, and these attendees: gaia.kestrelcaladd2000@office-v2.example | lumi.kestrelcaladd2001@office-v2.example | amal.kestrelcaladd2002@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 07

Packet ID: `1e6a7b52f4f95ec2f61a5043ad457f56a6cbe9fd7eae7340b35b02fd44c36e1c`

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
  "prompt": "Create spreadsheet office_43_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Niko BirchXlsxBasic4300,Item=Training,Cost=6300 | Owner=Niko BirchXlsxBasic4300,Item=Equipment,Cost=6425 | Owner=Niko BirchXlsxBasic4300,Item=Licenses,Cost=6550 | Owner=Niko BirchXlsxBasic4300,Item=Travel,Cost=6675 | Owner=Niko BirchXlsxBasic4300,Item=Research,Cost=6800 | Owner=Niko BirchXlsxBasic4300,Item=Facilities,Cost=6925. Row order rule: item_alphabetical. Add exactly one final Total row whose Cost cell is exactly the formula '=SUM(C2:C7)'.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 08

Packet ID: `1eb034156751b02fae182506a8e5346a1b87952480b6775a72ad82ac11003bdc`

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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative LatticeMultiOffsite0000'. Select one detail source using policy latest_issued. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly with no attendees. Reply to its sender with the exact body 'I will attend.' Create office_00_offsite.pptx with exactly one slide whose title is exactly the selected event name. Its bullets must be exactly the listed facts, one fact per bullet in the listed order, with no labels and no additional bullet. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 09

Packet ID: `264a3837076c5f04d37ab689ff83ab1fd1c8193e4dc76ee2ac86d2e433cf725c`

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
  "prompt": "Inspect calendar date 2028-05-11. Send exactly one chat message to Perrin LatticeCalBrief1800. Include, in policy severity_descending order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. The first message may contain only those formatted entries: exclude every other title and do not include any calendar date. Then send exactly one separate chat message to Niko JuniperCalBrief1800 containing, in this exact order, '2028-05-11' and 'priority-count=5'.",
  "subepisode_prompts": [],
  "today": "2028-05-08"
}
```

## Packet 10

Packet ID: `2857ef06e336b535bac01839339837c52f69649e3d454587aa6a6f4adb10302e`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative JuniperEmailReply2000 / REQUIRED /'. Select exactly one request using policy highest_priority. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative JuniperEmailReply2000'. Begin the body exactly with 'I will attend.' Then include, in this exact order, the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 11

Packet ID: `28708f86cc7bf6952185bfb7a2bde0ddadb13e9bb7d0bd3054fa141955819258`

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
    "For subject hale.dovetailpreferencelearning4100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_specific_scope. Policy definitions: most_recent selects the largest timestamp_rank; highest_priority selects the largest priority; most_specific_scope selects the largest scope_specificity. Apply only the named policy. Save exactly one memory. Its complete content must contain these fields in this exact order, separated only by semicolons: subject, duration_minutes, earliest_start, location, title_prefix. Copy subject from the subject above and copy the other four values from the selected bundle. Do not include its id or ranks.",
    "Schedule exactly one sync with Hale DovetailPreferenceLearning4100 on 2028-10-17. The attendee is hale.dovetailpreferencelearning4100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle. Treat the stored earliest_start as the exact event start. Construct the exact event title by concatenating the stored title_prefix, one space, the lowercase literal 'sync with ', and the exact colleague name shown above. The winning start, duration, location, and title prefix are not repeated here."
  ],
  "today": "2028-10-16"
}
```

## Packet 12

Packet ID: `2b31b6f24d25dc0ebebd8983e5ac6d28fe60bb87ca34c177c1c97239f4167b98`

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
        "date": "2028-03-10",
        "end": "09:00",
        "id": "candidate-feasibility-blocker",
        "location": "",
        "start": "08:30",
        "title": "Protected focus block"
      },
      {
        "attendees": [],
        "date": "2028-03-10",
        "end": "06:30",
        "id": "adjacent-0",
        "location": "",
        "start": "06:00",
        "title": "Existing block 1"
      },
      {
        "attendees": [],
        "date": "2028-03-10",
        "end": "07:00",
        "id": "adjacent-1",
        "location": "",
        "start": "06:30",
        "title": "Existing block 2"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-03-10. Candidate requests: id=candidate-A,title=Bryn BirchCalAdd0900 candidate-A design review,start=10:00,duration=45,priority=5,location=AsterCalAdd0900 Collaboration Hall | id=candidate-B,title=Bryn BirchCalAdd0900 candidate-B design review,start=11:00,duration=60,priority=9,location=AsterCalAdd0901 Collaboration Hall | id=candidate-C,title=Bryn BirchCalAdd0900 candidate-C design review,start=12:30,duration=30,priority=4,location=AsterCalAdd0902 Collaboration Hall | id=candidate-D,title=Bryn BirchCalAdd0900 candidate-D design review,start=08:30,duration=15,priority=99,location=AsterCalAdd0903 Collaboration Hall. A candidate is feasible only when its complete interval does not overlap any existing event on that date. Select one feasible request using policy earliest_feasible. Policy definitions: earliest_feasible selects the feasible request with the earliest start; highest_priority_feasible selects the feasible request with the largest numeric priority value; shortest_duration_feasible selects the feasible request with the shortest duration. Apply only the named policy. Add exactly one event with that candidate's exact title, time, location, and these attendees: amal.astercaladd0900@office-v2.example | fint.astercaladd0901@office-v2.example | kavi.astercaladd0902@office-v2.example | perrin.astercaladd0903@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-03-06"
}
```

## Packet 13

Packet ID: `32b2e03eb92bc25b0ed337bd1cefcfef28b0dd399e20e08826b70b5032873e5b`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 24 /'. Then create office_24_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: amount_descending. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row whose Amount cell is exactly the formula '=SUM(C2:C4)'. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-06-19"
}
```

## Packet 14

Packet ID: `35b5274c0fe2f429101f40fa5786e7b6832e1fd70fc603f38f4220189699ed99`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 30 /'. Then create office_30_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: amount_descending. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row whose Amount cell is exactly the formula '=SUM(C2:C6)'. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-07-31"
}
```

## Packet 15

Packet ID: `378113d928f0945fd1e450b7cae0999a882d97711b49743c7cffe79e2b01a4df`

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
  "prompt": "Inspect calendar date 2028-11-30. Send exactly one chat message to Orla CinderCalBrief4700. Include, in policy owner_alphabetical order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. The first message may contain only those formatted entries: exclude every other title and do not include any calendar date. Then send exactly one separate chat message to Mara AsterCalBrief4700 containing, in this exact order, '2028-11-30' and 'priority-count=6'.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 16

Packet ID: `3f4ae9449c35407701792b47b6420071cef2a4befce0220aa557251bb1371144`

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
  "prompt": "Inspect calendar date 2028-09-21. Send exactly one chat message to Iris EmberCalBrief3700. Include, in policy owner_alphabetical order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. The first message may contain only those formatted entries: exclude every other title and do not include any calendar date. Then send exactly one separate chat message to Gaia CinderCalBrief3700 containing, in this exact order, '2028-09-21' and 'priority-count=4'.",
  "subepisode_prompts": [],
  "today": "2028-09-18"
}
```

## Packet 17

Packet ID: `3fdd97c1284d84079b526c30a80137cd80a68bf8b02f9b65d6e9f78d4d1f8bb4`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative DovetailEmailReply1800 / REQUIRED /'. Select exactly one request using policy highest_priority. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative DovetailEmailReply1800'. Begin the body exactly with 'I will attend.' Then include, in this exact order, the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-05-08"
}
```

## Packet 18

Packet ID: `50c2df7cd855678cd7e6f30c42051a8dd14e9c4b91ef46765ebefeeefc341119`

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
    "For subject iris.asterpreferencelearning3100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy highest_priority. Policy definitions: most_recent selects the largest timestamp_rank; highest_priority selects the largest priority; most_specific_scope selects the largest scope_specificity. Apply only the named policy. Save exactly one memory. Its complete content must contain these fields in this exact order, separated only by semicolons: subject, duration_minutes, earliest_start, location, title_prefix. Copy subject from the subject above and copy the other four values from the selected bundle. Do not include its id or ranks.",
    "Schedule exactly one sync with Iris AsterPreferenceLearning3100 on 2028-08-08. The attendee is iris.asterpreferencelearning3100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle. Treat the stored earliest_start as the exact event start. Construct the exact event title by concatenating the stored title_prefix, one space, the lowercase literal 'sync with ', and the exact colleague name shown above. The winning start, duration, location, and title prefix are not repeated here."
  ],
  "today": "2028-08-07"
}
```

## Packet 19

Packet ID: `56fcc1f576f4797ae6bbc6569300c8fbe8f6cfbce4d97b101c1381a58ccdd70c`

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
  "prompt": "Create spreadsheet office_30_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Mara IndigoXlsxBasic3000,Item=Training,Cost=4675 | Owner=Mara IndigoXlsxBasic3000,Item=Equipment,Cost=4800 | Owner=Mara IndigoXlsxBasic3000,Item=Licenses,Cost=4925 | Owner=Mara IndigoXlsxBasic3000,Item=Travel,Cost=5050 | Owner=Mara IndigoXlsxBasic3000,Item=Research,Cost=5175. Row order rule: cost_descending. Add exactly one final Total row whose Cost cell is exactly the formula '=SUM(C2:C6)'.",
  "subepisode_prompts": [],
  "today": "2028-07-31"
}
```

## Packet 20

Packet ID: `5e6f1b585af7913d0864c2aa7b14dbdf9e4e3ccacb7ad69b6c06ee7c3fb02396`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-06-15,priority=5,depends_on=none | id=checkpoint-2,due=2028-06-16,priority=9,depends_on=none | id=checkpoint-3,due=2028-06-17,priority=7,depends_on=checkpoint-1 | id=checkpoint-4,due=2028-06-18,priority=4,depends_on=checkpoint-3 | id=checkpoint-5,due=2028-06-19,priority=3,depends_on=checkpoint-4 | id=checkpoint-6,due=2028-06-20,priority=2,depends_on=checkpoint-5. Order them using policy priority_descending. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Gaia KestrelRemindMsg2300 repeating the same full ordered ID list in order, followed by the exact sentence 'The full checklist will be complete by 2028-06-16.' This date is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-06-12"
}
```

## Packet 21

Packet ID: `61fb85d16898e29ac1a17b7cb9aa79c33d35db6afddc0fa5a9f163fc91283602`

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
        "date": "2028-12-01",
        "end": "09:00",
        "id": "candidate-feasibility-blocker",
        "location": "",
        "start": "08:30",
        "title": "Protected focus block"
      },
      {
        "attendees": [],
        "date": "2028-12-01",
        "end": "06:30",
        "id": "adjacent-0",
        "location": "",
        "start": "06:00",
        "title": "Existing block 1"
      },
      {
        "attendees": [],
        "date": "2028-12-01",
        "end": "07:00",
        "id": "adjacent-1",
        "location": "",
        "start": "06:30",
        "title": "Existing block 2"
      },
      {
        "attendees": [],
        "date": "2028-12-01",
        "end": "07:30",
        "id": "adjacent-2",
        "location": "",
        "start": "07:00",
        "title": "Existing block 3"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-12-01. Candidate requests: id=candidate-A,title=Jori JuniperCalAdd4700 candidate-A design review,start=10:00,duration=45,priority=5,location=IndigoCalAdd4700 Collaboration Hall | id=candidate-B,title=Jori JuniperCalAdd4700 candidate-B design review,start=11:00,duration=60,priority=9,location=IndigoCalAdd4701 Collaboration Hall | id=candidate-C,title=Jori JuniperCalAdd4700 candidate-C design review,start=12:30,duration=30,priority=4,location=IndigoCalAdd4702 Collaboration Hall | id=candidate-D,title=Jori JuniperCalAdd4700 candidate-D design review,start=08:30,duration=15,priority=99,location=IndigoCalAdd4703 Collaboration Hall. A candidate is feasible only when its complete interval does not overlap any existing event on that date. Select one feasible request using policy shortest_duration_feasible. Policy definitions: earliest_feasible selects the feasible request with the earliest start; highest_priority_feasible selects the feasible request with the largest numeric priority value; shortest_duration_feasible selects the feasible request with the shortest duration. Apply only the named policy. Add exactly one event with that candidate's exact title, time, location, and these attendees: iris.indigocaladd4700@office-v2.example | niko.indigocaladd4701@office-v2.example | cato.indigocaladd4702@office-v2.example | hale.indigocaladd4703@office-v2.example | mara.indigocaladd4704@office-v2.example | bryn.indigocaladd4705@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 22

Packet ID: `704ee5bd8740eed95eef25e938c7f9a627de5bb4fdf2d818cd4ef96f045a198a`

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

## Packet 23

Packet ID: `71439d8b4eef49528d999c5fe452ea50bd98f730cc93219810fff8b71ce6d449`

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
  "prompt": "Create presentation office_43_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative HarborPptxBasic4300-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative HarborPptxBasic4300-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative HarborPptxBasic4300-approved-fact-3 | section=Decision,sequence=4,risk=3,owner=Owner-D,fact=Initiative HarborPptxBasic4300-approved-fact-4 | section=Owners,sequence=6,risk=2,owner=Owner-E,fact=Initiative HarborPptxBasic4300-approved-fact-5 | section=Next Steps,sequence=5,risk=1,owner=Owner-F,fact=Initiative HarborPptxBasic4300-approved-fact-6. Order section slides by policy owner_alphabetical. Policy definitions: brief_sequence sorts by the smallest sequence value first; risk_descending sorts by the largest risk value first, breaking ties by section name; owner_alphabetical sorts by owner then section name alphabetically. Apply only the named policy. Use exactly 7 slides: one title slide named 'Initiative HarborPptxBasic4300 Review' with no body text, then one slide per section. Use each section name as its exact slide title. Each section slide's only bullet must be exactly that section's fact value, with no label and no additional bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 24

Packet ID: `7332dcb6fce5a4d2d5093f048f20fea0d3f8cac537da5f0e814292c48245d736`

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
  "prompt": "Create presentation office_00_review.pptx from these approved section records: section=Context,sequence=3,risk=5,owner=Owner-A,fact=Initiative FablePptxBasic0000-approved-fact-1 | section=Evidence,sequence=1,risk=4,owner=Owner-B,fact=Initiative FablePptxBasic0000-approved-fact-2 | section=Options,sequence=2,risk=6,owner=Owner-C,fact=Initiative FablePptxBasic0000-approved-fact-3. Order section slides by policy brief_sequence. Policy definitions: brief_sequence sorts by the smallest sequence value first; risk_descending sorts by the largest risk value first, breaking ties by section name; owner_alphabetical sorts by owner then section name alphabetically. Apply only the named policy. Use exactly 4 slides: one title slide named 'Initiative FablePptxBasic0000 Review' with no body text, then one slide per section. Use each section name as its exact slide title. Each section slide's only bullet must be exactly that section's fact value, with no label and no additional bullet. Do not create any other artifact.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 25

Packet ID: `8dac03b697880b895aa71d40ad935f74b807cb091bc8ae6753ae636eeb651788`

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
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative DovetailPptxFromEmail1300 /'. Then create office_13_regions.pptx with title slide 'Initiative DovetailPptxFromEmail1300 Revenue Review', followed by one slide per approved email ordered by policy sequence_ascending. The title slide must have no body text. Use Region as each exact section-slide title. Each section slide's only bullet must be exactly the bare Revenue cents integer, with no label and no additional bullet. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 26

Packet ID: `8e026f3051c0c24ed0204e4fbe8651e5764f3c9d41bae92261c4a6c720ba447a`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-01-20,priority=5,depends_on=none | id=checkpoint-2,due=2028-01-21,priority=9,depends_on=none | id=checkpoint-3,due=2028-01-22,priority=7,depends_on=checkpoint-1 | id=checkpoint-4,due=2028-01-23,priority=4,depends_on=checkpoint-3 | id=checkpoint-5,due=2028-01-24,priority=3,depends_on=checkpoint-4. Order them using policy due_date_ascending. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Orla GroveRemindMsg0200 repeating the same full ordered ID list in order, followed by the exact sentence 'The full checklist will be complete by 2028-01-20.' This date is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-01-17"
}
```

## Packet 27

Packet ID: `90b5706dcf3e5f3d72afff9534862a32d805dcd2c597b6a2c3573b1f5069ac52`

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
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative JuniperPptxFromEmail3500 /'. Then create office_35_regions.pptx with title slide 'Initiative JuniperPptxFromEmail3500 Revenue Review', followed by one slide per approved email ordered by policy region_alphabetical. The title slide must have no body text. Use Region as each exact section-slide title. Each section slide's only bullet must be exactly the bare Revenue cents integer, with no label and no additional bullet. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-09-04"
}
```

## Packet 28

Packet ID: `9c11ba44bcdcc04eae0940e1fe113f26ffb4b56f4c43ef93aaa2ef81df23700a`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-10-12,priority=5,depends_on=none | id=checkpoint-2,due=2028-10-13,priority=9,depends_on=none | id=checkpoint-3,due=2028-10-14,priority=7,depends_on=checkpoint-1. Order them using policy dependency_order. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Kavi GroveRemindMsg4000 repeating the same full ordered ID list in order, followed by the exact sentence 'The full checklist will be complete by 2028-10-13.' This date is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-10-09"
}
```

## Packet 29

Packet ID: `a655b238de1e23cc5075d4659c84146e8a1b8e46a3c2960e790cab2193444f04`

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
  "prompt": "Inspect calendar date 2028-05-25. Send exactly one chat message to Fint BirchCalBrief2000. Include, in policy severity_descending order, only event titles beginning 'Priority:' and each start time, formatting every entry exactly as '<title> at <HH:MM>'. The first message may contain only those formatted entries: exclude every other title and do not include any calendar date. Then send exactly one separate chat message to Demi LatticeCalBrief2000 containing, in this exact order, '2028-05-25' and 'priority-count=3'.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 30

Packet ID: `a93200211a681850c3e06cf47a1a147cceb2c002a68cb766d1cb28d6da510fb2`

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
  "prompt": "Create spreadsheet office_13_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Hale DovetailXlsxBasic1300,Item=Training,Cost=2550 | Owner=Hale DovetailXlsxBasic1300,Item=Equipment,Cost=2675 | Owner=Hale DovetailXlsxBasic1300,Item=Licenses,Cost=2800 | Owner=Hale DovetailXlsxBasic1300,Item=Travel,Cost=2925. Row order rule: source_order. Add exactly one final Total row whose Cost cell is exactly the formula '=SUM(C2:C5)'.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 31

Packet ID: `b1e0f58c56f37d18ac9f09162ec0c1b971742a7f39b6a2b83eb924ed995f6fc5`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative JuniperEmailReply1300 / REQUIRED /'. Select exactly one request using policy latest_request. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative JuniperEmailReply1300'. Begin the body exactly with 'I will attend.' Then include, in this exact order, the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-04-03"
}
```

## Packet 32

Packet ID: `be12aafafb8bdc214914e2e3baeecd136942a3fc0dbef7464847bde4d40e313e`

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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative CinderMultiOffsite4300'. Select one detail source using policy consensus_supported. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly with no attendees. Reply to its sender with the exact body 'I will attend.' Create office_43_offsite.pptx with exactly one slide whose title is exactly the selected event name. Its bullets must be exactly the listed facts, one fact per bullet in the listed order, with no labels and no additional bullet. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-10-30"
}
```

## Packet 33

Packet ID: `ceda16567824157a6ab0a39c5b57aa75eabf40ef17820bf832c4047a32a73d9a`

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
    "For subject kavi.kestrelpreferencelearning0100@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_recent. Policy definitions: most_recent selects the largest timestamp_rank; highest_priority selects the largest priority; most_specific_scope selects the largest scope_specificity. Apply only the named policy. Save exactly one memory. Its complete content must contain these fields in this exact order, separated only by semicolons: subject, duration_minutes, earliest_start, location, title_prefix. Copy subject from the subject above and copy the other four values from the selected bundle. Do not include its id or ranks.",
    "Schedule exactly one sync with Kavi KestrelPreferenceLearning0100 on 2028-01-11. The attendee is kavi.kestrelpreferencelearning0100@office-v2.example. Retrieve and apply the selected same-attempt preference bundle. Treat the stored earliest_start as the exact event start. Construct the exact event title by concatenating the stored title_prefix, one space, the lowercase literal 'sync with ', and the exact colleague name shown above. The winning start, duration, location, and title prefix are not repeated here."
  ],
  "today": "2028-01-10"
}
```

## Packet 34

Packet ID: `d2123c8d1ec1669e5448307eb4ee3a3007240a0459b2bcd109cf888ac747f040`

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
  "prompt": "Action items: id=checkpoint-1,due=2028-05-25,priority=5,depends_on=none | id=checkpoint-2,due=2028-05-26,priority=9,depends_on=none | id=checkpoint-3,due=2028-05-27,priority=7,depends_on=checkpoint-1. Order them using policy priority_descending. Policy definitions: due_date_ascending sorts by earliest due date then ID; priority_descending sorts by largest priority then ID; dependency_order repeatedly selects an item whose depends_on value is none or already selected, breaking multiple-eligible ties by larger priority, then earlier due date, then ID. Apply only the named policy. Create exactly one reminder at 14:00 on the first ordered item's due date. Use the resulting full ordered ID list as the reminder checklist. Then send exactly one chat message to Iris AsterRemindMsg2000 repeating the same full ordered ID list in order, followed by the exact sentence 'The full checklist will be complete by 2028-05-26.' This date is the first ordered item's due date. Mention every ordered ID exactly once and do not mention any other checkpoint ID. Preserve all reminders.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 35

Packet ID: `d246fc5f0c7bdfbfc7582cfe8fce318af454445451d96c1d8106c642feaf2de0`

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
        "date": "2028-06-16",
        "end": "09:00",
        "id": "candidate-feasibility-blocker",
        "location": "",
        "start": "08:30",
        "title": "Protected focus block"
      },
      {
        "attendees": [],
        "date": "2028-06-16",
        "end": "06:30",
        "id": "adjacent-0",
        "location": "",
        "start": "06:00",
        "title": "Existing block 1"
      }
    ],
    "memory": [],
    "messages": [],
    "reminders": [],
    "sent_emails": []
  },
  "prompt": "Inspect calendar date 2028-06-16. Candidate requests: id=candidate-A,title=Kavi KestrelCalAdd2300 candidate-A design review,start=10:00,duration=45,priority=5,location=JuniperCalAdd2300 Collaboration Hall | id=candidate-B,title=Kavi KestrelCalAdd2300 candidate-B design review,start=11:00,duration=60,priority=9,location=JuniperCalAdd2301 Collaboration Hall | id=candidate-C,title=Kavi KestrelCalAdd2300 candidate-C design review,start=12:30,duration=30,priority=4,location=JuniperCalAdd2302 Collaboration Hall | id=candidate-D,title=Kavi KestrelCalAdd2300 candidate-D design review,start=08:30,duration=15,priority=99,location=JuniperCalAdd2303 Collaboration Hall. A candidate is feasible only when its complete interval does not overlap any existing event on that date. Select one feasible request using policy highest_priority_feasible. Policy definitions: earliest_feasible selects the feasible request with the earliest start; highest_priority_feasible selects the feasible request with the largest numeric priority value; shortest_duration_feasible selects the feasible request with the shortest duration. Apply only the named policy. Add exactly one event with that candidate's exact title, time, location, and these attendees: jori.junipercaladd2300@office-v2.example | orla.junipercaladd2301@office-v2.example | demi.junipercaladd2302@office-v2.example | iris.junipercaladd2303@office-v2.example | niko.junipercaladd2304@office-v2.example | cato.junipercaladd2305@office-v2.example. Preserve every existing event.",
  "subepisode_prompts": [],
  "today": "2028-06-12"
}
```

## Packet 36

Packet ID: `d6c54ffa8d5406541a17fe964bc7b3cc9b7ca91e3dbcdc54c17595df84429bf4`

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

## Packet 37

Packet ID: `d911ff9597432451efeaa06db2b29469516c2c77fa6cd656289ac4e27be425ef`

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
    "For subject iris.asterpreferencelearning0200@office-v2.example, evaluate these preference bundles: id=bundle-A,timestamp_rank=3,priority=4,scope_specificity=2,duration_minutes=20,earliest_start=10:00,location=Video,title_prefix=Focus: | id=bundle-B,timestamp_rank=2,priority=9,scope_specificity=1,duration_minutes=25,earliest_start=11:00,location=Cedar room,title_prefix=Deep: | id=bundle-C,timestamp_rank=1,priority=3,scope_specificity=3,duration_minutes=30,earliest_start=12:00,location=Studio,title_prefix=Priority:. Select by policy most_recent. Policy definitions: most_recent selects the largest timestamp_rank; highest_priority selects the largest priority; most_specific_scope selects the largest scope_specificity. Apply only the named policy. Save exactly one memory. Its complete content must contain these fields in this exact order, separated only by semicolons: subject, duration_minutes, earliest_start, location, title_prefix. Copy subject from the subject above and copy the other four values from the selected bundle. Do not include its id or ranks.",
    "Schedule exactly one sync with Iris AsterPreferenceLearning0200 on 2028-01-18. The attendee is iris.asterpreferencelearning0200@office-v2.example. Retrieve and apply the selected same-attempt preference bundle. Treat the stored earliest_start as the exact event start. Construct the exact event title by concatenating the stored title_prefix, one space, the lowercase literal 'sync with ', and the exact colleague name shown above. The winning start, duration, location, and title prefix are not repeated here."
  ],
  "today": "2028-01-17"
}
```

## Packet 38

Packet ID: `d9e754596f17b116f4e0a8e596afc6cd5dfd2f9f01ae2bc3ec6714e36cfff064`

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
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative IndigoPptxFromEmail2000 /'. Then create office_20_regions.pptx with title slide 'Initiative IndigoPptxFromEmail2000 Revenue Review', followed by one slide per approved email ordered by policy revenue_descending. The title slide must have no body text. Use Region as each exact section-slide title. Each section slide's only bullet must be exactly the bare Revenue cents integer, with no label and no additional bullet. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-05-22"
}
```

## Packet 39

Packet ID: `e9f51477fa4bc31204e646033bdc659fc327a79be0e10d9f6f0c45f9729e2056`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 34 /'. Then create office_34_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: vendor_alphabetical. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row whose Amount cell is exactly the formula '=SUM(C2:C6)'. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-08-28"
}
```

## Packet 40

Packet ID: `eb9fa697da6ae13ee0bbf62e9eb71afdbf37bb9aca0005a182d3ec8c8f7f9b57`

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
  "prompt": "List the inbox and read every email whose subject begins 'FINAL PAID RECEIPT CASE 00 /'. Then create office_00_expenses.xlsx with headers Date | Vendor | Amount. Include one row per paid receipt. Row order rule: date_ascending. In the Amount column, enter USD dollar values: convert each amount_cents=N source value to N/100 dollars. Add one final Total row whose Amount cell is exactly the formula '=SUM(C2:C4)'. Ignore drafts and quotes.",
  "subepisode_prompts": [],
  "today": "2028-01-03"
}
```

## Packet 41

Packet ID: `ed288d8570cf761723c6ea542080fda6010246052f391bc2892555c9bd94f120`

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
  "prompt": "List the inbox and read the index email with subject 'OFFSITE SOURCE INDEX Initiative DovetailMultiOffsite1200'. Select one detail source using policy latest_issued. Policy definitions: latest_issued selects the largest issued_rank value (also the newest visible detail-email date); highest_approval_rank selects the largest approval_rank value; consensus_supported selects the largest consensus value. Apply only the named policy, then read that exact FINAL OFFSITE DETAIL email. Use only the selected detail to add the offsite event exactly with no attendees. Reply to its sender with the exact body 'I will attend.' Create office_12_offsite.pptx with exactly one slide whose title is exactly the selected event name. Its bullets must be exactly the listed facts, one fact per bullet in the listed order, with no labels and no additional bullet. Ignore draft messages.",
  "subepisode_prompts": [],
  "today": "2028-03-27"
}
```

## Packet 42

Packet ID: `ee6db5a2384b63c996cbcfe12db90f10a4de84664bab60e8a33f312eefe20a75`

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
  "prompt": "List the inbox and read every email whose subject begins 'APPROVED REGION Initiative AsterPptxFromEmail4100 /'. Then create office_41_regions.pptx with title slide 'Initiative AsterPptxFromEmail4100 Revenue Review', followed by one slide per approved email ordered by policy region_alphabetical. The title slide must have no body text. Use Region as each exact section-slide title. Each section slide's only bullet must be exactly the bare Revenue cents integer, with no label and no additional bullet. Ignore DRAFT REGION messages.",
  "subepisode_prompts": [],
  "today": "2028-10-16"
}
```

## Packet 43

Packet ID: `f020cad3c99f429df27da877beea5ff5773b14e4d9ad9257a95c6506b6884d5d`

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
  "prompt": "List the inbox and read the decision plus all three attendance requests with subject prefix 'Initiative LatticeEmailReply4700 / REQUIRED /'. Select exactly one request using policy decision_key_match. Policy definitions: latest_request selects the request with the most recent visible date; highest_priority selects the largest priority value; decision_key_match selects the request whose decision_key exactly equals the decision email's selection_key. Apply only the named policy. Reply exactly once to that request's sender. Subject must contain 'Initiative LatticeEmailReply4700'. Begin the body exactly with 'I will attend.' Then include, in this exact order, the decision's confirmation_code, confirmation_date, and the selected request_id, copying all three field values exactly as shown. Do not reply to any other sender or create any reminder, event, chat message, or file.",
  "subepisode_prompts": [],
  "today": "2028-11-27"
}
```

## Packet 44

Packet ID: `fac1a9798382158f955aeee97b3387fda14f468488e5bf68f53aac58af0c97f3`

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
  "prompt": "Create spreadsheet office_24_budget.xlsx. Headers: Owner | Item | Cost. Approved rows: Owner=Amal AsterXlsxBasic2400,Item=Training,Cost=3925 | Owner=Amal AsterXlsxBasic2400,Item=Equipment,Cost=4050 | Owner=Amal AsterXlsxBasic2400,Item=Licenses,Cost=4175. Row order rule: cost_descending. Add exactly one final Total row whose Cost cell is exactly the formula '=SUM(C2:C4)'.",
  "subepisode_prompts": [],
  "today": "2028-06-19"
}
```
