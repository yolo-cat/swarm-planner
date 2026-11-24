# Task Configuration Matrices & Launch Templates (SSOT)

This file is the **Single Source of Truth (SSOT)** for orchestration routing,
role-to-model allocation, file ownership & hook signals, and ready-to-paste
launch templates.

## 1. Orchestration Router & Scenario Matrix

| Scenario | Recommended Engine | Pre-Launch Prerequisite | Workspace / Features | Verification / Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Small / Sequential Edit** | **Single Session** or `/plan` *(Step 0 fast-exit)* | None (skip `/swarm`) | Default workspace | Direct edits + unit test |
| **Massive Audit / Pattern Scan** | **`/run-workflow`** | Define target list & valid JSON `schema` | `inherit`, `type_name="research"`, `parallel()` + `flash`/`flash_lite` | Deterministic Python aggregation |
| **Legacy Cartography (Phase 1)** | **`/run-workflow`** *(or `/swarm` if interactive cross-talk/`fork` needed)* | Forbid code edits; list top modules; designate writer for `docs/system-map.md` | `inherit` (`type_name="research"` in `/run-workflow`); compile to `docs/system-map.md` | Verified `file:line` evidence |
| **Legacy Characterization Tests** | **`/swarm`** | Clean `git status` + branch-vs-`main` check; lock prod code & assertions; add migration/DB hooks | Authors `share`, Verifier `inherit`, `tasks` | Real behavior vs. over-mocking; single-verifier DB runs |
| **Greenfield MVP Sprint** | **`/swarm`** | Clean `git status` + branch-vs-`main` check; scaffold + shared contracts + baseline build green | Authors `share`, Verifier `inherit`; `channel` *only if live `swarm` exposes `action:"channel"`* (else single-board `main`) | Contract conformance, zero duplicate helpers |
| **Large Refactor / Migration** | **`/swarm`** *(or `/run-workflow` for mechanical per-file transforms)* | Clean `git status` + branch-vs-`main` check; lock invariants & public signatures | Migrators `share`, Verifier `inherit`, `tasks` | Full build + regression suite |
| **Multi-Role Code Audit** | **`/swarm`** *(cross-model review)* or **`/run-workflow`** *(checklist sweep)* | Define diff target (e.g., vs. `main`) | All `inherit` (`type_name="research"` in `/run-workflow`); `#seq` citations | Severity-ranked findings; optional `share` fixes |
| **UI / Visual Polish** | **`/swarm`** | Clean `git status` + branch-vs-`main` check; specify target viewports & design tokens | Frontend `share`, Verifier `inherit`, `swarm_pane` | `plan.json` + `Screenshot:` milestones; light/dark & responsive |
| **Discovery -> Implementation** | **Hybrid** (Phase 1 `/run-workflow` -> Phase 2 `/swarm`) | Define Phase 1 artifact path & JSON `schema`; clean `git status` before Phase 2 | Phase 1 `inherit` (`type_name="research"`); Phase 2 `share` + `inherit` | Checkpoint Phase 1 artifact before spawning Phase 2 |

## 2. Heterogeneous Role-Model Strategy (`/swarm`)

> **Engine Model Contract**:
> - **`/run-workflow`** uses coarse model tiers only: `model="inherit"|"flash_lite"|"flash"|"pro"`. Never pass exact `/swarm` catalog IDs into `run_workflow`, and never pass coarse tiers to `model_matrix.py --validate`.
> - **`/swarm`** (and Hybrid Phase 2) uses exact catalog IDs (including `low`/`medium`/`high`/`xhigh`/`max` effort suffixes) verified by `model_matrix.py --validate`. Never use coarse aliases.

Resolve `<skill-dir>` from the `swarm-planner` `SKILL.md` path in `<skills>`
(global default `~/.gemini/config/skills/swarm-planner`). If
`<cwd>/skills/swarm-planner/` exists (dogfooding or editing this repo), verify
`<skill-dir>` matches repo source (`./scripts/install.sh --status` or
`diff -rq`/symlink) before relying on installed scripts or templates. Run
[model_matrix.py](../scripts/model_matrix.py) in Step 1 (`--from-swarm-json -`
preferred; `--from-agy` checks existence only with `quota=unknown`), obtain
explicit user sign-off in Steps 3–4, and validate chosen `/swarm` IDs in Step 5
with `--validate <comma-separated-ids> --require-quota` (adding
`--allowed-pool <comma-separated-ids>`—accepting exact IDs, display names, or
`family_key` wildcards—when pool-restricted, and optional `--require-diverse`
to enforce `cross-vendor` or `single-vendor cross-variant` coverage).

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
| **Monitor** *(optional)* | Inherits coordinator's model by default | Add **only** if `swarm_monitor` is in `<skills>`; brief must explicitly state it is the stall monitor (only `monitor` loads `swarm_monitor`—coordinators and other workers never load it) |
| **Quota Fallback Chain** | 1–2 pre-approved backup IDs per tier **within the user's approved pool** | Lets Coordinator `swarm{action:"model"}` hot-swap on `[quota]` without stopping or leaking outside a restricted pool (including same-family cross-variant/effort fallbacks) |

