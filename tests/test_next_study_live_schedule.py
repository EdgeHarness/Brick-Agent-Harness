import copy
from pathlib import Path

import pytest

from bench.next_study_schedule import (
    NextStudyScheduleError, build_development_shakeout_schedule,
    validate_development_shakeout_schedule,
)
from harness.instances import load_canonical_json


ROOT = Path(__file__).resolve().parents[1]


def test_development_shakeout_is_exact_balanced_and_deterministic():
    manifest = load_canonical_json(
        ROOT / "bench" / "manifests" / "office-v2" / "development.json"
    )
    schedule = build_development_shakeout_schedule(manifest, "4" * 64)
    assert validate_development_shakeout_schedule(schedule, manifest) == schedule
    assert schedule["logical_cell_count"] == 22
    assert schedule["maximum_physical_attempts"] == 44
    assert len({item["instance_id"] for item in schedule["records"]}) == 11
    assert {item["condition"] for item in schedule["records"]} == {
        "native_tools", "harness_full",
    }
    assert all(
        len({item["trial_seed"] for item in schedule["records"] if item["family"] == family}) == 1
        for family in {item["family"] for item in schedule["records"]}
    )
    changed = copy.deepcopy(schedule)
    changed["records"][0]["trial_seed"] += 1
    with pytest.raises(NextStudyScheduleError, match="drifted"):
        validate_development_shakeout_schedule(changed, manifest)
