"""Extract a streamed model tar without links, special files, or traversal."""
from __future__ import annotations

import argparse
import os
from pathlib import Path, PurePosixPath
import sys
import tarfile


MAX_MEMBERS = 100_000
MAX_TOTAL_BYTES = 90 * 1024**3


def _relative_member(name: str) -> Path:
    if not name or "\\" in name:
        raise RuntimeError("model archive contains a non-portable member path")
    posix = PurePosixPath(name)
    if posix.is_absolute() or any(part in {"", ".", ".."} for part in posix.parts):
        raise RuntimeError("model archive contains an unsafe member path")
    return Path(*posix.parts)


def extract_stream(stream, destination: Path) -> None:
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    members = 0
    total_bytes = 0
    config_files = 0
    with tarfile.open(fileobj=stream, mode="r|") as archive:
        for member in archive:
            members += 1
            if members > MAX_MEMBERS:
                raise RuntimeError("model archive contains too many members")
            relative = _relative_member(member.name)
            target = destination.joinpath(relative)
            if member.isdir():
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
                continue
            if not member.isreg():
                raise RuntimeError("model archive contains a link or special file")
            if member.size < 0 or total_bytes + member.size > MAX_TOTAL_BYTES:
                raise RuntimeError("model archive exceeds the extraction size limit")
            total_bytes += member.size
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError("model archive regular file has no content")
            observed = 0
            with target.open("xb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    observed += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if observed != member.size:
                raise RuntimeError("model archive member size changed during extraction")
            try:
                target.chmod(0o600)
            except OSError:
                pass
            if target.name == "config.json":
                config_files += 1
    if config_files != 1:
        raise RuntimeError("model archive must contain exactly one config.json")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args(argv)
    extract_stream(sys.stdin.buffer, args.destination)


if __name__ == "__main__":
    main()
