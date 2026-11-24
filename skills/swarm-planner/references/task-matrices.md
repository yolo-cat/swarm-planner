# Task Configuration Matrices & Launch Templates (SSOT)

## 1. Orchestration Router & Scenario Matrix

| Scenario | Engine | Prerequisite | Workspace / Features | Verification / Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Small / Sequential** | **Single Session** / `/plan` | None (skip `/swarm`) | Default workspace | Direct edits + unit test |
| **Massive Audit / Scan** | **`/run-workflow`** | Target list / `call_tool` & JSON `schema` | `inherit`, `type_name="research"`, `parallel()` / `pipeline()` / `call_tool()` + `flash`/`flash_lite` | Python aggregation |
| **Legacy Cartography** | **`/run-workflow`** *(or `/swarm` `#seq`/`fork`)* | Forbid edits; list modules; 1 `docs/system-map.md` writer | `inherit` (`type_name="research"`) | Verified `file:line` in `docs/system-map.md` |
| **Legacy Characterization** | **`/swarm`** | Clean git + branch-vs-`main`; lock prod code; DB hooks | Authors `share`, Verifier `inherit`, `tasks` | Real behavior; sequential DB |
| **Greenfield MVP Sprint** | **`/swarm`** | Clean git + branch-vs-`main`; scaffold + contracts + green build | Authors `share`, Verifier `inherit`; `channel` *if supported* (else `main`) | Contract conformance & DRY |
| **Large Refactor / Migration** | **`/swarm`** *(or `/run-workflow` transforms)* | Clean git + branch-vs-`main`; lock public signatures | `/swarm`: `share` + `inherit`, `tasks`; `/run-workflow`: `branch`/`share` + stateful `agent()` | Full build + regression suite |
| **Multi-Role Code Audit** | **`/swarm`** or **`/run-workflow`** | Define diff target (e.g., vs. `main`) | All `inherit` (`type_name="research"` in `/run-workflow`); `#seq` citations | Ranked findings; optional `share` fixes |
| **UI / Visual Polish** | **`/swarm`** | Clean git + branch-vs-`main`; viewports & tokens | Frontend `share`, Verifier `inherit`, `swarm_pane` (if in `<skills>`) | `plan.json` (post-add) + own-line full-window `Screenshot:` |
| **Discovery -> Implement** | **Hybrid** (`/run-workflow` -> `/swarm`) | Committed repo path or absolute `<appData>/brain/<phase1-id>/scratch/...` & `schema` | Fresh session/phase: P1 `inherit` (`type_name="research"`); P2 `share`+`inherit` | Human review + clean git before P2 |

> **Session-Boundary & Handoff-Path Rules (SSOT)**:
> - **Fresh Session Per Phase**: Keep `swarm-planner` read-only; run Phase 1 (`/run-workflow`) and Phase 2 (`/swarm`) in **separate fresh sessions** (avoids transcript bloat, `tester` -> `tester-2` name collisions, and dirty git state).
> - **Handoff Paths (`<handoff-artifact-path>`)**: Use a **committed repo-relative path** (`docs/system-map.md`) or an **explicit absolute Phase 1 scratch path** (`<appData>/brain/<phase1-id>/scratch/plan-manifest.json`)—never a bare relative `scratch/...` path.

## 2. Heterogeneous Role-Model Strategy (`/swarm`)

