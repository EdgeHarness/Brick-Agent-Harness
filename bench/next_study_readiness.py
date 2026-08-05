"""Model-free readiness report for the successor instrument.

This command never authorizes or executes a model.  It distinguishes completed
apparatus work from live shakeout and host-bound gates that software cannot
truthfully synthesize.
"""

import argparse
import json

from harness.instances import load_canonical_json

from . import generate_next_study
from .next_study_contract import load_design
from .next_study_rehearsal import DEFAULT_OUTPUT as REHEARSAL_PATH
from .next_study_schedule import verify_descriptive_selection
from .next_study_statistics import load_protocol


READINESS_SCHEMA = "brick.next-study.authorization-readiness/1"


def _manifests():
    return [
        load_canonical_json(generate_next_study.DEFAULT_DIRECTORY / (split + ".json"))
        for split in (
            "development", "calibration", "validation", "sentinel",
            "retained", "adversarial",
        )
    ]


def build_readiness_report():
    design = load_design()
    protocol = load_protocol()
    selection = verify_descriptive_selection()
    rehearsal = load_canonical_json(REHEARSAL_PATH)
    external_gates = {
        "score_masked_22_cell_development_shakeout": False,
        "clean_checkout_cross_platform_reproduction": False,
        "native_lenovo_preflight": False,
        "pinned_2b_4b_9b_model_digests": False,
        "host_and_runtime_fingerprints": False,
        "annotated_v0_13_0_candidate_tag": False,
        "issued_program_authorization": False,
    }
    return {
        "schema_version": READINESS_SCHEMA,
        "program_identity": "Brick successor controlled comparison",
        "current_activity": "instrument construction and qualification",
        "benchmark_running_now": False,
        "experiment_running_now": False,
        "live_model_calls": 0,
        "design_version": design["version"],
        "protocol_version": protocol["version"],
        "generator_version": design["fresh_suite"]["generator_version"],
        "descriptive_selection_sha256": selection["selection_sha256"],
        "offline_implementation_gates": {
            key: value for key, value in design["execution_gates"].items()
            if value is True
        },
        "external_or_evidence_dependent_gates": external_gates,
        "authorization_buildable": all(external_gates.values()),
        "model_free_rehearsal_passed": rehearsal.get("status") == "passed",
        "human_review_authorization_gate": False,
        "next_transition": (
            "complete native clean-checkout qualification, then separately authorize the score-masked 22-cell development shakeout"
        ),
        "later_transition": (
            "after a zero-invalid shakeout, bind host/model/schedules and issue the annotated v0.13.0 instrument authorization"
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    print(json.dumps(build_readiness_report(), sort_keys=True))


if __name__ == "__main__":
    main()


__all__ = ["READINESS_SCHEMA", "build_readiness_report", "main"]
