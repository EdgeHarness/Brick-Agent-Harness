"""Per-attempt real-filesystem tools.

Nothing in this module mutates the domain registry or process-wide execution
state. ``build_overlay`` closes each tool over one existing root and returns
an immutable bundle. Path containment is lexical/best-effort: symlinks are not
an OS sandbox, and an enabled PowerShell command is unsandboxed.
"""
from dataclasses import dataclass
import os
import shutil
import subprocess

from .errors import ToolError
from .runtime import ActionPolicy
from .tools import ToolRegistry


MAX_READ_BYTES = 200_000
MAX_OUTPUT_CHARS = 4_000
MAX_LIST_ENTRIES = 300
COMMAND_TIMEOUT = 60

# Never writable, whatever the selected root is.
_DENY_WRITE = (
    os.environ.get("SystemRoot", r"C:\Windows"),
    os.path.join(
        os.environ.get("SystemDrive", "C:") + os.sep, "Program Files"
    ),
    os.path.join(
        os.environ.get("SystemDrive", "C:") + os.sep, "Program Files (x86)"
    ),
    r"C:\Users\Lab User\SAIL\ollama",
    r"C:\Users\Lab User\SAIL\python",
    r"C:\Users\Lab User\SAIL\Project\results",
    r"C:\Users\Lab User\SAIL\Project\harness",
)

WRITE_TOOLS = frozenset(
    {"write_file", "append_file", "delete_path", "move_path", "run_command"}
)

_FILE_RULES = """

You also have file tools whose paths are lexically scoped to the working root
{root}. Paths are relative to that root; this is not an OS sandbox.
- Look before you write: call list_dir or read_file first, so you change the
  file that actually exists instead of one you assumed.
- Never delete or overwrite anything the task did not ask you to change.
- If run_command is available, PowerShell is unsandboxed and can reach outside
  the working root.
- The user is asked to confirm deletes, overwrites and shell commands. If one
  is declined, do not retry it - choose another approach."""

_SHELL_RULES = """

You have a run_command tool for the working directory {root}.
- PowerShell execution is unsandboxed and may access paths outside that
  directory; use it only when the task explicitly requires a shell command.
- The user is asked to confirm each shell command. If one is declined, do not
  retry it - choose another approach."""


@dataclass(frozen=True)
class ExecutionSurface:
    registry: ToolRegistry
    policy: ActionPolicy
    prompt_rules: str


@dataclass(frozen=True)
class FileAccessConfig:
    root: str
    allow_shell: bool = False


@dataclass(frozen=True)
class FileOverlay:
    root: str
    registry: ToolRegistry
    policy: ActionPolicy
    prompt_rules: str

    def compose(self, registry, policy, prompt_rules=""):
        """Atomically merge tools, effects, confirmer, and prompt guidance.

        Two different non-null confirmers are rejected rather than selecting
        one silently.
        """
        base_confirmer = policy.confirmer
        overlay_confirmer = self.policy.confirmer
        if (
            base_confirmer is not None
            and overlay_confirmer is not None
            and base_confirmer is not overlay_confirmer
        ):
            raise ValueError("cannot compose two different confirmers")
        confirmer = overlay_confirmer or base_confirmer
        effects = dict(policy.effect_by_tool)
        effects.update(self.policy.effect_by_tool)
        return ExecutionSurface(
            registry=registry.merged(self.registry),
            policy=ActionPolicy(effects, confirmer),
            prompt_rules=prompt_rules + self.prompt_rules,
        )


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _within(path, root):
    path, root = _norm(path), _norm(root)
    return path == root or path.startswith(root.rstrip("\\/") + os.sep)


def _resolve(access, rel, write=False):
    """Lexically resolve a model path; this does not contain symlink targets."""
    if not isinstance(rel, str) or not rel.strip():
        raise ToolError('path is required, e.g. "notes/todo.txt"')
    raw = os.path.expandvars(os.path.expanduser(rel.strip().strip('"')))
    path = os.path.abspath(os.path.join(access.root, raw))
    if not _within(path, access.root):
        raise ToolError(
            f"path is outside the allowed root {access.root}; stay inside it"
        )
    if write:
        for denied in _DENY_WRITE:
            if _within(path, denied):
                raise ToolError(
                    f"{path} is in a protected location and cannot be modified"
                )
    return path


def _ask(context, action, detail):
    if not context.policy.confirm(action, detail):
        raise ToolError(
            f"the user declined the {action}. Do not retry it; "
            "choose another approach."
        )


def _rel(access, path):
    try:
        return os.path.relpath(path, access.root)
    except ValueError:
        return path


def _clip(text, limit=MAX_OUTPUT_CHARS):
    text = str(text)
    if len(text) <= limit:
        return text
    return (
        text[:limit]
        + f"\n... [truncated, {len(text) - limit} more characters]"
    )


