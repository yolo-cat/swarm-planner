# Task Configuration Matrices & Launch Templates (SSOT)

This file is the **Single Source of Truth (SSOT)** for orchestration routing,
session boundaries, role-to-model allocation, file ownership & hook signals,
and ready-to-paste launch templates.

## 1. Orchestration Router & Scenario Matrix

| Scenario | Recommended Engine | Pre-Launch Prerequisite | Workspace / Features | Verification / Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Small / Sequential Edit** | **Single Session** or `/plan` *(Step 0 fast-exit)* | None (skip `/swarm`) | Default workspace | Direct edits + unit test |
| **Massive Audit / Pattern Scan** | **`/run-workflow`** | Define target list (or `call_tool` scan) & valid JSON `schema` | `inherit`, `type_name="research"` (or non-plan-gated custom agent), `parallel()` / `pipeline()` / `call_tool()` (`WaitMsBeforeAsync` <=10000 ms) + `flash`/`flash_lite` | Deterministic Python aggregation |
| **Legacy Cartography (Phase 1)** | **`/run-workflow`** *(or `/swarm` if interactive cross-talk/`fork` needed)* | Forbid code edits; list top modules; designate writer for `docs/system-map.md` | `inherit` (`type_name="research"` in `/run-workflow`); compile to `docs/system-map.md` | Verified `file:line` evidence |
| **Legacy Characterization Tests** | **`/swarm`** | Clean `git status` + branch-vs-`main` check; lock prod code & assertions; add migration/DB hooks | Authors `share`, Verifier `inherit`, `tasks` | Real behavior vs. over-mocking; single-verifier DB runs |
| **Greenfield MVP Sprint** | **`/swarm`** | Clean `git status` + branch-vs-`main` check; scaffold + shared contracts + baseline build green | Authors `share`, Verifier `inherit`; `channel` *only if live `swarm` exposes `action:"channel"`* (else single-board `main`) | Contract conformance, zero duplicate helpers |
| **Large Refactor / Migration** | **`/swarm`** *(or `/run-workflow` for mechanical transforms / bounded review-fix loops)* | Clean `git status` + branch-vs-`main` check; lock invariants & public signatures | `/swarm`: Migrators `share`, Verifier `inherit`, `tasks`; `/run-workflow`: `workspace="branch"`/`"share"` with edit-capable `type_name` + stateful `a = agent(...)` -> `await a(...)` review loop | Full build + regression suite |
| **Multi-Role Code Audit** | **`/swarm`** *(cross-model review)* or **`/run-workflow`** *(checklist sweep)* | Define diff target (e.g., vs. `main`) | All `inherit` (`type_name="research"` in `/run-workflow`); `#seq` citations | Severity-ranked findings; optional `share` fixes |
| **UI / Visual Polish** | **`/swarm`** | Clean `git status` + branch-vs-`main` check; specify target viewports & design tokens | Frontend `share`, Verifier `inherit`, `swarm_pane` (if in `<skills>`) | `plan.json` (after workers added) + worker own-line full-window `Screenshot:` milestones |
| **Discovery -> Implementation** | **Hybrid** (Phase 1 `/run-workflow` -> Phase 2 `/swarm`) | Define committed repo-relative or absolute Phase 1 `<appData>/brain/<phase1-id>/scratch/...` handoff path & JSON `schema`; clean `git status` before Phase 2 | Fresh session per phase: Phase 1 `inherit` (`type_name="research"`); Phase 2 `share` + `inherit` | Human reviews handoff artifact + clean git checkpoint before launching Phase 2 in a fresh session |

> **Session-Boundary & Cross-Session Handoff Rules (SSOT)**:
> - **Fresh Session Per Phase**: Keep the read-only `swarm-planner` pre-session separate from execution, and start a **fresh conversation session** between Phase 1 (`/run-workflow` discovery/cartography) and Phase 2 (`/swarm` implementation or characterization). Fresh sessions prevent Phase 1 transcripts from bloating Phase 2 context, avoid retired `/swarm` worker name collisions (`tester` -> `tester-2`), and enforce a human review + clean `git status --short` gate before spawning `share`/`branch` workers.
> - **Handoff Artifact Paths (`<handoff-artifact-path>`)**: Across fresh sessions, handoff files MUST be either a **committed repo-relative path** (e.g., `docs/system-map.md`, committed before Phase 2 so `git status --short` stays clean for `share` worktrees) or an **explicit absolute Phase 1 scratch path** (`<appData>/brain/<phase1-id>/scratch/plan-manifest.json`). Never use a bare relative `scratch/...` path across sessions (it either points to Phase 1's unreachable per-conversation brain directory or leaves an untracked file in `cwd` that breaks Phase 2's clean-git prerequisite).

