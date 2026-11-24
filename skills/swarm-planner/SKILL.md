---
name: swarm-planner
description: >-
  Pre-session orchestration planner to route tasks between single-session,
  /run-workflow, and /swarm, inspect live Antigravity model+thinking quotas,
  co-design project-tailored hooks and guardrails, and output a ready-to-paste
  launch prompt before spending multi-agent quota.
---

# Swarm Pre-Session Planner

Design the execution engine, model allocation, and guardrails **before**
spending multi-agent quota. Stay lightweight and read-only until the user
approves the blueprint: never launch `/swarm` or write business code here.

## Step 0: Fast-Exit & Triage

Check **before** running recon or `model_matrix.py`:

- **Single-Session / `/plan` Fast-Exit**: Small single-file edits, tightly
  coupled refactors, strictly sequential work, or 1–2 lookups -> execute
  directly (or `/plan`). Skip recon, `model_matrix.py`, and the interview.
- **Lightweight** (single feature, targeted migration, audit, bug hunt, UI
  polish): Read [task-matrices.md](./references/task-matrices.md), trim Steps 1
  & 3 to essentials, run a **compact Step 4 alignment** (engine, roster,
  `swarm_pane`, Role->Model matrix; skip custom hooks & heavy artifacts), then
  Step 5 pre-flight + Launch Plan.
- **Project-Level** (legacy takeover or greenfield setup): Run Steps 1–5 and
  read [task-matrices.md](./references/task-matrices.md) plus
  [legacy-playbook.md](./references/legacy-playbook.md) or
  [greenfield-playbook.md](./references/greenfield-playbook.md).

## Step 1: Lightweight Recon, Signals & Live Model Snapshot

Inspect only repo shape, guardrails, and models—do not deeply read business
logic:

1. **Repo, git & customization baseline**: Check layout, `AGENTS.md` /
   `GEMINI.md` / `.agents/`, build/test manifests, and git state
   (`git status --short`, `git branch --show-current`, and
   `git rev-list --left-right --count main...HEAD` in linked worktrees).
