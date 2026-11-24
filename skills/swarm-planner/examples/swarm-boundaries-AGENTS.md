# Swarm Worker Boundaries & Project Conventions

<!-- Template note: Keep this rule file well under the 24 KB Antigravity rules limit. Store detailed architecture diagrams in docs/ for on-demand reading, and remove this comment after tailoring. -->

## Commands

- Install: `<e.g., pnpm install --frozen-lockfile>`
- Unit tests (safe for parallel `share` workspaces): `<e.g., pnpm test:unit>`
- Full integration tests (run sequentially by `verifier` only): `<e.g., pnpm test:e2e>`
- Typecheck / lint: `<e.g., pnpm typecheck && pnpm lint>`

## Ownership & Central Files

- **Shared contracts** (`src/types/`, `prisma/schema.prisma`): Read-only during
  parallel feature work; coordinate changes via `@coordinator` before editing.
- **Central registries, lockfiles & protected modules** (`package.json`,
  `package-lock.json`, `pnpm-lock.yaml`, `Cargo.lock`, `uv.lock`, `src/auth/`,
  `src/billing/`, plus any `<central router/module>` mirrored into
  `PROTECTED_PATH_PATTERNS` in `pretool-guard.py`): Protected by `PreToolUse`
  guardrails (unattended-safe `deny` by default; set `SWARM_GUARD_INTERACTIVE=1`
  only for interactive single-session prompts). Escalate needed edits to
  `@coordinator`.

## No-Touch Zones

- `<path/to/legacy-billing-cron>`: Production dependency; do not refactor.
- `<path/to/generated>`: Auto-generated; regenerate via `<command>` only.
- `.env` / `.env.*` secrets (excluding `.env.example`, `.env.sample`,
  `.env.template`): Never read or edit directly.
- `.agents/plugins/swarm-guardrails/`: Do not edit, disable, or delete active
  sprint guardrails.

## Verification & Git Hygiene

- Commit finished work inside your `share` worktree before reporting `[done]`.
- Do not run `git push`.
- Cite `#seq` numbers on the swarm board instead of pasting long logs.