## 2. Heterogeneous Role-Model Strategy (`/swarm`)

> **Engine Model & Primitive Contract**:
> - **`/run-workflow`** uses coarse model tiers only: `model="inherit"|"flash_lite"|"flash"|"pro"` (never pass exact `/swarm` catalog IDs into `run_workflow`, and never pass coarse tiers to `model_matrix.py --validate`).
>   - **Workspace & `type_name`**: Read-only passes MUST pass `workspace="inherit"` and `type_name="research"` (or a non-plan-gated custom agent if `research` is absent—never default `type_name="self"` on read-only passes when plan gating is active, which deadlocks on `[plan review due]`). Parallel mechanical code-editing transforms use `workspace="branch"` (isolated clone) or `workspace="share"` (shared repo worktree) with an edit-capable `type_name` (`"self"` or custom coder agent).
>   - **Primitives & Invocation**: Use `parallel(items, fn)` for concurrent fail-fast fan-out and `pipeline(items, fn)` for sequential one-at-a-time execution in item order; stateful multi-turn agents (`a = agent(prompt, role=..., ...)` -> `await a(turn_prompt, schema)` -> `del a`) for bounded deterministic review/fix loops; `await call_tool(name, **args)` for zero-LLM deterministic tool calls (set `WaitMsBeforeAsync` up to `10000` ms on `run_workflow` for quick same-turn tool fan-outs, and catch `ToolError` checking `e.denied` for pre-tool hook/permission rejections since workflows cannot prompt users); `await trajectory(last=..., types=..., tools=..., min_index=..., max_index=...)` to mine earlier conversation steps before `run_workflow` started (evicted steps have `status == "CLEARED"`); and `Args` (read as `args` dict), `Cwd`, and `ScriptPath` (prefer writing non-trivial scripts to `<appData>/brain/<id>/scratch/workflow.py` and passing `ScriptPath` for easy line-level fixes/reruns; set exactly one of `Script` or `ScriptPath`).
> - **`/swarm`** (and Hybrid Phase 2) uses exact catalog IDs (including `low`/`medium`/`high`/`xhigh`/`max` effort suffixes) verified by [model_matrix.py](../scripts/model_matrix.py). Never use coarse aliases.

Follow `SKILL.md` Steps 1 & 5 for `<skill-dir>` resolution, repo-vs-installed
drift checks (`./scripts/install.sh --status` or `--check`), live catalog
inspection (`--from-swarm-json -` preferred; `--from-agy` checks existence only
with `quota=unknown`), and pre-flight validation:

- `--allowed-pool <comma-separated-ids>`, `--require-diverse`, and
  `--require-quota` **require `--validate <comma-separated-ids>`** (exiting `2`
  if `--validate` is omitted). Unknown tokens in `--allowed-pool` fail
  validation (exit `1`).
- Adding `--format json` to `--validate` emits structured JSON on stdout (for
  both exit `0` and exit `1`) with top-level keys `valid`, `results`,
  `diversity`, `errors`, and `warnings` (`diversity` is computed only over
  unique validated, in-pool, quota-ok models; `o1`/`o3`/`o4`/`gpt` normalize to
  vendor `openai`, and `model` + `model-high` share a base family as
  `single-variant`). Without `--validate`, `--format json` emits catalog family
  metadata (`count`, `families` with `vendor`, `quota_uniform`,
  `quotas_by_effort`).

Per `native_swarm` rules, coordinators never switch models on their own
initiative **except** when the user explicitly requests it **or** a member hits
`[quota]`/capacity exhaustion (switching to the user's pre-approved fallback
chain—staying strictly inside any user-restricted pool—or the coordinator's
model only when unrestricted).

