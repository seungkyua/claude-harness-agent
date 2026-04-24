from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class RunLayout:
    """File layout for a single harness run.

    The layout is the contract between agents — they communicate via files,
    not shared memory. Each agent gets a clean context and rereads from disk.
    """

    root: Path

    @property
    def brief(self) -> Path:
        return self.root / "brief.md"

    @property
    def spec(self) -> Path:
        return self.root / "spec.md"

    @property
    def project(self) -> Path:
        return self.root / "project"

    @property
    def reports_dir(self) -> Path:
        return self.root / "reports"

    def report(self, iteration: int) -> Path:
        return self.reports_dir / f"iter_{iteration:02d}.md"

    @property
    def latest_report(self) -> Path:
        return self.reports_dir / "latest.md"

    @property
    def log(self) -> Path:
        return self.root / "run.log"

    def ensure(self) -> None:
        for p in (self.root, self.project, self.reports_dir):
            p.mkdir(parents=True, exist_ok=True)


def new_run_dir(workspace_root: Path, label: str | None = None) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{ts}-{label}" if label else ts
    run_dir = workspace_root / "runs" / name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
