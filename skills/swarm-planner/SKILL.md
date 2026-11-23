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

## Step 0: Triage & Load Reference

Classify the request and read **only** the matching reference file(s):

- **Project-Level** (legacy codebase takeover or greenfield setup): run the
  full workflow (Steps 1–5).
  - Legacy codebase -> read [legacy-playbook.md](./references/legacy-playbook.md)
  - Greenfield project -> read [greenfield-playbook.md](./references/greenfield-playbook.md)
- **Lightweight** (single feature, migration, audit, bug hunt, or UI polish):
  run Steps 1–3, then jump to Step 5's Launch Prompt / Workflow Blueprint.
  - Read [task-matrices.md](./references/task-matrices.md)

## Step 1: Lightweight Recon, Signals & Live Model Snapshot

Inspect only enough to understand repository shape, guardrails, and available
models—do not deeply read business logic:

1. **Repo & customization baseline**: Check top-level layout, existing
   `AGENTS.md` / `GEMINI.md` / `.agents/`, and build/test manifests
   (`package.json`, `pyproject.toml`, `Cargo.toml`, `Makefile`, CI).
2. **Project hook signals**: Note concrete guardrail candidates from the repo:
   package manager lockfiles (`pnpm-lock.yaml`, `uv.lock`), DB `migrations/`,
   codegen sources (`proto/`, `openapi.*`, `generated/`), formatter configs
   (`.prettierrc`, `ruff.toml`), and shared local test DB/ports (`docker-compose*`).
   *(Only for massive 10+ package monorepos where top-level manifests are
   insufficient, optionally run a small read-only `run_workflow` pass on
   `flash_lite` with a JSON schema to inventory subpackages.)*
3. **Live Model × Thinking Effort × Quota snapshot**:
   - Call `swarm{action:"models", all:true}` and pipe its JSON into
     `python3 ./scripts/model_matrix.py --from-swarm-json -` (path relative to
     this skill folder), **or** run `python3 ./scripts/model_matrix.py --from-agy`
     as a CLI fallback when `swarm` is unavailable.
   - Never guess model IDs or thinking suffixes (`low`/`medium`/`high`/`xhigh`).
4. **Version alignment (when needed)**: For greenfield stacks or major library
   upgrades, run `context7-mcp` (`resolve-library-id` -> single-concept
   `query-docs`) to pin accurate APIs before parallel workers start.

## Step 2: Three-Way Orchestration Router

Select the lightest engine that cleanly fits the task:

- **Single Session / `/plan`**: Small single-file edits, tightly coupled
  single-function refactors, strictly sequential dependencies, or 1–2 quick
  lookups. Stop planning for `/swarm` here and execute or plan directly.
- **`/run-workflow`** (read `run-workflow` skill if chosen): Deterministic
  fan-out or fixed pipeline over an explicit list (e.g., auditing N files,
  legacy Phase 1 read-only cartography, rule-based migrations) where agents
  **do not** converse with each other, Python JSON-schema aggregation helps,
  and coarse model tiers (`flash_lite`/`flash`/`pro`) suffice.
- **`/swarm`**: Collaborative multi-role engineering (`author <-> verifier`
  iterative test/fix loops), long-running autonomous work (`swarm_monitor`),
  visual UI polish (`swarm_pane`), or tasks needing **heterogeneous exact
  models/thinking efforts**, cross-model verification, or in-flight
  `swarm{action:"model"}` quota hot-swapping.

*(Hybrid option: recommend `/run-workflow` for Phase 1 read-only discovery, then
`/swarm` for Phase 2+ collaborative implementation and verification.)*

## Step 3: Focused Decision Interview

Resolve only open project decisions that repo inspection cannot answer. Ask
**one question at a time** via `ask_question`, recommended option first:

1. **Ownership & no-touch zones**: Untouchable legacy modules/scripts, shared
   contracts (`src/types/*`, schemas), and central files (`package.json`,
   lockfiles, global routers).
2. **Runtime & test isolation**: Shared local DB, Redis, or fixed ports
   requiring sequential `verifier` runs or strict command flags.