| Role | Selection Principle | Rationale |
| :--- | :--- | :--- |
| **Coordinator** | High instruction-following / orchestrator variant | Tracks `#seq` references, handoffs, and merge order cleanly |
| **Core / Complex Author** | High/XHigh/Max reasoning flagship exact model ID | Protects concurrency, state machines, and shared contracts |
| **Routine Slice Author** | Fast, high-quota exact model ID (`low`/`medium` effort or fast variant) | Maximizes parallel throughput on CRUD, UI slices, and boilerplate |
| **Verifier** | **Cross-family strong analytical model** *(or distinct variant / higher thinking effort within a user-restricted single-family pool, e.g., Gemini Neon vs. Hydrogen/Carbon/Argon)* | Independent "second pair of eyes" catches single-model blind spots even under single-family pool constraints |
| **Monitor** *(standard when `swarm_monitor` is in `<skills>`)* | Inherits coordinator's model by default | Add whenever `swarm_monitor` is in `<skills>`; brief must state it is the stall monitor (only `monitor` loads `swarm_monitor`). Coordinator never assigns work to, replies to, or kills `monitor`, posts `@monitor resume` after restart, and posts standalone `[done] <summary>` (no `@` mentions) when finished so `monitor` kills its daemon cron |
| **Quota Fallback Chain** | 1–2 pre-approved backup IDs per tier **within the user's approved pool** | Lets Coordinator `swarm{action:"model"}` hot-swap on `[quota]` without stopping or leaking outside a restricted pool (including same-family cross-variant/effort fallbacks) |

> **Swarm UI Overview (`swarm_pane`) vs. Narrator (`swarm_narrator`)**: Gate on
> `<skills>`. When `swarm_pane` is in `<skills>`, load `swarm_pane` **before**
> adding/briefing the first workers and write
> `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` **once
> the workers are added** (`goal` in 4–8 words / <=12 max, `tasks`, and
> `threads` in 1–6 outcome groups; **never** put statuses, blockers, or asks in
> `plan.json`, and rewrite only when adding workers, moving work, or changing
> the goal). When `swarm_pane` is present, never add a `narrator` unless the
> user explicitly asks for one by name; if `swarm_pane` is absent from
> `<skills>` and `swarm_narrator` is in `<skills>`, `native_swarm` falls back
> to adding `narrator`.

## 3. File Ownership and Hook Signals (SSOT)

Default `PreToolUse` decisions in `/swarm` and `/run-workflow` must be
unattended-safe **`"deny"` + `@coordinator` escalation** (never `"ask"` /
`"force_ask"`, which deadlock or auto-deny unattended workers). Set
`SWARM_GUARD_INTERACTIVE=1` only for interactive single-session runs. Keep
every hook `<1–2s` (synchronous).

| Asset Class | Repo Signals | Recommended Ownership | Unattended-Safe Guardrail |
| :--- | :--- | :--- | :--- |
| **Independent Feature Modules** | `src/modules/*`, vertical slices | Dedicated author (`workspace:"share"`) | `PreToolUse` confines writes to `realpath(cwd)` (with `workspacePaths[0]` fallback) or `realpath(artifactDirectoryPath)` (for `swarm_pane` screenshots); blocks `../`, `$VAR`, symlink, & `/etc/*` escapes |
| **Central Manifests & Protected Modules** | `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock`, `uv.lock`, `src/auth/`, `src/billing/`, global router | Single integrator or `@coordinator`-approved edit | `PreToolUse` `"deny"` + `@coordinator` escalation on both write/edit tools **and** `run_command` mutations (opt-in `force_ask` with `SWARM_GUARD_INTERACTIVE=1`); toolchain lock blocks wrong package manager (e.g., `npm install`) |
| **Shared Contracts, Migrations & Codegen** | `src/types/*`, `openapi.*`, `proto/`, `generated/`, `migrations/` | Frozen before sprint; forward migrations only when authorized | `PreToolUse` `"deny"` on edits **and** `run_command` mutating bypasses (`sed -i`, redirections, `rm`/`mv`/`ln`) |
| **Secrets & Remote Git** | `.env`, `.env.*` (excluding `.env.example`/`.sample`/`.template`), `git push` | Never read secrets or push unless explicitly requested | `PreToolUse` `"deny"` on `.env` writes **and** reads (`read_file`/`view_file` including `AbsolutePath` + `run_command`, case-insensitive on macOS/Windows) and all `git ... push` command variants |
| **Shared Runtime Test Resources** | `docker-compose*`, local Postgres/Redis, fixed ports | Single `verifier` sequential runs (`workspace:"inherit"`) | `PreToolUse` `"deny"` on destructive DB resets (`dropdb`, `--force-reset`) |
| **Formatting & Startup Context** | `.prettierrc`, `ruff.toml`, `AGENTS.md`, `docs/system-map.md` | Automated per-file / per-session | `PostToolUse` (disabled-by-default single-file Prettier template scoped to Prettier extensions inside workspace, excluding `package-lock.json`, checking `Path`/`TargetFile`/`AbsolutePath`/`path`/`file_path`, falling back to `workspacePaths[0]` and local `node_modules/.bin/prettier`, `timeout=1.5`, outputs `{}`) + flat `SessionStart` (guards non-dict JSON, falls back to `workspacePaths[0]`, injects pointers only for existing `AGENTS.md` / `docs/system-map.md`). *Note: inline multiline `python3 -c '...'` hooks in `swarm-guardrails-hooks.json` require Unix `sh -c` (macOS/Linux); Windows `cmd /c` is not supported for inline multiline hooks.* |

