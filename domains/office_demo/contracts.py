"""Executable native-tool contracts for generated office experiments.

The historical office pack predates S1R and still exposes prose parameter
descriptions through :class:`harness.tools.ToolRegistry`.  S6C must not send
those descriptions to Ollama as if they were executable schemas.  This module
binds the same executors to closed ``ToolContract`` schemas; Ollama schemas and
runtime validation are then derived from the same objects.
"""

from harness import faults
from harness.builtin_tools import builtin_specs
from harness.errors import ToolError
from harness.typed_executor import ToolContract, TypedToolRegistry

from .tools import OFFICE_EFFECTS, office_specs


CONTRACT_VERSION = "office-native-tools/1.0.0"


def _object(properties=None, required=()):
    return {
        "type": "object",
        "properties": properties or {},
        "required": list(required),
    }


_STRING = {"type": "string", "minLength": 1}
_DATE = {"type": "string", "format": "date"}
_TIME = {"type": "string", "format": "time"}
_EMAIL = {"type": "string", "format": "email"}

SCHEMAS = {
    "list_emails": _object(),
    "read_email": _object({"id": _STRING}, ("id",)),
    "send_email": _object(
        {"to": _EMAIL, "subject": _STRING, "body": _STRING},
        ("to", "subject", "body"),
    ),
    "list_events": _object({"date": _DATE}),
    "add_event": _object(
        {
            "title": _STRING,
            "date": _DATE,
            "start_time": _TIME,
            "end_time": _TIME,
            "attendees": {
                "type": "array",
                "items": _EMAIL,
                "maxItems": 20,
                "uniqueItems": True,
            },
            "location": {"type": "string", "maxLength": 300},
        },
        ("title", "date", "start_time", "end_time"),
    ),
    "send_message": _object(
        {"to": _STRING, "text": _STRING}, ("to", "text")
    ),
    "set_reminder": _object(
        {"text": _STRING, "date": _DATE, "time": _TIME},
        ("text", "date", "time"),
    ),
    "create_presentation": _object(
        {
            "filename": {
                "type": "string",
                "pattern": r"(?i)^.+\.pptx$",
                "maxLength": 120,
            },
            "slides": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "items": _object(
                    {
                        "title": _STRING,
                        "bullets": {
                            "type": "array",
                            "items": {"type": "string", "minLength": 1},
                            "maxItems": 20,
                        },
                        "subtitle": {"type": "string", "maxLength": 500},
                    },
                    ("title",),
                ),
            },
        },
        ("filename", "slides"),
    ),
    # A closed, portable schema cannot express heterogeneous spreadsheet cells
    # without a union type.  The native contract therefore requires strings;
    # numeric text and formulas are preserved correctly by openpyxl and are
    # interpreted deterministically by the grader.
    "create_spreadsheet": _object(
        {
            "filename": {
                "type": "string",
                "pattern": r"(?i)^.+\.xlsx$",
                "maxLength": 120,
            },
            "rows": {
                "type": "array",
                "minItems": 1,
                "maxItems": 30,
                "items": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 12,
                    "items": {"type": "string", "maxLength": 1000},
                },
            },
            "sheet_name": {"type": "string", "maxLength": 31},
        },
        ("filename", "rows"),
    ),
    "read_spreadsheet": _object(
        {
            "filename": {
                "type": "string",
                "pattern": r"(?i)^.+\.xlsx$",
                "maxLength": 120,
            }
        },
        ("filename",),
    ),
    "think": _object(
        # A request may generate as many as 700 tokens.  The tool contract must
        # not reject a valid plan or completion review merely because its JSON
        # string crosses a smaller, unrelated character limit.  4096 remains a
        # bounded payload while covering the configured per-request output.
        {"thought": {"type": "string", "minLength": 1, "maxLength": 4096}},
        ("thought",),
    ),
    "save_memory": _object(
        {"fact": {"type": "string", "minLength": 1, "maxLength": 2000}},
        ("fact",),
    ),
    "recall_memories": _object(
        {"query": {"type": "string", "minLength": 1, "maxLength": 500}},
        ("query",),
    ),
    "done": _object(
        {"summary": {"type": "string", "minLength": 1, "maxLength": 1000}},
        ("summary",),
    ),
}


def _end_after_start(args):
    if args["end_time"] <= args["start_time"]:
        return ["end_time must be later than start_time"]
    return []


def _model_input_boundary(executor):
    """Keep deterministic office refusals on the model-fault axis."""

    def wrapped(context, args):
        try:
            return executor(context, args)
        except ToolError as exc:
            raise faults.ModelInputFault(str(exc)) from exc

    return wrapped


def build_registry(alias_recovery=True):
    """Return a fresh ordered registry for one isolated attempt."""

    if type(alias_recovery) is not bool:
        raise TypeError("alias_recovery must be a bool")

    specs = office_specs()
    specs.update(builtin_specs())
    effects = dict(OFFICE_EFFECTS)
    effects.update(
        {
            "think": "read",
            "save_memory": "state_write",
            "recall_memories": "read",
            "done": "read",
        }
    )
    contracts = []
    for name, spec in specs.items():
        executor = spec["run"]
        if name == "done":
            executor = lambda _context, args: {
                "finished": True,
                "summary": args["summary"],
            }
        else:
            executor = _model_input_boundary(executor)
        contracts.append(
            ToolContract(
                name,
                spec["desc"],
                SCHEMAS[name],
                executor,
                mutating=effects[name] != "read",
                invariants=(_end_after_start,) if name == "add_event" else (),
            )
        )
    aliases = (
        {
            # Read-only conveniences only.  No mutating office argument is
            # repaired by a global alias.
            "read_email": {"email_id": "id"},
            "__global__": {"file": "filename"},
        }
        if alias_recovery
        else {}
    )
    return TypedToolRegistry(contracts, alias_table=aliases)


def assert_legacy_surface_agrees():
    """Fail if native argument names drift from the compatibility registry."""

    specs = office_specs()
    specs.update(builtin_specs())
    if tuple(specs) != tuple(SCHEMAS):
        raise RuntimeError("office native tool ordering drifted")
    for name, spec in specs.items():
        properties = SCHEMAS[name].get("properties", {})
        if tuple(spec["params"]) != tuple(properties):
            raise RuntimeError(
                "office native argument names drifted for %s" % name
            )


assert_legacy_surface_agrees()


__all__ = [
    "CONTRACT_VERSION",
    "SCHEMAS",
    "assert_legacy_surface_agrees",
    "build_registry",
]
