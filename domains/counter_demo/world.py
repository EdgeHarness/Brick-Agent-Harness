"""Minimal persistent counter world."""
import json
import os


class CounterWorld:
    def __init__(self, workdir, persistent=False):
        self.workdir = str(workdir)
        self.persistent = persistent
        self.files_dir = os.path.join(self.workdir, "files")
        os.makedirs(self.files_dir, exist_ok=True)
        self.value = 0
        state_path = os.path.join(self.workdir, "state.json")
        if persistent and os.path.isfile(state_path):
            with open(state_path, encoding="utf-8") as stream:
                self.value = int(json.load(stream).get("value", 0))

    def snapshot(self, actions):
        os.makedirs(self.workdir, exist_ok=True)
        with open(
            os.path.join(self.workdir, "state.json"), "w", encoding="utf-8"
        ) as stream:
            json.dump({"value": self.value, "actions": actions}, stream, indent=2)