> **Pre-Spawn Git Readiness, Validation & Teardown Lifecycle**:
> - **Pre-spawn**: Before spawning `share`/`branch` workers, validate staged guardrails (`agy plugin validate .agents/plugins/swarm-guardrails --strict` + hook stdin dry-runs), verify `git status --short` is clean (scaffold, repo-relative handoff artifacts, and `.agents/plugins/swarm-guardrails/` committed to `HEAD`), and check branch-vs-`main` divergence (`git rev-list --left-right --count main...HEAD`).
> - **Post-sprint teardown** (choose one—**never hand-edit `~/.gemini/config/config.json`**):
>   1. **Delete `.agents/plugins/swarm-guardrails/`** (and commit removal if tracked): cleanest for temporary sprint guardrails.
>   2. **In-repo config toggle**: Set `"disabled": true` in `.agents/plugins/swarm-guardrails/plugin.json` to disable the entire plugin (**never** use bare `"enabled": false` in `plugin.json`—unknown top-level fields are silently discarded by the plugin loader), or set `"enabled": false` on individual hook entries in `hooks.json` (which disables only those hooks while leaving `rules/AGENTS.md` active).
>   3. **Global CLI / UI toggle**: Run `agy plugin disable swarm-guardrails` (or disable in the Customizations UI)—note this writes a global override in `~/.gemini/config/config.json` keyed by plugin directory name (`swarm-guardrails`) that overrides `plugin.json` and disables `swarm-guardrails` across other repos until re-enabled via `agy plugin enable swarm-guardrails`.

## 4. Ready-to-Paste Launch Templates

> **Planner-Only Assembly Checklist (`Shared /swarm Invariants`)** — *for the
> pre-session planner only; never write `Follow Shared /swarm Invariants`
> inside an output prompt (a fresh `/swarm` session has not read this file)*:
> - **`swarm_pane` / `plan.json` / `Screenshot:`**: Gate `swarm_pane` on `<skills>` (`swarm_narrator` fallback only when `swarm_pane` is absent and `swarm_narrator` is in `<skills>`). Load `swarm_pane` before adding/briefing workers; write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` **once workers are added** (`goal` <=12 words, `tasks`, 1–6 outcome `threads`; no statuses, blockers, or asks; rewrite only on roster/work/goal changes). Gate `Screenshot: <abs-path> | <caption <=10 words>` on visual UI work only: own-line worker board post (coordinator/narrator/monitor posts are ignored), `.png`/`.jpg`/`.jpeg`/`.webp` under worker's `<appData>/brain/<conversation id>/`, full-window on same screen/size/theme, no crops or diffs.
> - **`swarm_monitor` (`monitor`)**: Standard in `native_swarm` whenever `swarm_monitor` is in `<skills>` (inherits coordinator model; explicit stall-monitor brief; only `monitor` loads `swarm_monitor`). Coordinator never assigns work to, replies to, or kills `monitor`, posts `@monitor resume` after a server restart, and posts a standalone `[done] <summary>` (no `@` mentions) when finished so `monitor` kills its daemon cron.
> - **Board, Handoffs & Merge-Before-`kill` Landing**: Single-board `main` (`channel` only if live `swarm` exposes `action:"channel"` and >8 workers / 2+ areas); `<author> <-> verifier` peer `@mention` handoffs (no `@coordinator` CC, 2–3 retry circuit-breaker); commit in each `share` worktree and merge sequentially into the main working copy **before calling `swarm{action:"kill"}` on any `share`/`branch` author** (`kill` permanently deletes its workspace). Never push unless requested.

### Template A: Canonical `/swarm` Launch Prompt (Feature / Fix / UI Sprint)
```text
/swarm
Goal: Implement <feature/fix scope>. Done when `<test/build commands>` pass.

