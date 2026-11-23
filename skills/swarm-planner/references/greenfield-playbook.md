# Greenfield Project Playbook

Starting from a brand-new repository has no legacy coupling, but faces a
different failure mode: parallel workers inventing incompatible APIs,
directory conventions, toolchain commands, or colliding on central setup files.

> For the core Role-to-Model Strategy, File Ownership & Hook Signals table, and
> Launch Templates, use the SSOT in
> [task-matrices.md](./task-matrices.md#2-heterogeneous-role-model-strategy-swarm).
> This playbook covers **greenfield-specific deltas only**.

## Two-Step Startup Rule: Scaffold First, Swarm Second

Do **not** launch a multi-author `/swarm` on an empty repository.

1. **Step 0 — Single-Session Scaffold & Contracts (Pre-Swarm)**
   Ensure these exist and pass a baseline build/test before parallelizing:
   - Directory layout, naming conventions, and chosen package manager lockfile
   - Linter, formatter, and test runner baseline
   - Shared contracts (TypeScript interfaces, OpenAPI/Proto schemas, DB schema)
   - Concise conventions doc (API envelope, error handling, design tokens)
   - Current library/SDK versions pinned via `context7-mcp` (`query-docs`)
2. **Step 1 — Contract-Driven `/swarm` Sprint**
   Once contracts and baseline build pass, launch `/swarm` along **vertical
   feature slices** (`auth-slice`, `billing-slice`, `ui-shell`) rather than
   vague horizontal layers, using Template A in
   [task-matrices.md](./task-matrices.md#4-ready-to-paste-launch-templates).

## Pre-Swarm Readiness Checklist

Before generating the `/swarm` Launch Prompt, confirm:

- [ ] Baseline build and smoke test command run cleanly.
- [ ] Shared types/schemas live in a designated read-only-for-authors path.
- [ ] Central files (`package.json`, lockfiles, global routers) have a clear
      owner.
- [ ] Key library versions are aligned via `context7-mcp` if needed.
- [ ] Role-to-Model IDs and `[quota]` fallback chain are validated via
      `python3 "<skill-dir>/scripts/model_matrix.py"` (global default
      `~/.gemini/config/skills/swarm-planner/scripts/model_matrix.py`,
      [model_matrix.py](../scripts/model_matrix.py)) with `--require-quota`
      when using `--from-swarm-json`.
- [ ] If using `.agents/plugins/swarm-guardrails/`, commit/register the plugin
      (including `./hooks/pretool-guard.py`) **before** spawning `share`/`branch`
      workers so worktrees inherit it.

## Greenfield-Specific Deltas

- **Guardrail priorities** (see SSOT in
  [task-matrices.md](./task-matrices.md#3-file-ownership-and-hook-signals-ssot)):
  - Prioritize toolchain locking (`pnpm`/`uv` over `npm install`) and frozen
    contract/codegen protection (`src/types/*`, `openapi.*`, `generated/*`)
    using unattended-safe `"deny"` + `@coordinator` escalation.
  - Enable the `PostToolUse` single-file formatter template (`prettier`,
    `ruff format`, `gofmt`) only if formatting diff noise across parallel
    slices is a concern; keep it `<1–2s` and returning `{}`.
  - Tear down or disable `.agents/plugins/swarm-guardrails/` after the MVP
    sprint (`agy plugin disable swarm-guardrails` or `"enabled": false`).
- **Verifier focus (Spec & DRY Guardian)**: Assign the cross-family `verifier`
  to enforce contract conformance, integration wiring, and zero duplicated
  helpers across vertical slices.
- **Visual progression (`swarm_pane`)**: For UI slices, write `plan.json` after
  adding workers and instruct frontend authors to save screenshots under their
  own `<appData>/brain/<conversation id>/` directory (allowed by
  `pretool-guard.py` via `artifactDirectoryPath`) and flag each milestone with
  `Screenshot: <abs-path> | <caption <=10 words>`.
