"""Main Planner→Generator→Evaluator iteration loop."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.console import Console

from .agents import AgentResult, run_evaluator, run_generator, run_planner
from .config import HermesConfig
from .io import RunLayout, new_run_dir


console = Console()


@dataclass
class IterationResult:
    iteration: int
    generator: AgentResult
    evaluator: AgentResult
    verdict: str               # "PASS" | "FAIL" | "UNKNOWN"
    report_path: Path


@dataclass
class RunResult:
    run_dir: Path
    iterations: list[IterationResult]
    final_verdict: str
    total_cost_usd: float


_VERDICT_RE = re.compile(r"^\s*verdict:\s*(PASS|FAIL)\s*$", re.IGNORECASE | re.MULTILINE)


def _parse_verdict(report_path: Path) -> str:
    if not report_path.exists():
        return "UNKNOWN"
    text = report_path.read_text()
    matches = _VERDICT_RE.findall(text)
    if not matches:
        return "UNKNOWN"
    return matches[-1].upper()


def _mirror_latest(layout: RunLayout, iteration: int) -> None:
    src = layout.report(iteration)
    if src.exists():
        shutil.copyfile(src, layout.latest_report)


def _log(layout: RunLayout, msg: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    line = f"[{ts}] {msg}\n"
    with layout.log.open("a") as f:
        f.write(line)
    console.log(msg)


async def run(brief_path: Path, cfg: HermesConfig, *, label: str | None = None) -> RunResult:
    brief_path = brief_path.resolve()
    if not brief_path.is_file():
        raise FileNotFoundError(f"Brief not found: {brief_path}")

    run_dir = new_run_dir(cfg.workspace_root.resolve(), label=label)
    layout = RunLayout(run_dir)
    layout.ensure()

    # Copy the brief into the run directory so the planner has a stable path.
    shutil.copyfile(brief_path, layout.brief)

    _log(layout, f"Run directory: {layout.root}")
    _log(layout, f"Brief: {brief_path}")
    _log(layout, f"max_iterations={cfg.max_iterations}, stop_on_pass={cfg.stop_on_pass}")

    total_cost = 0.0

    # ---- initial plan ------------------------------------------------------
    console.rule("[bold cyan]Planner (initial)")
    planner_result = await run_planner(layout, cfg, revise=False)
    total_cost += planner_result.cost_usd
    _log(layout, f"planner: turns={planner_result.turns} cost=${planner_result.cost_usd:.4f}")
    if planner_result.error:
        _log(layout, f"planner ERROR: {planner_result.error}")
    if not layout.spec.exists():
        _log(layout, "Planner did not produce spec.md — aborting run.")
        return RunResult(
            run_dir=layout.root,
            iterations=[],
            final_verdict="ABORTED",
            total_cost_usd=total_cost,
        )

    iterations: list[IterationResult] = []

    for i in range(1, cfg.max_iterations + 1):
        # ---- optional replan ----------------------------------------------
        if cfg.replan_every > 0 and i > 1 and (i - 1) % cfg.replan_every == 0:
            console.rule(f"[bold cyan]Planner (revise, before iter {i})")
            rp = await run_planner(layout, cfg, revise=True)
            total_cost += rp.cost_usd
            _log(layout, f"replanner: turns={rp.turns} cost=${rp.cost_usd:.4f}")
            if rp.error:
                _log(layout, f"replanner ERROR: {rp.error}")

        # ---- generator -----------------------------------------------------
        console.rule(f"[bold green]Generator — iteration {i}")
        gen_result = await run_generator(layout, cfg, i)
        total_cost += gen_result.cost_usd
        _log(layout, f"generator[{i}]: turns={gen_result.turns} cost=${gen_result.cost_usd:.4f}")
        if gen_result.error:
            _log(layout, f"generator[{i}] ERROR: {gen_result.error}")

        # ---- evaluator -----------------------------------------------------
        console.rule(f"[bold yellow]Evaluator — iteration {i}")
        eval_result = await run_evaluator(layout, cfg, i)
        total_cost += eval_result.cost_usd
        _log(layout, f"evaluator[{i}]: turns={eval_result.turns} cost=${eval_result.cost_usd:.4f}")
        if eval_result.error:
            _log(layout, f"evaluator[{i}] ERROR: {eval_result.error}")

        _mirror_latest(layout, i)
        report_path = layout.report(i)
        verdict = _parse_verdict(report_path)
        _log(layout, f"iteration {i} verdict: {verdict}")

        iterations.append(IterationResult(
            iteration=i,
            generator=gen_result,
            evaluator=eval_result,
            verdict=verdict,
            report_path=report_path,
        ))

        # Abort the loop if either agent crashed mid-stream — further iterations
        # would just replay the failure. Keep the summary we already have.
        if gen_result.error or eval_result.error:
            _log(layout, f"Aborting loop: agent error at iteration {i}.")
            break

        if verdict == "PASS" and cfg.stop_on_pass:
            _log(layout, f"Stopping early: evaluator returned PASS at iteration {i}.")
            break

    final_verdict = iterations[-1].verdict if iterations else "UNKNOWN"
    _log(layout, f"DONE. final_verdict={final_verdict} total_cost=${total_cost:.4f}")

    return RunResult(
        run_dir=layout.root,
        iterations=iterations,
        final_verdict=final_verdict,
        total_cost_usd=total_cost,
    )