Project context & pre-spawn checks: Read `<AGENTS.md / docs/system-map.md>` first. Verify clean `git status --short` (with `.agents/plugins/swarm-guardrails/` committed if used) and branch-vs-`main` divergence before spawning `share`/`branch` workers.

Swarm UI Overview & Monitor: If `swarm_pane` is in `<skills>`, load `swarm_pane` before adding/briefing workers and write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` once workers are added (`goal` <=12 words, `tasks`, 1–6 outcome `threads`; never put statuses, blockers, or asks in `plan.json`, and rewrite only when adding workers, moving work, or changing the goal; never add `narrator` unless requested by name, or if `swarm_pane` is absent and `swarm_narrator` is in `<skills>`). <If visual UI work: workers save full-window .png/.jpg/.jpeg/.webp screenshots (same screen, window size, and theme; no crops or diffs) under their own `<appData>/brain/<conversation id>/` directory and post `Screenshot: <abs-path> | <caption <=10 words>` on its own line in a worker board post.> If `swarm_monitor` is in `<skills>`, add `monitor` (inheriting coordinator model) with an explicit stall-monitor brief (only `monitor` loads `swarm_monitor`; coordinator never assigns work to, replies to, or kills `monitor`, posts `@monitor resume` after a server restart, and posts a standalone `[done] <summary>` with no `@` mentions when finished so `monitor` stops its daemon cron).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family or distinct-variant/higher-effort model id>` (`inherit`, read-only review + integration tests)
- Quota fallback (within approved pool): On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (never leaving a user-restricted pool) and report the switch.

Workspace, Handoffs & Landing Rules:
- Authors use `workspace:"share"`; `verifier` uses `inherit` and never edits feature code directly.
- Board: single-board `main` (create `channel`s only if live `swarm` exposes `action:"channel"` and >8 workers / 2+ independent areas).
- Do not edit `<central shared files / lockfiles / no-touch paths>` without `@coordinator` sign-off.
- Peer handoffs: `<author> <-> verifier` directly via `@mention` (no `@coordinator` CC); max 2–3 retry bounces per issue before escalating to `@coordinator`.
- Landing & teardown: Commit in each `share` worktree; merge sequentially (`<core-author>` -> `<slice-author-1>` -> ...) after `verifier` sign-off **before `kill`ing any `share`/`branch` author** (`kill` permanently deletes its workspace), then run `<test/build commands>`. Never push. Post standalone `[done] <summary>` (no `@` mentions) and tear down temporary guardrails (delete `.agents/plugins/swarm-guardrails/`, set `"disabled": true` in `plugin.json`, set per-hook `"enabled": false` in `hooks.json`, or run `agy plugin disable swarm-guardrails`).
```

### Template B: `/run-workflow` Deterministic Blueprint (Audits / Scans / Mechanical Transforms / Phase 1)
```text
/run-workflow
Goal: <Scan/map/audit/transform N targets> and aggregate results into `<output-path>`.

Rules:
- Pass coarse model tiers only (`model="inherit"|"flash_lite"|"flash"|"pro"` — never exact `/swarm` IDs) and a valid JSON `schema` on every `agent()`. Prefer writing non-trivial scripts to `<appData>/brain/<id>/scratch/workflow.py` and invoking `run_workflow(ScriptPath=..., Description=..., Args=..., Cwd=...)` for easy line-level fixes and reruns.
- Read-only discovery/audit `agent(...)` calls MUST pass `type_name="research"` (or a non-plan-gated custom agent if `research` is absent—never default `type_name="self"`, which inherits plan gating and deadlocks on `[plan review due]`) and `workspace="inherit"`. For parallel mechanical code-editing transforms, use `workspace="branch"` or `"share"` with an edit-capable `type_name` (`"self"` or custom coder).
- Choose the lightest primitive per stage: `call_tool(name, **args)` + `WaitMsBeforeAsync` (<=10000 ms, catching `ToolError` and checking `e.denied`) for zero-LLM deterministic tool fan-outs; `await trajectory(tools=[...], last=...)` to mine prior conversation steps; `parallel(items, fn)` for concurrent fail-fast fan-out (one failure cancels the rest); `pipeline(items, fn)` for sequential ordered stages; or stateful `a = agent(...)` -> `await a(prompt, schema)` -> `del a` for bounded multi-turn review/fix loops.

