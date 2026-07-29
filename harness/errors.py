"""Core errors shared by domain worlds and tool registries."""


class ToolError(Exception):
    """A tool failure whose message is safe to return to the model."""
