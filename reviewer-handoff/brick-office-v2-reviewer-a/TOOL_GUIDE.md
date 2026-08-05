# Available tools

These descriptions define what the office assistant can inspect or change.
You do not need to simulate every API call; use them to decide whether the
requested result is possible and what exact result is required.

## `add_event`

Add an event to the calendar.

Parameters:

```json
{
  "properties": {
    "attendees": {
      "items": {
        "format": "email",
        "type": "string"
      },
      "maxItems": 20,
      "type": "array",
      "uniqueItems": true
    },
    "date": {
      "format": "date",
      "type": "string"
    },
    "end_time": {
      "format": "time",
      "type": "string"
    },
    "location": {
      "maxLength": 300,
      "type": "string"
    },
    "start_time": {
      "format": "time",
      "type": "string"
    },
    "title": {
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "title",
    "date",
    "start_time",
    "end_time"
  ],
  "type": "object"
}
```

## `create_presentation`

Create a real .pptx PowerPoint file. Each slide is an object with a 'title' and an optional 'bullets' list. A first slide without bullets becomes a title slide.

Parameters:

```json
{
  "properties": {
    "filename": {
      "maxLength": 120,
      "pattern": "(?i)^.+\\.pptx$",
      "type": "string"
    },
    "slides": {
      "items": {
        "properties": {
          "bullets": {
            "items": {
              "minLength": 1,
              "type": "string"
            },
            "maxItems": 20,
            "type": "array"
          },
          "subtitle": {
            "maxLength": 500,
            "type": "string"
          },
          "title": {
            "minLength": 1,
            "type": "string"
          }
        },
        "required": [
          "title"
        ],
        "type": "object"
      },
      "maxItems": 16,
      "minItems": 1,
      "type": "array"
    }
  },
  "required": [
    "filename",
    "slides"
  ],
  "type": "object"
}
```

## `create_spreadsheet`

Create a real .xlsx Excel file from a list of rows (first row is usually headers). A cell string starting with '=' becomes a formula.

Parameters:

```json
{
  "properties": {
    "filename": {
      "maxLength": 120,
      "pattern": "(?i)^.+\\.xlsx$",
      "type": "string"
    },
    "rows": {
      "items": {
        "items": {
          "maxLength": 1000,
          "type": "string"
        },
        "maxItems": 12,
        "minItems": 1,
        "type": "array"
      },
      "maxItems": 30,
      "minItems": 1,
      "type": "array"
    },
    "sheet_name": {
      "maxLength": 31,
      "type": "string"
    }
  },
  "required": [
    "filename",
    "rows"
  ],
  "type": "object"
}
```

## `done`

Call this exactly once, when the entire task is finished, with a short summary.

Parameters:

```json
{
  "properties": {
    "summary": {
      "maxLength": 1000,
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "summary"
  ],
  "type": "object"
}
```

## `list_emails`

List all emails in the inbox (id, from, date, subject). Newest first.

Parameters:

```json
{
  "properties": {},
  "required": [],
  "type": "object"
}
```

## `list_events`

List calendar events, optionally only for one date.

Parameters:

```json
{
  "properties": {
    "date": {
      "format": "date",
      "type": "string"
    }
  },
  "required": [],
  "type": "object"
}
```

## `read_email`

Read the full body of one email by its id.

Parameters:

```json
{
  "properties": {
    "id": {
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "id"
  ],
  "type": "object"
}
```

## `read_spreadsheet`

Read back the cell contents of an existing .xlsx file.

Parameters:

```json
{
  "properties": {
    "filename": {
      "maxLength": 120,
      "pattern": "(?i)^.+\\.xlsx$",
      "type": "string"
    }
  },
  "required": [
    "filename"
  ],
  "type": "object"
}
```

## `recall_memories`

Search long-term memory for saved facts relevant to a query.

Parameters:

```json
{
  "properties": {
    "query": {
      "maxLength": 500,
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "query"
  ],
  "type": "object"
}
```

## `save_memory`

Save a fact or preference to long-term memory so it persists across future tasks.

Parameters:

```json
{
  "properties": {
    "fact": {
      "maxLength": 2000,
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "fact"
  ],
  "type": "object"
}
```

## `send_email`

Send an email.

Parameters:

```json
{
  "properties": {
    "body": {
      "minLength": 1,
      "type": "string"
    },
    "subject": {
      "minLength": 1,
      "type": "string"
    },
    "to": {
      "format": "email",
      "type": "string"
    }
  },
  "required": [
    "to",
    "subject",
    "body"
  ],
  "type": "object"
}
```

## `send_message`

Send a chat/instant message to a person.

Parameters:

```json
{
  "properties": {
    "text": {
      "minLength": 1,
      "type": "string"
    },
    "to": {
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "to",
    "text"
  ],
  "type": "object"
}
```

## `set_reminder`

Set a reminder for yourself at a specific date and time.

Parameters:

```json
{
  "properties": {
    "date": {
      "format": "date",
      "type": "string"
    },
    "text": {
      "minLength": 1,
      "type": "string"
    },
    "time": {
      "format": "time",
      "type": "string"
    }
  },
  "required": [
    "text",
    "date",
    "time"
  ],
  "type": "object"
}
```

## `think`

Think out loud about the task. Use this to reason before acting. Has no external effect.

Parameters:

```json
{
  "properties": {
    "thought": {
      "maxLength": 4096,
      "minLength": 1,
      "type": "string"
    }
  },
  "required": [
    "thought"
  ],
  "type": "object"
}
```