> **Swarm UI Overview (`swarm_pane`) vs. Narrator**: Load `swarm_pane`
> **before** briefing/adding the first workers and write `plan.json` for
> **all** `/swarm` sessions (gating only `Screenshot:` lines on visual UI work).
> Do **not** allocate a `Narrator` role unless the user explicitly asks for it
> by name.

## 3. File Ownership and Hook Signals (SSOT)

Default `PreToolUse` decisions in `/swarm` and `/run-workflow` must be
unattended-safe **`"deny"` + `@coordinator` escalation** (never `"ask"` /
`"force_ask"`, which deadlock or auto-deny unattended workers). Set
`SWARM_GUARD_INTERACTIVE=1` only for interactive single-session runs. Keep
every hook `<1–2s` (synchronous).

| Asset Class | Repo Signals | Recommended Ownership | Unattended-Safe Guardrail |
| :--- | :--- | :--- | :--- |
| **Independent Feature Modules** | `src/modules/*`, vertical slices | Dedicated author (`workspace:"share"`) | `PreToolUse` confines writes to `realpath(cwd)` or `realpath(artifactDirectoryPath)` (for `swarm_pane` screenshots); blocks `../`, `$VAR`, symlink, & `/etc/*` escapes |
| **Central Manifests & Protected Modules** | `package.json`, `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock`, `uv.lock`, `src/auth/`, `src/billing/`, global router | Single integrator or `@coordinator`-approved edit | `PreToolUse` `"deny"` + `@coordinator` escalation on both write/edit tools **and** `run_command` mutations (opt-in `force_ask` with `SWARM_GUARD_INTERACTIVE=1`); toolchain lock blocks wrong package manager (e.g., `npm install`) |
| **Shared Contracts, Migrations & Codegen** | `src/types/*`, `openapi.*`, `proto/`, `generated/`, `migrations/` | Frozen before sprint; forward migrations only when authorized | `PreToolUse` `"deny"` on edits **and** `run_command` mutating bypasses (`sed -i`, redirections, `rm`/`mv`/`ln`) |
| **Secrets & Remote Git** | `.env`, `.env.*` (excluding `.env.example`/`.sample`/`.template`), `git push` | Never read secrets or push unless explicitly requested | `PreToolUse` `"deny"` on `.env` writes **and** reads (`read_file`/`view_file` + `run_command`, case-insensitive on macOS/Windows) and all `git ... push` command variants |
| **Shared Runtime Test Resources** | `docker-compose*`, local Postgres/Redis, fixed ports | Single `verifier` sequential runs (`workspace:"inherit"`) | `PreToolUse` `"deny"` on destructive DB resets (`dropdb`, `--force-reset`) |
| **Formatting & Startup Context** | `.prettierrc`, `ruff.toml`, `AGENTS.md`, `docs/system-map.md` | Automated per-file / per-session | `PostToolUse` (disabled-by-default single-file Prettier template scoped to Prettier extensions inside `cwd`, excluding `package-lock.json`, with `timeout=1.5`, outputs `{}`) + flat `SessionStart` (injects pointers only for existing `AGENTS.md` / `docs/system-map.md`) |

> **Pre-Spawn Git Readiness & Teardown Lifecycle**: Before spawning
> `share`/`branch` workers, verify `git status --short` is clean (scaffold and
> optional `.agents/plugins/swarm-guardrails/`—including
> `./hooks/pretool-guard.py`—committed to `HEAD`) and check branch-vs-`main`
> divergence (`git rev-list --left-right --count main...HEAD`) so worktrees do
> not fork from stale or dirty state. Disable or remove temporary guardrails
> after sprint teardown (`agy plugin disable swarm-guardrails`, `"enabled": false`,
> or delete `.agents/plugins/swarm-guardrails/`).

## 4. Ready-to-Paste Launch Templates

