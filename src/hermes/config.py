from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class Models:
    planner: str = "claude-opus-4-7"
    generator: str = "claude-sonnet-4-6"
    evaluator: str = "claude-sonnet-4-6"


@dataclass
class MaxTurns:
    planner: int = 20
    generator: int = 80
    evaluator: int = 40


@dataclass
class HermesConfig:
    max_iterations: int = 5
    stop_on_pass: bool = True
    replan_every: int = 0
    permission_mode: str = "bypassPermissions"
    workspace_root: Path = field(default_factory=lambda: Path("workspace"))
    models: Models = field(default_factory=Models)
    max_turns: MaxTurns = field(default_factory=MaxTurns)

    @classmethod
    def load(cls, path: Path) -> "HermesConfig":
        data: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        models = Models(**(data.get("models") or {}))
        max_turns = MaxTurns(**(data.get("max_turns") or {}))
        workspace_root = Path(data.get("workspace_root", "workspace"))
        return cls(
            max_iterations=int(data.get("max_iterations", 5)),
            stop_on_pass=bool(data.get("stop_on_pass", True)),
            replan_every=int(data.get("replan_every", 0)),
            permission_mode=str(data.get("permission_mode", "bypassPermissions")),
            workspace_root=workspace_root,
            models=models,
            max_turns=max_turns,
        )
