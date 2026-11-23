# swarm-planner

Antigravity Pre-Session orchestration planner skill & tooling repository.

Helps you evaluate and align on execution engine, model + thinking-effort allocation, and project-tailored guardrails **before** spending multi-agent quota:

- **Three-Way Orchestration Router**: Single Session (`/plan`) vs. `/run-workflow` vs. `/swarm` (plus Hybrid phasing).
- **Live Model × Thinking Effort × Quota Snapshot**: `skills/swarm-planner/scripts/model_matrix.py` parses `swarm{action:"models", all:true}` JSON or `agy models` CLI output and validates chosen model IDs.
- **Project-Tailored Guardrails**: Co-designs toggleable `.agents/plugins/swarm-guardrails/` bundles (`hooks.json`, `AGENTS.md`, `pretool-guard.py`) scoped to the target project.

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
