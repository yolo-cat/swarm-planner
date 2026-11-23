from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / "skills" / "swarm-planner" / "examples" / "pretool-guard.py"


def run_hook(payload: dict | str) -> subprocess.CompletedProcess[str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=raw,
        text=True,
        capture_output=True,
        check=False,
    )


class PretoolGuardTests(unittest.TestCase):
    def test_command_guards(self) -> None:
        cases = [
            ("git push origin main", "deny"),
            ("npm install lodash", "deny"),
            ("npx prisma db push --force-reset", "deny"),
            ("dropdb app_dev", "deny"),
            ("pnpm test --filter orders", "allow"),
        ]
        for cmd, expected in cases:
            proc = run_hook(
                {
                    "cwd": "/tmp/worktree",
                    "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                }
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            out = json.loads(proc.stdout)
            self.assertEqual(out["decision"], expected, f"Failed for cmd={cmd}: {out}")

    def test_path_guards_resolve_against_worker_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir)
            (worktree / "migrations").mkdir()
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "orders").mkdir(parents=True)

            cases = [
                ("migrations/001_init.sql", "deny"),
                ("generated/schema.ts", "deny"),
                (".env.production", "deny"),
                ("package.json", "force_ask"),
                ("pnpm-lock.yaml", "force_ask"),
                ("src/auth/login.ts", "force_ask"),
                (str(worktree / "src" / "orders" / "handler.ts"), "allow"),
            ]
            for path_arg, expected in cases:
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "edit_file", "args": {"Path": path_arg}},
                    }
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertEqual(out["decision"], expected, f"Failed for path={path_arg}: {out}")

    def test_malformed_json_fails_safe_to_ask(self) -> None:
        proc = run_hook("{not-valid-json")
        self.assertEqual(proc.returncode, 0)
        out = json.loads(proc.stdout)
        self.assertEqual(out["decision"], "ask")


if __name__ == "__main__":
    unittest.main()
