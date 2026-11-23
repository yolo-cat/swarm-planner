---
name: swarm-planner
description: >-
  Pre-session orchestration planner to route tasks between single-session,
  /run-workflow, and /swarm, inspect live Antigravity model+thinking quotas,
  co-design project-tailored hooks and guardrails, and output a ready-to-paste
  launch prompt before spending multi-agent quota.
---

# Swarm Pre-Session Planner

Design the right execution engine, model allocation, and project guardrails
**before** spending multi-agent quota. Keep this pre-session lightweight and
read-only until the user approves the blueprint: never launch `/swarm` or write
business code in this phase.

## Step 0: Fast-Exit & Triage

Check for an immediate fast-exit **before** running repo recon or
`model_matrix.py`:

- **Single-Session / `/plan` Fast-Exit**: If the task is a small single-file
  edit, a tightly coupled single-function refactor, strictly sequential work,
  or 1–2 quick lookups, stop multi-agent planning immediately and recommend
  executing directly (or using `/plan`). Do not run recon, `model_matrix.py`,
  or the interview.
- **Lightweight** (single feature, targeted migration, audit, bug hunt, or UI
  polish): Read [task-matrices.md](./references/task-matrices.md), trim Step 1
  recon and Step 3 interview to essentials, skip plugin scaffolding, and jump
  from Step 3 to Step 5's model pre-flight check + Launch Plan.
- **Project-Level** (legacy codebase takeover or greenfield setup): Run the
  full workflow (Steps 1–5). Read
  [task-matrices.md](./references/task-matrices.md) plus:
  - Legacy codebase -> [legacy-playbook.md](./references/legacy-playbook.md)
  - Greenfield project -> [greenfield-playbook.md](./references/greenfield-playbook.md)

## Step 1: Lightweight Recon, Signals & Live Model Snapshot

Inspect only enough to understand repository shape, guardrails, and available
models—do not deeply read business logic:

1. **Repo & customization baseline**: Check top-level layout, existing
   `AGENTS.md` / `GEMINI.md` / `.agents/`, and build/test manifests
   (`package.json`, `pyproject.toml`, `Cargo.toml`, `Makefile`, CI).
