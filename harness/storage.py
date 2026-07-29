"""Deterministic per-domain paths for persistent configured-agent state."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path
    workspace: Path
    memory: Path
    logs: Path
    artifacts: Path


def agent_runtime_paths(agent_dir, domain):
    """Resolve the pack-selected legacy or namespaced runtime layout."""
    agent_dir = Path(agent_dir)
    if domain.runtime_layout == "legacy_agent_v0":
        return RuntimePaths(
            root=agent_dir,
            workspace=agent_dir / "workspace",
            memory=agent_dir / "memory" / "memory.jsonl",
            logs=agent_dir / "logs",
            artifacts=agent_dir / "workspace" / "files",
        )
    root = agent_dir / "runtime" / domain.name / domain.version
    workspace = root / "workspace"
    return RuntimePaths(
        root=root,
        workspace=workspace,
        memory=root / "memory" / "memory.jsonl",
        logs=root / "logs",
        artifacts=workspace / "files",
    )
