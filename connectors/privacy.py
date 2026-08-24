"""Run-local state used whenever a real business connector is enabled."""

from pathlib import Path
import tempfile

from harness.memory import MemoryStore


class EphemeralMemoryStore(MemoryStore):
    """Memory semantics without loading or writing a persistent JSONL file."""

    def __init__(self):
        self.path = None
        self.facts = []

    def save(self, fact):
        fact = str(fact).strip()
        if not fact:
            return "nothing to save"
        if fact in self.facts:
            return f"already in run-only memory: {fact}"
        self.facts.append(fact)
        return f"saved for this run only: {fact}"


class EphemeralRunStorage:
    """Attempt workspace and artifacts that are removed when a run ends."""

    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="brick-connector-")
        self.root = Path(self._temporary.name)
        self.workspace = self.root / "workspace"
        self.artifacts = self.root / "artifacts"
        self.workspace.mkdir()
        self.artifacts.mkdir()

    def cleanup(self):
        self._temporary.cleanup()
