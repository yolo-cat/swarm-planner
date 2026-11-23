from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "skills" / "swarm-planner" / "examples"
HOOK_PATH = EXAMPLES_DIR / "pretool-guard.py"
HOOKS_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-hooks.json"
PLUGIN_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-plugin.json"


def run_hook(
    payload: dict | str,
    *,
    env_overrides: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    env = os.environ.copy()
    env.pop("SWARM_GUARD_INTERACTIVE", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=raw,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


class PretoolGuardTests(unittest.TestCase):
    def test_command_guards_and_bypasses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            (worktree / "migrations").mkdir(parents=True)
            (worktree / "generated").mkdir(parents=True)
            (worktree / "src").mkdir(parents=True)

            denied_cmds = [
                "git push origin main",
                "git -C . push origin main",
                "git status && git -C ../repo push",
                "npm install lodash",
                "npm i lodash",
                "npx prisma db push --force-reset",
                "dropdb app_dev",
                "cat .env",
                "head -n 5 .env.production",
                "grep SECRET ./.env.local",
                "cp .env.example .env",
                "sed -i 's/a/b/' migrations/001_init.sql",
                "perl -pi -e 's/a/b/' generated/schema.ts",
                "echo hi >> migrations/001_init.sql",
                "echo hi | tee generated/out.ts",
                "rm migrations/001_init.sql",
                "echo hi > ../outside.txt",
                "echo hi >> /etc/passwd",
                "rm -rf ../outside",
                "mv src/a.py ../outside.py",
                "cp src/a.py /tmp/outside.py",
                "touch ../outside",
                "chmod 644 /etc/passwd",
                "truncate -s 0 ../outside",
                "dd if=/dev/zero of=../outside bs=1 count=1",
            ]
            for cmd in denied_cmds:
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    }
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertEqual(out["decision"], "deny", f"Expected deny for cmd={cmd}: {out}")

            allowed_cmds = [
                "git status",
                "cat README.md",
                "cat .env.example",
                "cp .env.example .env.template",
                "pytest",
                "python3 -m unittest discover -s tests -v",
                "pnpm test --filter orders",
                "python3 -m json.tool package.json > /dev/null",
                "pytest 2>&1",
                "sed -i -e '/foo/d' src/app.py",
                "echo ok > output.log",
            ]
            for cmd in allowed_cmds:
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    }
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertEqual(out["decision"], "allow", f"Expected allow for cmd={cmd}: {out}")

    def test_path_guards_confinement_artifacts_and_unattended_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worktree = root / "worktree"
            artifacts = root / "artifacts"
            (worktree / "migrations").mkdir(parents=True)
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "orders").mkdir(parents=True)
            artifacts.mkdir()

            # Forbidden paths -> deny with generalized @coordinator message
            for forbidden in ("migrations/001_init.sql", "generated/schema.ts", ".env", ".env.production"):
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "edit_file", "args": {"Path": forbidden}},
                    }
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertEqual(out["decision"], "deny", f"Failed for {forbidden}: {out}")
                self.assertIn("@coordinator", out["reason"])
                self.assertNotIn("Edit source schema", out["reason"])

            # Protected paths -> unattended-safe 'deny' by default, 'force_ask' only when interactive
            for protected in ("package.json", "pnpm-lock.yaml", "src/auth/login.ts", "src/billing/charge.ts"):
                proc_default = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    }
                )
                self.assertEqual(proc_default.returncode, 0, proc_default.stderr)
                out_default = json.loads(proc_default.stdout)
                self.assertEqual(out_default["decision"], "deny", f"Default must deny {protected}: {out_default}")
                self.assertIn("@coordinator", out_default["reason"])

                proc_interactive = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    },
                    env_overrides={"SWARM_GUARD_INTERACTIVE": "1"},
                )
                self.assertEqual(proc_interactive.returncode, 0, proc_interactive.stderr)
                out_interactive = json.loads(proc_interactive.stdout)
                self.assertEqual(
                    out_interactive["decision"],
                    "force_ask",
                    f"Interactive should force_ask {protected}: {out_interactive}",
                )

            # Path traversal outside workspace & artifacts -> deny
            for escaped in ("../outside.txt", "/etc/passwd"):
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "artifactDirectoryPath": str(artifacts),
                        "toolCall": {"name": "edit_file", "args": {"Path": escaped}},
                    }
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                out = json.loads(proc.stdout)
                self.assertEqual(out["decision"], "deny", f"Must deny escape {escaped}: {out}")
                self.assertIn("escapes", out["reason"].lower())

            # Artifact directory write (outside cwd) -> allow (supports swarm_pane screenshots)
            proc_art = run_hook(
                {
                    "cwd": str(worktree),
                    "artifactDirectoryPath": str(artifacts),
                    "toolCall": {
                        "name": "write_file",
                        "args": {"Path": str(artifacts / "screenshot.png")},
                    },
                }
            )
            self.assertEqual(proc_art.returncode, 0, proc_art.stderr)
            self.assertEqual(json.loads(proc_art.stdout)["decision"], "allow")

            # Normal workspace paths & .env.example/.sample/.template -> allow
            for allowed in (
                str(worktree / "src" / "orders" / "handler.ts"),
                ".env.example",
                ".env.sample",
                ".env.template",
            ):
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "replace_file_content", "args": {"TargetFile": allowed}},
                    }
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout)["decision"], "allow", f"Should allow {allowed}")

    def test_malformed_json_denies_by_default_and_asks_when_interactive(self) -> None:
        proc_default = run_hook("{not-valid-json")
        self.assertEqual(proc_default.returncode, 0)
        self.assertEqual(json.loads(proc_default.stdout)["decision"], "deny")

        proc_interactive = run_hook("{not-valid-json", env_overrides={"SWARM_GUARD_INTERACTIVE": "1"})
        self.assertEqual(proc_interactive.returncode, 0)
        self.assertEqual(json.loads(proc_interactive.stdout)["decision"], "ask")


