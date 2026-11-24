# swarm-planner

Antigravity Pre-Session orchestration planner skill & tooling repository.

Helps you evaluate and align on execution engine, model + thinking-effort allocation, and project-tailored guardrails **before** spending multi-agent quota:

- **Step 0 Fast-Exit & Triage**: Immediately exits to Single Session / `/plan` for small or sequential edits before spending tokens on recon or model snapshots; splits remaining work into **Lightweight** (compact Step 4 alignment) vs. **Project-Level** flows.
- **Three-Way Engine Router**: `/run-workflow` (coarse tiers `inherit`/`flash_lite`/`flash`/`pro` + `type_name="research"` for read-only passes) vs. `/swarm` (exact catalog IDs + `low`/`medium`/`high`/`xhigh`/`max` effort suffixes) vs. **Hybrid** (Phase 1 `/run-workflow` -> Phase 2 `/swarm`), backed by batched `ask_question` interviews and SSOT templates in [task-matrices.md](./skills/swarm-planner/references/task-matrices.md).
- **Live Model × Thinking Effort × Quota Snapshot**: `skills/swarm-planner/scripts/model_matrix.py` parses `swarm{action:"models", all:true}` JSON (`--from-swarm-json -`) or `agy models` CLI output (`--from-agy`), emits `--format json` family metadata (`vendor`, `quota_uniform`, `quotas_by_effort`), and validates chosen `/swarm` IDs with `--validate`, `--require-quota`, `--require-diverse`, and `--allowed-pool`.
  - When invoked from a target project `cwd`, resolve `<skill-dir>` from the `swarm-planner` `SKILL.md` path in `<skills>` (global default: `~/.gemini/config/skills/swarm-planner/scripts/model_matrix.py`), and run `make install-status` (or `./scripts/install.sh --status`) when dogfooding inside this repo to detect repo-vs-installed drift.
  - `--from-swarm-json` with `--require-quota` enforces usable live quota; `--from-agy` checks model existence only (`quota=unknown`).
- **Unattended-Safe Project Guardrails**: Co-designs toggleable `.agents/plugins/swarm-guardrails/` bundles (`plugin.json`, `hooks.json`, `hooks/pretool-guard.py`, `rules/AGENTS.md`):
  - `PreToolUse` (`pretool-guard.py`, matching `run_command|read_file|view_file|write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content`) confines file writes/edits to `cwd` or `artifactDirectoryPath` (for `swarm_pane` screenshots), blocks `.env` reads (`read_file`/`view_file`) and `run_command` `.env`/push/forbidden-path/protected-path bypasses (case-insensitive on macOS/Windows), and defaults to unattended-safe `"deny"` + `@coordinator` escalation (`SWARM_GUARD_INTERACTIVE=1` opts into `"force_ask"` for interactive single-session runs).
  - `PostToolUse` ships disabled by default (`"enabled": false`) as a working single-file Prettier template scoped to Prettier extensions inside `cwd` (excluding `package-lock.json`) with `timeout=1.5` (`{}` output); `SessionStart` uses a flat handler list pointing only to existing `AGENTS.md` / `docs/system-map.md`.
  - Verify clean `git status` and commit/register `.agents/plugins/swarm-guardrails/` **before** spawning `share`/`branch` workers so worktrees inherit it, and disable/remove after the sprint (`agy plugin disable swarm-guardrails` or `"enabled": false`).

## Repository Layout

```text
swarm-planner/
├── Makefile
├── README.md
├── scripts/
│   └── install.sh                  # Runs tests (optional --skip-tests), checks --status, & installs skill to ~/.gemini/config/skills/
├── skills/
│   └── swarm-planner/              # Distributable Antigravity Skill package
│       ├── SKILL.md
│       ├── scripts/model_matrix.py
│       ├── references/
│       └── examples/
└── tests/                          # Unit & dry-run regression tests
    ├── test_install.py
    ├── test_model_matrix.py
    └── test_pretool_guard.py
```

## Development & Verification

Run all unit tests, shell syntax checks, and JSON schema checks:

```bash
make test
```

## Install as Global Skill

Test and install (atomic copy sync) into `~/.gemini/config/skills/swarm-planner`:

```bash
make install
```

