import copy

import pytest

from bench.next_study_successor import (
    BLOCKER_CLOSURES, SuccessorAuthorizationError, load_authorization,
    load_closure, validate_authorization, validate_closure,
)


def test_explicit_2_2_0_authorization_preserves_terminal_history():
    authorization = load_authorization()
    assert authorization["from_generator_version"] == "office-generators/2.1.2"
    assert authorization["to_generator_version"] == "office-generators/2.2.0"
    assert authorization["protocol_version"] == "1.5.0"
    assert authorization["target_instrument_tag"] == "v0.13.2"
    assert authorization["live_study_cells_run"] == 0
    assert authorization["no_effectiveness_data_inspected"] is True
    assert authorization["estimand_or_claim_rule_changed"] is False
    assert authorization["authorized_blocker_ids"] == sorted(BLOCKER_CLOSURES)


def test_2_2_0_closure_binds_all_ten_repairs_and_offline_evidence():
    closure = load_closure()
    assert closure["status"] == "passed"
    assert closure["generator_version"] == "office-generators/2.2.0"
    assert closure["protocol_version"] == "1.5.0"
    assert [item["blocker_id"] for item in closure["closed_blockers"]] == sorted(
        BLOCKER_CLOSURES
    )
    assert len(closure["closed_blockers"]) == 10
    assert all(closure["checks"].values())
    assert closure["live_model_calls"] == 0
    assert closure["effectiveness_data_inspected"] is False


def test_successor_authorization_and_closure_fail_closed_on_tampering():
    authorization = copy.deepcopy(load_authorization())
    authorization["authorized_blocker_ids"].pop()
    with pytest.raises(SuccessorAuthorizationError):
        validate_authorization(authorization)

    closure = copy.deepcopy(load_closure())
    closure["checks"]["semantic_simulation_passed"] = False
    with pytest.raises(SuccessorAuthorizationError):
        validate_closure(closure)
