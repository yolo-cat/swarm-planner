# Task Configuration Matrices & Launch Templates (SSOT)

This file is the **Single Source of Truth (SSOT)** for orchestration routing,
role-to-model allocation, file ownership & hook signals, and ready-to-paste
launch templates.

## 1. Orchestration Router & Scenario Matrix

| Scenario | Recommended Engine | Pre-Launch Prerequisite | Workspace / Features | Verification / Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Small / Sequential Edit** | **Single Session** or `/plan` *(Step 0 fast-exit)* | None (skip `/swarm`) | Default workspace | Direct edits + unit test |
| **Massive Audit / Pattern Scan** | **`/run-workflow`** | Define target list & JSON `schema` | `inherit`, `parallel()` + `flash`/`flash_lite` | Deterministic Python aggregation |
| **Legacy Cartography (Phase 1)** | **`/run-workflow`** *(or `/swarm` if interactive cross-talk/`fork` needed)* | Forbid code edits; list top modules | `inherit`; compile to `docs/system-map.md` | Verified `file:line` evidence |
| **Legacy Characterization Tests** | **`/swarm`** | Lock prod code & assertions; add migration/DB hooks | Authors `share`, Verifier `inherit`, `tasks` | Real behavior vs. over-mocking; single-verifier DB runs |
| **Greenfield MVP Sprint** | **`/swarm`** | Scaffold + shared contracts + baseline build green | Authors `share`, Verifier `inherit`; `channel` *only if live `swarm` exposes `action:"channel"`* (else single-board `main`) | Contract conformance, zero duplicate helpers |
| **Large Refactor / Migration** | **`/swarm`** *(or `/run-workflow` for mechanical per-file transforms)* | Lock invariants & public signatures | Migrators `share`, Verifier `inherit`, `tasks` | Full build + regression suite |
| **Multi-Role Code Audit** | **`/swarm`** *(cross-model review)* or **`/run-workflow`** *(checklist sweep)* | Define diff target (e.g., vs. `main`) | All `inherit`; `#seq` citations | Severity-ranked findings; optional `share` fixes |
| **UI / Visual Polish** | **`/swarm`** | Specify target viewports & design tokens | Frontend `share`, Verifier `inherit`, `swarm_pane` | `plan.json` + `Screenshot:` milestones; light/dark & responsive |
| **Discovery -> Implementation** | **Hybrid** (Phase 1 `/run-workflow` -> Phase 2 `/swarm`) | Define Phase 1 artifact path & schema | Phase 1 `inherit`; Phase 2 `share` + `inherit` | Checkpoint Phase 1 artifact before spawning Phase 2 |

## 2. Heterogeneous Role-Model Strategy (`/swarm`)

Resolve `<skill-dir>` from the `swarm-planner` `SKILL.md` path in `<skills>`
(global default `~/.gemini/config/skills/swarm-planner`), run
[model_matrix.py](../scripts/model_matrix.py) in Step 1 (`--from-swarm-json -`
preferred; `--from-agy` checks existence only with `quota=unknown`), and obtain
explicit user sign-off in Steps 3–4.