Staged Design:
1. `phase("Discover")`: Single `agent(..., type_name="research", workspace="inherit", role="Discover targets", model="flash_lite", schema={"type": "array", "items": {"type": "string"}})` (or `call_tool` scan) lists target modules/files.
2. `phase("Analyze")`: `parallel(targets, lambda t: agent(..., type_name="research", workspace="inherit", role=f"Analyze {t}", model="flash", schema={"type": "object", "properties": {"path": {"type": "string"}, "entry_points": {"type": "array", "items": {"type": "string"}}, "deps": {"type": "array", "items": {"type": "string"}}, "risks": {"type": "array", "items": {"type": "string"}}}, "required": ["path", "entry_points", "deps", "risks"]}))` (use `pipeline(targets, ...)` when stages must run sequentially).
3. Aggregate deterministically in Python, verify schema completeness, and write `<output-path>` cleanly.
```

### Template C: Legacy Takeover `/swarm` Mode Deltas (Substitute into Template A)

Use Template A's `/swarm` structure (`Project context & pre-spawn checks`,
`Swarm UI Overview & Monitor`, `Quota fallback`, `Board`, and `Peer handoffs`
blocks unchanged) and substitute the mode-specific `Goal`, `Roles`, and
`Landing` lines below:

- **Interactive Cartography Mode (`workspace:"inherit"`, read-only)**:
  - `Goal`: Map `<legacy repo/modules>` into `docs/system-map.md` with verified `file:line` evidence (strictly read-only investigators).
  - `Roles`: `<investigator-1..k>` (optional roles: `infra-runner`, `entry-tracer`, `data-modeler`, `hotspot-auditor`) + `verifier`, all running `workspace:"inherit"` and read-only.
  - `Compilation & Teardown`: Investigators cite `#seq` when cross-referencing; **Coordinator (or one named writer)** compiles accepted `#seq` summaries into `docs/system-map.md`. `kill` read-only `inherit` investigators once their `#seq` summary is accepted (unless `fork`ing). Post standalone `[done] <summary>` (no `@` mentions) when finished.
- **Characterization Test Mode (`workspace:"share"` authors + sequential `verifier`)**:
  - `Goal`: Write characterization tests for `<modules>` locking existing behavior without altering production logic or weakening assertions. Done when `<test commands>` pass.
  - `Roles`: `<tester-1..k>` (`workspace:"share"`, sharded via `tasks`) + 1 cross-family (or distinct-variant/higher-effort) `verifier` (`workspace:"inherit"`, flags over-mocked stubs and runs shared-DB/port integration tests sequentially).
  - `Landing`: Commit test additions in each `share` worktree and merge sequentially (`<tester-1>` -> `<tester-2>` -> ...) after `verifier` sign-off **before `kill`ing any `share` tester** (`kill` deletes its workspace). Never push. Post standalone `[done] <summary>` (no `@` mentions) when finished.

### Template D: Hybrid Two-Session Handoff (Phase 1 `/run-workflow` -> Checkpoint -> Phase 2 `/swarm`)

#### Prompt 1: Phase 1 Read-Only Discovery (`/run-workflow`, Session 1)
```text
/run-workflow
Goal: Inventory `<target modules/files>` and write a structured handoff artifact at `<committed repo path e.g. docs/system-map.md OR absolute <appData>/brain/<phase1-id>/scratch/plan-manifest.json>`.

Apply Template B `/run-workflow` rules (`type_name="research"` or non-plan-gated custom agent, `workspace="inherit"`, `role="..."`, coarse tiers `"inherit"|"flash_lite"|"flash"|"pro"` only, fail-fast `parallel()` / sequential `pipeline()`, optional `call_tool()` with `WaitMsBeforeAsync` + `ToolError.denied` handling, and `ScriptPath` in scratch for iterative reruns):
1. `phase("Discover")`: `agent(..., type_name="research", workspace="inherit", role="Discover targets", model="flash_lite", schema={"type": "array", "items": {"type": "string"}})`.
2. `phase("Map")`: `parallel(targets, lambda t: agent(..., type_name="research", workspace="inherit", role=f"Map {t}", model="flash", schema={"type": "object", "properties": {"path": {"type": "string"}, "public_api": {"type": "array", "items": {"type": "string"}}, "deps": {"type": "array", "items": {"type": "string"}}, "test_cmd": {"type": "string"}, "risks": {"type": "array", "items": {"type": "string"}}}, "required": ["path", "public_api", "deps", "test_cmd", "risks"]}))`.
3. Write `<handoff-artifact-path>` deterministically (read-only on production code) and stop for human review.
```

