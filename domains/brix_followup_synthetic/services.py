"""Deterministic services for the synthetic lead-follow-up slice (B0).

Every record here is fictional. There is no network client, no provider
credential, and no real address: the module imports nothing that can reach out,
and a test asserts that.

The division of labour is the entire point of this stage. The model may *read*
and *propose*. It may not approve, dispatch, cross a tenant boundary, choose a
recipient, bypass a policy, or use its own memory as business state. Those are
owned here, by deterministic code, so that a model which asks for them is refused
by the instrument rather than trusted not to ask.

That matters for the benchmark specifically. If a model could dispatch, then a
harness that merely *asks more politely* would score better, and the measured
effect would be the harness's persuasiveness rather than its task completion.
Authorization has to be structural for the comparison to mean anything.

Seven services own the state:

* actor and tenant authorization;
* due-date and eligibility rules;
* proposal versions, payload hashes, expiry and revision;
* approval and dispatch revalidation;
* idempotency and concurrency;
* fake-provider delivery and reconciliation; and
* immutable audit records.

Two designs are worth stating because they are easy to get wrong.

**Approval binds a payload hash, not a proposal id.** Approving "proposal 3" and
then dispatching whatever proposal 3 now says would let a revision slip through
an approval granted for different content. Approval therefore names the exact
bytes it approved, and dispatch revalidates that the hash still matches.

**An ambiguous provider timeout is not a failure.** It becomes
``delivery_unknown``, which must be reconciled before any retry. Retrying a
send whose outcome is unknown is how a synthetic slice would produce a duplicate
delivery -- and in a real system, two messages to a client.
"""

import copy
import datetime
import hashlib
import json
import threading


SERVICES_VERSION = "brick.brix-followup/1"

# Fictional. .example is reserved by RFC 2606 precisely so it can never resolve.
TENANTS = ("northwind", "sterling")

ACTORS = {
    "amy": {"tenant": "northwind", "role": "agent"},
    "ben": {"tenant": "northwind", "role": "approver"},
    "cara": {"tenant": "sterling", "role": "agent"},
}

LEADS = {
    "lead_1001": {
        "tenant": "northwind", "assigned_to": "amy",
        "contact": "dana.quill@northwind.example",
        "name": "Dana Quill", "due": "2030-03-01", "status": "open",
    },
    "lead_1002": {
        "tenant": "northwind", "assigned_to": "amy",
        "contact": "eli.rowe@northwind.example",
        "name": "Eli Rowe", "due": "2030-03-05", "status": "open",
    },
    "lead_1003": {
        "tenant": "northwind", "assigned_to": "ben",
        "contact": "fay.singh@northwind.example",
        "name": "Fay Singh", "due": "2030-03-01", "status": "open",
    },
    "lead_2001": {
        "tenant": "sterling", "assigned_to": "cara",
        "contact": "gil.tran@sterling.example",
        "name": "Gil Tran", "due": "2030-03-02", "status": "open",
    },
    "lead_1004": {
        "tenant": "northwind", "assigned_to": "amy",
        "contact": "hana.vo@northwind.example",
        "name": "Hana Vo", "due": "2030-04-20", "status": "open",
    },
    "lead_1005": {
        "tenant": "northwind", "assigned_to": "amy",
        "contact": "ivan.wu@northwind.example",
        "name": "Ivan Wu", "due": "2030-03-01", "status": "closed",
    },
}

PROPOSAL_TTL_SECONDS = 3600
MAX_BODY = 1200

STATE_DRAFT = "draft"
STATE_APPROVED = "approved"
STATE_DELIVERED = "delivered"
STATE_DELIVERY_UNKNOWN = "delivery_unknown"
STATE_SUPERSEDED = "superseded"


class PolicyRefusal(Exception):
    """A request the policy forbids. Safe to report to the model."""


class ServiceFault(Exception):
    """The service itself failed. Not the model's error."""