> **Engine Model & Primitive Contract**:
> - **`/run-workflow`**: Coarse tiers only (`model="inherit"|"flash_lite"|"flash"|"pro"`—never exact `/swarm` IDs or `model_matrix.py --validate`) + JSON `schema`. Read-only passes: `workspace="inherit"`, `type_name="research"` (or non-plan-gated agent; never `type_name="self"`, which deadlocks on `[plan review due]`); mechanical edits: `workspace="branch"`/`"share"` + edit-capable `type_name`. Primitives: `parallel(items, fn)` (fail-fast), `pipeline(items, fn)` (sequential), stateful `a = agent(...)` -> `await a(prompt, schema)` -> `del a`, `call_tool(name, **args)` (`WaitMsBeforeAsync` <=10000 ms, `ToolError.denied`), `await trajectory(...)` (`status == "CLEARED"` if evicted), `Args`, `Cwd`, `ScriptPath` (`<appData>/brain/<id>/scratch/workflow.py`).
> - **`/swarm`** (and Hybrid Phase 2): Exact catalog IDs (`low`/`medium`/`high`/`xhigh`/`max`) verified via [model_matrix.py](../scripts/model_matrix.py) (`SKILL.md` Steps 1 & 5: `<skill-dir>`, `--from-swarm-json -`, `--from-agy`, `./scripts/install.sh --status`/`--check`). `--allowed-pool`, `--require-diverse`, and `--require-quota` **require `--validate <ids>`** (exit `2` if omitted; unknown `--allowed-pool` tokens exit `1`). `--validate <ids> --format json` emits `{valid, results, diversity, errors, warnings}` on exit `0`/`1` (`o1`/`o3`/`o4`/`gpt` -> `openai`; `model` + `model-high` -> `single-variant`).

| Role | Selection Principle | Rationale |
| :--- | :--- | :--- |
| **Coordinator** | High instruction-following / orchestrator | Tracks `#seq`, handoffs, merge order |
| **Core Author** | High/XHigh/Max reasoning flagship ID | Concurrency, state machines, contracts |
| **Slice Author** | Fast, high-quota ID (`low`/`medium` effort) | Parallel CRUD, UI slices, boilerplate |
| **Verifier** | **Cross-family analytical ID** *(or distinct variant/effort in 1-family pool, e.g., Neon vs. Hydrogen/Carbon/Argon)* | Catches single-model blind spots |
| **Monitor** *(standard if `swarm_monitor` in `<skills>`)* | Inherits coordinator model | Stall-monitor brief; **only `monitor`** loads `swarm_monitor`. Never assign/reply/kill `monitor` (unless asked); `@monitor resume` on restart; standalone `[done] <summary>` (no `@`) when done |
| **Quota Fallback** | 1–2 backup IDs/tier **in approved pool** | `swarm{action:"model"}` hot-swap on `[quota]` inside pool |

