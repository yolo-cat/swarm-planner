# swarm-planner

Antigravity Pre-Session orchestration planner skill & tooling repository.

Helps you evaluate and align on execution engine, model + thinking-effort allocation, and project-tailored guardrails **before** spending multi-agent quota:

- **Step 0 Fast-Exit & Triage**: Immediately exits to Single Session / `/plan` for small or sequential edits before spending tokens on recon or model snapshots; splits remaining work into **Lightweight** vs. **Project-Level** flows.
- **Three-Way Engine Router**: `/run-workflow` vs. `/swarm` vs. **Hybrid** (Phase 1 `/run-workflow` -> Phase 2 `/swarm`), backed by batched `ask_question` interviews and SSOT templates in [task-matrices.md](./skills/swarm-planner/references/task-matrices.md).
- **Live Model × Thinking Effort × Quota Snapshot**: `skills/swarm-planner/scripts/model_matrix.py` parses `swarm{action:"models", all:true}` JSON (`--from-swarm-json -`) or `agy models` CLI output (`--from-agy`), and validates chosen IDs with `--validate` and `--require-quota`.
  - When invoked from a target project `cwd`, resolve `<skill-dir>` from the `swarm-planner` `SKILL.md` path in `<skills>` (global default: `~/.gemini/config/skills/swarm-planner/scripts/model_matrix.py`).
  - `--from-swarm-json` with `--require-quota` enforces usable live quota; `--from-agy` checks model existence only (`quota=unknown`).
- **Unattended-Safe Project Guardrails**: Co-designs toggleable `.agents/plugins/swarm-guardrails/` bundles (`plugin.json`, `hooks.json`, `hooks/pretool-guard.py`, `rules/AGENTS.md`):
  - `PreToolUse` (`pretool-guard.py`) confines file writes/edits to `cwd` or `artifactDirectoryPath` (for `swarm_pane` screenshots), blocks `run_command` `.env`/push/forbidden-path bypasses, and defaults to unattended-safe `"deny"` + `@coordinator` escalation (`SWARM_GUARD_INTERACTIVE=1` opts into `"force_ask"`/`"ask"` for interactive single-session runs).
  - `PostToolUse` ships disabled by default (`"enabled": false`) as a working single-file formatter template (`{}` output); `SessionStart` uses a flat handler list pointing only to existing `AGENTS.md` / `docs/system-map.md`.
  - Commit/register `.agents/plugins/swarm-guardrails/` **before** spawning `share`/`branch` workers so worktrees inherit it, and disable/remove after the sprint (`agy plugin disable swarm-guardrails` or `"enabled": false`).

## Repository Layout

```text
swarm-planner/
├── Makefile
├── README.md
├── scripts/
│   └── install.sh                  # Runs tests (optional skip) & installs skill to ~/.gemini/config/skills/
├── skills/
│   └── swarm-planner/              # Distributable Antigravity Skill package
│       ├── SKILL.md
│       ├── scripts/model_matrix.py
│       ├── references/
│       └── examples/
└── tests/                          # Unit & dry-run regression tests
    ├── test_model_matrix.py
    └── test_pretool_guard.py
```

## Development & Verification

Run all unit tests and JSON schema checks:

```bash
make test
```

## Install as Global Skill

Test and install (clean sync) into `~/.gemini/config/skills/swarm-planner`:

```bash
make install
```

Or pass `--symlink` to `scripts/install.sh` for live-linked local development, or `--uninstall` to remove the global copy:

```bash
./scripts/install.sh --symlink
./scripts/install.sh --uninstall
```
