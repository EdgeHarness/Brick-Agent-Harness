"""_verify() must never return anything other than what it returns today -
bench/ results are sealed against that value - but a failure to consult the
verifier at all must not look the same as the verifier actually answering.
These tests pin both the fault records and the untouched fallback value.
"""
import requests

from harness import agent


def test_connection_error_records_instrument_fault_and_falls_open(attempt_factory):
    attempt = attempt_factory()
    ep = agent.Episode()

    class Unreachable:
        def chat(self, *a, **k):
            raise requests.ConnectionError("ollama is down")

    verdict = agent._verify(Unreachable(), "Do something", attempt, ep)

    # Byte-identical to the pre-fix fallback: this is what protects the
    # sealed bench numbers, so the return value must not move even though
    # the failure is now recorded.
    assert verdict == {"complete": True, "missing": ""}

    faults = [e for e in ep.transcript if e["kind"] == "verify_fault"]
    assert len(faults) == 1
    assert faults[0]["content"].startswith("instrument:")


def test_unparseable_reply_records_model_output_fault_and_falls_open(attempt_factory):
    attempt = attempt_factory()
    ep = agent.Episode()

    class Garbage:
        def chat(self, *a, **k):
            return "not valid json"

    verdict = agent._verify(Garbage(), "Do something", attempt, ep)

    # Same fallback value as the instrument case above, but the two must be
    # told apart in the transcript - see the "model_output:" prefix below.
    assert verdict == {"complete": True, "missing": ""}

    faults = [e for e in ep.transcript if e["kind"] == "verify_fault"]
    assert len(faults) == 1
    assert faults[0]["content"].startswith("model_output:")


def test_valid_reply_is_returned_unaltered_with_no_fault_recorded(attempt_factory):
    attempt = attempt_factory()
    ep = agent.Episode()

    class Answers:
        def chat(self, *a, **k):
            return '{"complete": false, "missing": "send the email"}'

    verdict = agent._verify(Answers(), "Do something", attempt, ep)

    assert verdict == {"complete": False, "missing": "send the email"}
    assert not [e for e in ep.transcript if e["kind"] == "verify_fault"]
