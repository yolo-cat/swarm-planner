# Legacy Codebase Playbook

Taking over a legacy codebase carries hidden coupling, undocumented side
effects, and missing tests. Never start by editing business logic across a
large parallel swarm.

> For the core Role-to-Model Strategy, File Ownership & Hook Signals table, and
> Launch Templates, use the SSOT in
> [task-matrices.md](./task-matrices.md#2-heterogeneous-role-model-strategy-swarm).
> This playbook covers **legacy-specific deltas only**.

## Recommended Multi-Session & Hybrid Roadmap

Split work across sessions—and pick the right engine per phase—rather than
piling everything into one swarm (see Templates B, C, and D in
[task-matrices.md](./task-matrices.md#4-ready-to-paste-launch-templates)):

1. **Session 1 — Read-Only Cartography (`/run-workflow` preferred; `/swarm` if interactive)**
   - **Why `/run-workflow` often wins here**: Pure read-only scanning across
     modules does not require workers to chat on a board. A staged Python
     workflow (`phase("Discover")` -> `parallel(modules, ...)` on `flash` /
     `flash_lite` with strict JSON `schema`) deterministically compiles one
     clean System Map file without board chatter.
   - **When to use `/swarm` (`inherit`) instead**: When investigators must
     actively cross-reference clues via `#seq` or you plan to `fork:"<member>"`
     directly into a hot fixer in the same session (`infra-runner`,
     `entry-tracer`, `data-modeler`, `hotspot-auditor`).
   - **Required deliverable**: Persistent System Map Markdown (`docs/system-map.md`)
     with verified `file:line` references.
2. **Session 2 — Characterization Safety Net (`/swarm`: `tasks` + `share`)**
   - Lock current behavior before refactoring: write characterization/golden
     tests covering critical paths **without** altering production logic or
     weakening existing assertions.
   - Shard modules across `tester-1..k` (`workspace:"share"`), paired with 1
     cross-family `verifier` (`inherit`) validating real behavior (flagging
     over-mocked stubs) and running full integration suites sequentially.
3. **Session 3+ — Targeted Hardening & Fixes (`/swarm` or Single Session)**
   - Tackle one bounded goal per session (or fast-exit to Single Session /
     `/plan` in Step 0 for small single-file fixes).
   - For mysterious bugs, run read-only archaeology (`git blame`, callers, data
     state) before assigning a fixer.

## Legacy-Specific Guardrail Deltas

Refer to the SSOT table in
[task-matrices.md](./task-matrices.md#3-file-ownership-and-hook-signals-ssot) and
validate model IDs via `python3 "<skill-dir>/scripts/model_matrix.py"` (global
default `~/.gemini/config/skills/swarm-planner/scripts/model_matrix.py`,
[model_matrix.py](../scripts/model_matrix.py)). For legacy repos, prioritize:

- **Historical migrations lock**: `PreToolUse` `"deny"` on edits (and
  `run_command` mutations) targeting applied `migrations/*` files so workers
  only create forward migrations when authorized.
- **Shared DB / reset protection**: `PreToolUse` `"deny"` on destructive
  commands (`dropdb`, `--force-reset`, truncate scripts) when tests share local
  Docker/DB.
- **Untouchable legacy crons / core modules**: `PreToolUse` `"deny"` +
  `@coordinator` escalation on business-critical paths identified in Step 3
  (never `"ask"`/`"force_ask"` in unattended runs).
- **Flat `SessionStart` pointer**: Inject `docs/system-map.md` (and `AGENTS.md`
  when present) without consuming static rules budget.
- **Pre-spawn commit & post-sprint teardown**: Commit/register
  `.agents/plugins/swarm-guardrails/` (including `./hooks/pretool-guard.py`)
  **before** spawning `share`/`branch` workers, and disable or remove the
  temporary plugin after the sprint (`agy plugin disable swarm-guardrails` or
  `"enabled": false`).

## Legacy Pitfalls to Guard Against

- **External runtime collisions**: `workspace:"share"` isolates files, **not**
  local databases, Redis, or hardcoded ports. Keep integration runs in one
  sequential `verifier`.
- **Context bloat on huge files**: Instruct the `/swarm` coordinator to `kill`
  read-only investigators once their `#seq` summary is accepted (unless
  `fork`ing them).
- **Session boundaries**: Start fresh sessions between phases to keep the board
  clean, avoid retired worker name collisions (`tester` -> `tester-2`), and let
  the human review deliverables before advancing.
