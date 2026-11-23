# Swarm Worker Boundaries & Project Conventions

> Keep this rule file concise (well under the 24 KB limit) so every cold-started
> `/swarm` worker gets critical guardrails without wasting context budget.
> Store detailed architecture diagrams in `docs/` for on-demand reading.

## Commands

- Install: `<e.g., npm ci>`
- Unit tests (safe for parallel `share` workspaces): `<e.g., npm run test:unit>`
- Full integration tests (run sequentially by `verifier` only): `<e.g., npm run test:e2e>`
- Typecheck / lint: `<e.g., npm run typecheck && npm run lint>`

## Ownership & Central Files

- **Shared contracts** (`src/types/`, `prisma/schema.prisma`): Read-only during
  parallel feature work; coordinate changes before editing.
- **Central registries & lockfiles** (`package.json`, `package-lock.json`,
  `src/routes.ts`): Do not edit directly inside feature branches without
  coordinator approval.

## No-Touch Zones

- `<path/to/legacy-billing-cron>`: Production dependency; do not refactor.
- `<path/to/generated>`: Auto-generated; regenerate via `<command>` only.

## Verification & Git Hygiene

- Commit finished work inside your `share` workspace before reporting `[done]`.
- Do not run `git push`.
- Cite `#seq` numbers on the swarm board instead of pasting long logs.
