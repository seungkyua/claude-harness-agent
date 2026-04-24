"""Three agents for the Planner-Generator-Evaluator loop.

Each agent is a single invocation of the Claude Agent SDK with:
  - A clean context (we deliberately do not reuse clients between calls).
  - File-based handoffs — the prior agent's artifact on disk is the input.
  - A role-scoped system prompt and tool allowlist.

The loop itself lives in hermes.orchestrator.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    Message,
    ResultMessage,
    TextBlock,
    query,
)
from claude_agent_sdk.types import ToolResultBlock, ToolUseBlock
from rich.console import Console

from .config import HermesConfig
from .io import RunLayout


def _quiet_enabled() -> bool:
    return os.environ.get("HERMES_QUIET", "").strip().lower() in ("1", "true", "yes", "on")


# rich.Console(quiet=True) makes every .print() a no-op, so we can keep the
# call sites unchanged. Evaluated at module load — if you toggle HERMES_QUIET
# mid-run you'll need to re-import.
_live_console = Console(quiet=_quiet_enabled())


# Map tool name → (input key we extract, max chars to show).
# Anything else falls back to a compact JSON summary.
_TOOL_SHORT_KEY: dict[str, str] = {
    "Bash": "command",
    "Read": "file_path",
    "Write": "file_path",
    "Edit": "file_path",
    "Glob": "pattern",
    "Grep": "pattern",
}


def _summarize_tool_use(block: ToolUseBlock, width: int = 120) -> str:
    name = block.name
    inp = block.input or {}
    key = _TOOL_SHORT_KEY.get(name)
    if key and key in inp:
        detail = str(inp[key])
    else:
        # Fall back to the first 2 keys so we still get a one-liner.
        shown = {k: inp[k] for k in list(inp)[:2]}
        detail = ", ".join(f"{k}={v!r}" for k, v in shown.items())
    detail = detail.replace("\n", " ")
    if len(detail) > width:
        detail = detail[: width - 1] + "…"
    return f"{name}: {detail}"


def _summarize_tool_result(block: ToolResultBlock, width: int = 120) -> str:
    content = block.content
    if isinstance(content, list):
        # content is a list of dicts like [{"type": "text", "text": "..."}]
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(str(item["text"]))
        text = "\n".join(texts)
    else:
        text = str(content or "")
    first_line = text.strip().splitlines()[0] if text.strip() else "(empty)"
    if len(first_line) > width:
        first_line = first_line[: width - 1] + "…"
    return first_line


def _forward_stderr(line: str) -> None:
    """Pipe the nested `claude` CLI's stderr to our own stderr so shell
    redirection (`2> todo-debug.log`) actually captures it.

    Without this callback, the SDK captures stderr internally and only exposes
    a generic `exit code 1` message — which makes debugging spawn failures
    (auth, nested session guards, missing CLI) nearly impossible.
    """
    sys.stderr.write(f"[claude-cli] {line}\n")
    sys.stderr.flush()


# ---- prompt loading --------------------------------------------------------

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


def _load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text()


# ---- result type -----------------------------------------------------------


@dataclass
class AgentResult:
    role: str
    text: str            # concatenation of assistant text blocks (human-readable trace)
    turns: int           # number of assistant messages
    cost_usd: float      # total_cost_usd reported by SDK, if available
    duration_ms: int     # duration_ms reported by SDK, if available
    error: str | None = None   # populated if the SDK stream raised partway through


async def _run_agent(
    *,
    role: str,
    prompt: str,
    system_prompt: str,
    model: str,
    max_turns: int,
    cwd: Path,
    allowed_tools: list[str],
    permission_mode: str,
) -> AgentResult:
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=model,
        max_turns=max_turns,
        cwd=str(cwd),
        allowed_tools=allowed_tools,
        permission_mode=permission_mode,  # type: ignore[arg-type]
        stderr=_forward_stderr,
    )

    chunks: list[str] = []
    turns = 0
    cost_usd = 0.0
    duration_ms = 0
    error: str | None = None

    try:
        stream: AsyncIterator[Message] = query(prompt=prompt, options=options)
        async for msg in stream:
            if isinstance(msg, AssistantMessage):
                turns += 1
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        chunks.append(block.text)
                        first_line = block.text.strip().splitlines()[0] if block.text.strip() else ""
                        if first_line:
                            if len(first_line) > 140:
                                first_line = first_line[:139] + "…"
                            _live_console.print(f"  [dim]{role}[/dim] {first_line}")
                    elif isinstance(block, ToolUseBlock):
                        _live_console.print(
                            f"  [cyan]{role}[/cyan] [dim]→[/dim] {_summarize_tool_use(block)}"
                        )
                    elif isinstance(block, ToolResultBlock):
                        colour = "red" if block.is_error else "dim"
                        _live_console.print(
                            f"  [{colour}]{role} ←[/{colour}] {_summarize_tool_result(block)}"
                        )
            elif isinstance(msg, ResultMessage):
                cost_usd = float(getattr(msg, "total_cost_usd", 0.0) or 0.0)
                duration_ms = int(getattr(msg, "duration_ms", 0) or 0)
    except Exception as e:  # SDK transport crash, API error, etc.
        error = f"{type(e).__name__}: {e}"

    return AgentResult(
        role=role,
        text="\n".join(chunks),
        turns=turns,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
        error=error,
    )


# ---- Planner ---------------------------------------------------------------

PLANNER_TOOLS = ["Read", "Write", "Edit", "Glob", "Grep"]


async def run_planner(layout: RunLayout, cfg: HermesConfig, *, revise: bool) -> AgentResult:
    """Read brief.md (+ latest report, if revising), produce/update spec.md."""
    system_prompt = _load_prompt("planner")
    if revise and layout.latest_report.exists():
        user_prompt = (
            "Revise the existing `spec.md` based on the latest evaluator report.\n\n"
            f"- Brief:           `{layout.brief.name}`\n"
            f"- Current spec:    `{layout.spec.name}`\n"
            f"- Latest feedback: `reports/{layout.latest_report.name}`\n\n"
            "Read all three, then overwrite `spec.md` with a revised plan that "
            "resolves the evaluator's findings without ballooning scope."
        )
    else:
        user_prompt = (
            "Write `spec.md` in the current directory based on the user's brief.\n\n"
            f"- Brief: `{layout.brief.name}`\n\n"
            "Follow the structure laid out in your system prompt. Do not start coding."
        )

    return await _run_agent(
        role="planner",
        prompt=user_prompt,
        system_prompt=system_prompt,
        model=cfg.models.planner,
        max_turns=cfg.max_turns.planner,
        cwd=layout.root,
        allowed_tools=PLANNER_TOOLS,
        permission_mode=cfg.permission_mode,
    )


# ---- Generator -------------------------------------------------------------

GENERATOR_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


async def run_generator(layout: RunLayout, cfg: HermesConfig, iteration: int) -> AgentResult:
    """Implement or amend the project based on spec.md + latest evaluator report."""
    system_prompt = _load_prompt("generator")

    if iteration == 1:
        user_prompt = (
            "Implement the project from scratch.\n\n"
            f"- Spec:             `{layout.spec.name}`\n"
            f"- Project directory: `{layout.project.name}/` (create files here)\n\n"
            "Read `spec.md`, then build the initial version inside `project/`. "
            "Include a README describing how to install, run, and test."
        )
    else:
        user_prompt = (
            f"Iteration {iteration}: amend the project to address evaluator findings.\n\n"
            f"- Spec:              `{layout.spec.name}`\n"
            f"- Project directory: `{layout.project.name}/`\n"
            f"- Latest feedback:   `reports/{layout.latest_report.name}`\n\n"
            "Read the latest report first, then make the smallest set of changes "
            "that resolves every CRITICAL and MAJOR finding. Leave MINOR findings "
            "for a future iteration unless trivial."
        )

    return await _run_agent(
        role="generator",
        prompt=user_prompt,
        system_prompt=system_prompt,
        model=cfg.models.generator,
        max_turns=cfg.max_turns.generator,
        cwd=layout.root,
        allowed_tools=GENERATOR_TOOLS,
        permission_mode=cfg.permission_mode,
    )


# ---- Evaluator -------------------------------------------------------------

EVALUATOR_TOOLS = ["Read", "Write", "Edit", "Bash", "Glob", "Grep"]


async def run_evaluator(layout: RunLayout, cfg: HermesConfig, iteration: int) -> AgentResult:
    """Run build + tests, compare to spec, write reports/iter_NN.md."""
    system_prompt = _load_prompt("evaluator")
    report_name = layout.report(iteration).name
    user_prompt = (
        f"Evaluate iteration {iteration}.\n\n"
        f"- Spec:              `{layout.spec.name}`\n"
        f"- Project directory: `{layout.project.name}/`\n"
        f"- Write your report to: `reports/{report_name}`\n"
        f"- Also copy it to:      `reports/latest.md`\n\n"
        "Actually run the project's install/build/test commands inside `project/` "
        "(use Bash). Inspect the code against the spec. Be skeptical — do not "
        "approve mediocre work. End with `verdict: PASS` or `verdict: FAIL` on "
        "its own line, as specified in your system prompt."
    )

    return await _run_agent(
        role="evaluator",
        prompt=user_prompt,
        system_prompt=system_prompt,
        model=cfg.models.evaluator,
        max_turns=cfg.max_turns.evaluator,
        cwd=layout.root,
        allowed_tools=EVALUATOR_TOOLS,
        permission_mode=cfg.permission_mode,
    )
