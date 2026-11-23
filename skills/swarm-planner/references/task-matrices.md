# Task Configuration Matrices & Launch Templates

## 1. Orchestration Router & Scenario Matrix

| Scenario | Recommended Engine | Pre-Launch Prerequisite | Workspace / Features | Verification / Focus |
| :--- | :--- | :--- | :--- | :--- |
| **Small / Sequential Edit** | **Single Session** or `/plan` | None (skip `/swarm`) | Default workspace | Direct edits + unit test |
| **Massive Audit / Pattern Scan** | **`/run-workflow`** | Define target list & JSON `schema` | `inherit`, `parallel()` + `flash`/`flash_lite` | Deterministic Python aggregation |
| **Legacy Cartography (Phase 1)** | **`/run-workflow`** *(or `/swarm` if interactive cross-talk/`fork` needed)* | Forbid code edits; list top modules | `inherit`; compile to `docs/system-map.md` | Verified `file:line` evidence |
| **Legacy Characterization Tests** | **`/swarm`** | Lock prod code & assertions; add migration/DB hooks | Authors `share`, Verifier `inherit`, `tasks` | Real behavior vs. over-mocking; single-verifier DB runs |
| **Greenfield MVP Sprint** | **`/swarm`** | Scaffold + shared contracts + baseline build green | Authors `share`, Verifier `inherit`, `channel` (>8) | Contract conformance, zero duplicate helpers |
| **Large Refactor / Migration** | **`/swarm`** *(or `/run-workflow` for mechanical per-file transforms)* | Lock invariants & public signatures | Migrators `share`, Verifier `inherit`, `tasks` | Full build + regression suite |
| **Multi-Role Code Audit** | **`/swarm`** *(cross-model review)* or **`/run-workflow`** *(checklist sweep)* | Define diff target (e.g., vs. `main`) | All `inherit`; `#seq` citations | Severity-ranked findings; optional `share` fixes |
| **UI / Visual Polish** | **`/swarm`** | Specify target viewports & design tokens | Frontend `share`, Verifier `inherit`, `swarm_pane` | `Screenshot:` milestones; light/dark & responsive |

## 2. Heterogeneous Role-Model Strategy (`/swarm`)

Run `scripts/model_matrix.py` in Step 1 first, then assign **exact verified IDs**
with explicit user sign-off in Step 3–4 (required by `native_swarm` rules):

| Role | Selection Principle | Rationale |
| :--- | :--- | :--- |
| **Coordinator** | High instruction-following / orchestrator variant | Tracks `#seq` references, channels, and handoffs cleanly |
| **Core / Complex Author** | High/XHigh reasoning flagship model | Protects concurrency, state machines, and shared contracts |
| **Routine Slice Author** | Fast, high-quota model (`low`/`medium` or Flash tier) | Maximizes parallel throughput on CRUD, UI slices, and boilerplate |
| **Verifier** | **Cross-family strong analytical model** | Independent "second pair of eyes" catches single-model blind spots |
| **Narrator / Monitor** | Lightweight / high-remaining-quota model | Keeps UI overview & stall detection running without draining flagship quota |
| **Quota Fallback Chain** | 1–2 pre-approved backup IDs per tier | Lets Coordinator `swarm{action:"model"}` hot-swap on `[quota]` without stopping |

## 3. File Ownership Matrix

| Asset Class | Examples | Recommended Ownership & Guardrail |
| :--- | :--- | :--- |
| **Independent Feature Modules** | `src/modules/auth/*` | Dedicated author (`workspace:"share"`) |
| **Central Manifests & Registries** | `package.json`, lockfile, global router | Single integrator or `PreToolUse` `force_ask` hook |
| **Shared Contracts & Generated Code** | `src/types/*`, `openapi.*`, `migrations/` | Frozen before sprint; `PreToolUse` `deny` hook on derived files |
| **Shared Runtime Test Resources** | Local Postgres/Redis, fixed ports | Single `verifier` sequential runs + `PreToolUse` reset guard |

## 4. Ready-to-Paste Launch Templates

### Template A: `/swarm` Sprint with Authorized Models & Guardrails
```text
/swarm
Goal: Implement <feature/fix scope>. Done when `<test/build commands>` pass.

Project context & guardrails: Read `<AGENTS.md / docs/system-map.md>` first.
<Note active hooks in .agents/plugins/swarm-guardrails if installed.>

Authorized Role -> Model Assignments (user-approved):
- Coordinator: `<default or exact model id>`
- `<core-author>`: `<exact high-reasoning model id>` (owns `<core-path>`)
- `<slice-author-1..k>`: `<exact fast/high-quota model id>` (owns `<slice-paths>`)
- `verifier`: `<exact cross-family model id>` (read-only review + integration tests)
- Quota fallback: If any member hits `[quota]`, `swarm{action:"model"}` to `<backup-model-id>` (or Coordinator's model) and report the switch.

Workspace & Handoff Rules:
- Authors use `workspace:"share"`; `verifier` uses `inherit` and never edits feature code directly.
- Do not edit `<central shared files / lockfiles / no-touch paths>` without `@coordinator` sign-off.
- Hand off `<author> <-> verifier` directly via `@mention`; tag `@coordinator` only on `[done]` or blockers.
- Commit in each `share` workspace and merge into the main working copy after verification passes. Never push.
```

### Template B: Legacy Read-Only Cartography (`/swarm` Interactive Mode)
```text
/swarm
Goal: Map this legacy repository without modifying any code. Write a persistent
system guide at `<target-doc-path>` with verified `file:line` references.

Authorized Role -> Model Assignments (user-approved):
- `infra-runner` (`<model-id>`): Build scripts, env vars, CI, test health.
- `entry-tracer` (`<high-reasoning-id>`): Primary entry points and request flows.
- `data-modeler` (`<high-reasoning-id>`): DB schemas, migrations, global state.
- `hotspot-auditor` (`<fast-model-id>`): Git churn hotspots, coupling, dead code.

Rules:
- All workers run `workspace:"inherit"` and are strictly read-only.
- Cite `#seq` when cross-referencing findings; coordinator compiles `<target-doc-path>`.
```

### Template C: `/run-workflow` Deterministic Blueprint (Audits / Phase 1 Cartography)
```text
/run-workflow
Goal: <Scan/map/audit N targets> and aggregate results into `<output-path>`.

Staged Design:
1. `phase("Discover")`: Single `agent(..., schema={"type":"array","items":{"type":"string"}})` lists target modules/files.
2. `phase("Analyze")`: `parallel(targets, ...)` on `model="flash"` (or `"flash_lite"`) returns strict JSON per item:
   `{"path": str, "entry_points": [str], "deps": [str], "risks": [str]}`.
3. Aggregate deterministically in Python and write `<output-path>` cleanly.
```
