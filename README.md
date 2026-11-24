# swarm-planner

Antigravity Pre-Session orchestration planner skill & tooling repository.

Helps you evaluate and align on execution engine, model + thinking-effort allocation, and project-tailored guardrails **before** spending multi-agent quota:

- **Step 0 Fast-Exit & Triage**: Exits immediately to Single Session / `/plan` for small or sequential edits before spending tokens on recon or model snapshots; splits remaining work into **Lightweight** (compact Step 4 alignment; skips custom hooks by default unless explicitly requested in Step 3) vs. **Project-Level** flows.
- **Three-Way Engine Router**: Routes between `/run-workflow` (coarse tiers `inherit`/`flash_lite`/`flash`/`pro`, `type_name="research"` for read-only passes vs. `workspace="branch"`/`"share"` for parallel mechanical edits, `parallel`/`pipeline`, stateful multi-turn `agent()`, `call_tool` + `WaitMsBeforeAsync` + `ToolError.denied`, `trajectory()`, and `Args`/`Cwd`/`ScriptPath`), `/swarm` (exact catalog IDs + `low`/`medium`/`high`/`xhigh`/`max` effort suffixes, `<skills>`-gated `swarm_pane` `plan.json` written after adding workers + own-line full-window UI `Screenshot:`, `<skills>`-gated `swarm_monitor` + standalone `[done] <summary>` teardown, and merge-before-`kill` landing), and **Hybrid** (fresh Phase 1 `/run-workflow` session -> human/clean-git checkpoint -> fresh Phase 2 `/swarm` session via two separate pasteable prompts using committed repo-relative or absolute Phase 1 `<appData>/brain/<phase1-id>/scratch/...` handoff paths), backed by SSOT templates in [task-matrices.md](./skills/swarm-planner/references/task-matrices.md).
- **Live Model × Thinking Effort × Quota Snapshot**: `skills/swarm-planner/scripts/model_matrix.py` parses `swarm{action:"models", all:true}` JSON (`--from-swarm-json -`) or `agy models` CLI output (`--from-agy`), emits `--format json` catalog metadata (`vendor`, `quota_uniform`, `quotas_by_effort`), and validates chosen `/swarm` IDs with `--validate`, `--require-quota`, `--require-diverse`, and `--allowed-pool` (`--allowed-pool`, `--require-diverse`, and `--require-quota` require `--validate`, exiting `2` if omitted; `--validate <ids> --format json` outputs structured JSON with keys `valid`, `results`, `diversity`, `errors`, `warnings` on both exit `0` and exit `1`). Resolve `<skill-dir>` from `<skills>` and run `make install-status` (`./scripts/install.sh --status` or `--check`) when dogfooding inside this repo.
- **Unattended-Safe Project Guardrails**: Co-designs toggleable `.agents/plugins/swarm-guardrails/` bundles (`plugin.json`, `hooks.json` at plugin root, `hooks/pretool-guard.py`, `rules/AGENTS.md`):
  - `PreToolUse` (`pretool-guard.py`) enforces workspace/`artifactDirectoryPath` confinement, blocks `.env` reads/writes (`read_file`/`view_file` including `AbsolutePath` + `run_command`), blocks `git push` and protected-path mutations, and defaults to unattended-safe `"deny"` + `@coordinator` escalation (`SWARM_GUARD_INTERACTIVE=1` opts into `"force_ask"` for interactive single-session runs).
  - `PostToolUse` (disabled by default via per-hook `"enabled": false`, with `AbsolutePath`, `workspacePaths[0]`, and local `node_modules/.bin/prettier` fallbacks) and `SessionStart` (`workspacePaths[0]` fallback + non-dict JSON guard, injecting existing `AGENTS.md` / `docs/system-map.md`) use inline multiline `python3 -c '...'` commands that require Unix `sh -c` (macOS/Linux; Windows `cmd /c` is not supported for inline multiline hooks).
  - Validate staged bundles with `agy plugin validate .agents/plugins/swarm-guardrails --strict`, verify clean `git status`, and commit before spawning `share`/`branch` workers. After sprint teardown, either (1) delete `.agents/plugins/swarm-guardrails/`, (2) set `"disabled": true` in `plugin.json` (never bare `"enabled": false` in `plugin.json`) or per-hook `"enabled": false` in `hooks.json` (`rules/AGENTS.md` remains active), or (3) run `agy plugin disable swarm-guardrails` (persists a global directory-name override in `~/.gemini/config/config.json` across repos sharing that name; never hand-edit `config.json`).

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