2. **Project hook signals**: Identify guardrail candidates via
   [task-matrices.md](./references/task-matrices.md#3-file-ownership-and-hook-signals-ssot).
   *(For 10+ package monorepos only, optionally run a read-only `run_workflow`
   pass with `type_name="research"`, `workspace="inherit"`, `model="flash_lite"`,
   and a valid JSON Schema—never `type_name="self"`, which inherits plan gating
   and deadlocks on `[plan review due]`.)*
3. **Live Model × Thinking Effort × Quota snapshot**:
   - Resolve `<skill-dir>` from this skill's `SKILL.md` path in `<skills>`
     (default `~/.gemini/config/skills/swarm-planner`), pointing to
     [model_matrix.py](./scripts/model_matrix.py). Never run repo-relative
     `./scripts/model_matrix.py` from a target project `cwd`.
   - **Repo-vs-installed drift check**: When `<cwd>/skills/swarm-planner/`
     exists, compare it against `<skill-dir>` (`./scripts/install.sh --status`
     or `diff -rq`/`readlink`) and warn/sync before relying on `<skill-dir>`.
   - Pipe `swarm{action:"models", all:true}` JSON into:
     `python3 "<skill-dir>/scripts/model_matrix.py" --from-swarm-json -`
   - Fallback when `swarm` is unavailable (existence only; `quota=unknown`):
     `python3 "<skill-dir>/scripts/model_matrix.py" --from-agy`
   - Never guess model IDs or effort suffixes (`low`/`medium`/`high`/`xhigh`/`max`).
4. **Version alignment (when needed)**: For greenfield stacks or major upgrades,
   pin APIs via `context7-mcp` (`resolve-library-id` -> `query-docs`).

## Step 2: Three-Way Orchestration Router

Select the lightest multi-agent engine that fits:

- **`/run-workflow`** (read `run-workflow` skill if chosen): Deterministic
  fan-out/pipeline over an explicit list (audits, legacy Phase 1 cartography,
  mechanical transforms) with no board chatter, Python JSON-schema aggregation,
  and coarse tiers (`inherit`/`flash_lite`/`flash`/`pro`—never exact `/swarm`
  IDs). Read-only passes must set `type_name="research"` (or a non-plan-gated
  subagent).
- **`/swarm`**: Collaborative `author <-> verifier` loops, autonomous work
  (`swarm_monitor`), Swarm UI Overview (`swarm_pane` + UI `Screenshot:`),
  heterogeneous exact models/efforts, cross-family (or single-family
  cross-variant) verification, or `swarm{action:"model"}` quota hot-swapping.
- **Hybrid (`/run-workflow` -> `/swarm`)**: Phase 1 read-only discovery into a
  structured artifact, then Phase 2 `/swarm` implementation and verification.

## Step 3: Batched Decision Interview

Resolve only open questions in **1–2 batched `ask_question` calls** (recommended
option first):

1. **Ownership & no-touch zones**: Untouchable legacy paths, shared contracts,
   and central manifests/lockfiles.
2. **Runtime & test isolation**: Shared local DB, Redis, or fixed ports
   requiring sequential `verifier` runs.
3. **Role-Model Matrix & Quota Fallback** *(for `/swarm`)*: Present the Step 1
   matrix with [task-matrices.md](./references/task-matrices.md#2-heterogeneous-role-model-strategy-swarm)
   and obtain explicit user approval for exact role IDs and `[quota]` fallback.
   If the user restricts models to one family (or other families lack quota),
   preserve that allowlist across all roles and `[quota]` fallbacks (never
   falling back to an unrestricted coordinator model) and pair distinct
   variants/efforts (e.g., Neon vs. Hydrogen/Carbon/Argon).
4. **Guardrails vs. Soft Rules** *(Project-Level, or Lightweight if requested)*:
   Propose hooks from Step 1 signals using the unattended-safe `"deny"` +
   `@coordinator` defaults in
   [task-matrices.md](./references/task-matrices.md#3-file-ownership-and-hook-signals-ssot)
   (`SWARM_GUARD_INTERACTIVE=1` for interactive single-session runs).
5. **Landing strategy**: Sequential merge from `share` worktrees vs. branch
   review (never push unless requested).

## Step 4: Blueprint Alignment & Approval

Summarize the design before writing files *(compact for Lightweight: skip
custom hooks & heavy artifacts)*:

- **Engine & session split**: `/run-workflow` vs. `/swarm` vs. Hybrid.
- **Roster & isolation**: Worker names, owned paths, `workspace` (`inherit` for
  readers/verifiers; `share`/`branch` for authors), `tasks`/`n`/`fork`, and
  `channel` **only if live `swarm` exposes `action:"channel"`** (else `main`).
  - **Swarm UI Overview (`swarm_pane`)**: For **all** `/swarm` sessions,
    coordinator loads `swarm_pane` **before** briefing/adding workers and writes
    `plan.json` (gate `Screenshot: <abs-path> | <caption <=10 words>` on visual
    UI work only). Never add a `Narrator` unless asked by name.
  - **Stall Monitor (`swarm_monitor`)**: Add `monitor` only if `swarm_monitor`
    is in `<skills>` (inherits coordinator's model); brief must name it as the
    stall monitor, and **only `monitor`** loads `swarm_monitor` (never the
    coordinator or other workers).
- **Approved Role-to-Model Matrix & Fallback**: Exact verified IDs +
  pool-constrained `[quota]` swap order.
- **Custom Hooks Table** *(Project-Level, if selected)*: Hook, `Event` +
  `Matcher`, pain point, `decision`, and latency check (**`<1–2s`**
  synchronously; no full test suites or naïve global `Stop` hooks).
- **Optional alignment artifacts (Project-Level)**: Implementation Plan
  (`RequestFeedback: true`, `UserFacing: true`) or `generative_ui` widget
  (`<= 450px` inline tuner or module map).

## Step 5: Persist Guardrails (Optional) & Deliver Launch Plan

Once the user approves the blueprint:

1. **Optional project plugin guardrails** *(Project-Level, if approved)*:
   - Bundle under `.agents/plugins/swarm-guardrails/` (`plugin.json`,
     `hooks.json` at plugin root, `hooks/pretool-guard.py`, `rules/AGENTS.md`
     well under 24 KB) from
     [swarm-boundaries-AGENTS.md](./examples/swarm-boundaries-AGENTS.md),
     [swarm-guardrails-plugin.json](./examples/swarm-guardrails-plugin.json),
     [swarm-guardrails-hooks.json](./examples/swarm-guardrails-hooks.json), and
     [pretool-guard.py](./examples/pretool-guard.py).
   - Follow [task-matrices.md](./references/task-matrices.md#3-file-ownership-and-hook-signals-ssot)
     for hook semantics, pre-spawn clean git + guardrail commit, and
     post-sprint teardown.
2. **Pre-flight Validation**:
   - **`/swarm` & Hybrid Phase 2**: Validate all assigned + fallback exact IDs
     (never pass `/run-workflow` coarse tiers):
     - Swarm JSON (add `--allowed-pool <ids>` when pool-restricted; optional
       `--require-diverse`):
       `python3 "<skill-dir>/scripts/model_matrix.py" --from-swarm-json <json> --validate <comma-separated-ids> --require-quota`
     - CLI fallback (existence only; `quota=unknown`):
       `python3 "<skill-dir>/scripts/model_matrix.py" --from-agy --validate <comma-separated-ids>`
   - **`/run-workflow` & Hybrid Phase 1**: Verify coarse tiers only
     (`inherit`/`flash_lite`/`flash`/`pro`), `type_name="research"` on
     read-only passes, and valid JSON Schema objects.
   - **If guardrails were written**: Validate JSON, `chmod +x` scripts, and
     **dry-run each hook with mock stdin JSON** (exit `0`, `<1–2s`, stdout:
     `PreToolUse` `{"decision": ...}`, `PostToolUse` `{}`, `SessionStart`
     `{"injectSteps": ...}`).
3. **Deliver Ready-to-Paste Launch Plan**: Use Templates A–D in
   [task-matrices.md](./references/task-matrices.md#4-ready-to-paste-launch-templates)
   (`type_name="research"` for B/D, `swarm_pane` `plan.json` for all `/swarm` +
   `Screenshot:` for UI, 2–3 retry circuit-breaker, sequential merge, and
   pool-constrained `Role -> Model` + `[quota]` fallback).
