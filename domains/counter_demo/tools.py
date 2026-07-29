"""Counter-demo tools."""
from harness.errors import ToolError


def _increment(context, args):
    amount = args["amount"]
    if type(amount) is not int:
        raise ToolError("'amount' must be an integer")
    context.world.value += amount
    return {"value": context.world.value}


def counter_specs():
    return {
        "read_counter": {
            "desc": "Read the current counter value.",
            "params": {},
            "example": {"tool": "read_counter", "args": {}},
            "run": lambda context, args: {"value": context.world.value},
        },
        "increment_counter": {
            "desc": "Increase the counter by an integer amount.",
            "params": {"amount": ("integer", True)},
            "example": {
                "tool": "increment_counter",
                "args": {"amount": 1},
            },
            "run": _increment,
            "suppress_identical_repeats": False,
        },
    }
