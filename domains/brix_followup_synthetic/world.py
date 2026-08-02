"""Attempt-scoped world for the synthetic lead-follow-up slice (B0).

Each attempt gets a fresh `FollowupService`, so no lead state, proposal, or
delivery can survive into another attempt. That isolation is not tidiness: an
attempt that inherited a prior attempt's approved proposal could appear to
complete work it never did, and the grader would score a real success.

The world is deliberately non-persistent. The released office domain reused task
directories, so a stale artifact could satisfy a later run's check. Nothing here
writes business state to disk.
"""

import datetime

from domains.brix_followup_synthetic import services as svc
from domains.brix_followup_synthetic import tools as domain_tools


DEFAULT_ACTOR = "amy"


class FollowupWorld:
    """Holds one attempt's authoritative service and its typed registry."""

    def __init__(self, workdir, persistent=False, actor=DEFAULT_ACTOR,
                 today=None, now=None, provider=None):
        # `persistent` is accepted for DomainPack compatibility and
        # deliberately ignored: business state must never outlive an attempt.
        self.workdir = workdir
        self.actor = actor
        self.service = svc.FollowupService(
            today=today or datetime.date(2030, 3, 1),
            now=now,
            provider=provider,
        )
        self.registry = domain_tools.build_registry(self.service, actor)
        self.finished_summary = None

    def snapshot(self, actions):
        """Record nothing extra: the audit log already is the snapshot."""
        return None

    def audit(self):
        return self.service.audit()

    def proposals_for(self, lead_id):
        return [
            proposal for proposal in self.service.proposals.values()
            if proposal["lead_id"] == lead_id
        ]

    def deliveries(self):
        return list(self.service.provider.sent)
