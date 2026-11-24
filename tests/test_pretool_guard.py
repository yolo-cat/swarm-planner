from __future__ import annotations

import importlib.util
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
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = REPO_ROOT / "skills" / "swarm-planner" / "examples"
HOOK_PATH = EXAMPLES_DIR / "pretool-guard.py"
HOOKS_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-hooks.json"
PLUGIN_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-plugin.json"
AGENTS_MD_PATH = EXAMPLES_DIR / "swarm-boundaries-AGENTS.md"


def load_guard_module():
    spec = importlib.util.spec_from_file_location("pretool_guard", HOOK_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pg = load_guard_module()


def run_hook(
    payload: dict | str,
    *,
    env_overrides: dict[str, str] | None = None,
    cwd: Path | str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run pretool-guard.py as a real subprocess CLI (for targeted CLI smoke tests)."""
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    env = os.environ.copy()
    env.pop("SWARM_GUARD_INTERACTIVE", None)
    env.pop("SWARM_GUARD_CASE_INSENSITIVE", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=raw,
        text=True,
        capture_output=True,
        env=env,
        cwd=str(cwd) if cwd is not None else None,
        check=False,
    )


def eval_hook(
    payload: dict,
    *,
    env_overrides: dict[str, str] | None = None,
) -> dict:
    """Fast in-process evaluation of check_tool_call() with isolated env vars."""
    clean_env = os.environ.copy()
    clean_env.pop("SWARM_GUARD_INTERACTIVE", None)
    clean_env.pop("SWARM_GUARD_CASE_INSENSITIVE", None)
    if env_overrides:
        clean_env.update(env_overrides)
    with mock.patch.dict(os.environ, clean_env, clear=True):
        return pg.check_tool_call(payload)


class PretoolGuardTests(unittest.TestCase):
    def test_command_guards_and_bypasses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worktree = root / "worktree"
            (worktree / "migrations").mkdir(parents=True)
            (worktree / "generated").mkdir(parents=True)
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "billing").mkdir(parents=True)
            outside_target = root / "outside_real.txt"
            outside_target.write_text("outside\n", encoding="utf-8")
            escape_link = worktree / "escape_link.txt"
            escape_link.symlink_to(outside_target)

            denied_cmds = [
                # Original baseline bypasses
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
                # RSI3-01: quote-splitting, backslash escapes, globs, and brace expansions
                'git p""ush origin main',
                r"git p\ush origin main",
                'npm in""stall lodash',
                r"npm in\stall lodash",
                "drop''db app_dev",
                'cat .""env',
                "cat '.e'nv",
                r"cat \.env",
                r"cat < \.env",
                "cat .env*",
                "cat .env.*",
                "cat {.env,README.md}",
                # RSI3-02 & RSI3-08: inline shell post--c options/--, eval --, here-strings/pipes, xargs ordering
                'sh -c -- "rm ../outside"',
                'sh -c - "rm ../outside"',
                'bash -c -- "rm ../outside"',
                'bash -c -e "rm ../outside"',
                'bash -O extglob -c "rm ../outside"',
                'bash +O extglob -c "rm ../outside"',
                'bash -c -O extglob "rm ../outside"',
                'bash -cO extglob "rm ../outside"',
                'bash +eO extglob -c "rm ../outside"',
                'bash +123 -c "rm ../outside"',
                'eval -- "rm ../outside"',
                'bash <<< "rm ../outside"',
                'bash <<< "echo hi > ../outside"',
                'echo "rm ../outside" | sh',
                'echo ../outside | xargs -I{} sh -c "rm {}"',
                "env -C .. rm outside",
                "env --chdir=.. rm outside",
                "env -C migrations rm 001_init.sql",
                # RSI3-03: quote-unaware segment splitting
                'sh -c "rm ../outside; echo ok"',
                'sh -c "cd .. && rm outside"',
                'eval "rm ../outside; echo ok"',
                'rm "x;y" ../outside',
                'mv "x;y" migrations/001_init.sql',
                # RSI3-07: attached --option=PATH, perl -e/-E, sed w, stale $PWD, directory ln target
                "cp --target-directory=../outside src/a.py",
                "mv --target-directory=../outside src/a.py",
                "ln -s --target-directory=../outside src/a.py",
                "patch --directory=.. -p1",
                "patch -o../outside -i p.diff",
                "perl -e \"unlink('../outside')\"",
                "perl -E \"unlink('../outside')\"",
                'sed -n "w ../outside" package.json',
                "sed -i '' 'w ../outside' package.json",
                'sed "s/a/b/w ../outside" package.json',
                'cd .. && rm "$PWD/outside"',
                "ln -s auth/login.ts src",
                # RSI3-10: compound blocks, exec, wrapper -D/-S/bundled flags, $'...', >(...)
                "{ rm ../outside; }",
                "if true; then rm ../outside; fi",
                "true && ! rm ../outside",
                "time (rm ../outside)",
                "exec rm ../outside",
                'env -S "rm ../outside"',
                'env --split-string="rm ../outside"',
                "sudo -D .. rm outside",
                "xargs -rn 1 rm ../outside",
                "timeout -vk 5 10 rm ../outside",
                "echo hi | tee >(dd of=../outside)",
                "$'rm' ../outside",
                # RSI3-15: previously uncovered parser, wrapper, redir, separator, and symlink branches
                'eval "rm ../outside"',
                "pushd .. && rm outside",
                "cd - && rm outside",
                "cd && rm outside",
                "cd $SWARM_UNSET_DIR && rm foo",
                'bash -lc "rm ../outside"',
                "bash -c",
                "sh -c 'sh -c \"sh -c \\\"sh -c \\\\\\\"sh -c \\\\\\\\\\\\\\\"sh -c pytest\\\\\\\\\\\\\\\"\\\\\\\"\\\"\"'",
                "rsync -a src/ ../outside/",
                "patch ../outside",
                "install -m 755 src/a.py ../outside",
                "unlink ../outside",
                "chown root ../outside",
                "command rm ../outside",
                "nohup rm ../outside",
                "stdbuf -o 0 rm ../outside",
                "doas -u root rm ../outside",
                "ionice -c 3 rm ../outside",
                "time -f %e rm ../outside",
                "sudo -- rm ../outside",
                "timeout -k 5 10 rm ../outside",
                "timeout --kill-after=5 10 rm ../outside",
                "echo hi &> ../outside",
                "echo hi &>> ../outside",
                "FOO=1 rm ../outside",
                "false || rm ../outside",
                "true; rm ../outside",
                "true\nrm ../outside",
                "sed --in-place 's/a/b/' ../outside",
                "echo hi > escape_link.txt",
            ]
            for cmd in denied_cmds:
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    }
                )
                self.assertEqual(out["decision"], "deny", f"Expected deny for cmd={cmd!r}: {out}")

            # Verify deep nesting > MAX_RECURSION_DEPTH fails closed cleanly
            deep = "pytest"
            for _ in range(pg.MAX_RECURSION_DEPTH + 2):
                deep = f"eval {json.dumps(deep)}"
            deep_out = eval_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "run_command", "args": {"CommandLine": deep}},
                }
            )
            self.assertEqual(deep_out["decision"], "deny", f"Expected recursion deny: {deep_out}")

            allowed_cmds = [
                "git status",
                "cat README.md",
                "cat .env.example",
                "cat {.env.example,.env.template}",
                "cp .env.example .env.template",
                "pytest",
                "python3 -m unittest discover -s tests -v",
                "pnpm test --filter orders",
                "python3 -m json.tool package.json > /dev/null",
                "pytest 2>&1",
                "pytest 2>&-",
                "sed -i -e '/foo/d' src/app.py",
                "echo ok > output.log",
                "cd src && pytest",
                "cd src && cd - && rm src/a.py",
                "pushd .. && popd && rm src/a.py",
                "git ls-files | xargs grep foo",
                "npm run test -- -i",
                'sh -c "pytest"',
                'echo "a;b" && pytest',
                "dd if=/dev/zero of=/dev/null bs=1 count=1",
                "echo hi | tee /dev/null",
            ]
            for cmd in allowed_cmds:
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    }
                )
                self.assertEqual(out["decision"], "allow", f"Expected allow for cmd={cmd!r}: {out}")

            # RSI3-09 & RSI3-15: whitespace CommandLine falls back to lowercase `command`
            ws_cmd = eval_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {
                        "name": "run_command",
                        "args": {"CommandLine": "   ", "command": "rm ../outside"},
                    },
                }
            )
            self.assertEqual(ws_cmd["decision"], "deny")

    def test_run_command_enforces_protected_path_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "billing").mkdir(parents=True)

            protected_cmds = [
                "echo '{}' > package.json",
                "echo '{}' > package-lock.json",
                "sed -i 's/a/b/' src/auth/login.ts",
                "rm pnpm-lock.yaml",
                "rm Cargo.lock",
                "cp x src/billing/charge.ts",
                "dd if=/dev/zero of=uv.lock",
                "ln -s auth/login.ts src",
            ]
            for cmd in protected_cmds:
                out_default = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    }
                )
                self.assertEqual(out_default["decision"], "deny", f"Default must deny {cmd}: {out_default}")
                self.assertIn("@coordinator", out_default["reason"])

                out_interactive = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "run_command", "args": {"CommandLine": cmd}},
                    },
                    env_overrides={"SWARM_GUARD_INTERACTIVE": "1"},
                )
                self.assertEqual(
                    out_interactive["decision"],
                    "force_ask",
                    f"Interactive should force_ask {cmd}: {out_interactive}",
                )

            read_out = eval_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {
                        "name": "run_command",
                        "args": {"CommandLine": "python3 -m json.tool package.json > /dev/null"},
                    },
                }
            )
            self.assertEqual(read_out["decision"], "allow")

    def test_case_insensitive_and_case_sensitive_modes_on_any_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir(parents=True)
            ci_env = {"SWARM_GUARD_CASE_INSENSITIVE": "1"}
            cs_env = {"SWARM_GUARD_CASE_INSENSITIVE": "0"}

            # Explicit case-insensitive mode (SWARM_GUARD_CASE_INSENSITIVE=1)
            for forbidden in (".ENV", ".ENV.PRODUCTION", "MIGRATIONS/001_init.sql"):
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": forbidden}},
                    },
                    env_overrides=ci_env,
                )
                self.assertEqual(out["decision"], "deny", f"Failed for {forbidden}")

            for protected in ("Package.json", "SRC/AUTH/login.ts"):
                out_def = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    },
                    env_overrides=ci_env,
                )
                self.assertEqual(out_def["decision"], "deny", f"Failed for {protected}")
                out_int = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    },
                    env_overrides={**ci_env, "SWARM_GUARD_INTERACTIVE": "1"},
                )
                self.assertEqual(out_int["decision"], "force_ask", f"Failed for {protected}")

            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "run_command", "args": {"CommandLine": "cat .ENV"}}},
                    env_overrides=ci_env,
                )["decision"],
                "deny",
            )
            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "read_file", "args": {"Path": ".ENV"}}},
                    env_overrides=ci_env,
                )["decision"],
                "deny",
            )
            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "read_file", "args": {"Path": ".ENV.EXAMPLE"}}},
                    env_overrides=ci_env,
                )["decision"],
                "allow",
            )

            # RSI3-29: Explicit case-sensitive mode (SWARM_GUARD_CASE_INSENSITIVE=0) works even on macOS/Windows
            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "read_file", "args": {"Path": ".ENV"}}},
                    env_overrides=cs_env,
                )["decision"],
                "allow",
            )
            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "read_file", "args": {"Path": ".env"}}},
                    env_overrides=cs_env,
                )["decision"],
                "deny",
            )
            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "Package.json"}}},
                    env_overrides=cs_env,
                )["decision"],
                "allow",
            )
            self.assertEqual(
                eval_hook(
                    {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "package.json"}}},
                    env_overrides=cs_env,
                )["decision"],
                "deny",
            )

    def test_path_guards_confinement_read_tools_fail_closed_and_unattended_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worktree = root / "worktree"
            artifacts = root / "artifacts"
            plugin_dir = worktree / ".agents" / "plugins" / "swarm-guardrails"
            external_doc = root / "external-skill.md"
            outside_target = root / "outside_write.txt"
            (worktree / "migrations").mkdir(parents=True)
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "orders").mkdir(parents=True)
            (worktree / "subdir").mkdir(parents=True)
            (worktree / "rel_artifacts").mkdir(parents=True)
            plugin_dir.mkdir(parents=True)
            artifacts.mkdir()
            external_doc.write_text("# skill\n", encoding="utf-8")
            outside_target.write_text("secret\n", encoding="utf-8")
            (worktree / ".env").write_text("SECRET=1\n", encoding="utf-8")
            (worktree / "subdir" / ".env").write_text("SECRET=2\n", encoding="utf-8")
            symlink_to_env = worktree / "innocent.txt"
            symlink_to_env.symlink_to(worktree / ".env")
            symlink_outside = worktree / "escape_write.txt"
            symlink_outside.symlink_to(outside_target)

            # Read tools: block .env / .env.* / subdir/.env / symlink->.env across Path and AbsolutePath (RSI3-04/09/15)
            for read_tool, key in (
                ("read_file", "Path"),
                ("view_file", "Path"),
                ("view_file", "AbsolutePath"),
            ):
                for blocked_read in (
                    ".env",
                    ".env.production",
                    "subdir/.env",
                    "innocent.txt",
                    str(worktree / ".env.production"),
                    str(symlink_to_env),
                ):
                    out = eval_hook(
                        {
                            "cwd": str(worktree),
                            "toolCall": {"name": read_tool, "args": {key: blocked_read}},
                        }
                    )
                    self.assertEqual(
                        out["decision"], "deny", f"{read_tool} ({key}) must deny {blocked_read}: {out}"
                    )

                for allowed_read in (
                    "package.json",
                    "migrations/001_init.sql",
                    "src/auth/login.ts",
                    ".env.example",
                    str(external_doc),
                ):
                    out = eval_hook(
                        {
                            "cwd": str(worktree),
                            "toolCall": {"name": read_tool, "args": {key: allowed_read}},
                        }
                    )
                    self.assertEqual(
                        out["decision"], "allow", f"{read_tool} ({key}) should allow {allowed_read}: {out}"
                    )

            # RSI3-09: READ_TOOLS whitespace shadowing, non-string args, and empty/missing args fail closed
            for bad_read_args in (
                {"Path": "   ", "TargetFile": ".env"},
                {"Path": [".env"]},
                {},
                {"Path": ""},
                {"AbsolutePath": "   "},
            ):
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "read_file", "args": bad_read_args},
                    }
                )
                self.assertEqual(out["decision"], "deny", f"Expected deny for {bad_read_args}: {out}")

            # Write/edit tools fail closed when target path is empty, missing, or non-string
            for write_tool in ("write_file", "write_to_file", "multi_replace_file_content"):
                for bad_args in ({}, {"Path": ""}, {"TargetFile": "   "}, {"Path": ["a.txt"]}):
                    out = eval_hook(
                        {
                            "cwd": str(worktree),
                            "toolCall": {"name": write_tool, "args": bad_args},
                        }
                    )
                    self.assertEqual(
                        out["decision"], "deny", f"{write_tool} with {bad_args} must fail closed: {out}"
                    )

            # `file_path`, `path`, and symlink escaping workspace are inspected on write/edit tools
            for args in (
                {"file_path": ".env"},
                {"path": "../outside.txt"},
                {"Path": "escape_write.txt"},
            ):
                out = eval_hook({"cwd": str(worktree), "toolCall": {"name": "edit_file", "args": args}})
                self.assertEqual(out["decision"], "deny", f"Expected deny for {args}: {out}")

            # Forbidden paths -> deny with generalized @coordinator message
            for forbidden in ("migrations/001_init.sql", "generated/schema.ts", ".env", ".env.production"):
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "edit_file", "args": {"Path": forbidden}},
                    }
                )
                self.assertEqual(out["decision"], "deny", f"Failed for {forbidden}: {out}")
                self.assertIn("@coordinator", out["reason"])
                self.assertNotIn("Edit source schema", out["reason"])

            # Protected paths -> unattended-safe 'deny' by default, 'force_ask' only when interactive
            for protected in (
                "package.json",
                "package-lock.json",
                "pnpm-lock.yaml",
                "Cargo.lock",
                "uv.lock",
                "src/auth/login.ts",
                "src/billing/charge.ts",
            ):
                out_default = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    }
                )
                self.assertEqual(out_default["decision"], "deny", f"Default must deny {protected}: {out_default}")
                self.assertIn("@coordinator", out_default["reason"])

                out_interactive = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "write_file", "args": {"Path": protected}},
                    },
                    env_overrides={"SWARM_GUARD_INTERACTIVE": "1"},
                )
                self.assertEqual(
                    out_interactive["decision"],
                    "force_ask",
                    f"Interactive should force_ask {protected}: {out_interactive}",
                )

            # Path traversal outside workspace & artifacts -> deny
            for escaped in ("../outside.txt", "/etc/passwd"):
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "artifactDirectoryPath": str(artifacts),
                        "toolCall": {"name": "edit_file", "args": {"Path": escaped}},
                    }
                )
                self.assertEqual(out["decision"], "deny", f"Must deny escape {escaped}: {out}")
                self.assertIn("escapes", out["reason"].lower())

            # Artifact directory write (outside cwd) -> allow for screenshot, deny for .env (RSI3-09)
            out_art = eval_hook(
                {
                    "cwd": str(worktree),
                    "artifactDirectoryPath": str(artifacts),
                    "toolCall": {
                        "name": "write_file",
                        "args": {"Path": str(artifacts / "screenshot.png")},
                    },
                }
            )
            self.assertEqual(out_art["decision"], "allow")

            out_art_env = eval_hook(
                {
                    "cwd": str(worktree),
                    "artifactDirectoryPath": str(artifacts),
                    "toolCall": {
                        "name": "write_file",
                        "args": {"Path": str(artifacts / ".env")},
                    },
                }
            )
            self.assertEqual(out_art_env["decision"], "deny")

            # RSI3-09: Relative artifactDirectoryPath resolves against payload["cwd"], NOT hook os.getcwd()
            prev_cwd = os.getcwd()
            try:
                os.chdir(plugin_dir)
                out_rel_art = eval_hook(
                    {
                        "cwd": str(worktree),
                        "artifactDirectoryPath": "rel_artifacts",
                        "toolCall": {
                            "name": "write_file",
                            "args": {"Path": str(worktree / "rel_artifacts" / "shot.png")},
                        },
                    }
                )
                self.assertEqual(out_rel_art["decision"], "allow")

                # RSI3-11: workspacePaths[0] fallback when cwd is omitted
                out_ws_fallback = eval_hook(
                    {
                        "workspacePaths": [str(worktree)],
                        "toolCall": {
                            "name": "write_file",
                            "args": {"Path": "src/orders/handler.ts"},
                        },
                    }
                )
                self.assertEqual(out_ws_fallback["decision"], "allow")

                out_ws_escape = eval_hook(
                    {
                        "workspacePaths": [str(worktree)],
                        "toolCall": {
                            "name": "write_file",
                            "args": {"Path": "../outside.txt"},
                        },
                    }
                )
                self.assertEqual(out_ws_escape["decision"], "deny")
            finally:
                os.chdir(prev_cwd)

            # Normal workspace paths & .env.example/.sample/.template -> allow
            for allowed in (
                str(worktree / "src" / "orders" / "handler.ts"),
                ".env.example",
                ".env.sample",
                ".env.template",
            ):
                out = eval_hook(
                    {
                        "cwd": str(worktree),
                        "toolCall": {"name": "replace_file_content", "args": {"TargetFile": allowed}},
                    }
                )
                self.assertEqual(out["decision"], "allow", f"Should allow {allowed}")

    def test_cli_subprocess_smoke_and_malformed_or_nondict_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir) / "worktree"
            worktree.mkdir()

            # Targeted CLI subprocess smoke tests: allow, deny, interactive force_ask
            allow_proc = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "run_command", "args": {"CommandLine": "pytest"}},
                }
            )
            self.assertEqual(allow_proc.returncode, 0, allow_proc.stderr)
            self.assertEqual(json.loads(allow_proc.stdout)["decision"], "allow")

            deny_proc = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "view_file", "args": {"AbsolutePath": ".env"}},
                }
            )
            self.assertEqual(deny_proc.returncode, 0, deny_proc.stderr)
            self.assertEqual(json.loads(deny_proc.stdout)["decision"], "deny")

            ask_proc = run_hook(
                {
                    "cwd": str(worktree),
                    "toolCall": {"name": "write_file", "args": {"Path": "package.json"}},
                },
                env_overrides={"SWARM_GUARD_INTERACTIVE": "1"},
            )
            self.assertEqual(ask_proc.returncode, 0, ask_proc.stderr)
            self.assertEqual(json.loads(ask_proc.stdout)["decision"], "force_ask")

        # Malformed and non-dict JSON payloads fail closed (deny default, ask interactive)
        for bad_raw in ("{not-valid-json", "[]", "null"):
            proc_default = run_hook(bad_raw)
            self.assertEqual(proc_default.returncode, 0)
            self.assertEqual(json.loads(proc_default.stdout)["decision"], "deny")

            proc_interactive = run_hook(bad_raw, env_overrides={"SWARM_GUARD_INTERACTIVE": "1"})
            self.assertEqual(proc_interactive.returncode, 0)
            self.assertEqual(json.loads(proc_interactive.stdout)["decision"], "ask")


class GuardrailsHooksConfigTests(unittest.TestCase):
    def test_plugin_and_hooks_json_schema_compliance(self) -> None:
        plugin = json.loads(PLUGIN_JSON_PATH.read_text(encoding="utf-8"))
        self.assertEqual(
            plugin,
            {
                "name": "swarm-guardrails",
                "version": "1.0.0",
                "author": "Project Team",
                "description": "Pre-session guardrail hooks and boundary rules for Antigravity swarms.",
            },
        )

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

            # RSI3-16: hooks.json MUST live at plugin root (<plugin_dir>/hooks.json), never hooks/hooks.json
            staged_hooks_json = plugin_dir / "hooks.json"
            shutil.copy2(PLUGIN_JSON_PATH, plugin_dir / "plugin.json")
            shutil.copy2(HOOKS_JSON_PATH, staged_hooks_json)
            shutil.copy2(HOOK_PATH, hooks_dir / "pretool-guard.py")
            shutil.copy2(AGENTS_MD_PATH, rules_dir / "AGENTS.md")

            self.assertTrue(staged_hooks_json.is_file())
            self.assertFalse((hooks_dir / "hooks.json").exists())

            # Execute from hooks.json's parent directory, matching hooks.md:131
            payload = json.dumps(
                {
                    "workspacePaths": [str(repo)],
                    "toolCall": {"name": "view_file", "args": {"AbsolutePath": ".env"}},
                }
            )
            proc = subprocess.run(
                ["sh", "-c", pre_cmd],
                cwd=str(staged_hooks_json.parent),
                input=payload,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout)["decision"], "deny")

    def test_posttool_and_sessionstart_inline_dry_runs(self) -> None:
        hooks = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
        post_cmd = hooks["swarm-posttool-format"]["PostToolUse"][0]["hooks"][0]["command"]
        session_cmd = hooks["swarm-session-context"]["SessionStart"][0]["command"]

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            worktree = root / "worktree"
            plugin_dir = worktree / ".agents" / "plugins" / "swarm-guardrails"
            artifacts = root / "artifacts"
            fake_bin = root / "bin"
            worktree.mkdir()
            plugin_dir.mkdir(parents=True)
            artifacts.mkdir()
            fake_bin.mkdir()

            # Create files for all Prettier extensions plus excluded files & escaping symlink
            ext_files = [
                worktree / "a.js",
                worktree / "b.jsx",
                worktree / "c.ts",
                worktree / "d.tsx",
                worktree / "e.css",
                worktree / "f.scss",
                worktree / "g.json",
                worktree / "h.md",
                worktree / "i.yaml",
                worktree / "j.yml",
            ]
            py_file = worktree / "app.py"
            lock_file = worktree / "package-lock.json"
            nested_lock = worktree / "apps" / "web" / "package-lock.json"
            nested_lock.parent.mkdir(parents=True)
            upper_lock = worktree / "PACKAGE-LOCK.JSON"
            ext_md = artifacts / "notes.md"
            for f in (*ext_files, py_file, lock_file, nested_lock, upper_lock, ext_md):
                f.write_text("x\n", encoding="utf-8")
            symlink_ext = worktree / "link_outside.md"
            symlink_ext.symlink_to(ext_md)

            log_file = root / "prettier.log"
            fake_prettier = fake_bin / "prettier"
            fake_prettier.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{log_file}'\n",
                encoding="utf-8",
            )
            fake_prettier.chmod(fake_prettier.stat().st_mode | stat.S_IEXEC)

            env_with_prettier = os.environ.copy()
            env_with_prettier["PATH"] = f"{fake_bin}{os.pathsep}{env_with_prettier.get('PATH', '')}"

            # PostToolUse: all 10 extensions + arg keys (Path, TargetFile, AbsolutePath, path, file_path) + workspacePaths fallback
            formatted_cases = [
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "a.js"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"TargetFile": "b.jsx"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"AbsolutePath": "c.ts"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"path": "d.tsx"}}},
                {"cwd": str(worktree), "toolCall": {"name": "edit_file", "args": {"file_path": "e.css"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "f.scss"}}},
                {"cwd": str(worktree), "toolCall": {"name": "edit_file", "args": {"file_path": "g.json"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "h.md"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "i.yaml"}}},
                {"workspacePaths": [str(worktree)], "toolCall": {"name": "write_file", "args": {"Path": "j.yml"}}},
            ]
            skipped_cases: list[dict | str] = [
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "app.py"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "package-lock.json"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "apps/web/package-lock.json"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "PACKAGE-LOCK.JSON"}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": str(ext_md)}}},
                {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "link_outside.md"}}},
                {
                    "cwd": str(worktree),
                    "error": "exit status 1",
                    "toolCall": {"name": "write_file", "args": {"Path": "c.ts"}},
                },
                "{bad-json",
                "null",
                "[]",
            ]
            for item in (*formatted_cases, *skipped_cases):
                raw = item if isinstance(item, str) else json.dumps(item)
                proc = subprocess.run(
                    ["sh", "-c", post_cmd],
                    cwd=str(plugin_dir),
                    input=raw,
                    text=True,
                    capture_output=True,
                    env=env_with_prettier,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(json.loads(proc.stdout), {})

            logged = log_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(logged), 10, f"Unexpected prettier calls: {logged}")
            for expected in ext_files:
                self.assertTrue(any(expected.name in line for line in logged), f"Missing {expected.name} in {logged}")
            for forbidden in ("app.py", "package-lock.json", "PACKAGE-LOCK.JSON", "notes.md", "link_outside.md"):
                self.assertFalse(any(forbidden in line for line in logged), f"Should skip {forbidden}: {logged}")

            # RSI3-27: Missing prettier on PATH and no node_modules/.bin/prettier -> clean no-op {}
            no_prettier_bin = root / "no_prettier_bin"
            no_prettier_bin.mkdir()
            for tool in ("sh", "python3"):
                resolved = shutil.which(tool)
                if resolved:
                    (no_prettier_bin / tool).symlink_to(resolved)
            env_no_prettier = os.environ.copy()
            env_no_prettier["PATH"] = str(no_prettier_bin)

            proc_no_prettier = subprocess.run(
                ["sh", "-c", post_cmd],
                cwd=str(plugin_dir),
                input=json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "c.ts"}}}),
                text=True,
                capture_output=True,
                env=env_no_prettier,
                check=False,
            )
            self.assertEqual(proc_no_prettier.returncode, 0, proc_no_prettier.stderr)
            self.assertEqual(json.loads(proc_no_prettier.stdout), {})

            # RSI3-26: Local <worktree>/node_modules/.bin/prettier fallback when prettier is absent from PATH
            local_log = root / "local_prettier.log"
            local_prettier = worktree / "node_modules" / ".bin" / "prettier"
            local_prettier.parent.mkdir(parents=True)
            local_prettier.write_text(
                f"#!/bin/sh\nprintf '%s\\n' \"$*\" >> '{local_log}'\n",
                encoding="utf-8",
            )
            local_prettier.chmod(local_prettier.stat().st_mode | stat.S_IEXEC)

            proc_local = subprocess.run(
                ["sh", "-c", post_cmd],
                cwd=str(plugin_dir),
                input=json.dumps(
                    {
                        "workspacePaths": [str(worktree)],
                        "toolCall": {"name": "write_file", "args": {"AbsolutePath": "c.ts"}},
                    }
                ),
                text=True,
                capture_output=True,
                env=env_no_prettier,
                check=False,
            )
            self.assertEqual(proc_local.returncode, 0, proc_local.stderr)
            self.assertEqual(json.loads(proc_local.stdout), {})
            local_logged = local_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(local_logged), 1)
            self.assertIn("c.ts", local_logged[0])

            # Slow prettier hits timeout=1.5 cleanly, still printing {} and exiting 0 (generous upper bound vs sleep 6)
            fake_prettier.write_text("#!/bin/sh\nsleep 6\n", encoding="utf-8")
            start = time.monotonic()
            slow_proc = subprocess.run(
                ["sh", "-c", post_cmd],
                input=json.dumps({"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": "c.ts"}}}),
                text=True,
                capture_output=True,
                env=env_with_prettier,
                check=False,
            )
            elapsed = time.monotonic() - start
            self.assertEqual(slow_proc.returncode, 0, slow_proc.stderr)
            self.assertEqual(json.loads(slow_proc.stdout), {})
            self.assertLess(elapsed, 4.5, f"PostToolUse timeout failed to abort sleep 6 early: {elapsed:.2f}s")

            # SessionStart: malformed, empty, and non-dict JSON stdin (RSI3-11 & RSI3-27)
            for edge_stdin in ("null", "[]", "123", "", "{bad-json", "{}"):
                proc_edge = subprocess.run(
                    ["sh", "-c", session_cmd],
                    cwd=str(plugin_dir),
                    input=edge_stdin,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(proc_edge.returncode, 0, f"SessionStart failed on {edge_stdin!r}: {proc_edge.stderr}")
                parsed = json.loads(proc_edge.stdout)
                self.assertIn("Swarm Guardrails active", parsed["injectSteps"][0]["systemMessage"]["systemMessage"])

            # SessionStart: neither file exists
            proc_none = subprocess.run(
                ["sh", "-c", session_cmd],
                cwd=str(plugin_dir),
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

            # SessionStart: AGENTS.md only (tested via workspacePaths[0] fallback when cwd is omitted!)
            (worktree / "AGENTS.md").write_text("# Boundaries\n", encoding="utf-8")
            proc_agents = subprocess.run(
                ["sh", "-c", session_cmd],
                cwd=str(plugin_dir),
                input=json.dumps({"workspacePaths": [str(worktree)]}),
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
                cwd=str(plugin_dir),
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
