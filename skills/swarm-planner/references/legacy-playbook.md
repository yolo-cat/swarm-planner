# Legacy Codebase Playbook

Taking over a legacy codebase carries hidden coupling, undocumented side
effects, and missing tests. Never start by editing business logic across a
large parallel swarm.

> For the core Role-to-Model Strategy, File Ownership & Hook Signals table,
> generic guardrail lifecycle, and Launch Templates, use the SSOT in
> [task-matrices.md](./task-matrices.md#2-heterogeneous-role-model-strategy-swarm).
> This playbook covers **legacy-specific deltas only**.

## Recommended Multi-Session & Hybrid Roadmap

Split work across sessions—and pick the right engine per phase—rather than
piling everything into one swarm (see Templates A–D in
[task-matrices.md](./task-matrices.md#4-ready-to-paste-launch-templates)):

1. **Session 1 — Read-Only Cartography (Template B `/run-workflow` preferred; Template C Cartography `/swarm` if interactive)**
   - **Why `/run-workflow` (Template B) often wins here**: Pure read-only
     scanning across modules does not require workers to chat on a board. A
     staged Python workflow (`phase("Discover")` -> `parallel(modules, ...)`
     with `type_name="research"` on `flash`/`flash_lite` and strict JSON
     `schema`) deterministically compiles one clean System Map file without
     board chatter or `[plan review due]` deadlocks.
   - **When to use `/swarm` (Template C Cartography, `inherit`) instead**: When
     investigators must actively cross-reference clues via `#seq` or you plan
     to `fork:"<member>"` directly into a hot fixer in the same session
     (optional role names: `infra-runner`, `entry-tracer`, `data-modeler`,
     `hotspot-auditor`), with the Coordinator (or one named writer) compiling
     accepted `#seq` summaries into `docs/system-map.md`.
   - **Required deliverable**: Persistent System Map Markdown
     (`docs/system-map.md`) with verified `file:line` references.
2. **Session 2 — Characterization Safety Net (Template C Characterization `/swarm`: `tasks` + `share`)**
   - Lock current behavior before refactoring: write characterization/golden
     tests covering critical paths **without** altering production logic or
     weakening existing assertions.
   - Shard modules across `tester-1..k` (`workspace:"share"`), paired with 1
     cross-family (or distinct-variant/higher-effort within a single-family
     pool) `verifier` (`inherit`) validating real behavior (flagging
     over-mocked stubs) and running full integration suites sequentially.
3. **Session 3+ — Targeted Hardening & Fixes (Template A `/swarm`, Template D Hybrid, or Single Session)**
   - Tackle one bounded goal per session using Template A (or Template D when
     chaining a Phase 1 `/run-workflow` discovery pass into Phase 2 `/swarm`
     fixes; fast-exit to Single Session / `/plan` in Step 0 for small
     single-file fixes).
   - For mysterious bugs, run read-only archaeology (`git blame`, callers, data
     state) before assigning a fixer.

## Legacy-Specific Guardrail Deltas

Validate `/swarm` model IDs and apply generic guardrail lifecycle rules
(unattended-safe `deny`, pre-spawn commit, post-sprint teardown) per
[task-matrices.md](./task-matrices.md#2-heterogeneous-role-model-strategy-swarm)
and [task-matrices.md](./task-matrices.md#3-file-ownership-and-hook-signals-ssot).
For legacy repos, prioritize:

- **Historical migrations lock**: `PreToolUse` `"deny"` on edits (and
  `run_command` mutations) targeting applied `migrations/*` files so workers
  only create forward migrations when authorized.
- **Shared DB / reset protection**: `PreToolUse` `"deny"` on destructive
  commands (`dropdb`, `--force-reset`, truncate scripts) when tests share local
  Docker/DB.
- **Untouchable legacy crons / core modules**: `PreToolUse` `"deny"` +
  `@coordinator` escalation on business-critical paths identified in Step 3.
- **`SessionStart` priority**: Point `SessionStart` to `docs/system-map.md`
  (alongside `AGENTS.md` when present) so cold-started workers read verified
  legacy boundaries without consuming static rules budget.

## Legacy Pitfalls to Guard Against

- **External runtime collisions**: `workspace:"share"` isolates files, **not**
  local databases, Redis, or hardcoded ports. Keep integration runs in one
  sequential `verifier`.
- **Context bloat vs. `share` worktree safety**: Instruct the `/swarm`
  coordinator to `kill` read-only `inherit` investigators once their `#seq`
  summary is accepted (unless `fork`ing them), but in Characterization/Fix
  sessions **never `kill` a `share`/`branch` author before merging its commit**
  (`kill` permanently deletes the worker's workspace).
- **Cross-phase session boundaries**: Follow the SSOT session-boundary and
  handoff-path rules in
  [task-matrices.md](./task-matrices.md#1-orchestration-router-scenario-matrix):
  start a fresh session between Cartography (Session 1), Characterization
  (Session 2), and Hardening (Session 3+) so discovery transcripts do not bloat
  implementation context, retired worker names (`tester` -> `tester-2`) do not
  collide, and the human reviews committed `docs/system-map.md` (or an explicit
  absolute Phase 1 `<appData>/brain/<phase1-id>/scratch/...` artifact) with a
  clean git tree before spawning `share` authors.
