from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "skills" / "swarm-planner" / "examples"
HOOK_PATH = EXAMPLES_DIR / "pretool-guard.py"
HOOKS_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-hooks.json"
PLUGIN_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-plugin.json"
AGENTS_MD_PATH = EXAMPLES_DIR / "swarm-boundaries-AGENTS.md"


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
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "billing").mkdir(parents=True)

            denied_cmds = [
                "git push origin main",
                "git -C . push origin main",
                "git status && git -C ../repo push",
                "git \\\n push origin main",
                "npm install lodash",
                "npm i lodash",
                "npm --prefix apps/web install",
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
                "echo hi >| ../outside.txt",
                "echo hi <> ../outside.txt",
                'echo "hi >&/etc/passwd',
                "echo hi >> /etc/passwd",
                "rm -rf ../outside",
                "sudo -u root rm ../outside",
                "env -u FOO rm ../outside",
                "nice -n 10 rm ../outside",
                "timeout 5 rm ../outside",
                "echo ../outside | xargs rm",
                "xargs -n 1 rm ../outside",
                "true & rm -rf ../outside",
                "cd .. && rm outside",
                "cd migrations && rm 001_init.sql",
                "(rm ../outside)",
                "echo $(rm ../outside)",
                "echo `rm ../outside`",
                'sh -c "rm ../outside"',
                "ln -s /etc/passwd leak",
                "ln -s foo ../outside_link",
                "ln -s ../../etc/passwd src/leak",
                "mv src/a.py ../outside.py",
                "cp src/a.py /tmp/outside.py",
                "touch ../outside",
                "chmod 644 /etc/passwd",
                "truncate -s 0 ../outside",
                "dd if=/dev/zero of=../outside bs=1 count=1",
                "echo hi > $HOME/outside.txt",
                "rm ${TMPDIR}/outside",
                "echo hi > $SWARM_UNSET_TEST_VAR/outside.txt",
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
                self.assertEqual(out["decision"], "deny", f"Expected deny for cmd={cmd!r}: {out}")

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
                "cd src && pytest",
                "git ls-files | xargs grep foo",
                "npm run test -- -i",
                'sh -c "pytest"',
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
                self.assertEqual(out["decision"], "allow", f"Expected allow for cmd={cmd!r}: {out}")

    def test_run_command_enforces_protected_path_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "billing").mkdir(parents=True)

            protected_cmds = [
                "echo '{}' > package.json",
                "sed -i 's/a/b/' src/auth/login.ts",
                "rm pnpm-lock.yaml",
                "cp x src/billing/charge.ts",
                "dd if=/dev/zero of=uv.lock",
            ]
            for cmd in protected_cmds:
                proc_default = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    }
                )
                self.assertEqual(proc_default.returncode, 0, proc_default.stderr)
                out_default = json.loads(proc_default.stdout)
                self.assertEqual(out_default["decision"], "deny", f"Default must deny {cmd}: {out_default}")
                self.assertIn("@coordinator", out_default["reason"])

                proc_interactive = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    },
                    env_overrides={"SWARM_GUARD_INTERACTIVE": "1"},
                )
                self.assertEqual(proc_interactive.returncode, 0, proc_interactive.stderr)
                out_interactive = json.loads(proc_interactive.stdout)
                self.assertEqual(
                    out_interactive["decision"],
                    "force_ask",
                    f"Interactive should force_ask {cmd}: {out_interactive}",
                )

            # Read-only inspection of protected path remains allowed
            read_proc = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {
                        "name": "run_command",
                        "args": {"CommandLine": "python3 -m json.tool package.json > /dev/null"},
                    },
                }
            )
            self.assertEqual(read_proc.returncode, 0)
            self.assertEqual(json.loads(read_proc.stdout)["decision"], "allow")

    def test_case_insensitive_path_and_command_guards(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir(parents=True)
            ci_env = {"SWARM_GUARD_CASE_INSENSITIVE": "1"}

            for forbidden in (".ENV", ".ENV.PRODUCTION", "MIGRATIONS/001_init.sql"):
                proc = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": forbidden}},
                    },
                    env_overrides=ci_env,
                )
                self.assertEqual(proc.returncode, 0)
                self.assertEqual(json.loads(proc.stdout)["decision"], "deny", f"Failed for {forbidden}")

            for protected in ("Package.json", "SRC/AUTH/login.ts"):
                proc_def = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    },
                    env_overrides=ci_env,
                )
                self.assertEqual(json.loads(proc_def.stdout)["decision"], "deny", f"Failed for {protected}")
                proc_int = run_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    },
                    env_overrides={**ci_env, "SWARM_GUARD_INTERACTIVE": "1"},
                )
                self.assertEqual(json.loads(proc_int.stdout)["decision"], "force_ask", f"Failed for {protected}")

            # Case-variant shell and read_file .ENV checks
            cmd_proc = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "cat .ENV"}},
                },
                env_overrides=ci_env,
            )
            self.assertEqual(json.loads(cmd_proc.stdout)["decision"], "deny")

            read_env = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "read_file", "args": {"Path": ".ENV"}},
                },
                env_overrides=ci_env,
            )
            self.assertEqual(json.loads(read_env.stdout)["decision"], "deny")

            # .ENV.EXAMPLE remains allowed
            allow_example = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "read_file", "args": {"Path": ".ENV.EXAMPLE"}},
                },
                env_overrides=ci_env,
            )
            self.assertEqual(json.loads(allow_example.stdout)["decision"], "allow")

    def test_path_guards_confinement_read_tools_fail_closed_and_unattended_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worktree = root / "worktree"
            artifacts = root / "artifacts"
            external_doc = root / "external-skill.md"
            (worktree / "migrations").mkdir(parents=True)
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "orders").mkdir(parents=True)
            artifacts.mkdir()
            external_doc.write_text("# skill\n", encoding="utf-8")
            (worktree / ".env").write_text("SECRET=1\n", encoding="utf-8")
            symlink_to_env = worktree / "innocent.txt"
            symlink_to_env.symlink_to(worktree / ".env")

            # Read tools: block .env / .env.* / symlink->.env, allow everything else
            for read_tool in ("read_file", "view_file"):
                for blocked_read in (".env", ".env.production", "innocent.txt"):
                    proc = run_hook(
                        {
                            "cwd": str(worktree),
                            "toolCall": {"name": read_tool, "args": {"Path": blocked_read}},
                        }
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    out = json.loads(proc.stdout)
                    self.assertEqual(
                        out["decision"], "deny", f"{read_tool} must deny {blocked_read}: {out}"
                    )

                for allowed_read in (
                    "package.json",
                    "migrations/001_init.sql",
                    "src/auth/login.ts",
                    ".env.example",
                    str(external_doc),
                ):
                    proc = run_hook(
                        {
                            "cwd": str(worktree),
                            "toolCall": {"name": read_tool, "args": {"Path": allowed_read}},
                        }
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    out = json.loads(proc.stdout)
                    self.assertEqual(
                        out["decision"], "allow", f"{read_tool} should allow {allowed_read}: {out}"
                    )

            # Write/edit tools fail closed when target path is empty or missing
            for write_tool in ("write_file", "write_to_file", "multi_replace_file_content"):
                for bad_args in ({}, {"Path": ""}, {"TargetFile": "   "}):
                    proc = run_hook(
                        {
                            "cwd": str(worktree),
                            "toolCall": {"name": write_tool, "args": bad_args},
                        }
                    )
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    out = json.loads(proc.stdout)
                    self.assertEqual(
                        out["decision"], "deny", f"{write_tool} with {bad_args} must fail closed: {out}"
                    )

            # `file_path` arg key is also inspected on write/edit tools
            proc_fp = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "edit_file", "args": {"file_path": ".env"}},
                }
            )
            self.assertEqual(json.loads(proc_fp.stdout)["decision"], "deny")

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

        # PreToolUse: grouped with matcher (including read_file|view_file) & hooks
        pre_groups = hooks["swarm-pretool-guard"]["PreToolUse"]
        self.assertIsInstance(pre_groups, list)
        self.assertEqual(len(pre_groups), 1)
        self.assertEqual(
            pre_groups[0]["matcher"],
            "run_command|read_file|view_file|write_file|edit_file|write_to_file|replace_file_content|multi_replace_file_content",
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

    def test_agents_md_size_budget_and_staged_plugin_pretool_dry_run(self) -> None:
        # RSI-21: AGENTS.md must remain well under the 24 KB Antigravity rules budget
        size_bytes = AGENTS_MD_PATH.stat().st_size
        self.assertLess(size_bytes, 24 * 1024, f"AGENTS.md template too large: {size_bytes} bytes")

        hooks = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
        pre_cmd = hooks["swarm-pretool-guard"]["PreToolUse"][0]["hooks"][0]["command"]

        with tempfile.TemporaryDirectory() as tmpdir:
            repo = Path(tmpdir)
            plugin_dir = repo / ".agents" / "plugins" / "swarm-guardrails"
            hooks_dir = plugin_dir / "hooks"
            rules_dir = plugin_dir / "rules"
            hooks_dir.mkdir(parents=True)
            rules_dir.mkdir(parents=True)

            shutil.copy2(PLUGIN_JSON_PATH, plugin_dir / "plugin.json")
            shutil.copy2(HOOKS_JSON_PATH, hooks_dir / "hooks.json")
            shutil.copy2(HOOK_PATH, hooks_dir / "pretool-guard.py")
            shutil.copy2(AGENTS_MD_PATH, rules_dir / "AGENTS.md")

            payload = json.dumps(
                {
                    "cwd": str(repo),
                    "toolCall": {"name": "read_file", "args": {"Path": ".env"}},
                }
            )
            start = time.monotonic()
            proc = subprocess.run(
                ["sh", "-c", pre_cmd],
                cwd=str(plugin_dir),
                input=payload,
                text=True,
                capture_output=True,
                check=False,
            )
            elapsed = time.monotonic() - start
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertLess(elapsed, 1.0, f"Staged pretool-guard took too long: {elapsed:.3f}s")
            self.assertEqual(json.loads(proc.stdout)["decision"], "deny")

    def test_posttool_and_sessionstart_inline_dry_runs(self) -> None:
        hooks = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
        post_cmd = hooks["swarm-posttool-format"]["PostToolUse"][0]["hooks"][0]["command"]
        session_cmd = hooks["swarm-session-context"]["SessionStart"][0]["command"]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worktree = root / "worktree"
            artifacts = root / "artifacts"
            fake_bin = root / "bin"
            worktree.mkdir()
            artifacts.mkdir()
            fake_bin.mkdir()

            py_file = worktree / "app.py"
            ts_file = worktree / "app.ts"
            json_file = worktree / "config.json"
            lock_file = worktree / "package-lock.json"
            ext_md = artifacts / "notes.md"
            for f in (py_file, ts_file, json_file, lock_file, ext_md):
                f.write_text("x\n", encoding="utf-8")

            log_file = root / "prettier.log"
            fake_prettier = fake_bin / "prettier"
            fake_prettier.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log_file}'\n",
                encoding="utf-8",
            )
            fake_prettier.chmod(fake_prettier.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

            # PostToolUse: .ts and .json inside cwd invoke prettier; .py, package-lock.json, external .md, error, and bad JSON do not
            cases = [
                json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "app.ts"}}}),
                json.dumps({"cwd": str(worktree), "toolCall": {"name": "edit_file", "args": {"file_path": "config.json"}}}),
                json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "app.py"}}}),
                json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "package-lock.json"}}}),
                json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": str(ext_md)}}}),
                json.dumps(
                    {
                        "cwd": str(worktree),
                        "error": "exit status 1",
                        "toolCall": {"name": "write_file", "args": {"Path": "app.ts"}},
                    }
                ),
                "{bad-json",
            ]
            for payload in cases:
                proc = subprocess.run(
                    ["sh", "-c", post_cmd],
                    input=payload,
                    text=True,
                    capture_output=True,
                    env=env,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout), {})

            logged = log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(logged), 2, f"Unexpected prettier calls: {logged}")
            self.assertTrue(any("app.ts" in line for line in logged))
            self.assertTrue(any("config.json" in line for line in logged))
            self.assertFalse(any("app.py" in line for line in logged))
            self.assertFalse(any("package-lock.json" in line for line in logged))
            self.assertFalse(any("notes.md" in line for line in logged))

            # Slow prettier hits timeout=1.5 cleanly, still printing {} and exiting 0
            fake_prettier.write_text("#!/bin/sh\nsleep 3\n", encoding="utf-8")
            start = time.monotonic()
            slow_proc = subprocess.run(
                ["sh", "-c", post_cmd],
                input=json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "app.ts"}}}),
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            elapsed = time.monotonic() - start
            self.assertEqual(slow_proc.returncode, 0, slow_proc.stderr)
            self.assertEqual(json.loads(slow_proc.stdout), {})
            self.assertLess(elapsed, 2.8, f"PostToolUse timeout exceeded expected bound: {elapsed:.2f}s")

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
