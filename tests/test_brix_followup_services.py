"""B0 deterministic services for the synthetic lead-follow-up slice.

The exit gate names tenant, approval, concurrency, expiry, idempotency,
ambiguous-delivery, audit and no-network tests. Each section below covers one.

Everything is fictional and nothing reaches a network. The point of the stage is
that the model may read and propose but cannot approve, dispatch, cross a tenant
boundary, choose a recipient, or bypass a policy -- and that those limits are
structural rather than a matter of the model choosing not to ask. If a model
could dispatch, a harness that merely asked more persuasively would score higher
and the measured effect would be persuasion rather than task completion.
"""

import datetime
import threading

import pytest

from domains.brix_followup_synthetic import services as svc


def service(**kwargs):
    return svc.FollowupService(**kwargs)


def approved(service_obj, actor="amy", lead="lead_1001", body="Following up."):
    proposal = service_obj.propose_followup(actor, lead, body)
    service_obj.approve("ben", proposal["proposal_id"],
                        proposal["payload_hash"])
    return proposal


# --- tenant ------------------------------------------------------------------


def test_an_actor_cannot_inspect_another_tenants_lead():
    with pytest.raises(svc.PolicyRefusal):
        service().inspect_lead("amy", "lead_2001")


def test_cross_tenant_refusal_does_not_reveal_that_the_lead_exists():
    """Distinguishing 'not yours' from 'does not exist' is itself a leak."""
    s = service()
    with pytest.raises(svc.PolicyRefusal) as other:
        s.inspect_lead("amy", "lead_2001")
    with pytest.raises(svc.PolicyRefusal) as absent:
        s.inspect_lead("amy", "lead_9999")
    assert str(other.value) == str(absent.value).replace("lead_9999",
                                                         "lead_2001")


def test_due_list_is_confined_to_the_actors_own_assigned_leads():
    due = service().list_due_followups("amy")
    ids = [item["lead_id"] for item in due]
    assert "lead_2001" not in ids       # other tenant
    assert "lead_1003" not in ids       # same tenant, assigned to ben
    assert "lead_1001" in ids


def test_an_actor_cannot_propose_on_another_tenants_lead():
    with pytest.raises(svc.PolicyRefusal):
        service().propose_followup("amy", "lead_2001", "hello")


def test_an_approver_cannot_approve_another_tenants_proposal():
    # lead_2001 falls due on 2030-03-02, so `today` must reach it.
    s = service(today=datetime.date(2030, 3, 2))
    proposal = s.propose_followup("cara", "lead_2001", "hi")
    with pytest.raises(svc.PolicyRefusal):
        s.approve("ben", proposal["proposal_id"], proposal["payload_hash"])


# --- eligibility and the recipient the model cannot choose -------------------


def test_a_lead_not_yet_due_is_excluded_and_cannot_be_proposed():
    s = service()
    assert "lead_1004" not in [i["lead_id"] for i in
                               s.list_due_followups("amy")]
    with pytest.raises(svc.PolicyRefusal, match="not yet due"):
        s.propose_followup("amy", "lead_1004", "hi")


def test_a_closed_lead_cannot_be_proposed():
    with pytest.raises(svc.PolicyRefusal, match="not open"):
        service().propose_followup("amy", "lead_1005", "hi")


def test_the_recipient_comes_from_authoritative_state_not_the_model():
    """A model must not be able to redirect a message by asking."""
    s = service()
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    stored = s.proposals[proposal["proposal_id"]]
    assert stored["recipient"] == svc.LEADS["lead_1001"]["contact"]


def test_propose_rejects_blank_and_oversized_bodies():
    s = service()
    with pytest.raises(svc.PolicyRefusal):
        s.propose_followup("amy", "lead_1001", "   ")
    with pytest.raises(svc.PolicyRefusal):
        s.propose_followup("amy", "lead_1001", "x" * 5000)


# --- approval ----------------------------------------------------------------


def test_dispatch_requires_approval():
    s = service()
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    with pytest.raises(svc.PolicyRefusal, match="not approved"):
        s.dispatch(proposal["proposal_id"])
    assert s.provider.sent == []


def test_a_non_approver_cannot_approve():
    s = service()
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    with pytest.raises(svc.PolicyRefusal, match="may not approve"):
        s.approve("amy", proposal["proposal_id"], proposal["payload_hash"])


