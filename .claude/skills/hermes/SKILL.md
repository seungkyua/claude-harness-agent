---
name: hermes
description: Run a Planner→Generator→Evaluator loop to autonomously develop a program from a short brief. Use when the user types /hermes or asks to "run the hermes loop" on a brief file. Orchestrates three sub-agents via the Task tool and iterates until PASS or a max iteration count.
---

# Hermes — iterative program development loop

This skill orchestrates three sub-agents defined in `.claude/agents/`:

- **planner** → reads a brief, writes `spec.md`
- **generator** → reads spec + latest report, writes/edits `project/`
- **evaluator** → runs tests on `project/`, writes `reports/iter_NN.md`
  ending with `verdict: PASS` or `verdict: FAIL`

The three agents do not share context. They communicate only through files in
the run directory. You (the main conversation) are the orchestrator.

## Invocation

Expected forms:

- `/hermes <brief_path> [iterations=5] [label]`
- `/hermes briefs/example-todo-cli.md 3 todo`
- free-form: "run hermes on briefs/foo.md for 4 iterations"

Parse arguments as:

- `brief_path` (required) — relative or absolute path to a markdown brief.
- `iterations` (optional, default **5**) — maximum Generator↔Evaluator rounds.
- `label` (optional) — short tag appended to the run directory name.

Two booleans worth remembering (default values shown):

- `stop_on_pass = true` — stop the loop early once evaluator returns PASS.
- `replan_every = 0` — if > 0, re-invoke planner every N iterations.

If the user did not supply these, use the defaults. If the user explicitly
asked to "keep going past PASS" or similar, set `stop_on_pass = false`.

## Procedure

Perform these steps **in order**. Use tools directly — do not ask the user
for confirmation between steps.

### 1. Validate the brief

- Verify `brief_path` exists. If not, report and stop.
- If `iterations` is not a positive integer, report and stop.

### 2. Create the run directory

```
workspace/runs/<YYYYMMDD-HHMMSS>[-<label>]/
├── brief.md       ← copy of the original brief
├── spec.md        ← planner writes
├── project/       ← generator writes
└── reports/       ← evaluator writes
```

Use Bash to create the directory and copy the brief. Example:

```bash
ts=$(date +%Y%m%d-%H%M%S)
run="workspace/runs/${ts}${label:+-$label}"
mkdir -p "$run/project" "$run/reports"
cp "$brief_path" "$run/brief.md"
```

Remember the run directory path — every sub-agent call references it.

### 3. Planner (once)

Invoke the `planner` sub-agent via the Task tool. Pass the run directory as
context. Example prompt to the sub-agent:

> Write `spec.md` in `<run_dir>` based on `<run_dir>/brief.md`. Follow the
> structure in your system prompt. Do not start coding.

After it returns, verify `<run_dir>/spec.md` exists. If not, abort and report.

### 4. Iteration loop

For `i` from 1 to `iterations`:

#### 4a. (Optional) Re-plan

If `replan_every > 0` and `i > 1` and `(i - 1) % replan_every == 0`, invoke
planner again with a prompt like:

> Revise `<run_dir>/spec.md` based on `<run_dir>/reports/latest.md`. Resolve
> the evaluator's findings without ballooning scope.

#### 4b. Generator

Invoke the `generator` sub-agent. Prompt:

> Iteration `<i>`. Run directory: `<run_dir>`. Read `spec.md` (and, on
> iter ≥ 2, `reports/latest.md`). Implement or amend `project/` accordingly.
> Prove it builds and its own tests pass before finishing.

#### 4c. Evaluator

Invoke the `evaluator` sub-agent. Prompt:

> Iteration `<i>`. Run directory: `<run_dir>`. Write your report to
> `reports/iter_<NN>.md` (NN is `<i>` zero-padded to 2 digits) and mirror it
> to `reports/latest.md`. Follow the write-first protocol in your system
> prompt. End with `verdict: PASS` or `verdict: FAIL`.

#### 4d. Parse verdict

Read the last non-empty line of `<run_dir>/reports/iter_<NN>.md`. It must
match `verdict: PASS` or `verdict: FAIL` (case-insensitive). If it matches
neither, log `UNKNOWN`.

- If verdict is PASS and `stop_on_pass`, break the loop.
- If the sub-agent errored (Task returned an error), log and break — further
  iterations will just replay the failure.

### 5. Summary

After the loop, print a compact summary to the user:

- Run directory (absolute path)
- Iterations actually run
- Final verdict (from the last iteration's report)
- Path to `project/` (the real deliverable)
- Path to `reports/latest.md` (the final evaluation)

Example:

```
Run directory: /…/workspace/runs/20260424-120001-todo
Iterations ran: 2
Final verdict: PASS
Project:       /…/workspace/runs/20260424-120001-todo/project
Latest report: /…/workspace/runs/20260424-120001-todo/reports/latest.md
```

## Rules for the orchestrator (you)

- **Do not touch `project/` or `reports/` yourself.** Only sub-agents write
  there. You only create the directory skeleton and read files to check
  verdicts.
- **Do not re-plan unless `replan_every` says so.** The planner is expensive
  and re-planning too often destabilises the spec.
- **Do not summarize the sub-agents' text output in the main conversation**
  beyond the end-of-run summary. The artifacts on disk are the source of
  truth.
- **Abort gracefully on sub-agent failure.** Report what succeeded up to that
  point; do not attempt to recover mid-run.
- **Timeouts are sub-agent responsibility.** If a sub-agent hangs inside a
  Bash call, that is a prompt tuning issue (see the evaluator prompt's
  timeout guidance), not something for you to work around.

## Authentication note

Program execution uses the Claude Code CLI session itself — no API key or
`.env` setup is required. If you are logged in (`claude login`), the loop
works out of the box.