def _list_dir(access, args):
    path = _resolve(access, args.get("path", "."))
    if not os.path.isdir(path):
        raise ToolError(f"{_rel(access, path)} is not a directory")
    out = []
    for name in sorted(os.listdir(path))[:MAX_LIST_ENTRIES]:
        full = os.path.join(path, name)
        if os.path.isdir(full):
            out.append(f"{name}/")
        else:
            try:
                out.append(f"{name} ({os.path.getsize(full)} bytes)")
            except OSError:
                out.append(name)
    if not out:
        return f"{_rel(access, path)} is empty"
    return f"{_rel(access, path)} contains:\n" + "\n".join(out)


def _read_file(access, args):
    path = _resolve(access, args.get("path"))
    if not os.path.isfile(path):
        raise ToolError(f"{_rel(access, path)} does not exist or is not a file")
    size = os.path.getsize(path)
    if size > MAX_READ_BYTES:
        raise ToolError(
            f"{_rel(access, path)} is {size} bytes, too large to read "
            f"(limit {MAX_READ_BYTES})"
        )
    with open(path, "rb") as handle:
        blob = handle.read()
    if b"\x00" in blob[:2000]:
        raise ToolError(
            f"{_rel(access, path)} looks like a binary file; "
            "it cannot be read as text"
        )
    return _clip(blob.decode("utf-8", errors="replace"))


def _write_file(access, context, args):
    path = _resolve(access, args.get("path"), write=True)
    content = args.get("content")
    if content is None:
        raise ToolError("missing required parameter 'content'")
    content = content if isinstance(content, str) else str(content)
    if os.path.exists(path):
        _ask(
            context,
            "overwrite",
            f"{path} ({os.path.getsize(path)} bytes will be replaced)",
        )
    os.makedirs(os.path.dirname(path) or access.root, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return f"wrote {len(content)} characters to {_rel(access, path)}"


def _append_file(access, args):
    path = _resolve(access, args.get("path"), write=True)
    text = args.get("text")
    if text is None:
        raise ToolError("missing required parameter 'text'")
    os.makedirs(os.path.dirname(path) or access.root, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(str(text) + "\n")
    return f"appended 1 line to {_rel(access, path)}"


def _delete_path(access, context, args):
    path = _resolve(access, args.get("path"), write=True)
    if not os.path.exists(path):
        raise ToolError(f"{_rel(access, path)} does not exist")
    if os.path.isdir(path):
        count = sum(len(files) for _, _, files in os.walk(path))
        _ask(
            context,
            "delete",
            f"{path} (directory containing {count} files)",
        )
        shutil.rmtree(path)
        return f"deleted directory {_rel(access, path)} and {count} files"
    _ask(context, "delete", f"{path} ({os.path.getsize(path)} bytes)")
    os.remove(path)
    return f"deleted {_rel(access, path)}"


def _move_path(access, context, args):
    source = _resolve(access, args.get("path"), write=True)
    destination = _resolve(access, args.get("to"), write=True)
    if not os.path.exists(source):
        raise ToolError(f"{_rel(access, source)} does not exist")
    if os.path.exists(destination):
        raise ToolError(
            f"{_rel(access, destination)} already exists; delete it first "
            "or choose another name"
        )
    _ask(context, "move", f"{source} -> {destination}")
    os.makedirs(os.path.dirname(destination) or access.root, exist_ok=True)
    shutil.move(source, destination)
    return (
        f"moved {_rel(access, source)} to "
        f"{_rel(access, destination)}"
    )


def _search_files(access, args):
    query = args.get("query")
    if not query:
        raise ToolError("missing required parameter 'query'")
    query = str(query).lower()
    root = _resolve(access, args.get("path", "."))
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name
            for name in dirnames
            if not name.startswith(".") and name != "__pycache__"
        ]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if query in name.lower():
                hits.append(f"{_rel(access, full)} (filename match)")
            elif os.path.splitext(name)[1].lower() in (
                ".txt",
                ".md",
                ".py",
                ".json",
                ".csv",
                ".ps1",
                ".log",
                ".ini",
                ".yml",
                ".yaml",
            ):
                try:
                    if os.path.getsize(full) > MAX_READ_BYTES:
                        continue
                    with open(
                        full, encoding="utf-8", errors="ignore"
                    ) as handle:
                        for line_number, line in enumerate(handle, 1):
                            if query in line.lower():
                                hits.append(
                                    f"{_rel(access, full)}:{line_number}: "
                                    f"{line.strip()[:120]}"
                                )
                                break
                except OSError:
                    continue
            if len(hits) >= 40:
                return "found (showing first 40):\n" + "\n".join(hits)
    if hits:
        return "found:\n" + "\n".join(hits)
    return f"no matches for {query!r} under {_rel(access, root)}"


def _run_command(access, context, args):
    if not access.allow_shell:
        raise ToolError(
            "shell access is disabled for this agent; "
            "use the file tools instead"
        )
    command = args.get("command")
    if not command:
        raise ToolError("missing required parameter 'command'")
    _ask(context, "shell command", str(command))
    try:
        process = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                str(command),
            ],
            cwd=access.root,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise ToolError(f"command timed out after {COMMAND_TIMEOUT}s")
    output = (process.stdout or "") + (
        ("\n[stderr]\n" + process.stderr) if process.stderr else ""
    )
    return _clip(
        f"exit code {process.returncode}\n{output.strip() or '(no output)'}"
    )


