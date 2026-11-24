# swarm-planner

Antigravity Pre-Session orchestration planner skill & tooling repository.

Helps you evaluate and align on execution engine, model + thinking-effort allocation, and project-tailored guardrails **before** spending multi-agent quota:

- **Step 0 Fast-Exit & Triage**: Exits immediately to Single Session / `/plan` for small or sequential edits before spending tokens on recon or model snapshots; splits remaining work into **Lightweight** (compact Step 4 alignment; skips custom hooks by default unless explicitly requested in Step 3) vs. **Project-Level** flows.
- **Three-Way Engine Router**: Routes between `/run-workflow` (coarse tiers `inherit`/`flash_lite`/`flash`/`pro`, read-only `type_name="research"` vs. `workspace="branch"`/`"share"` transforms, `parallel`/`pipeline`, stateful `agent()`, `call_tool` + `WaitMsBeforeAsync`, `trajectory()`, `Args`/`Cwd`/`ScriptPath`), `/swarm` (exact catalog IDs + effort suffixes, `<skills>`-gated `swarm_pane` + `swarm_monitor`, merge-before-`kill` landing), and **Hybrid** (fresh Phase 1 `/run-workflow` -> human/clean-git checkpoint -> fresh Phase 2 `/swarm` via two separate pasteable prompts in [task-matrices.md](./skills/swarm-planner/references/task-matrices.md)).
- **Live Model × Thinking Effort × Quota Snapshot**: `skills/swarm-planner/scripts/model_matrix.py` parses `swarm{action:"models", all:true}` JSON (`--from-swarm-json -`) or `agy models` (`--from-agy`), emits `--format json` catalog metadata, and validates `/swarm` IDs via `--validate` with `--require-quota`, `--require-diverse`, and `--allowed-pool` (the latter three require `--validate`, exiting `2` if omitted; `--validate <ids> --format json` outputs structured JSON with keys `valid`, `results`, `diversity`, `errors`, `warnings`). Resolve `<skill-dir>` from `<skills>` and check drift via `make install-status` (`./scripts/install.sh --status` or `--check`).
- **Unattended-Safe Project Guardrails**: Co-designs `.agents/plugins/swarm-guardrails/` bundles (`plugin.json`, `hooks.json` at plugin root, `hooks/pretool-guard.py`, `rules/AGENTS.md`):
  - `PreToolUse` (`pretool-guard.py`) enforces workspace/`artifactDirectoryPath` confinement, blocks `.env` reads/writes, `git push`, and protected-path mutations, and defaults to unattended-safe `"deny"` + `@coordinator` escalation (`SWARM_GUARD_INTERACTIVE=1` for interactive runs).
  - `PostToolUse` (disabled-by-default single-file Prettier template with local `node_modules/.bin/prettier` and `workspacePaths[0]` fallbacks) and `SessionStart` (injecting existing `AGENTS.md` / `docs/system-map.md`) use inline multiline `python3 -c '...'` commands requiring Unix `sh -c` (Windows `cmd /c` not supported for inline multiline hooks).
  - Validate with `agy plugin validate .agents/plugins/swarm-guardrails --strict` and commit before spawning `share`/`branch` workers. Tear down after the sprint by (1) deleting `.agents/plugins/swarm-guardrails/`, (2) setting `"disabled": true` in `plugin.json` (never bare `"enabled": false` in `plugin.json`) or per-hook `"enabled": false` in `hooks.json` (`rules/AGENTS.md` stays active), or (3) running `agy plugin disable swarm-guardrails` (persists globally in `~/.gemini/config/config.json` across repos sharing that plugin name; never hand-edit `config.json`).

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
└── tests/                          # Unit, dry-run & cross-module contract tests
    ├── test_contracts.py
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

Check repo-vs-installed drift (missing install, dangling symlink, worktree target mismatch, executable-bit/symlink drift, or modified files):

```bash
make install-status
# or: ./scripts/install.sh --status  (alias: --check)
```

Or use `make install-symlink` / `./scripts/install.sh --symlink` for live-linked local development (in linked or dirty git worktrees, pass `make install-symlink INSTALL_FLAGS=--force` or `./scripts/install.sh --symlink --force` to override the dangling-worktree safety guard), `--skip-tests` to skip pre-install tests, or `make uninstall` / `./scripts/install.sh --uninstall` to remove the global copy:

```bash
./scripts/install.sh --symlink
# in a linked or dirty git worktree:
make install-symlink INSTALL_FLAGS=--force
# or: ./scripts/install.sh --symlink --force
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
