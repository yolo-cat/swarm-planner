# Legacy Codebase Playbook

Taking over a legacy codebase carries hidden coupling, undocumented side
effects, and missing tests. Never start by editing business logic across a
large parallel swarm.

## Recommended Multi-Session & Hybrid Roadmap

Split work across sessions—and pick the right engine per phase—rather than
piling everything into one swarm:

1. **Session 1 — Read-Only Cartography (`run_workflow` preferred; `/swarm` if interactive)**
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
     cross-model `verifier` (`inherit`) validating coverage and running full
     integration suites sequentially.
3. **Session 3+ — Targeted Hardening & Fixes (`/swarm` or Single Session)**
   - Tackle one bounded goal per session (or use a single agent for small
     single-file fixes).
   - For mysterious bugs, run read-only archaeology (`git blame`, callers, data
     state) before assigning a fixer.

## Legacy Hook Signals & Guardrails (`PreToolUse` / `SessionStart`)

During Step 1 & Step 3, inspect the legacy repo for high-ROI hooks to include in
`.agents/plugins/swarm-guardrails/`:

- **Applied migrations lock**: `PreToolUse` `deny` edits to historical
  `migrations/*` files so workers only create forward migrations when authorized.
- **Shared DB / reset protection**: `PreToolUse` `deny` destructive commands
  (`dropdb`, `--force-reset`, truncate scripts) when tests share local Docker/DB.
- **Untouchable legacy crons / core modules**: `PreToolUse` `deny` or
  `force_ask` on business-critical paths identified by the user.
- **`SessionStart` pointer**: Inject `docs/system-map.md` and local test DB
  constraints without consuming static `AGENTS.md` rule budget.

## Role-Model Strategy for Legacy Work

Verify available IDs and quotas with `scripts/model_matrix.py` first:
- **Archaeology / Complex Bug Fixers (`entry-tracer`, `data-modeler`, Phase 3)**:
  Assign `high`/`xhigh` reasoning models to trace indirect callers and state.
- **Characterization Test Shards (`tester-1..k`)**: Fast, high-quota models once
  behavior specs are clear.
- **Verifier**: Use a different model family than the test/fix authors so it
  independently flags over-mocked stubs and missing edge cases.

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
