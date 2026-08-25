"""Empty local world for a connector-only, screen-only workflow."""


class BrixHubSpotWorld:
    """Carries no CRM records and persists no draft or business state."""

    def __init__(self, workdir, persistent=False):
        self.workdir = str(workdir)
        self.persistent = bool(persistent)

    def snapshot(self, actions):
        del actions
        return None
