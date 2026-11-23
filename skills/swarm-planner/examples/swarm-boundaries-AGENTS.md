# Swarm Worker Boundaries & Project Conventions

> Keep this rule file concise (well under the 24 KB limit) so every cold-started
> `/swarm` worker gets critical guardrails without wasting context budget.
> Store detailed architecture diagrams in `docs/` for on-demand reading.

## Commands

- Install: `<e.g., pnpm install --frozen-lockfile>`
- Unit tests (safe for parallel `share` workspaces): `<e.g., pnpm test:unit>`
- Full integration tests (run sequentially by `verifier` only): `<e.g., pnpm test:e2e>`
- Typecheck / lint: `<e.g., pnpm typecheck && pnpm lint>`

## Ownership & Central Files

- **Shared contracts** (`src/types/`, `prisma/schema.prisma`): Read-only during
  parallel feature work; coordinate changes via `@coordinator` before editing.
- **Central registries & lockfiles** (`package.json`, `package-lock.json`,
  `pnpm-lock.yaml`, `src/routes.ts`): Protected by `PreToolUse` guardrails
  (unattended-safe `deny` by default; set `SWARM_GUARD_INTERACTIVE=1` only for
  interactive single-session prompts). Escalate needed edits to `@coordinator`.

## No-Touch Zones

- `<path/to/legacy-billing-cron>`: Production dependency; do not refactor.
- `<path/to/generated>`: Auto-generated; regenerate via `<command>` only.
- `.env` / `.env.*` secrets (excluding `.env.example`, `.env.sample`,
  `.env.template`): Never read or edit directly.

## Verification & Git Hygiene

- Commit sprint guardrails (`.agents/plugins/swarm-guardrails/`) before spawning
  `share`/`branch` workers so worktrees inherit them, and disable or remove
  temporary sprint guardrails after merge teardown.
- Commit finished work inside your `share` worktree before reporting `[done]`.
- Do not run `git push`.
- Cite `#seq` numbers on the swarm board instead of pasting long logs.