2. **Project hook signals**: Identify concrete guardrail candidates from the
   repo using the SSOT table in
   [task-matrices.md](./references/task-matrices.md#3-file-ownership-and-hook-signals-ssot)
   (lockfiles, `migrations/`, codegen/schemas, formatter configs, shared DBs).
   *(For massive 10+ package monorepos only, optionally run a small read-only
   `run_workflow` pass on `flash_lite` with a JSON schema to inventory
   subpackages.)*
3. **Live Model × Thinking Effort × Quota snapshot**:
   - Resolve `<skill-dir>` from this skill's `SKILL.md` path listed in
     `<skills>` (global default: `~/.gemini/config/skills/swarm-planner`),
     pointing to [model_matrix.py](./scripts/model_matrix.py). Never invoke a
     repo-relative `./scripts/model_matrix.py` from a target project `cwd`.
   - Call `swarm{action:"models", all:true}` and pipe its JSON into:
     `python3 "<skill-dir>/scripts/model_matrix.py" --from-swarm-json -`
   - Fallback when `swarm` is unavailable:
     `python3 "<skill-dir>/scripts/model_matrix.py" --from-agy`
     *(Note: `--from-agy` lists and checks model existence only; it reports
     `quota=unknown` and cannot verify live remaining quota.)*
   - Never guess model IDs or thinking suffixes (`low`/`medium`/`high`/`xhigh`).
4. **Version alignment (when needed)**: For greenfield stacks or major library
   upgrades, run `context7-mcp` (`resolve-library-id` -> single-concept
   `query-docs`) to pin accurate APIs before parallel workers start.

## Step 2: Three-Way Orchestration Router

*(Single-Session / `/plan` tasks already fast-exited in Step 0.)* Select the
lightest multi-agent engine that fits:

- **`/run-workflow`** (read `run-workflow` skill if chosen): Deterministic
  fan-out or fixed pipeline over an explicit list (e.g., auditing N files,
  legacy Phase 1 read-only cartography, mechanical per-file transforms) where
  agents **do not** converse on a board, Python JSON-schema aggregation helps,
  and coarse model tiers (`flash_lite`/`flash`/`pro`) suffice.
- **`/swarm`**: Collaborative multi-role engineering (`author <-> verifier`
  iterative test/fix loops), long-running autonomous work (`swarm_monitor`),
  visual UI polish (`swarm_pane`), or tasks needing **heterogeneous exact
  models/thinking efforts**, cross-model verification, or in-flight
  `swarm{action:"model"}` quota hot-swapping.
- **Hybrid (`/run-workflow` -> `/swarm`)**: Use `/run-workflow` for Phase 1
  read-only discovery/cartography into a structured artifact, then hand off to
  `/swarm` for Phase 2+ collaborative implementation and verification.

## Step 3: Batched Decision Interview

Resolve only open decisions that Step 1 recon could not already answer. Batch
related questions into **1–2 structured `ask_question` calls** (recommended
option first; skip any question already settled by the repo):

1. **Ownership & no-touch zones**: Untouchable legacy modules/scripts, shared
   contracts (`src/types/*`, schemas), and central files (`package.json`,
   lockfiles, global routers).
2. **Runtime & test isolation**: Shared local DB, Redis, or fixed ports
   requiring sequential `verifier` runs or strict command flags.
3. **Sizing, Role-Model Matrix & Quota Fallback** *(for `/swarm`)*: Present the
   live matrix from Step 1 alongside the SSOT strategy in
   [task-matrices.md](./references/task-matrices.md#2-heterogeneous-role-model-strategy-swarm).
   Obtain **explicit user approval** for each role's exact model ID + thinking
   effort and an approved `[quota]` fallback chain. *(Per `native_swarm` rules,
   coordinators never switch models on their own initiative **except** when the
   user explicitly requests it **or** a member hits `[quota]`/capacity
   exhaustion, switching to the coordinator's model or the user's pre-approved
   fallback chain.)*
4. **Guardrails vs. Soft Rules** *(Project-Level, or Lightweight if requested)*:
   Propose concrete hooks from Step 1 signals using unattended-safe `"deny"` +
   `@coordinator` escalation by default (avoiding `ask`/`force_ask` deadlock or
   auto-deny in `/swarm` and `/run-workflow`; opt-in `SWARM_GUARD_INTERACTIVE=1`
   is available for interactive single-session runs).
5. **Landing strategy**: Commit in `share` worktrees and merge in a
   deterministic sequential order vs. branch review (never push to remote
   unless explicitly requested).

## Step 4: Blueprint Alignment & Approval

Summarize the concrete design before writing any project files:

- **Engine & session split**: `/run-workflow` vs. `/swarm` vs. Hybrid phasing.
- **Roster & isolation**: Worker names, owned paths, `workspace` mode
  (`inherit` for readers/verifiers; `share`/`branch` for parallel authors),
  `tasks`/`n`/`fork`, and `channel`/`channels` **only if the live `swarm` tool
  exposes `action:"channel"`** (otherwise use single-board `main`).
  - **UI Overview (`swarm_pane`)**: Use `swarm_pane` (`plan.json` +
    `Screenshot: <abs-path> | <caption <=10 words>` for visual work) as the
    default Swarm UI Overview. Do **not** allocate a `Narrator` role unless the
    user explicitly asks for one by name.
  - **Stall Monitor (`swarm_monitor`)**: Include `monitor` only if the
    `swarm_monitor` skill is available, inheriting the coordinator's model by
    default.
- **Approved Role-to-Model Matrix & Fallback**: Exact verified model IDs per
  role and pre-authorized `[quota]` swap order.
- **Custom Hooks Table** *(if selected)*: Hook name, `Event` + `Matcher`,
  project pain point solved, `decision`/action (`"deny"` default for unattended
  runs), and latency check (**must stay <1–2s** because Antigravity hooks run
  synchronously; never put full test suites in hooks, and avoid naïve global
  `Stop` hooks that trap `waiting` `/swarm` workers or `coordinator`).
- **Optional alignment artifacts (Project-Level)**: Create an Implementation
  Plan artifact (`RequestFeedback: true`, `UserFacing: true`) or a
  `generative_ui` widget (`<= 450px` inline tuner or standalone module map)
  when helpful.

## Step 5: Persist Guardrails (Optional) & Deliver Launch Plan

Once the user approves the blueprint:

1. **Optional project plugin guardrails** *(Project-Level, if approved)*:
   - Bundle project rules and hooks as a toggleable project plugin under
     `.agents/plugins/swarm-guardrails/` (`plugin.json`, `hooks.json` directly
     at the plugin root, `hooks/pretool-guard.py`, and `rules/AGENTS.md` well
     under the 24 KB rules budget).
   - Start from [swarm-boundaries-AGENTS.md](./examples/swarm-boundaries-AGENTS.md),
     [swarm-guardrails-plugin.json](./examples/swarm-guardrails-plugin.json),
     [swarm-guardrails-hooks.json](./examples/swarm-guardrails-hooks.json), and
     [pretool-guard.py](./examples/pretool-guard.py):
     - `PreToolUse` (`pretool-guard.py`): Confines file writes/edits to
       `realpath(cwd)` or `realpath(artifactDirectoryPath)` (allowing
       `swarm_pane` screenshots), blocks `run_command` `.env`/push/forbidden-path
       bypasses, and defaults to unattended-safe `"deny"` + `@coordinator`
       escalation (`SWARM_GUARD_INTERACTIVE=1` for interactive single-session).
     - `PostToolUse`: Ships disabled by default (`"enabled": false`) as a
       working single-file formatter template that skips on `error`, no-ops if
       the formatter binary is absent, and always outputs `{}`.
     - `SessionStart`: Flat handler list that inspects `cwd` and injects
       pointers only for existing `AGENTS.md` and/or `docs/system-map.md`.
   - **Pre-spawn commit requirement**: Commit/register
     `.agents/plugins/swarm-guardrails/` (including `./hooks/pretool-guard.py`)
     **before** spawning `workspace:"share"` or `workspace:"branch"` workers so
     every worktree inherits the plugin and hook script.
   - **Post-sprint teardown**: After the sprint lands, disable or remove the
     temporary guardrails (`agy plugin disable swarm-guardrails`, set
     `"enabled": false` in `config.json`/`hooks.json`, or delete
     `.agents/plugins/swarm-guardrails/`).
2. **Pre-flight Validation**:
   - Validate all chosen model IDs via `<skill-dir>/scripts/model_matrix.py`:
     - With swarm JSON (enforces usable quota):
       `python3 "<skill-dir>/scripts/model_matrix.py" --from-swarm-json <json> --validate <comma-separated-ids> --require-quota`
     - With CLI fallback (existence only; `quota=unknown`):
       `python3 "<skill-dir>/scripts/model_matrix.py" --from-agy --validate <comma-separated-ids>`
   - If guardrails were written: validate JSON syntax, ensure hook scripts are
     executable (`chmod +x`), and **dry-run each hook with a mock stdin JSON
     payload** to verify exit `0`, `<1–2s` latency, and exact stdout contract
     (`PreToolUse` `{"decision": ...}`, `PostToolUse` `{}`, `SessionStart`
     `{"injectSteps": ...}`).
3. **Deliver the Ready-to-Paste Launch Plan**:
   Use Templates A–D in
   [task-matrices.md](./references/task-matrices.md#4-ready-to-paste-launch-templates)
   so the next session has Goal + Definition of Done, Roster + ownership +
   no-touch zones, `workspace` isolation, peer handoffs with a max 2–3
   `author <-> verifier` retry circuit-breaker, deterministic sequential merge
   order, authorized `Role -> Model` IDs + `[quota]` fallback chain, and
   `swarm_pane` instructions where UI applies.
