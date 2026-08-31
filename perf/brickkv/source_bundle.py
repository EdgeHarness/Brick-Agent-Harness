"""Deterministically bind every source file executed by the CHTC GPU job."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import stat
import subprocess


SOURCE_FILES = tuple(sorted((
    "perf/__init__.py",
    "perf/brickkv/__init__.py",
    "perf/brickkv/run_matrix.py",
    "perf/brickkv/gpu_prefix_study.py",
    "perf/brickkv/gpu_matrix.py",
    "perf/brickkv/safe_extract.py",
    "perf/brickkv/source_bundle.py",
    "perf/brickkv/chtc/run_vllm_apc.sh",
    "perf/brickkv/chtc/vllm-apc.sub",
)))
REVISION_PATTERN = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


def _frame(digest, label: bytes, value: bytes):
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def _revision(value: str) -> str:
    if not isinstance(value, str) or not REVISION_PATTERN.fullmatch(value):
        raise RuntimeError("source revision must be a full lowercase Git object ID")
    return value


def source_bundle_digest(root: Path, revision: str, paths=SOURCE_FILES) -> str:
    root = root.resolve(strict=True)
    revision = _revision(revision)
    digest = hashlib.sha256()
    _frame(digest, b"format", b"brickkv-source-bundle/2")
    _frame(digest, b"source_revision", revision.encode("ascii"))
    for relative in sorted(paths):
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise RuntimeError(f"unsafe source bundle path: {relative}")
        path = root / relative
        before = path.lstat()
        if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
            raise RuntimeError(f"source bundle entry is not a regular file: {relative}")
        content = path.read_bytes()
        after = path.lstat()
        if (
            stat.S_ISLNK(after.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(content) != after.st_size
        ):
            raise RuntimeError(f"source bundle entry changed while hashing: {relative}")
        _frame(digest, b"path", relative.encode("utf-8"))
        _frame(digest, b"content", content)
    return "sha256:" + digest.hexdigest()


def verify_git_revision(root: Path, revision: str, paths=SOURCE_FILES) -> None:
    """Require the submitted runner files to be clean files at repository HEAD."""
    root = root.resolve(strict=True)
    revision = _revision(revision)
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if head.returncode != 0 or head.stdout.decode("ascii", "replace").strip() != revision:
        raise RuntimeError("source revision is not the repository HEAD commit")
    status = subprocess.run(
        [
            "git", "status", "--porcelain=v1", "--untracked-files=all",
            "--", *sorted(paths),
        ],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if status.returncode != 0:
        raise RuntimeError("Git could not verify the submitted source files")
    if status.stdout:
        raise RuntimeError("submitted source files differ from the source revision")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--revision", required=True)
    parser.add_argument("--verify-git", action="store_true")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.verify_git:
        verify_git_revision(root, args.revision)
    print(source_bundle_digest(root, args.revision))


if __name__ == "__main__":
    main()