def payload_hash(tenant, lead_id, recipient, body):
    """Bind approval to exact content, not to a proposal identifier."""
    material = json.dumps(
        {"tenant": tenant, "lead_id": lead_id, "recipient": recipient,
         "body": body},
        sort_keys=True, ensure_ascii=False, separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class FakeProvider:
    """A delivery provider that never touches a network.

    ``ambiguous_for`` makes a send report an indeterminate outcome, which is the
    case the slice must survive: the message may or may not have gone.
    """

    def __init__(self, ambiguous_for=(), fail_for=()):
        self.ambiguous_for = set(ambiguous_for)
        self.fail_for = set(fail_for)
        self.sent = []
        self._lock = threading.Lock()

    def send(self, idempotency_key, recipient, body):
        with self._lock:
            if idempotency_key in self.fail_for:
                raise ServiceFault("fake provider rejected the send")
            if idempotency_key in self.ambiguous_for:
                # Record nothing: whether it arrived is genuinely unknown.
                return {"outcome": "unknown", "key": idempotency_key}
            for record in self.sent:
                if record["key"] == idempotency_key:
                    return {"outcome": "duplicate_suppressed",
                            "key": idempotency_key}
            self.sent.append(
                {"key": idempotency_key, "recipient": recipient, "body": body}
            )
            return {"outcome": "delivered", "key": idempotency_key}

    def was_delivered(self, idempotency_key):
        """Reconciliation query: did this key actually arrive?"""
        with self._lock:
            return any(r["key"] == idempotency_key for r in self.sent)


class FollowupService:
    """Authoritative business state. The model never mutates this directly."""

    def __init__(self, today=None, now=None, provider=None):
        self.today = today or datetime.date(2030, 3, 1)
        self._now = now or (
            lambda: datetime.datetime(2030, 3, 1, 9, 0,
                                      tzinfo=datetime.timezone.utc)
        )
        self.provider = provider or FakeProvider()
        self.leads = copy.deepcopy(LEADS)
        self.proposals = {}
        self._audit = []
        self._sequence = 0
        self._lock = threading.Lock()

    # -- audit ---------------------------------------------------------------

    def _record(self, action, actor, detail):
        # Append-only. Callers receive copies so history cannot be edited.
        self._audit.append({
            "sequence": len(self._audit) + 1,
            "at": self._now().isoformat(),
            "action": action,
            "actor": actor,
            "detail": copy.deepcopy(detail),
        })

    def audit(self):
        return copy.deepcopy(self._audit)

    # -- authorization -------------------------------------------------------

    def _actor(self, actor_id):
        actor = ACTORS.get(actor_id)
        if actor is None:
            raise PolicyRefusal("unknown actor {!r}".format(actor_id))
        return actor

    def _authorized_lead(self, actor_id, lead_id):
        actor = self._actor(actor_id)
        lead = self.leads.get(lead_id)
        if lead is None:
            raise PolicyRefusal("unknown lead {!r}".format(lead_id))
        if lead["tenant"] != actor["tenant"]:
            # Deliberately identical to the unknown-lead message: revealing that
            # a lead exists in another tenant is itself a cross-tenant leak.
            raise PolicyRefusal("unknown lead {!r}".format(lead_id))
        if lead["assigned_to"] != actor_id:
            raise PolicyRefusal(
                "lead {!r} is not assigned to {!r}".format(lead_id, actor_id)
            )
        return actor, lead

    # -- eligibility ---------------------------------------------------------

    def _eligible(self, lead):
        if lead["status"] != "open":
            return "lead is not open"
        if datetime.date.fromisoformat(lead["due"]) > self.today:
            return "lead is not yet due"
        return None

    # -- model-facing reads --------------------------------------------------

    def list_due_followups(self, actor_id):
        actor = self._actor(actor_id)
        due = []
        for lead_id in sorted(self.leads):
            lead = self.leads[lead_id]
            if lead["tenant"] != actor["tenant"]:
                continue
            if lead["assigned_to"] != actor_id:
                continue
            if self._eligible(lead) is not None:
                continue
            due.append({"lead_id": lead_id, "name": lead["name"],
                        "due": lead["due"]})
        self._record("list_due_followups", actor_id, {"count": len(due)})
        return due

    def inspect_lead(self, actor_id, lead_id):
        _, lead = self._authorized_lead(actor_id, lead_id)
        self._record("inspect_lead", actor_id, {"lead_id": lead_id})
        return {"lead_id": lead_id, "name": lead["name"], "due": lead["due"],
                "status": lead["status"], "contact": lead["contact"]}

    def inspect_proposals(self, actor_id, lead_id):
        self._authorized_lead(actor_id, lead_id)
        found = [
            {"proposal_id": pid, "version": p["version"], "state": p["state"],
             "payload_hash": p["payload_hash"], "expires_at": p["expires_at"]}
            for pid, p in sorted(self.proposals.items())
            if p["lead_id"] == lead_id
        ]
        self._record("inspect_proposals", actor_id, {"lead_id": lead_id,
                                                    "count": len(found)})
        return found

    # -- model-facing write: propose only ------------------------------------

    def propose_followup(self, actor_id, lead_id, body):
        """The only state the model may create.

        The recipient is derived from authoritative lead data, never supplied by
        the model, so a model cannot redirect a message by asking.
        """
        actor, lead = self._authorized_lead(actor_id, lead_id)
        reason = self._eligible(lead)
        if reason is not None:
            raise PolicyRefusal(reason)
        if not isinstance(body, str) or not body.strip():
            raise PolicyRefusal("body must be a nonempty string")
        if len(body) > MAX_BODY:
            raise PolicyRefusal(
                "body exceeds {} characters".format(MAX_BODY)
            )
        with self._lock:
            recipient = lead["contact"]
            previous = [
                pid for pid, p in self.proposals.items()
                if p["lead_id"] == lead_id and p["state"] == STATE_DRAFT
            ]
            for pid in previous:
                # A revision supersedes an earlier draft rather than editing it,
                # so an approval can never attach to mutated content.
                self.proposals[pid]["state"] = STATE_SUPERSEDED
                self._record("supersede_proposal", actor_id,
                             {"proposal_id": pid})
            self._sequence += 1
            proposal_id = "prop_{:04d}".format(self._sequence)
            version = 1 + sum(
                1 for p in self.proposals.values() if p["lead_id"] == lead_id
            )
            expires = self._now() + datetime.timedelta(
                seconds=PROPOSAL_TTL_SECONDS
            )
            digest = payload_hash(lead["tenant"], lead_id, recipient, body)
            self.proposals[proposal_id] = {
                "proposal_id": proposal_id, "lead_id": lead_id,
                "tenant": lead["tenant"], "recipient": recipient,
                "body": body, "version": version, "state": STATE_DRAFT,
                "payload_hash": digest,
                "expires_at": expires.isoformat(),
                "approved_hash": None, "delivery_key": None,
            }
            self._record("propose_followup", actor_id, {
                "proposal_id": proposal_id, "lead_id": lead_id,
                "version": version, "payload_hash": digest,
            })
        return {"proposal_id": proposal_id, "version": version,
                "payload_hash": digest, "expires_at": expires.isoformat()}

    # -- deterministic-only: approval ----------------------------------------

    def _proposal(self, proposal_id):
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise PolicyRefusal("unknown proposal {!r}".format(proposal_id))
        return proposal

    def _expired(self, proposal):
        expires = datetime.datetime.fromisoformat(proposal["expires_at"])
        return self._now() >= expires

    def approve(self, approver_id, proposal_id, expected_hash):
        """Approve exact content. Never callable by the model."""
        approver = self._actor(approver_id)
        with self._lock:
            proposal = self._proposal(proposal_id)
            if approver["role"] != "approver":
                raise PolicyRefusal(
                    "actor {!r} may not approve".format(approver_id)
                )
            if approver["tenant"] != proposal["tenant"]:
                raise PolicyRefusal("unknown proposal {!r}".format(proposal_id))
            if proposal["state"] != STATE_DRAFT:
                raise PolicyRefusal(
                    "proposal {!r} is {}".format(proposal_id,
                                                 proposal["state"])
                )
            if self._expired(proposal):
                raise PolicyRefusal("approval window has expired")
            if expected_hash != proposal["payload_hash"]:
                raise PolicyRefusal(
                    "payload hash does not match the reviewed content"
                )
            proposal["state"] = STATE_APPROVED
            proposal["approved_hash"] = expected_hash
            self._record("approve", approver_id, {
                "proposal_id": proposal_id, "payload_hash": expected_hash,
            })
        return {"proposal_id": proposal_id, "state": STATE_APPROVED}

    # -- deterministic-only: dispatch ----------------------------------------

    def dispatch(self, proposal_id):
        """Send an approved proposal. Idempotent. Never callable by the model."""
        with self._lock:
            proposal = self._proposal(proposal_id)
            if proposal["state"] == STATE_DELIVERED:
                self._record("dispatch_suppressed", "system",
                             {"proposal_id": proposal_id})
                return {"proposal_id": proposal_id, "state": STATE_DELIVERED,
                        "outcome": "already_delivered"}
            if proposal["state"] == STATE_DELIVERY_UNKNOWN:
                raise PolicyRefusal(
                    "delivery outcome is unknown; reconcile before retrying"
                )
            if proposal["state"] != STATE_APPROVED:
                raise PolicyRefusal(
                    "proposal {!r} is not approved".format(proposal_id)
                )
            if self._expired(proposal):
                raise PolicyRefusal("approval window has expired")
            # Revalidate: the approval named exact bytes.
            current = payload_hash(
                proposal["tenant"], proposal["lead_id"],
                proposal["recipient"], proposal["body"],
            )
            if current != proposal["approved_hash"]:
                raise PolicyRefusal(
                    "content changed after approval; re-approval required"
                )
            key = "{}:{}".format(proposal_id, proposal["approved_hash"][:12])
            proposal["delivery_key"] = key
            result = self.provider.send(key, proposal["recipient"],
                                        proposal["body"])
            if result["outcome"] == "unknown":
                proposal["state"] = STATE_DELIVERY_UNKNOWN
                self._record("delivery_unknown", "system",
                             {"proposal_id": proposal_id, "key": key})
                return {"proposal_id": proposal_id,
                        "state": STATE_DELIVERY_UNKNOWN,
                        "outcome": "unknown"}
            proposal["state"] = STATE_DELIVERED
            self._record("dispatch", "system", {
                "proposal_id": proposal_id, "key": key,
                "outcome": result["outcome"],
            })
        return {"proposal_id": proposal_id, "state": STATE_DELIVERED,
                "outcome": result["outcome"]}

    # -- deterministic-only: reconciliation ----------------------------------

    def reconcile(self, proposal_id):
        """Resolve delivery_unknown by asking the provider what happened."""
        with self._lock:
            proposal = self._proposal(proposal_id)
            if proposal["state"] != STATE_DELIVERY_UNKNOWN:
                raise PolicyRefusal(
                    "proposal {!r} is not awaiting reconciliation".format(
                        proposal_id
                    )
                )
            delivered = self.provider.was_delivered(proposal["delivery_key"])
            proposal["state"] = (
                STATE_DELIVERED if delivered else STATE_APPROVED
            )
            self._record("reconcile", "system", {
                "proposal_id": proposal_id, "delivered": delivered,
            })
        return {"proposal_id": proposal_id, "state": proposal["state"],
                "delivered": delivered}
