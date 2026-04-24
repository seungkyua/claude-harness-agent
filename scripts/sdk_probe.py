"""Minimal reproduction: call Claude Agent SDK the same way hermes does,
with a short prompt, and forward the nested CLI's stderr to our own stderr.

Run:
    CLAUDE_AGENT_SDK_SKIP_VERSION_CHECK=1 python scripts/sdk_probe.py 2> probe.log
    cat probe.log
"""
from __future__ import annotations

import asyncio
import sys
import traceback

from dotenv import load_dotenv
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    Message,
    ResultMessage,
    TextBlock,
    query,
)


def log_err(line: str) -> None:
    sys.stderr.write(f"[claude-cli] {line}\n")
    sys.stderr.flush()


async def main() -> int:
    load_dotenv()

    options = ClaudeAgentOptions(
        system_prompt="You are terse. Respond with exactly one word.",
        model="claude-opus-4-7",
        max_turns=1,
        permission_mode="bypassPermissions",
        allowed_tools=[],
        stderr=log_err,
    )

    print(f"SDK options: model={options.model} max_turns={options.max_turns}")
    print("Calling query() ...")
    sys.stdout.flush()

    try:
        async for msg in query(prompt="Respond with only: PONG", options=options):
            kind = type(msg).__name__
            if isinstance(msg, AssistantMessage):
                for b in msg.content:
                    if isinstance(b, TextBlock):
                        print(f"[{kind}] text={b.text!r}")
            elif isinstance(msg, ResultMessage):
                print(
                    f"[{kind}] cost_usd={getattr(msg, 'total_cost_usd', None)} "
                    f"duration_ms={getattr(msg, 'duration_ms', None)}"
                )
            else:
                print(f"[{kind}] {msg!r}")
            sys.stdout.flush()
    except Exception:
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