Per `native_swarm` rules, coordinators never switch models on their own
initiative **except** when the user explicitly requests it **or** a member hits
`[quota]`/capacity exhaustion (switching to the coordinator's model or the
user's pre-approved fallback chain).

| Role | Selection Principle | Rationale |
| :--- | :--- | :--- |
| **Coordinator** | High instruction-following / orchestrator variant | Tracks `#seq` references, handoffs, and merge order cleanly |
| **Core / Complex Author** | High/XHigh reasoning flagship model | Protects concurrency, state machines, and shared contracts |
| **Routine Slice Author** | Fast, high-quota model (`low`/`medium` or Flash tier) | Maximizes parallel throughput on CRUD, UI slices, and boilerplate |
| **Verifier** | **Cross-family strong analytical model** | Independent "second pair of eyes" catches single-model blind spots |
| **Monitor** *(optional)* | Inherits coordinator's model by default | Add **only** if `swarm_monitor` is in `<skills>`; detects board stalls without inventing work |
| **Quota Fallback Chain** | 1–2 pre-approved backup IDs per tier | Lets Coordinator `swarm{action:"model"}` hot-swap on `[quota]` without stopping |

> **Swarm UI Overview (`swarm_pane`) vs. Narrator**: Do **not** allocate a
> `Narrator` role by default. `swarm_pane` (`plan.json` + `Screenshot:` lines)
> replaces it as the default Swarm UI Overview. Add a `Narrator` **only** if
> the user explicitly asks for it by name.

## 3. File Ownership and Hook Signals (SSOT)

Default `PreToolUse` decisions in `/swarm` and `/run-workflow` must be
unattended-safe **`"deny"` + `@coordinator` escalation** (never `"ask"` /
`"force_ask"`, which deadlock or auto-deny unattended workers). Set
`SWARM_GUARD_INTERACTIVE=1` only for interactive single-session runs. Keep
every hook `<1–2s` (synchronous).

| Asset Class | Repo Signals | Recommended Ownership | Unattended-Safe Guardrail |
| :--- | :--- | :--- | :--- |
| **Independent Feature Modules** | `src/modules/*`, vertical slices | Dedicated author (`workspace:"share"`) | `PreToolUse` confines writes to `realpath(cwd)` or `realpath(artifactDirectoryPath)` (for `swarm_pane` screenshots); blocks `../` & `/etc/*` escapes |
| **Central Manifests & Registries** | `package.json`, `pnpm-lock.yaml`, `uv.lock`, global router | Single integrator or `@coordinator`-approved edit | `PreToolUse` `"deny"` + `@coordinator` escalation (opt-in `force_ask` with `SWARM_GUARD_INTERACTIVE=1`); toolchain lock blocks wrong package manager (e.g., `npm install`) |
| **Shared Contracts, Migrations & Codegen** | `src/types/*`, `openapi.*`, `proto/`, `generated/`, `migrations/` | Frozen before sprint; forward migrations only when authorized | `PreToolUse` `"deny"` on edits **and** `run_command` mutating bypasses (`sed -i`, redirections, `rm`/`mv`) |
| **Secrets & Remote Git** | `.env`, `.env.*` (excluding `.env.example`/`.sample`/`.template`), `git push` | Never read secrets or push unless explicitly requested | `PreToolUse` `"deny"` on `.env` writes/reads and all `git ... push` command variants |
| **Shared Runtime Test Resources** | `docker-compose*`, local Postgres/Redis, fixed ports | Single `verifier` sequential runs (`workspace:"inherit"`) | `PreToolUse` `"deny"` on destructive DB resets (`dropdb`, `--force-reset`) |
| **Formatting & Startup Context** | `.prettierrc`, `ruff.toml`, `AGENTS.md`, `docs/system-map.md` | Automated per-file / per-session | `PostToolUse` (disabled-by-default working single-file formatter template, outputs `{}`) + flat `SessionStart` (injects pointers only for existing `AGENTS.md` / `docs/system-map.md`) |

> **Worktree & Teardown Lifecycle**: If installing
> `.agents/plugins/swarm-guardrails/`, commit/register the plugin (including
> `./hooks/pretool-guard.py`) **before** spawning `share`/`branch` workers so
> worktrees inherit it. Disable or remove after the sprint
> (`agy plugin disable swarm-guardrails`, `"enabled": false`, or delete the
> temporary plugin).

## 4. Ready-to-Paste Launch Templates

### Template A: `/swarm` Feature / Fix Sprint
```text
/swarm
Goal: Implement <feature/fix scope>. Done when `<test/build commands>` pass.

Project context & guardrails: Read `<AGENTS.md / docs/system-map.md>` first.
<If .agents/plugins/swarm-guardrails is active: note it is committed pre-spawn; disable/remove after sprint.>

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family model id>` (read-only review + integration tests)
- Optional `monitor`: add only if `swarm_monitor` is in `<skills>` (inherits coordinator's model). Do NOT add a `narrator` unless explicitly requested.
- Quota fallback: If any member hits `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (or Coordinator's model) and report the switch.

Workspace, Overview & Handoff Rules:
- Authors use `workspace:"share"`; `verifier` uses `inherit` and never edits feature code directly.
- Board: Use single-board `main` (create `channel`s only if the live `swarm` tool exposes `action:"channel"` and >8 workers / 2+ independent areas).
- Swarm UI Overview (`swarm_pane`): Write `<appData>/brain/<conversation id>/.system_generated/swarm/plan.json` after adding workers. <If UI work: instruct frontend authors to save screenshots under their own `<appData>/brain/<conversation id>/` and post `Screenshot: <abs-path> | <caption <=10 words>`.>
- Do not edit `<central shared files / lockfiles / no-touch paths>` without `@coordinator` sign-off.
- Peer handoffs: `<author> <-> verifier` directly via `@mention` (no `@coordinator` CC). Retry circuit-breaker: after at most 2–3 failed bounce cycles on the same issue, escalate to `@coordinator`.
- Landing: Each author commits in its `share` worktree. After `verifier` approves all slices, merge into the main working copy in deterministic sequential order: `<author-1>` -> `<author-2>` -> ... -> run final `<test/build commands>`. Never push.
```

### Template B: `/run-workflow` Deterministic Blueprint (Audits / Scans / Phase 1)
```text
/run-workflow
Goal: <Scan/map/audit N targets> and aggregate results into `<output-path>`.

Staged Design:
1. `phase("Discover")`: Single `agent(..., model="flash_lite", schema={"type":"array","items":{"type":"string"}})` lists target modules/files.
2. `phase("Analyze")`: `parallel(targets, ...)` on `model="flash"` (or `"flash_lite"`) returns strict JSON per item:
   `{"path": str, "entry_points": [str], "deps": [str], "risks": [str]}`.
3. Aggregate deterministically in Python, verify schema completeness, and write `<output-path>` cleanly (read-only on production code).
```

### Template C: Legacy Takeover (`/swarm` Interactive Cartography or Characterization)
```text
/swarm
Goal: <Map this legacy repo into `docs/system-map.md` with verified `file:line` evidence (read-only) | OR | Write characterization tests for `<modules>` without altering production logic>.

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<investigator-or-tester-1..k>`: `<exact model ids>` (owns `<assigned modules/test paths>`)
- `verifier`: `<exact cross-family model id>` (read-only audit + sequential integration/DB runs)
- Quota fallback: On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (or Coordinator's model) and report the switch.

Rules:
- Cartography mode: All workers run `workspace:"inherit"` and are strictly read-only; cite `#seq` when cross-referencing; `kill` investigators once their `#seq` summary is accepted (unless `fork`ing).
- Characterization mode: Authors use `workspace:"share"`, `verifier` uses `inherit` and runs shared-DB/port integration tests sequentially.
- Peer handoffs: `<author> <-> verifier` via `@mention` with a max 2–3 retry circuit-breaker escalating to `@coordinator`.
- Landing (if editing tests): Commit in each `share` worktree and merge sequentially (`<tester-1>` -> `<tester-2>` -> ...) after `verifier` sign-off. Never push.
```

### Template D: Hybrid Handoff (Phase 1 `/run-workflow` -> Phase 2 `/swarm`)
```text
# Phase 1: Deterministic Read-Only Discovery (`/run-workflow`)
/run-workflow
Goal: Inventory `<target modules/files>` and write a structured handoff artifact at `<docs/system-map.md or scratch/plan-manifest.json>`.
1. `phase("Discover")`: Enumerate targets via `agent(..., model="flash_lite", schema={"type":"array","items":{"type":"string"}})`.
2. `phase("Map")`: `parallel(targets, ...)` on `model="flash"` extracting `{"path", "public_api", "deps", "test_cmd", "risks"}`.
3. Write `<handoff-artifact-path>` deterministically and stop for human/coordinator review.

# --- Review `<handoff-artifact-path>`, commit guardrails if used, then launch Phase 2 ---

# Phase 2: Collaborative Implementation (`/swarm`)
/swarm
Goal: Implement `<scope>` using the verified findings in `<handoff-artifact-path>`. Done when `<test/build commands>` pass.

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family model id>` (`inherit`, read-only review + integration tests)
- Quota fallback: On `[quota]`/capacity, `swarm{action:"model"}` to `<backup-model-id>` (or Coordinator's model) and report the switch.

Rules:
- Every worker reads `<handoff-artifact-path>` first (do not re-discover the whole repo).
- Authors use `workspace:"share"`; `verifier` uses `inherit`. Use single-board `main` unless live `swarm` exposes `action:"channel"`.
- Swarm UI Overview (`swarm_pane`): Write `plan.json` after adding workers; for UI work, post `Screenshot: <abs-path> | <caption <=10 words>` from each worker's `<appData>/brain/<conversation id>/`.
- Peer handoffs: `<author> <-> verifier` directly via `@mention`; max 2–3 retry bounces per issue before escalating to `@coordinator`.
- Landing: Commit in each `share` worktree and merge into the main working copy in deterministic sequential order (`<core-author>` -> `<slice-author-1>` -> ...), then run final verification. Never push.
```