3. **Sizing, Role-Model Matrix & Quota Fallback** *(critical for `/swarm`)*:
   Present the live matrix from Step 1 and obtain **explicit user approval** for
   each role's exact model ID + thinking effort (Coordinator, Core/Complex
   Authors, Routine Slice Authors, cross-family Verifier, lightweight
   Narrator/Monitor) and an approved `[quota]` fallback chain—because `/swarm`
   forbids coordinators from switching models without explicit user instruction.
4. **Project-Tailored Hooks vs. Soft Rules**: Propose concrete hooks from Step 1
   signals and project risks (e.g., lock `pnpm`/`uv`, deny writes to
   migrations/codegen, `force_ask` on `auth/`/`billing/`, block destructive DB
   resets/`git push`, fast single-file `PostToolUse` formatting, `SessionStart`
   context injection).
5. **Landing strategy**: Commit in `share` worktrees and merge/cherry-pick vs.
   branch review (never push to remote unless explicitly requested).

## Step 4: Blueprint Alignment & Approval

Summarize the concrete design before writing any project files:

- **Engine & session split**: Single vs. `/run-workflow` vs. `/swarm` (or Hybrid
  phasing).
- **Roster & isolation**: Worker names, owned paths, `workspace` mode
  (`inherit` for readers/verifiers; `share`/`branch` for parallel authors), and
  `tasks`/`n`/`fork`/`channel` (>8 workers or 2+ independent areas).
- **Approved Role-to-Model Matrix & Fallback**: Exact verified model IDs per role
  and pre-authorized `[quota]` swap order.
- **Custom Hooks Table** *(if selected)*: Hook name, `Event` + `Matcher`,
  project pain point solved, `decision`/action, and latency check (**must stay
  <1–2s** because Antigravity hooks run synchronously; never put full test
  suites in hooks, and avoid naïve global `Stop` hooks that trap `waiting`
  `/swarm` workers or `coordinator`).
- **Optional alignment artifacts (Project-Level)**: Create an Implementation Plan
  artifact (`RequestFeedback: true`, `UserFacing: true`) or a `generative_ui`
  widget (`<= 450px` inline tuner or standalone module map) when helpful.

## Step 5: Persist Guardrails (Optional) & Deliver Launch Plan

Once the user approves the blueprint:

1. **Optional project customizations** (Project-Level, if approved):
   - Prefer bundling project rules, skills, and hooks as a toggleable project
     plugin under `.agents/plugins/swarm-guardrails/` (`plugin.json`,
     `rules/AGENTS.md`, `skills/`, and `hooks.json` directly at the plugin root)
     so hard hooks can be disabled cleanly outside `/swarm` sprints.
   - Use [swarm-boundaries-AGENTS.md](./examples/swarm-boundaries-AGENTS.md),
     [swarm-guardrails-plugin.json](./examples/swarm-guardrails-plugin.json),
     [swarm-guardrails-hooks.json](./examples/swarm-guardrails-hooks.json), and
     [pretool-guard.py](./examples/pretool-guard.py) as starting models.
   - Keep `AGENTS.md` well under the 24 KB / 20,000-token rules budget; resolve
     hook paths via `payload["cwd"]` so they work inside `workspace:"share"`
     worktrees.
2. **Pre-flight Validation**:
   - Run `python3 ./scripts/model_matrix.py --from-swarm-json <json> --validate <comma-separated-ids>`
     (or `--from-agy`) to confirm every chosen model ID exists and has usable quota.
   - Validate JSON/YAML syntax, ensure hook scripts are executable (`chmod +x`),
     and **dry-run each hook script with a mock stdin JSON payload** to verify
     exit `0`, <1–2s execution, and exact stdout contract (`PreToolUse` decision,
     `PostToolUse` `{}`).
3. **Deliver the Ready-to-Paste Launch Plan**:
   - **If `/swarm` (or Hybrid Phase 2+)**: Output a self-contained `/swarm`
     Launch Prompt stating Goal + Definition of Done, Roster + file ownership +
     no-touch zones, central-file policy, `workspace` isolation, peer handoffs
     (`author <-> verifier` via `@mention`), **explicit user-authorized
     `Role -> Model` IDs + `[quota]` fallback chain**, and merge rules.
   - **If `/run-workflow`**: Output the staged `phase` / `parallel` / `pipeline`
     blueprint, recommended `flash_lite`/`flash`/`pro` tiers, and JSON `schema`
     contract so the next session can write and run it immediately.
