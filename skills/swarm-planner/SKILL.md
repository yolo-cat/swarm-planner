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
  `swarm_pane`, Role->Model matrix; skip custom hooks & heavy artifacts by
  default, including custom hooks in Steps 4–5 only if explicitly requested in
  Step 3), then Step 5 pre-flight + Launch Plan.
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
   pass using either a `call_tool(...)` fan-out with `WaitMsBeforeAsync`
   <=10000 ms and `ToolError.denied` handling, or `agent(...)` with
   `type_name="research"`—or a non-plan-gated custom agent—`workspace="inherit"`,
   `model="flash_lite"`, and a valid JSON `schema`; never `type_name="self"`,
   which inherits plan gating and deadlocks on `[plan review due]`.)*
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
     *(optional `--format json` emits catalog family metadata `count` and
     `families` with `vendor`, `quota_uniform`, `quotas_by_effort`).*
   - Fallback when `swarm` is unavailable (existence only; `quota=unknown`):
     `python3 "<skill-dir>/scripts/model_matrix.py" --from-agy`
   - Never guess model IDs or effort suffixes (`low`/`medium`/`high`/`xhigh`/`max`).
4. **Version alignment (when needed)**: For greenfield stacks or major upgrades,
   pin APIs via `context7-mcp` (`resolve-library-id` -> `query-docs`).

## Step 2: Three-Way Orchestration Router

Select the lightest multi-agent engine that fits:

- **`/run-workflow`** (read `run-workflow` skill if chosen): Deterministic
  fan-out (`parallel(items, fn)`, fail-fast) or sequential `pipeline(items, fn)`
  over an explicit list, zero-LLM tool fan-outs (`call_tool(name, **args)` +
  `WaitMsBeforeAsync` <=10000 ms + `ToolError.denied`), stateful multi-turn
  review/fix loops (`a = agent(...)` -> `await a(prompt, schema)` -> `del a`),
  prior-step mining (`await trajectory(...)`), and pre-session context/reruns
  via `Args`, `Cwd`, and `ScriptPath` (in `<appData>/brain/<id>/scratch/`).
  Uses Python JSON-schema aggregation and coarse tiers only
  (`inherit`/`flash_lite`/`flash`/`pro`—never exact `/swarm` IDs). Read-only
  passes must set `type_name="research"` (or a non-plan-gated custom agent) and
  `workspace="inherit"`; parallel mechanical code-editing transforms use
  `workspace="branch"` or `"share"` with an edit-capable `type_name` (`"self"`
  or custom coder).
- **`/swarm`**: Collaborative `author <-> verifier` loops, autonomous stall
  detection (`swarm_monitor` if in `<skills>`), Swarm UI Overview (`swarm_pane`
  if in `<skills>`, else `swarm_narrator` fallback if in `<skills>`),
  heterogeneous exact models/efforts, cross-family (or single-family
  cross-variant) verification, or `swarm{action:"model"}` quota hot-swapping.