Check repo-vs-installed drift (missing install, dangling symlink, worktree target mismatch, or modified files):

```bash
make install-status
# or: ./scripts/install.sh --status  (alias: --check)
```

Or use `make install-symlink` / `--symlink` for live-linked local development (requires `--force` in linked or dirty git worktrees to avoid dangling symlinks when pruned), `--skip-tests` to skip pre-install tests, or `make uninstall` / `--uninstall` to remove the global copy:

```bash
./scripts/install.sh --symlink
./scripts/install.sh --uninstall
```

## Changelog

### `v0.3.0` (2026-11-24) — RSI Audit Hardening & Installer Drift Protection (`5128134` / `fe62d18`, `34cda07` / `cb853fb`)

- **Installer & Build (`scripts/install.sh`, `Makefile`, `tests/test_install.py`)**: Added `--status` / `--check` repo-vs-installed drift detection, atomic `--copy` staging (`mktemp` + `rsync`/`cp -Rp` fallback), linked/dirty git worktree guard for `--symlink` (`--force`), `CDPATH=""` + `cd -P` safety, conflicting mode-flag rejection, default pre-install test execution with `--skip-tests`, `make lint-shell`, `make install-status`, and `PYTHONDONTWRITEBYTECODE=1 -B`.
- **Guardrails & Hooks (`pretool-guard.py`, `swarm-guardrails-hooks.json`, `tests/test_pretool_guard.py`)**: Added `read_file|view_file` `.env` secret read blocking, fail-closed write/edit path checks, `run_command` enforcement of `PROTECTED_PATH_PATTERNS` and parser-bypass fixes (`>|`/`<>`, wrapper option-args, `cd`/`pushd`, subshells/`$()`, `ln`/`rsync`/`patch`, `npm ... install`, `$VAR` targets, macOS/Windows case-insensitive matching), and `PostToolUse` Prettier scoping (Prettier extensions inside `cwd`, excluding `package-lock.json`, `timeout=1.5`).
- **Model Matrix (`model_matrix.py`, `tests/test_model_matrix.py`)**: Hardened `--validate` / `--from-swarm-json` / numeric quota parsing, wildcard concrete-ID suggestions, exit-2 malformed payload & `agy` stderr filtering, mixed-quota family normalization (`vendor`, `quota_uniform`, top-level `null`), pool-diversity classification, `--require-diverse`, and `--allowed-pool`.
- **Skill Docs & Templates (`SKILL.md`, `references/*`, `swarm-boundaries-AGENTS.md`, `README.md`)**: Enforced `/run-workflow` coarse tiers (`inherit`/`flash_lite`/`flash`/`pro`) + `type_name="research"` + valid JSON Schema, aligned `swarm_pane`/`swarm_monitor` contracts, added single-family cross-variant pool and repo-vs-installed/worktree drift checks, fixed Template C writer ownership, removed coordinator teardown rules from worker `AGENTS.md`, and deduplicated `SKILL.md` (`-16.8%` size).

### `v0.2.0` (2026-11-24) — Phase 1 Contract Hardening & SSOT Alignment (`091db07` / `e332eda`, `6270bfd` / `f60e52c`)

- Hardened `model_matrix.py` (`--require-quota`, orchestrator & per-variant quota parsing, PTY/CR spinner filtering for `agy models`).
- Hardened `pretool-guard.py` and `swarm-guardrails-hooks.json` with workspace/`artifactDirectoryPath` confinement, unattended-safe `"deny"` default (`SWARM_GUARD_INTERACTIVE=1` for interactive prompts), working `PostToolUse` formatter template (`enabled: false`), and conditional `SessionStart` injection for existing `AGENTS.md` / `docs/system-map.md`.
- Introduced Step 0 fast-exit & Lightweight/Project-Level triage, three-way engine router, and consolidated SSOT templates across `SKILL.md`, `references/*`, and `README.md`.

### `v0.1.0` (2026-11-24) — Initial Standalone Release (`d9abc18`)

- Initialized the standalone `swarm-planner` skill repository with `SKILL.md`, `scripts/model_matrix.py`, reference playbooks & matrices, `.agents/plugins/swarm-guardrails/` examples, `scripts/install.sh`, `Makefile`, and initial `unittest` suite.