def test_approval_binds_the_payload_hash_not_the_proposal_id():
    """Approving an id and dispatching whatever it now says would let a revision
    slip through an approval granted for different content."""
    s = service()
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    with pytest.raises(svc.PolicyRefusal, match="payload hash"):
        s.approve("ben", proposal["proposal_id"], "0" * 64)


def test_dispatch_revalidates_the_hash_after_approval():
    s = service()
    proposal = approved(s)
    # Simulate any path that mutated stored content post-approval.
    s.proposals[proposal["proposal_id"]]["body"] = "tampered"
    with pytest.raises(svc.PolicyRefusal, match="content changed"):
        s.dispatch(proposal["proposal_id"])
    assert s.provider.sent == []


def test_a_revision_supersedes_the_earlier_draft():
    s = service()
    first = s.propose_followup("amy", "lead_1001", "v1")
    second = s.propose_followup("amy", "lead_1001", "v2")
    assert s.proposals[first["proposal_id"]]["state"] == svc.STATE_SUPERSEDED
    assert second["version"] == 2


def test_a_superseded_proposal_cannot_be_approved():
    s = service()
    first = s.propose_followup("amy", "lead_1001", "v1")
    s.propose_followup("amy", "lead_1001", "v2")
    with pytest.raises(svc.PolicyRefusal):
        s.approve("ben", first["proposal_id"], first["payload_hash"])


# --- expiry ------------------------------------------------------------------


BASE = datetime.datetime(2030, 3, 1, 9, 0, tzinfo=datetime.timezone.utc)


class Clock:
    """A settable clock.

    Deliberately not a sequence of offsets: that would depend on how many
    _now() calls a code path happens to make, which is the same brittleness
    that produced the S4 path-length defect. A test states the time it means.
    """

    def __init__(self, at=BASE):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, seconds):
        self.at = self.at + datetime.timedelta(seconds=seconds)


def test_an_expired_proposal_cannot_be_approved():
    clock = Clock()
    s = service(now=clock)
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    clock.advance(svc.PROPOSAL_TTL_SECONDS + 1)
    with pytest.raises(svc.PolicyRefusal, match="expired"):
        s.approve("ben", proposal["proposal_id"], proposal["payload_hash"])


def test_an_expired_approval_cannot_be_dispatched():
    clock = Clock()
    s = service(now=clock)
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    s.approve("ben", proposal["proposal_id"], proposal["payload_hash"])
    clock.advance(svc.PROPOSAL_TTL_SECONDS + 1)
    with pytest.raises(svc.PolicyRefusal, match="expired"):
        s.dispatch(proposal["proposal_id"])
    assert s.provider.sent == []


def test_a_proposal_just_inside_its_window_is_still_approvable():
    """Pin the boundary so the expiry rule is exact rather than approximate."""
    clock = Clock()
    s = service(now=clock)
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    clock.advance(svc.PROPOSAL_TTL_SECONDS - 1)
    assert s.approve(
        "ben", proposal["proposal_id"], proposal["payload_hash"]
    )["state"] == svc.STATE_APPROVED


# --- idempotency --------------------------------------------------------------


def test_dispatching_twice_delivers_once():
    s = service()
    proposal = approved(s)
    first = s.dispatch(proposal["proposal_id"])
    second = s.dispatch(proposal["proposal_id"])
    assert first["state"] == svc.STATE_DELIVERED
    assert second["outcome"] == "already_delivered"
    assert len(s.provider.sent) == 1


def test_the_provider_suppresses_a_duplicate_idempotency_key():
    provider = svc.FakeProvider()
    key = "k1"
    assert provider.send(key, "a@b.example", "x")["outcome"] == "delivered"
    assert provider.send(key, "a@b.example", "x")["outcome"] == (
        "duplicate_suppressed"
    )
    assert len(provider.sent) == 1


# --- concurrency --------------------------------------------------------------


def test_concurrent_dispatch_delivers_exactly_once():
    s = service()
    proposal = approved(s)
    outcomes = []
    errors = []

    def run():
        try:
            outcomes.append(s.dispatch(proposal["proposal_id"]))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(s.provider.sent) == 1
    assert sum(1 for o in outcomes if o["outcome"] == "delivered") == 1