> **Shared `/swarm` Invariants** *(referenced by Templates A, C, and D Phase 2)*:
> - **Swarm UI Overview (`swarm_pane`)**: Coordinator loads `swarm_pane` **before** briefing/adding the first workers and writes `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` (outcome-grouped `threads`) for **all** `/swarm` sessions. Gate `Screenshot: <abs-path> | <caption <=10 words>` (saved under each worker's own `<appData>/brain/<conversation id>/`) on visual UI work only. Do **not** add a `narrator` unless explicitly requested by name.
> - **Optional `monitor` (`swarm_monitor`)**: Add only if `swarm_monitor` is in `<skills>` (inherits coordinator's model); explicitly state in its brief that it is the stall monitor (only `monitor` loads `swarm_monitor`; coordinators and other workers never load it).
> - **Board**: Use single-board `main` (create `channel`s only if live `swarm` exposes `action:"channel"` and >8 workers / 2+ independent areas).
> - **Pre-spawn & Teardown**: Verify clean `git status --short`, check branch-vs-`main` divergence, and commit/register `.agents/plugins/swarm-guardrails/` (if used) before spawning `share`/`branch` workers; disable/remove temporary guardrails after sprint teardown.
> - **Peer Handoffs**: `<author> <-> verifier` directly via `@mention` (no `@coordinator` CC); max 2–3 failed bounce cycles on the same issue before escalating to `@coordinator`.
> - **Landing**: Commit in each `share` worktree; after `verifier` approves all slices, merge into the main working copy in deterministic sequential order and run final test/build commands. **Never push**.

### Template A: `/swarm` Feature / Fix Sprint
```text
/swarm
Goal: Implement <feature/fix scope>. Done when `<test/build commands>` pass.

Project context & guardrails: Read `<AGENTS.md / docs/system-map.md>` first. Follow Shared `/swarm` Invariants (load `swarm_pane` pre-brief -> write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json`; <if UI work: require `Screenshot: <abs-path> | <caption <=10 words>` from each worker's `<appData>/brain/<conversation id>/`>; optional `monitor` with explicit stall-monitor brief only if `swarm_monitor` is in `<skills>`, never `narrator`; pre-spawn clean git + guardrail commit & post-sprint teardown).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family or distinct-variant/higher-effort model id>` (`inherit`, read-only review + integration tests)
- Quota fallback (within approved pool): On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (never leaving a user-restricted pool) and report the switch.

Workspace & Landing Rules:
- Authors use `workspace:"share"`; `verifier` uses `inherit` and never edits feature code directly.
- Board: single-board `main` (channels only if live `swarm` exposes `action:"channel"`).
- Do not edit `<central shared files / lockfiles / no-touch paths>` without `@coordinator` sign-off.
- Peer handoffs: `<author> <-> verifier` via `@mention` (no `@coordinator` CC); max 2–3 retry bounces per issue before escalating to `@coordinator`.
- Landing: Commit in each `share` worktree; merge sequentially (`<core-author>` -> `<slice-author-1>` -> ...) after `verifier` sign-off, then run `<test/build commands>`. Never push.
```

### Template B: `/run-workflow` Deterministic Blueprint (Audits / Scans / Phase 1)
```text
/run-workflow
Goal: <Scan/map/audit N targets> and aggregate results into `<output-path>`.

Rules:
- Read-only `agent(...)` calls MUST pass `type_name="research"`, `workspace="inherit"`, `role="..."`, and coarse model tiers (`"inherit"`, `"flash_lite"`, `"flash"`, `"pro"` — never exact `/swarm` IDs). Never leave default `type_name="self"` on read-only passes (inherits two-phase plan/execute gating and deadlocks on `[plan review due]`).
- Note: `parallel()` is fail-fast (if one agent fails, the rest are cancelled).

Staged Design:
1. `phase("Discover")`: Single `agent(..., type_name="research", workspace="inherit", role="Discover targets", model="flash_lite", schema={"type": "array", "items": {"type": "string"}})` lists target modules/files.
2. `phase("Analyze")`: `parallel(targets, lambda t: agent(..., type_name="research", workspace="inherit", role=f"Analyze {t}", model="flash", schema={"type": "object", "properties": {"path": {"type": "string"}, "entry_points": {"type": "array", "items": {"type": "string"}}, "deps": {"type": "array", "items": {"type": "string"}}, "risks": {"type": "array", "items": {"type": "string"}}}, "required": ["path", "entry_points", "deps", "risks"]}))`.
3. Aggregate deterministically in Python, verify schema completeness, and write `<output-path>` cleanly (read-only on production code).
```

### Template C: Legacy Takeover (`/swarm` Interactive Cartography or Characterization)
```text
/swarm
Goal: <Map this legacy repo into `docs/system-map.md` with verified `file:line` evidence (read-only investigators) | OR | Write characterization tests for `<modules>` without altering production logic>.

Project context & guardrails: Read `<AGENTS.md / docs/system-map.md>` first. Follow Shared `/swarm` Invariants (load `swarm_pane` pre-brief -> write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json`; optional `monitor` with explicit stall-monitor brief only if `swarm_monitor` is in `<skills>`, never `narrator`; single-board `main` unless live `swarm` exposes `action:"channel"`; pre-spawn clean git + guardrail commit & post-sprint teardown).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<investigator-or-tester-1..k>`: `<exact model ids>` (owns `<assigned modules/test paths>`; optional cartography roles: `infra-runner`, `entry-tracer`, `data-modeler`, `hotspot-auditor`)
- `verifier`: `<exact cross-family or distinct-variant/higher-effort model id>` (`inherit`, read-only audit + sequential integration/DB runs)
- Quota fallback (within approved pool): On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (never leaving a user-restricted pool) and report the switch.

Mode Rules:
- Cartography mode: Investigators and `verifier` run `workspace:"inherit"` and are strictly read-only; cite `#seq` when cross-referencing. **Coordinator (or one named writer)** compiles accepted `#seq` summaries into `docs/system-map.md`. `kill` investigators once their `#seq` summary is accepted (unless `fork`ing).
- Characterization mode: Authors use `workspace:"share"`, `verifier` uses `inherit` and runs shared-DB/port integration tests sequentially.
- Peer handoffs: `<author> <-> verifier` via `@mention` (no `@coordinator` CC); max 2–3 retry bounces per issue before escalating to `@coordinator`.
- Landing (if editing tests): Commit in each `share` worktree and merge sequentially (`<tester-1>` -> `<tester-2>` -> ...) after `verifier` sign-off. Never push.
```

### Template D: Hybrid Handoff (Phase 1 `/run-workflow` -> Phase 2 `/swarm`)
```text
# Phase 1: Deterministic Read-Only Discovery (`/run-workflow`)
# Follow Template B rules (`type_name="research"`, `workspace="inherit"`, `role="..."`, coarse tiers only, fail-fast `parallel()`):
/run-workflow
Goal: Inventory `<target modules/files>` and write a structured handoff artifact at `<docs/system-map.md or scratch/plan-manifest.json>`.
1. `phase("Discover")`: `agent(..., type_name="research", workspace="inherit", role="Discover targets", model="flash_lite", schema={"type": "array", "items": {"type": "string"}})`.
2. `phase("Map")`: `parallel(targets, lambda t: agent(..., type_name="research", workspace="inherit", role=f"Map {t}", model="flash", schema={"type": "object", "properties": {"path": {"type": "string"}, "public_api": {"type": "array", "items": {"type": "string"}}, "deps": {"type": "array", "items": {"type": "string"}}, "test_cmd": {"type": "string"}, "risks": {"type": "array", "items": {"type": "string"}}}, "required": ["path", "public_api", "deps", "test_cmd", "risks"]}))`.
3. Write `<handoff-artifact-path>` deterministically and stop for human/coordinator review.

# --- Review `<handoff-artifact-path>`, verify clean git + commit guardrails if used, then launch Phase 2 ---

# Phase 2: Collaborative Implementation (`/swarm`)
/swarm
Goal: Implement `<scope>` using the verified findings in `<handoff-artifact-path>`. Done when `<test/build commands>` pass.

Project context & guardrails: Every worker reads `<handoff-artifact-path>` (and `<AGENTS.md>` if present) first—do not re-discover the whole repo. Follow Shared `/swarm` Invariants (load `swarm_pane` pre-brief -> write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json`; <if UI work: `Screenshot: <abs-path> | <caption <=10 words>`>; optional `monitor` with explicit stall-monitor brief only if `swarm_monitor` is in `<skills>`, never `narrator`; single-board `main` unless live `swarm` exposes `action:"channel"`; post-sprint guardrail teardown).

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family or distinct-variant/higher-effort model id>` (`inherit`, read-only review + integration tests)
- Quota fallback (within approved pool): On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (never leaving a user-restricted pool) and report the switch.

Workspace & Landing Rules:
- Authors use `workspace:"share"`; `verifier` uses `inherit`.
- Peer handoffs: `<author> <-> verifier` directly via `@mention` (no `@coordinator` CC); max 2–3 retry bounces per issue before escalating to `@coordinator`.
- Landing: Commit in each `share` worktree and merge sequentially (`<core-author>` -> `<slice-author-1>` -> ...) after `verifier` sign-off, then run final verification. Never push.
```
