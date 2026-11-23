# Greenfield Project Playbook

Starting from a brand-new repository has no legacy coupling, but faces a
different failure mode: parallel workers inventing incompatible APIs,
directory conventions, toolchain commands, or colliding on central setup files.

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
   feature slices** rather than vague horizontal layers.

## Pre-Swarm Readiness Checklist

Before generating the `/swarm` Launch Prompt, confirm:
- [ ] Baseline build and smoke test command run cleanly.
- [ ] Shared types/schemas live in a designated read-only-for-authors path.
- [ ] Central files (`package.json`, lockfiles, global routers) have a clear owner.
- [ ] Key library versions are aligned via `context7-mcp` if needed.
- [ ] Role-to-Model IDs and `[quota]` fallback chain are validated via
      `scripts/model_matrix.py`.

## Greenfield Hook Signals & Guardrails

Tailor `.agents/plugins/swarm-guardrails/` from the chosen tech stack:
- **Toolchain lock (`PreToolUse`)**: Enforce the repo's package manager (e.g.,
  deny `npm install` when `pnpm-lock.yaml` or `uv.lock` is used).
- **Frozen contract & codegen protection (`PreToolUse`)**: Return `deny` or
  `force_ask` if a feature-slice author attempts to edit `src/types/*`,
  `openapi.*`, `generated/*`, or central `package.json`/lockfiles directly.
- **Fast single-file formatting (`PostToolUse`)**: Optionally run the project's
  fast formatter (`prettier`, `ruff format`, `gofmt`) on the edited file only
  so parallel slices do not create formatting diff noise.
- **Toggleable Plugin packaging**: Bundle rules + hooks in
  `.agents/plugins/swarm-guardrails/` so developers can disable strict central
  locks cleanly after the MVP sprint.

## Role-Model Strategy for Greenfield Sprints

- **Step 0 Contract Design & Complex Core Slice**: High/XHigh reasoning model
  to lock clean interfaces and edge-case semantics early.
- **Independent Vertical Feature Slices (`auth-slice`, `billing-slice`, `ui-shell`)**:
  Fast, high-quota models (`low`/`medium` or Flash tier) when specs are crisp.
- **Verifier (Spec & DRY Guardian)**: Strong cross-family analytical model
  tasked with checking contract conformance, integration wiring, and zero
  duplicated helpers across slices.
- **Visual progression (`swarm_pane`)**: For UI slices, instruct frontend
  workers to post `Screenshot: <absolute path> | <summary <= 10 words>` saved
  under their own `<appData>/brain/<conversation id>/` directory.