def test_concurrent_approval_grants_once():
    s = service()
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    granted = []

    def run():
        try:
            granted.append(
                s.approve("ben", proposal["proposal_id"],
                          proposal["payload_hash"])
            )
        except svc.PolicyRefusal:
            pass

    threads = [threading.Thread(target=run) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(granted) == 1


# --- ambiguous delivery -------------------------------------------------------


def test_an_ambiguous_send_enters_delivery_unknown():
    s = service()
    proposal = approved(s)
    key = "{}:{}".format(proposal["proposal_id"],
                         proposal["payload_hash"][:12])
    s.provider.ambiguous_for.add(key)
    result = s.dispatch(proposal["proposal_id"])
    assert result["state"] == svc.STATE_DELIVERY_UNKNOWN


def test_retry_is_refused_until_reconciliation():
    """Retrying a send whose outcome is unknown is how a duplicate delivery
    happens -- two messages to one client."""
    s = service()
    proposal = approved(s)
    key = "{}:{}".format(proposal["proposal_id"],
                         proposal["payload_hash"][:12])
    s.provider.ambiguous_for.add(key)
    s.dispatch(proposal["proposal_id"])
    with pytest.raises(svc.PolicyRefusal, match="reconcile before retrying"):
        s.dispatch(proposal["proposal_id"])


def test_reconciliation_finding_no_delivery_returns_to_approved():
    s = service()
    proposal = approved(s)
    key = "{}:{}".format(proposal["proposal_id"],
                         proposal["payload_hash"][:12])
    s.provider.ambiguous_for.add(key)
    s.dispatch(proposal["proposal_id"])
    result = s.reconcile(proposal["proposal_id"])
    assert result["delivered"] is False
    assert result["state"] == svc.STATE_APPROVED
    s.provider.ambiguous_for.discard(key)
    assert s.dispatch(proposal["proposal_id"])["state"] == svc.STATE_DELIVERED
    assert len(s.provider.sent) == 1


def test_reconciliation_finding_a_delivery_marks_delivered_without_resending():
    s = service()
    proposal = approved(s)
    key = "{}:{}".format(proposal["proposal_id"],
                         proposal["payload_hash"][:12])
    s.provider.ambiguous_for.add(key)
    s.dispatch(proposal["proposal_id"])
    # The message did in fact arrive.
    s.provider.sent.append({"key": key, "recipient": "x", "body": "y"})
    result = s.reconcile(proposal["proposal_id"])
    assert result["delivered"] is True
    assert result["state"] == svc.STATE_DELIVERED
    assert len(s.provider.sent) == 1


def test_reconciling_a_settled_proposal_is_refused():
    s = service()
    proposal = approved(s)
    s.dispatch(proposal["proposal_id"])
    with pytest.raises(svc.PolicyRefusal, match="not awaiting"):
        s.reconcile(proposal["proposal_id"])


# --- audit --------------------------------------------------------------------


def test_every_transition_is_audited_in_order():
    s = service()
    proposal = approved(s)
    s.dispatch(proposal["proposal_id"])
    actions = [entry["action"] for entry in s.audit()]
    assert actions == ["propose_followup", "approve", "dispatch"]
    assert [e["sequence"] for e in s.audit()] == [1, 2, 3]


def test_the_audit_log_cannot_be_edited_through_its_accessor():
    s = service()
    s.list_due_followups("amy")
    log = s.audit()
    log.clear()
    log_again = s.audit()
    assert len(log_again) == 1
    log_again[0]["action"] = "tampered"
    assert s.audit()[0]["action"] == "list_due_followups"


def test_a_refusal_leaves_no_delivery_and_the_audit_shows_no_dispatch():
    s = service()
    proposal = s.propose_followup("amy", "lead_1001", "hi")
    with pytest.raises(svc.PolicyRefusal):
        s.dispatch(proposal["proposal_id"])
    assert "dispatch" not in [e["action"] for e in s.audit()]


# --- no network ----------------------------------------------------------------


def test_the_services_module_imports_nothing_that_can_reach_a_network():
    import ast
    import pathlib

    source = pathlib.Path(svc.__file__).read_text(encoding="utf-8")
    imported = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {"requests", "urllib", "http", "socket", "ftplib", "smtplib",
                 "asyncio", "aiohttp", "httpx"}
    assert not (imported & forbidden), imported & forbidden


def test_all_addresses_are_reserved_example_domains():
    """RFC 2606 reserves .example so an address can never resolve."""
    for lead in svc.LEADS.values():
        assert lead["contact"].endswith(".example")


def test_the_network_guard_would_catch_an_accidental_call():
    """conftest blocks the session globally; assert the guard is live here too."""
    import requests

    with pytest.raises(AssertionError, match="network access is forbidden"):
        requests.get("http://127.0.0.1:1/x")
