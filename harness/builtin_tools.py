"""Domain-independent control and memory tools."""
import copy

from .domain import (
    DONE_DESCRIPTION,
    DONE_PARAMS,
    THINK_DESCRIPTION,
    THINK_PARAMS,
)


_NEUTRAL_EXAMPLES = {
    "think": {
        "tool": "think",
        "args": {
            "thought": "The result has three items; I should sort them."
        },
    },
    "save_memory": {
        "tool": "save_memory",
        "args": {"fact": "The preferred output format is JSON."},
    },
    "recall_memories": {
        "tool": "recall_memories",
        "args": {"query": "output preferences"},
    },
    "done": {
        "tool": "done",
        "args": {"summary": "Completed the requested update."},
    },
}


def builtin_specs(examples=None):
    # Return a new ordered mapping so registry composition never shares mutable
    # dictionaries between domains.
    return {
        "think": {
            "desc": THINK_DESCRIPTION,
            "params": THINK_PARAMS,
            "example": copy.deepcopy(
                (examples or _NEUTRAL_EXAMPLES)["think"]
            ),
            "run": lambda c, a: "Noted. Continue with your next action.",
        },
        "save_memory": {
            "desc": "Save a fact or preference to long-term memory so it persists across future tasks.",
            "params": {"fact": ("string", True)},
            "example": copy.deepcopy(
                (examples or _NEUTRAL_EXAMPLES)["save_memory"]
            ),
            "run": lambda c, a: c.memory.save(a["fact"]),
        },
        "recall_memories": {
            "desc": "Search long-term memory for saved facts relevant to a query.",
            "params": {"query": ("string", True)},
            "example": copy.deepcopy(
                (examples or _NEUTRAL_EXAMPLES)["recall_memories"]
            ),
            "run": lambda c, a: (
                c.memory.search(a["query"], k=5) or "no matching memories"
            ),
        },
        "done": {
            "desc": DONE_DESCRIPTION,
            "params": DONE_PARAMS,
            "example": copy.deepcopy(
                (examples or _NEUTRAL_EXAMPLES)["done"]
            ),
            "run": None,
        },
    }


BUILTIN_EFFECTS = {"save_memory": "state_write"}