- **Hybrid (`/run-workflow` -> `/swarm`)**: Keep this pre-session planner
  read-only, run Phase 1 (`/run-workflow` discovery) in a fresh session into a
  structured handoff artifact (either a committed repo-relative path like
  `docs/system-map.md` or an explicit absolute Phase 1
  `<appData>/brain/<phase1-id>/scratch/...` path—never a bare relative
  `scratch/...` path across sessions), pause for human review + clean git, and
  run Phase 2 (`/swarm` implementation) in a second fresh session.

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
4. **Guardrails vs. Soft Rules** *(Project-Level, or Lightweight only if
   explicitly requested)*: Propose hooks from Step 1 signals using the
   unattended-safe `"deny"` + `@coordinator` defaults in
   [task-matrices.md](./references/task-matrices.md#3-file-ownership-and-hook-signals-ssot)
   (`SWARM_GUARD_INTERACTIVE=1` for interactive single-session runs).
5. **Landing strategy**: Sequential merge from `share` worktrees vs. branch
   review (never `kill` a `share`/`branch` author before merging its committed
   work, and never push unless requested).

## Step 4: Blueprint Alignment & Approval

Summarize the design before writing files *(compact for Lightweight: skip
custom hooks & heavy artifacts unless explicitly requested in Step 3)*:

- **Engine & session split**: `/run-workflow` vs. `/swarm` vs. Hybrid (for
  Hybrid, explicitly separate this read-only pre-session planner -> fresh Phase
  1 `/run-workflow` session -> human review & clean-git checkpoint -> fresh
  Phase 2 `/swarm` session, using a committed repo-relative or absolute Phase 1
  `<appData>/brain/<phase1-id>/scratch/...` handoff path).
- **Roster & isolation**: Worker names, owned paths, `workspace` (`inherit` for
  readers/verifiers; `share`/`branch` for authors), `tasks`/`n`/`fork`, and
  `channel` **only if live `swarm` exposes `action:"channel"`** (else `main`).
  - **Swarm UI Overview (`swarm_pane`)**: Gate on `<skills>`: when `swarm_pane`
    is in `<skills>`, coordinator loads `swarm_pane` **before** adding/briefing
    workers and writes `plan.json` **once workers are added** (`goal` <=12
    words, `tasks`, 1–6 outcome `threads`; never store statuses, blockers, or
    asks in `plan.json`, and rewrite only on roster/work/goal changes). Never
    add a `narrator` unless asked by name (or if `swarm_pane` is absent and
    `swarm_narrator` is in `<skills>`). Gate `Screenshot: <abs-path> | <caption
    <=10 words>` on visual UI work only (own-line worker post,
    `.png`/`.jpg`/`.jpeg`/`.webp`, full-window on same screen/size/theme, no
    crops or diffs).
  - **Stall Monitor (`swarm_monitor`)**: Standard in `native_swarm` whenever
    `swarm_monitor` is in `<skills>` (inherits coordinator's model); brief must
    name it as the stall monitor, and **only `monitor`** loads `swarm_monitor`
    (never the coordinator or other workers). Coordinator never assigns work to,
    replies to, or kills `monitor`, posts `@monitor resume` after a server
    restart, and posts a standalone `[done] <summary>` (no `@` mentions) when
    finished so `monitor` stops its daemon cron.
- **Approved Role-to-Model Matrix & Fallback**: Exact verified IDs +
  pool-constrained `[quota]` swap order.
- **Custom Hooks Table** *(Project-Level, or Lightweight if explicitly
  requested in Step 3)*: Hook, `Event` + `Matcher`, pain point, `decision`, and
  latency check (**`<1–2s`** synchronously; no full test suites or naïve global
  `Stop` hooks).
- **Optional alignment artifacts (Project-Level)**: Implementation Plan
  (`RequestFeedback: true`, `UserFacing: true`) or `generative_ui` widget
  (`<= 450px` inline tuner or module map).

## Step 5: Persist Guardrails (Optional) & Deliver Launch Plan

Once the user approves the blueprint:

1. **Optional project plugin guardrails** *(Project-Level, or Lightweight if
   explicitly requested in Step 3, once approved)*:
   - Bundle under `.agents/plugins/swarm-guardrails/` (`plugin.json`,
     `hooks.json` at plugin root, `hooks/pretool-guard.py`, `rules/AGENTS.md`
     well under 24 KB) from
     [swarm-boundaries-AGENTS.md](./examples/swarm-boundaries-AGENTS.md),
     [swarm-guardrails-plugin.json](./examples/swarm-guardrails-plugin.json),
     [swarm-guardrails-hooks.json](./examples/swarm-guardrails-hooks.json), and
     [pretool-guard.py](./examples/pretool-guard.py). *(Note: inline multiline
     `PostToolUse`/`SessionStart` commands in `swarm-guardrails-hooks.json`
     require Unix `sh -c` and are not supported under Windows `cmd /c`;
     `PostToolUse` falls back to `workspacePaths[0]` and local
     `node_modules/.bin/prettier`.)*
   - Follow [task-matrices.md](./references/task-matrices.md#3-file-ownership-and-hook-signals-ssot)
     for hook semantics, pre-spawn clean git + guardrail commit, and
     post-sprint teardown (delete `.agents/plugins/swarm-guardrails/`, set
     `"disabled": true` in `plugin.json`—never bare `"enabled": false` in
     `plugin.json`—set per-hook `"enabled": false` in `hooks.json`, or run
     `agy plugin disable swarm-guardrails`, which persists in global
     `~/.gemini/config/config.json` across repos sharing that plugin name).
2. **Pre-flight Validation**:
   - **`/swarm` & Hybrid Phase 2**: Validate all assigned + fallback exact IDs
     (never pass `/run-workflow` coarse tiers). `--allowed-pool`,
     `--require-diverse`, and `--require-quota` require `--validate` (exiting
     `2` if omitted); passing `--validate ... --format json` outputs structured
     JSON on stdout (even on exit `1`) with keys `valid`, `results`,
     `diversity`, `errors`, `warnings`:
     - Swarm JSON (add `--allowed-pool <ids>` when pool-restricted; optional
       `--require-diverse` and `--format json`):
       `python3 "<skill-dir>/scripts/model_matrix.py" --from-swarm-json <json> --validate <comma-separated-ids> --require-quota`
     - CLI fallback (existence only; `quota=unknown`):
       `python3 "<skill-dir>/scripts/model_matrix.py" --from-agy --validate <comma-separated-ids>`
   - **`/run-workflow` & Hybrid Phase 1**: Verify coarse tiers only
     (`inherit`/`flash_lite`/`flash`/`pro`), `type_name="research"` (or
     non-plan-gated custom agent) + `workspace="inherit"` on read-only passes
     vs. `workspace="branch"`/`"share"` on parallel edit passes, valid JSON
     `schema` objects, and `WaitMsBeforeAsync`/`ToolError.denied` handling when
     using `call_tool`.
   - **If guardrails were written**: Run
     `agy plugin validate .agents/plugins/swarm-guardrails --strict`, validate
     JSON, `chmod +x` scripts, and **dry-run each hook with mock stdin JSON**
     (exit `0`, `<1–2s`, stdout: `PreToolUse` `{"decision": ...}`, `PostToolUse`
     `{}`, `SessionStart` `{"injectSteps": ...}`).
3. **Deliver Ready-to-Paste Launch Plan**: Use Templates A–D in
   [task-matrices.md](./references/task-matrices.md#4-ready-to-paste-launch-templates)
   (self-contained prompts with no `Follow Shared /swarm Invariants`
   self-reference; two separate pasteable blocks for Template D with committed
   repo-relative or absolute Phase 1 `<appData>/brain/<phase1-id>/scratch/...`
   handoff paths; `<skills>`-gated `swarm_pane` `plan.json` after adding workers
   + worker own-line full-window `Screenshot:` for UI; `<skills>`-gated
   `swarm_monitor` + standalone `[done] <summary>` teardown; 2–3 retry
   circuit-breaker; sequential merge **before** `kill`ing `share`/`branch`
   authors; and pool-constrained `Role -> Model` + `[quota]` fallback).