def _file_specs(access):
    return {
        "list_dir": {
            "desc": "List the files and folders in a directory on the real computer.",
            "params": {
                "path": (
                    "string, folder path relative to the working root; "
                    "omit for the root itself",
                    False,
                )
            },
            "example": {"tool": "list_dir", "args": {"path": "."}},
            "run": lambda context, args: _list_dir(access, args),
        },
        "read_file": {
            "desc": "Read the text contents of a real file on this computer.",
            "params": {"path": ("string, path to the file", True)},
            "example": {
                "tool": "read_file",
                "args": {"path": "notes/todo.txt"},
            },
            "run": lambda context, args: _read_file(access, args),
        },
        "write_file": {
            "desc": "Create a real file, or replace its entire contents. Writes the exact text given.",
            "params": {
                "path": ("string, path to the file", True),
                "content": ("string, the full text to write", True),
            },
            "example": {
                "tool": "write_file",
                "args": {
                    "path": "notes/summary.txt",
                    "content": "Three meetings on Wednesday.",
                },
            },
            "run": lambda context, args: _write_file(
                access, context, args
            ),
        },
        "append_file": {
            "desc": "Add one line to the end of a real file, creating it if needed.",
            "params": {
                "path": ("string, path to the file", True),
                "text": ("string, the line to add", True),
            },
            "example": {
                "tool": "append_file",
                "args": {
                    "path": "notes/log.txt",
                    "text": "Called Dana.",
                },
            },
            "run": lambda context, args: _append_file(access, args),
        },
        "delete_path": {
            "desc": "Delete a real file or folder. This cannot be undone, so be certain first.",
            "params": {"path": ("string, path to delete", True)},
            "example": {
                "tool": "delete_path",
                "args": {"path": "notes/draft.txt"},
            },
            "run": lambda context, args: _delete_path(
                access, context, args
            ),
        },
        "move_path": {
            "desc": "Move or rename a real file or folder.",
            "params": {
                "path": ("string, what to move", True),
                "to": ("string, the new path", True),
            },
            "example": {
                "tool": "move_path",
                "args": {"path": "a.txt", "to": "archive/a.txt"},
            },
            "run": lambda context, args: _move_path(
                access, context, args
            ),
        },
        "search_files": {
            "desc": "Search filenames and text files for a word or phrase, under a folder.",
            "params": {
                "query": (
                    "string, the word or phrase to look for",
                    True,
                ),
                "path": (
                    "string, folder to search in; omit for the whole root",
                    False,
                ),
            },
            "example": {
                "tool": "search_files",
                "args": {"query": "invoice"},
            },
            "run": lambda context, args: _search_files(access, args),
        },
        "run_command": {
            "desc": "Run one PowerShell command on this computer and read its output.",
            "params": {
                "command": ("string, the command line to run", True)
            },
            "example": {
                "tool": "run_command",
                "args": {"command": "git status --short"},
            },
            "run": lambda context, args: _run_command(
                access, context, args
            ),
        },
    }


def build_overlay(
    root, allow_shell=False, confirmer=None, shell_only=False
):
    """Return one non-global, lexically scoped filesystem overlay."""
    if shell_only and not allow_shell:
        raise ValueError("shell_only=True requires allow_shell=True")
    resolved = os.path.abspath(
        os.path.expandvars(os.path.expanduser(str(root)))
    )
    if not os.path.isdir(resolved):
        raise ToolError(f"working root {resolved} does not exist")
    access = FileAccessConfig(resolved, bool(allow_shell))
    all_specs = _file_specs(access)
    selected = {
        name: spec
        for name, spec in all_specs.items()
        if not (shell_only and name != "run_command")
        and not (name == "run_command" and not allow_shell)
    }
    effects = {name: "read" for name in selected}
    for name in WRITE_TOOLS:
        if name in selected:
            effects[name] = (
                "shell" if name == "run_command" else "external_write"
            )
    rules = _SHELL_RULES if shell_only else _FILE_RULES
    return FileOverlay(
        root=resolved,
        registry=ToolRegistry(selected),
        policy=ActionPolicy(effects, confirmer),
        prompt_rules=rules.format(root=resolved),
    )
