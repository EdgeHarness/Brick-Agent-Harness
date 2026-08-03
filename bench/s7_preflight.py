"""Read-only D0/S7 preflight layered over the frozen S6 instrument."""

import argparse
import json
from importlib import metadata
from pathlib import Path
import sys

from bench import s6_preflight
from bench.s7_contract import DEFAULT_PROTOCOL, load_protocol, s7_protocol_sha256


def collect(protocol_path=DEFAULT_PROTOCOL, require_clean=True):
    protocol = load_protocol(protocol_path)
    analysis = protocol["analysis"]
    actual_minor = "%d.%d" % (sys.version_info.major, sys.version_info.minor)
    if actual_minor != analysis["python_minor"]:
        raise RuntimeError(
            "S7 analysis requires Python %s; found %s"
            % (analysis["python_minor"], actual_minor)
        )
    numpy_version = metadata.version("numpy")
    if numpy_version != analysis["numpy_version"]:
        raise RuntimeError(
            "S7 analysis requires NumPy %s; found %s"
            % (analysis["numpy_version"], numpy_version)
        )
    base_path = Path(__file__).resolve().parents[1] / protocol["base_protocol_path"]
    base = s6_preflight.collect(base_path, require_clean=require_clean)
    environment = dict(base["environment"])
    environment.update({
        "s7_protocol_sha256": s7_protocol_sha256(protocol),
        "analysis_python_minor": actual_minor,
        "analysis_numpy_version": numpy_version,
    })
    return {
        "schema_version": "brick.s7.preflight/1",
        "passed": True,
        "require_clean": bool(require_clean),
        "environment": environment,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--allow-dirty", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = collect(args.protocol, require_clean=not args.allow_dirty)
    except Exception as exc:
        result = {
            "schema_version": "brick.s7.preflight/1",
            "passed": False,
            "error": "%s: %s" % (type(exc).__name__, exc),
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
