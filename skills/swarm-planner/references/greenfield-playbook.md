# Greenfield Project Playbook

Starting from a brand-new repository has no legacy coupling, but faces a
different failure mode: parallel workers inventing incompatible APIs,
directory conventions, toolchain commands, or colliding on central setup files.

> For the core Role-to-Model Strategy, File Ownership & Hook Signals table,
> generic guardrail lifecycle, and Launch Templates, use the SSOT in
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
- [ ] Role-to-Model IDs and `[quota]` fallback chain are validated per
      `SKILL.md` Step 5 / [task-matrices.md](./task-matrices.md#2-heterogeneous-role-model-strategy-swarm)
      (`--from-swarm-json - --validate <comma-separated-ids> --require-quota`,
      plus `--allowed-pool` when pool-restricted).
- [ ] Git tree is clean (scaffold and optional guardrails committed) per
      [task-matrices.md](./task-matrices.md#3-file-ownership-and-hook-signals-ssot)
      before spawning `share`/`branch` workers.

## Greenfield-Specific Deltas

- **Guardrail priorities** (see SSOT in
  [task-matrices.md](./task-matrices.md#3-file-ownership-and-hook-signals-ssot)
  for generic `deny` semantics, hook latency, pre-spawn commit, and teardown):
  - Prioritize toolchain locking (`pnpm`/`uv` over `npm install`) and frozen
    contract/codegen protection (`src/types/*`, `openapi.*`, `generated/*`).
  - Enable the `PostToolUse` single-file formatter template (`prettier`,
    `ruff format`, `gofmt`) only if formatting diff noise across parallel
    slices is a concern.
- **Verifier focus (Spec & DRY Guardian)**: Assign the cross-family (or
  distinct-variant/higher-effort within a single-family pool) `verifier` to
  enforce contract conformance, integration wiring, and zero duplicated helpers
  across vertical slices.
- **Swarm UI Overview & Visual progression (`swarm_pane`)**: Load `swarm_pane`
  before briefing/adding workers and write `plan.json` for **all** `/swarm`
  sessions. For UI slices specifically, instruct frontend authors to save
  screenshots under their own `<appData>/brain/<conversation id>/` directory
  (allowed by `pretool-guard.py` via `artifactDirectoryPath`) and flag each
  milestone with `Screenshot: <abs-path> | <caption <=10 words>`.
