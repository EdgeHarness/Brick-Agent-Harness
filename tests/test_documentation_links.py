"""Every relative link in a tracked markdown file resolves.

Added after moving six root documents into docs/ silently broke six links that
nothing would have caught: a dead cross-reference in a canonical document is
read as the document being wrong, not the link. Checks tracked files only, so
it fails the same way on a clean clone as it does here.
"""
import pathlib
import re
import subprocess

PROJECT = pathlib.Path(__file__).resolve().parents[1]
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)\s]*)?\)")
EXTERNAL = ("http://", "https://", "mailto:", "#")


def tracked_markdown():
    listed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=PROJECT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [PROJECT / name for name in listed]


def test_every_relative_markdown_link_resolves():
    broken = []
    for path in tracked_markdown():
        for match in LINK.finditer(path.read_text(encoding="utf-8")):
            target = match.group(1)
            if target.startswith(EXTERNAL):
                continue
            if not (path.parent / target).exists():
                broken.append(f"{path.relative_to(PROJECT)} -> {target}")
    assert not broken, "dead documentation links:\n  " + "\n  ".join(broken)


def test_the_canonical_documents_are_where_claude_md_says():
    """CLAUDE.md names three documents canonical. If one moves without that
    file being updated, every session starts from a wrong map."""
    claude = (PROJECT / "CLAUDE.md").read_text(encoding="utf-8")
    for name in ("PROJECT_SETUP.md", "PROJECT_GUIDE.md", "EXECUTION.md"):
        assert (PROJECT / "docs" / name).is_file(), f"docs/{name} is missing"
        assert f"docs/{name}" in claude, f"CLAUDE.md does not point at docs/{name}"