> **Inter-Phase Human & Git Checkpoint (Before Launching Phase 2)**:
> 1. Review `<handoff-artifact-path>`. If repo-relative (e.g., `docs/system-map.md`), commit it (along with `.agents/plugins/swarm-guardrails/` if used) so `git status --short` is clean; if kept in Phase 1 scratch, copy its **exact absolute path** (`<appData>/brain/<phase1-id>/scratch/plan-manifest.json`) into Prompt 2—never pass a bare relative `scratch/...` path across sessions.
> 2. Open a **fresh conversation session** and paste Prompt 2 below.

#### Prompt 2: Phase 2 Collaborative Implementation (`/swarm`, Fresh Session 2)
```text
/swarm
Goal: Implement `<scope>` using the verified findings in `<committed repo path e.g. docs/system-map.md OR absolute <appData>/brain/<phase1-id>/scratch/plan-manifest.json>`. Done when `<test/build commands>` pass.

Project context & pre-spawn checks: Every worker reads `<handoff-artifact-path>` (and `<AGENTS.md>` if present) first—do not re-discover the whole repo. Verify clean `git status --short` (committed repo handoff artifact + optional `.agents/plugins/swarm-guardrails/`) and branch-vs-`main` divergence before spawning `share`/`branch` workers.

Swarm UI Overview & Monitor: If `swarm_pane` is in `<skills>`, load `swarm_pane` before adding/briefing workers and write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` once workers are added (`goal` <=12 words, `tasks`, 1–6 outcome `threads`; never put statuses, blockers, or asks in `plan.json`, and rewrite only on roster/work/goal changes; never add `narrator` unless requested by name, or if `swarm_pane` is absent and `swarm_narrator` is in `<skills>`). <If visual UI work: workers save full-window .png/.jpg/.jpeg/.webp screenshots (same screen, window size, and theme; no crops or diffs) under their own `<appData>/brain/<conversation id>/` directory and post `Screenshot: <abs-path> | <caption <=10 words>` on its own line in a worker board post.> If `swarm_monitor` is in `<skills>`, add `monitor` (inheriting coordinator model) with an explicit stall-monitor brief (only `monitor` loads `swarm_monitor`; coordinator never assigns work to, replies to, or kills `monitor`, posts `@monitor resume` after a server restart, and posts a standalone `[done] <summary>` with no `@` mentions when finished so `monitor` stops its daemon cron).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family or distinct-variant/higher-effort model id>` (`inherit`, read-only review + integration tests)
- Quota fallback (within approved pool): On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (never leaving a user-restricted pool) and report the switch.

Workspace, Handoffs & Landing Rules:
- Authors use `workspace:"share"`; `verifier` uses `inherit` and never edits feature code directly.
- Board: single-board `main` (create `channel`s only if live `swarm` exposes `action:"channel"` and >8 workers / 2+ independent areas).
- Do not edit `<central shared files / lockfiles / no-touch paths>` without `@coordinator` sign-off.
- Peer handoffs: `<author> <-> verifier` directly via `@mention` (no `@coordinator` CC); max 2–3 retry bounces per issue before escalating to `@coordinator`.
- Landing & teardown: Commit in each `share` worktree; merge sequentially (`<core-author>` -> `<slice-author-1>` -> ...) after `verifier` sign-off **before `kill`ing any `share`/`branch` author** (`kill` permanently deletes its workspace), then run `<test/build commands>`. Never push. Post standalone `[done] <summary>` (no `@` mentions) and tear down temporary guardrails (delete `.agents/plugins/swarm-guardrails/`, set `"disabled": true` in `plugin.json`, set per-hook `"enabled": false` in `hooks.json`, or run `agy plugin disable swarm-guardrails`).
```
