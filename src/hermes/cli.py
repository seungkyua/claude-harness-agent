"""Command-line entry point."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from .config import HermesConfig
from .orchestrator import run


console = Console()


# Env vars set by the Claude Code CLI for its own child processes. If they leak
# into our subprocess env, the nested `claude` CLI that Claude Agent SDK spawns
# refuses to start and dies with "Command failed with exit code 1". Strip them.
_CLAUDE_CODE_LEAK_VARS = (
    "CLAUDECODE",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDE_CODE_SSE_PORT",
)


def _scrub_claude_code_env() -> list[str]:
    removed: list[str] = []
    for name in _CLAUDE_CODE_LEAK_VARS:
        if name in os.environ:
            os.environ.pop(name, None)
            removed.append(name)
    return removed


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="hermes",
        description="Planner-Generator-Evaluator harness for iterative program development.",
    )
    p.add_argument("brief", type=Path, help="Path to the brief (a markdown file).")
    p.add_argument(
        "--config", type=Path, default=Path("config.yaml"),
        help="Path to YAML config (default: ./config.yaml).",
    )
    p.add_argument(
        "--iterations", type=int, default=None,
        help="Override max_iterations from the config.",
    )
    p.add_argument(
        "--label", type=str, default=None,
        help="Optional label appended to the run directory name.",
    )
    p.add_argument(
        "--no-stop-on-pass", action="store_true",
        help="Keep iterating even after evaluator returns PASS.",
    )
    return p.parse_args(argv)


def _is_placeholder_api_key(value: str) -> bool:
    """A real Anthropic key is long (~100 chars) and starts with `sk-ant-api`.
    Placeholders from `.env.example` or half-filled values will be shorter or
    literal `sk-ant-...`. If we pass a bad key to the CLI subprocess it will
    silently exit 1 after auth failure — the symptom we hit. Strip it so the
    CLI can fall back to its OAuth session.
    """
    v = value.strip()
    return (
        not v
        or v == "sk-ant-..."
        or v.endswith("...")
        or not v.startswith("sk-ant-")
        or len(v) < 40
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    scrubbed = _scrub_claude_code_env()
    if scrubbed:
        console.print(
            "[yellow]Detected Claude Code session env vars — stripped "
            f"{', '.join(scrubbed)} so the nested `claude` CLI can start.[/yellow]"
        )

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key and _is_placeholder_api_key(api_key):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        console.print(
            "[yellow]ANTHROPIC_API_KEY looks like a placeholder — stripped it "
            "so the `claude` CLI can use its OAuth session instead.[/yellow]"
        )

    args = _parse_args(argv or sys.argv[1:])

    if not args.config.is_file():
        console.print(f"[red]Config not found: {args.config}[/red]")
        return 2

    cfg = HermesConfig.load(args.config)
    if args.iterations is not None:
        cfg.max_iterations = args.iterations
    if args.no_stop_on_pass:
        cfg.stop_on_pass = False

    if not args.brief.is_file():
        console.print(f"[red]Brief not found: {args.brief}[/red]")
        return 2

    result = asyncio.run(run(args.brief, cfg, label=args.label))

    console.rule("[bold]Summary")
    console.print(f"Run directory:   {result.run_dir}")
    console.print(f"Iterations ran:  {len(result.iterations)}")
    console.print(f"Final verdict:   {result.final_verdict}")
    console.print(f"Total cost USD:  ${result.total_cost_usd:.4f}")
    console.print(f"Project:         {result.run_dir / 'project'}")
    console.print(f"Latest report:   {result.run_dir / 'reports' / 'latest.md'}")

    any_error = any(
        it.generator.error or it.evaluator.error for it in result.iterations
    )
    if any_error:
        console.print("[yellow]One or more agents errored during the run — see run.log.[/yellow]")

    # Exit 0 if the last iteration passed, even if later agents crashed.
    return 0 if result.final_verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
