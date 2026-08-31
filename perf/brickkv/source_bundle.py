"""Deterministically bind every source file executed by the CHTC GPU job."""
from __future__ import annotations

import hashlib
from pathlib import Path
import stat


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


def _frame(digest, label: bytes, value: bytes):
    digest.update(len(label).to_bytes(4, "big"))
    digest.update(label)
    digest.update(len(value).to_bytes(8, "big"))
    digest.update(value)


def source_bundle_digest(root: Path, paths=SOURCE_FILES) -> str:
    root = root.resolve(strict=True)
    digest = hashlib.sha256()
    _frame(digest, b"format", b"brickkv-source-bundle/1")
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


def main():
    root = Path(__file__).resolve().parents[2]
    print(source_bundle_digest(root))


if __name__ == "__main__":
    main()