class GuardrailsHooksConfigTests(unittest.TestCase):
    def test_plugin_and_hooks_json_schema_compliance(self) -> None:
        plugin = json.loads(PLUGIN_JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(plugin, {"name": "swarm-guardrails", "author": "Project Team"})

        hooks = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
        self.assertIn("swarm-pretool-guard", hooks)
        self.assertIn("swarm-posttool-format", hooks)
        self.assertIn("swarm-session-context", hooks)

        # PreToolUse: grouped with matcher & hooks
        pre_groups = hooks["swarm-pretool-guard"]["PreToolUse"]
        self.assertIsInstance(pre_groups, list)
        self.assertEqual(len(pre_groups), 1)
        self.assertEqual(
            pre_groups[0]["matcher"],
            "run_command|write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content",
        )
        pre_handler = pre_groups[0]["hooks"][0]
        self.assertEqual(pre_handler["type"], "command")
        self.assertEqual(pre_handler["command"], "python3 ./hooks/pretool-guard.py")
        self.assertEqual(pre_handler["timeout"], 5)

        # PostToolUse: disabled by default, grouped with matcher & hooks
        post_spec = hooks["swarm-posttool-format"]
        self.assertIs(post_spec["enabled"], False)
        post_groups = post_spec["PostToolUse"]
        self.assertEqual(
            post_groups[0]["matcher"],
            "write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content",
        )
        post_handler = post_groups[0]["hooks"][0]
        self.assertEqual(post_handler["type"], "command")
        self.assertEqual(post_handler["timeout"], 5)

        # SessionStart: FLAT list of handler objects (no matcher/hooks wrapper per hooks.md)
        session_handlers = hooks["swarm-session-context"]["SessionStart"]
        self.assertIsInstance(session_handlers, list)
        self.assertEqual(len(session_handlers), 1)
        self.assertNotIn("matcher", session_handlers[0])
        self.assertNotIn("hooks", session_handlers[0])
        self.assertEqual(session_handlers[0]["type"], "command")
        self.assertEqual(session_handlers[0]["timeout"], 5)

    def test_posttool_and_sessionstart_inline_dry_runs(self) -> None:
        hooks = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
        post_cmd = hooks["swarm-posttool-format"]["PostToolUse"][0]["hooks"][0]["command"]
        session_cmd = hooks["swarm-session-context"]["SessionStart"][0]["command"]

        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir)
            sample_file = worktree / "app.py"
            sample_file.write_text("x = 1\n", encoding="utf-8")

            # PostToolUse: valid payload, error payload, and malformed input must all print {} and exit 0
            for payload in (
                json.dumps(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": "app.py"}},
                    }
                ),
                json.dumps(
                    {
                        "cwd": str(worktree),
                        "error": "exit status 1",
                        "toolCall": {"name": "write_file", "args": {"Path": "app.py"}},
                    }
                ),
                "{bad-json",
            ):
                proc = subprocess.run(
                    ["sh", "-c", post_cmd],
                    input=payload,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout), {})

            # SessionStart: neither file exists
            proc_none = subprocess.run(
                ["sh", "-c", session_cmd],
                input=json.dumps({"cwd": str(worktree)}),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc_none.returncode, 0, proc_none.stderr)
            msg_none = json.loads(proc_none.stdout)["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("Swarm Guardrails active", msg_none)
            self.assertNotIn("AGENTS.md", msg_none)
            self.assertNotIn("docs/system-map.md", msg_none)

            # SessionStart: AGENTS.md only
            (worktree / "AGENTS.md").write_text("# Boundaries\n", encoding="utf-8")
            proc_agents = subprocess.run(
                ["sh", "-c", session_cmd],
                input=json.dumps({"cwd": str(worktree)}),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc_agents.returncode, 0, proc_agents.stderr)
            msg_agents = json.loads(proc_agents.stdout)["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("AGENTS.md", msg_agents)
            self.assertNotIn("docs/system-map.md", msg_agents)

            # SessionStart: both AGENTS.md and docs/system-map.md
            (worktree / "docs").mkdir()
            (worktree / "docs" / "system-map.md").write_text("# Map\n", encoding="utf-8")
            proc_both = subprocess.run(
                ["sh", "-c", session_cmd],
                input=json.dumps({"cwd": str(worktree)}),
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc_both.returncode, 0, proc_both.stderr)
            msg_both = json.loads(proc_both.stdout)["injectSteps"][0]["systemMessage"]["systemMessage"]
            self.assertIn("AGENTS.md", msg_both)
            self.assertIn("docs/system-map.md", msg_both)


if __name__ == "__main__":
    unittest.main()
