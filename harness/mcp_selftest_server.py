"""Launch Brick's credential-free MCP self-test without package collision.

The official MCP SDK installs a top-level package named ``mcp``. Executing the
self-test as ``mcp.selftest_server`` therefore fails when that SDK is present.
This stable harness module runs the repository fixture by its verified local
path instead of importing through the conflicting package name.
"""

from pathlib import Path
import runpy


def main():
    source = Path(__file__).resolve().parents[1] / "mcp" / "selftest_server.py"
    if not source.is_file():
        raise RuntimeError("Brick MCP self-test source is unavailable")
    runpy.run_path(str(source), run_name="__main__")


if __name__ == "__main__":
    main()