> **`swarm_pane` vs. `swarm_narrator`**: If `swarm_pane` is in `<skills>`, load pre-add and write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` **once workers are added** (`goal.title` 4–8w, `goal.line` <=12w, `tasks`, 1–6 `threads`; no statuses/blockers/asks; rewrite only on roster/work/goal changes; no `narrator` unless asked, or `swarm_narrator` fallback if `swarm_pane` absent). UI work only: full-window `.png`/`.jpg`/`.jpeg`/`.webp` in `<appData>/brain/<conversation id>/` (same screen/size/theme; no crops/diffs) and own-line worker `Screenshot: <abs-path> | <caption <=10 words>` (coordinator/narrator/monitor ignored).

## 3. File Ownership and Hook Signals (SSOT)

Default `PreToolUse` decision: unattended-safe **`"deny"` + `@coordinator`**
(`SWARM_GUARD_INTERACTIVE=1` for interactive runs; all hooks `<1–2s`).

| Asset Class | Repo Signals | Ownership | Unattended-Safe Guardrail |
| :--- | :--- | :--- | :--- |
| **Feature Modules** | `src/modules/*`, slices | Author (`share`) | `PreToolUse` confines writes to `cwd` (`workspacePaths[0]` fallback) or `artifactDirectoryPath`; blocks `../`, `$VAR`, symlinks, `/etc/*` |
| **Central Manifests & Protected** | `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock`, `uv.lock`, `src/auth/`, `src/billing/` | Integrator / `@coordinator` | `PreToolUse` `"deny"` + `@coordinator` on write/edit & `run_command`; blocks `npm install` |
| **Contracts, Migrations & Codegen** | `src/types/*`, `openapi.*`, `proto/`, `generated/`, `migrations/` | Frozen; forward-only | `PreToolUse` `"deny"` on edits & `run_command` (`sed -i`, redirs, `rm`/`mv`/`ln`) |
| **Secrets & Remote Git** | `.env`, `.env.*` (except `.env.example`/`.sample`/`.template`), `git push` | Never read or push | `PreToolUse` `"deny"` on `.env` writes & reads (`read_file`/`view_file` `AbsolutePath` + `run_command`, case-insensitive) and `git ... push` |
| **Shared Runtime** | `docker-compose*`, DB/Redis, ports | Sequential `verifier` (`inherit`) | `PreToolUse` `"deny"` on `dropdb`, `--force-reset` |
| **Formatting & Startup Context** | `.prettierrc`, `ruff.toml`, `AGENTS.md`, `docs/system-map.md` | Per-file / session | `PostToolUse` (disabled-by-default Prettier template in workspace, excluding `package-lock.json`, `AbsolutePath`/`workspacePaths[0]`/`node_modules/.bin/prettier` fallbacks, `timeout=1.5`, `{}`) + flat `SessionStart` (non-dict JSON guard + `workspacePaths[0]` fallback for `AGENTS.md`/`docs/system-map.md`). *Inline multiline hooks require Unix `sh -c` (no Windows `cmd /c`).* |

> **Pre-Spawn Readiness & Teardown Lifecycle**:
> - **Pre-spawn**: `agy plugin validate .agents/plugins/swarm-guardrails --strict` + hook dry-runs, clean `git status --short` (scaffold/handoff/guardrails committed), and `git rev-list --left-right --count main...HEAD`.
> - **Teardown** (never hand-edit `config.json`): (1) delete `.agents/plugins/swarm-guardrails/`; (2) `"disabled": true` in `plugin.json` (never bare `"enabled": false` in `plugin.json`) or per-hook `"enabled": false` in `hooks.json` (`rules/AGENTS.md` stays active); (3) `agy plugin disable swarm-guardrails` (persists in `~/.gemini/config/config.json` across repos sharing that name).

## 4. Ready-to-Paste Launch Templates

> **Planner-Only Assembly Rule**: Assemble prompts from Sections 1–3 above.
> **Never** emit internal doc references (`Follow Shared /swarm Invariants` or
> `Apply Template B`) inside a fenced launch prompt.

### Template A: Canonical `/swarm` Prompt (Feature / Fix / UI)
```text
/swarm
Goal: Implement <feature/fix scope>. Done when `<test/build commands>` pass.

Context & pre-spawn: Read `<AGENTS.md / docs/system-map.md>`. Verify clean `git status --short` (guardrails committed if used) and branch-vs-`main` before spawning `share`/`branch` workers.
UI & Monitor: If `swarm_pane` in `<skills>`, load pre-add and write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` post-add (`goal.title` 4–8w, `goal.line` <=12w, `tasks`, 1–6 `threads`; no statuses/blockers/asks; rewrite only on roster/work/goal changes; no `narrator` unless asked). <If UI work: full-window .png/.jpg/.jpeg/.webp in `<appData>/brain/<conversation id>/` (same screen/size/theme; no crops/diffs) + own-line worker `Screenshot: <abs-path> | <caption <=10 words>`.> If `swarm_monitor` in `<skills>`, add `monitor` with stall-monitor brief (only `monitor` loads `swarm_monitor`; never assign/reply/kill `monitor` unless asked; `@monitor resume` on restart; standalone `[done] <summary>` with no `@` when done).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default/exact id>` | `<core-author>`: `<exact flagship id>` (`<core-path>`) | `<slice-author-1..k>`: `<exact fast id>` (`<slice-paths>`) | `verifier`: `<exact cross-family/variant id>` (`inherit`, read-only review + tests)
- Quota fallback: On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-id>` (inside approved pool).

Workspace, Handoffs & Landing:
- Authors use `workspace:"share"`; `verifier` uses `inherit` (read-only). Board: `main` (`channel`s only if `action:"channel"` exists). Do not edit `<no-touch/lockfiles>` without `@coordinator`.
- Peer handoffs: `<author> <-> verifier` via `@mention` (no `@coordinator` CC; max 2–3 retry bounces before escalating).
- Landing & teardown: Commit in each `share` worktree; merge sequentially (`<core-author>` -> `<slice-author-1>` -> ...) after `verifier` sign-off **before `kill`ing any `share`/`branch` author** (`kill` deletes workspace), then run `<test/build commands>`. Never push. Post standalone `[done] <summary>` (no `@`) and tear down guardrails.
```

### Template B: `/run-workflow` Blueprint (Audits / Scans / Transforms / Phase 1)
```text
/run-workflow
Goal: <Scan/map/audit/transform N targets> and aggregate results into `<output-path>`.

Rules: Coarse tiers only (`model="inherit"|"flash_lite"|"flash"|"pro"` — never exact `/swarm` IDs) and a JSON `schema` on every `agent()`. Prefer `ScriptPath` in `<appData>/brain/<id>/scratch/workflow.py` (`Args`, `Cwd`). Read-only `agent(...)`: `type_name="research"` (never `type_name="self"`), `workspace="inherit"`; parallel edits: `workspace="branch"`/`"share"` + edit-capable `type_name`. Primitives: `call_tool()` (`WaitMsBeforeAsync` <=10000 ms, `ToolError.denied`), `await trajectory(...)`, `parallel()` (fail-fast), `pipeline()` (sequential), stateful `a = agent(...)` -> `await a(prompt, schema)` -> `del a`.
1. `phase("Discover")`: `agent(..., type_name="research", workspace="inherit", role="Discover targets", model="flash_lite", schema={"type": "array", "items": {"type": "string"}})` (or `call_tool` scan).
2. `phase("Analyze")`: `parallel(targets, lambda t: agent(..., type_name="research", workspace="inherit", role=f"Analyze {t}", model="flash", schema={"type": "object", "properties": {"path": {"type": "string"}, "entry_points": {"type": "array", "items": {"type": "string"}}, "deps": {"type": "array", "items": {"type": "string"}}, "risks": {"type": "array", "items": {"type": "string"}}}, "required": ["path", "entry_points", "deps", "risks"]}))` (or `pipeline(targets, ...)`).
3. Aggregate deterministically in Python, verify schema completeness, and write `<output-path>`.
```

### Template C: Legacy `/swarm` Mode Deltas (Substitute into Template A)

Keep Template A's `Context & pre-spawn`, `UI & Monitor`, `Quota fallback`,
`Board`, and `Peer handoffs`, and replace `Goal`, roles, `Workspace`, and
`Landing & teardown`:

- **Cartography Mode (`workspace:"inherit"`, read-only)**:
  - `Goal`: Map `<modules>` into `docs/system-map.md` with verified `file:line` evidence.
  - `Authorized Role -> Model Assignments` & `Workspace`: `<investigator-1..k>` (`infra-runner`, `entry-tracer`, `data-modeler`, `hotspot-auditor`) + `verifier`, all `workspace:"inherit"` and read-only (cite `#seq`).
  - `Landing & teardown`: **Coordinator (or 1 named writer)** compiles accepted `#seq` summaries into `docs/system-map.md`; `kill` read-only `inherit` investigators once accepted (unless `fork`ing); post standalone `[done] <summary>` (no `@`) and tear down guardrails.
- **Characterization Mode (`workspace:"share"` testers + sequential `verifier`)**:
  - `Goal`: Write characterization tests for `<modules>` without altering prod logic or assertions. Done when `<test commands>` pass.
  - `Authorized Role -> Model Assignments` & `Workspace`: `<tester-1..k>` (`workspace:"share"`, test files only, `tasks`) + 1 cross-family/distinct-variant `verifier` (`workspace:"inherit"`, flags over-mocking, runs shared-DB/port suites sequentially).
  - `Landing & teardown`: Commit in each `share` worktree and merge sequentially (`<tester-1>` -> `<tester-2>` -> ...) after `verifier` sign-off **before `kill`ing any `share` tester** (`kill` deletes workspace); never push; post standalone `[done] <summary>` (no `@`) and tear down guardrails.

### Template D: Hybrid Two-Session Handoff (Phase 1 `/run-workflow` -> Phase 2 `/swarm`)

#### Prompt 1: Phase 1 Read-Only Discovery (`/run-workflow`, Session 1)
```text
/run-workflow
Goal: Inventory `<target modules/files>` and write `<committed repo path e.g. docs/system-map.md OR absolute <appData>/brain/<phase1-id>/scratch/plan-manifest.json>`.

Rules: Read-only `agent(...)` MUST use `type_name="research"` (never `type_name="self"`), `workspace="inherit"`, `role="..."`, coarse tiers (`"inherit"|"flash_lite"|"flash"|"pro"`), and JSON `schema`; use `parallel()`/`pipeline()`, optional `call_tool()` (`WaitMsBeforeAsync` <=10000 ms, `ToolError.denied`), and `ScriptPath` in scratch.
1. `phase("Discover")`: `agent(..., type_name="research", workspace="inherit", role="Discover targets", model="flash_lite", schema={"type": "array", "items": {"type": "string"}})`.
2. `phase("Map")`: `parallel(targets, lambda t: agent(..., type_name="research", workspace="inherit", role=f"Map {t}", model="flash", schema={"type": "object", "properties": {"path": {"type": "string"}, "public_api": {"type": "array", "items": {"type": "string"}}, "deps": {"type": "array", "items": {"type": "string"}}, "test_cmd": {"type": "string"}, "risks": {"type": "array", "items": {"type": "string"}}}, "required": ["path", "public_api", "deps", "test_cmd", "risks"]}))`.
3. Write `<handoff-artifact-path>` deterministically (read-only on prod code) and stop for review.
```

> **Inter-Phase Checkpoint**: Review `<handoff-artifact-path>`. If repo-relative (`docs/system-map.md`), commit it (plus optional `.agents/plugins/swarm-guardrails/`) so `git status --short` is clean; if in Phase 1 scratch, pass its **exact absolute path** (`<appData>/brain/<phase1-id>/scratch/plan-manifest.json`) into Prompt 2 (never a relative `scratch/...` path). Paste Prompt 2 in a **fresh session**.

#### Prompt 2: Phase 2 Collaborative Implementation (`/swarm`, Fresh Session 2)
```text
/swarm
Goal: Implement `<scope>` using `<committed repo path e.g. docs/system-map.md OR absolute <appData>/brain/<phase1-id>/scratch/plan-manifest.json>`. Done when `<test/build commands>` pass.

Context & pre-spawn: Read `<handoff-artifact-path>` (and `<AGENTS.md>`) first—do not re-discover the repo. Verify clean `git status --short` (handoff + optional guardrails committed) and branch-vs-`main` before spawning `share`/`branch` workers.
UI & Monitor: If `swarm_pane` in `<skills>`, load pre-add and write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` post-add (`goal.title` 4–8w, `goal.line` <=12w, `tasks`, 1–6 `threads`; no statuses/blockers/asks; rewrite only on roster/work/goal changes; no `narrator` unless asked). <If UI work: full-window .png/.jpg/.jpeg/.webp in `<appData>/brain/<conversation id>/` and own-line worker `Screenshot: <abs-path> | <caption <=10 words>`.> If `swarm_monitor` in `<skills>`, add `monitor` with stall-monitor brief (only `monitor` loads `swarm_monitor`; never assign/reply/kill `monitor` unless asked; `@monitor resume` on restart; standalone `[done] <summary>` with no `@` when done).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default/exact id>` | `<core-author>`: `<exact flagship id>` (`<core-path>`) | `<slice-author-1..k>`: `<exact fast id>` (`<slice-paths>`) | `verifier`: `<exact cross-family/variant id>` (`inherit`, read-only review + tests)
- Quota fallback: On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-id>` (inside approved pool).

Workspace, Handoffs & Landing:
- Authors use `workspace:"share"`; `verifier` uses `inherit` (read-only). Board: `main` (`channel`s only if `action:"channel"` exists). Do not edit `<no-touch/lockfiles>` without `@coordinator`.
- Peer handoffs: `<author> <-> verifier` via `@mention` (no `@coordinator` CC; max 2–3 retry bounces before escalating).
- Landing & teardown: Commit in each `share` worktree; merge sequentially (`<core-author>` -> `<slice-author-1>` -> ...) after `verifier` sign-off **before `kill`ing any `share`/`branch` author** (`kill` deletes workspace), then run `<test/build commands>`. Never push. Post standalone `[done] <summary>` (no `@`) and tear down guardrails.
```
