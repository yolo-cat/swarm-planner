from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = REPO_ROOT / "skills" / "swarm-planner"
EXAMPLES_DIR = SKILL_DIR / "examples"
REFERENCES_DIR = SKILL_DIR / "references"
HOOK_PATH = EXAMPLES_DIR / "pretool-guard.py"
HOOKS_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-hooks.json"
PLUGIN_JSON_PATH = EXAMPLES_DIR / "swarm-guardrails-plugin.json"
AGENTS_MD_PATH = EXAMPLES_DIR / "swarm-boundaries-AGENTS.md"
MODEL_MATRIX_PATH = SKILL_DIR / "scripts" / "model_matrix.py"
INSTALL_SCRIPT_PATH = REPO_ROOT / "scripts" / "install.sh"
MAKEFILE_PATH = REPO_ROOT / "Makefile"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pg = _load_module("pretool_guard_contract", HOOK_PATH)
mm = _load_module("model_matrix_contract", MODEL_MATRIX_PATH)


def _extract_balanced_braces(text: str, open_idx: int) -> str | None:
    depth = 0
    in_single = False
    in_double = False
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if in_single:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx : i + 1]
        i += 1
    return None


class CrossModuleContractTests(unittest.TestCase):
    def test_hooks_json_matchers_match_pretool_guard_tool_sets(self) -> None:
        hooks = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
        pre_matcher = set(hooks["swarm-pretool-guard"]["PreToolUse"][0]["matcher"].split("|"))
        post_matcher = set(hooks["swarm-posttool-format"]["PostToolUse"][0]["matcher"].split("|"))

        expected_pre = pg.READ_TOOLS | pg.WRITE_TOOLS | {"run_command"}
        expected_post = set(pg.WRITE_TOOLS)

        self.assertEqual(pre_matcher, expected_pre)
        self.assertEqual(post_matcher, expected_post)

    def test_agents_md_protected_and_env_paths_trigger_pretool_guard(self) -> None:
        agents_text = AGENTS_MD_PATH.read_text(encoding="utf-8")

        # Extract the bullet describing central registries, lockfiles & protected modules
        protected_block_match = re.search(
            r"Central registries, lockfiles.*?(?=\n\n|\n- |\Z)",
            agents_text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(protected_block_match, "Expected protected modules bullet in AGENTS.md")
        protected_block = protected_block_match.group(0)

        # Collect backticked path examples (skipping placeholders <...> and symbols like PreToolUse/@coordinator)
        backticked = re.findall(r"`([^`]+)`", protected_block)
        protected_paths = [
            tok
            for tok in backticked
            if not tok.startswith(("<", "@"))
            and tok not in {"PROTECTED_PATH_PATTERNS", "pretool-guard.py", "PreToolUse", "deny", "SWARM_GUARD_INTERACTIVE=1"}
            and ("." in tok or "/" in tok)
        ]
        # Verify lockfiles explicitly called out in RSI3-31 are present
        for required in (
            "package.json",
            "package-lock.json",
            "pnpm-lock.yaml",
            "Cargo.lock",
            "uv.lock",
            "src/auth/",
            "src/billing/",
        ):
            self.assertIn(required, protected_paths, f"Missing {required} in AGENTS.md protected paths")

        with tempfile.TemporaryDirectory() as tmpdir:
            worktree = Path(tmpdir)
            (worktree / "src" / "auth").mkdir(parents=True)
            (worktree / "src" / "billing").mkdir(parents=True)

            clean_env = os.environ.copy()
            clean_env.pop("SWARM_GUARD_INTERACTIVE", None)
            clean_env.pop("SWARM_GUARD_CASE_INSENSITIVE", None)

            for raw in protected_paths:
                sample = f"{raw}sample.ts" if raw.endswith("/") else raw
                with mock.patch.dict(os.environ, clean_env, clear=True):
                    write_def = pg.check_tool_call(
                        {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": sample}}}
                    )
                    cmd_def = pg.check_tool_call(
                        {"cwd": str(worktree), "toolCall": {"name": "run_command", "args": {"CommandLine": f"rm {sample}"}}}
                    )
                self.assertEqual(write_def["decision"], "deny", f"write_file should deny {sample}")
                self.assertEqual(cmd_def["decision"], "deny", f"run_command should deny {sample}")

                with mock.patch.dict(os.environ, {**clean_env, "SWARM_GUARD_INTERACTIVE": "1"}, clear=True):
                    write_int = pg.check_tool_call(
                        {"cwd": str(worktree), "toolCall": {"name": "write_file", "args": {"Path": sample}}}
                    )
                    cmd_int = pg.check_tool_call(
                        {"cwd": str(worktree), "toolCall": {"name": "run_command", "args": {"CommandLine": f"rm {sample}"}}}
                    )
                self.assertEqual(write_int["decision"], "force_ask", f"Interactive write_file should force_ask {sample}")
                self.assertEqual(cmd_int["decision"], "force_ask", f"Interactive run_command should force_ask {sample}")

            # Verify .env exclusions documented in AGENTS.md match pretool-guard.py
            for safe_env in (".env.example", ".env.sample", ".env.template"):
                self.assertIn(safe_env, agents_text)
                with mock.patch.dict(os.environ, clean_env, clear=True):
                    self.assertEqual(
                        pg.check_tool_call(
                            {"cwd": str(worktree), "toolCall": {"name": "view_file", "args": {"AbsolutePath": safe_env}}}
                        )["decision"],
                        "allow",
                    )
            for secret_env in (".env", ".env.local"):
                with mock.patch.dict(os.environ, clean_env, clear=True):
                    self.assertEqual(
                        pg.check_tool_call(
                            {"cwd": str(worktree), "toolCall": {"name": "view_file", "args": {"AbsolutePath": secret_env}}}
                        )["decision"],
                        "deny",
                    )

    def test_coarse_workflow_tiers_inline_schemas_and_markdown_links(self) -> None:
        # 1. Coarse /run-workflow tiers must NEVER pass model_matrix.py --validate
        sample_entries = mm.parse_swarm_json(
            json.dumps(
                {
                    "models": [
                        "gemini-3-flash-low",
                        "gemini-3-flash-high",
                        "gemini-pro-orchestrator",
                        "claude-sonnet-4-6-high",
                    ],
                    "quotas": {
                        "gemini-3-flash-low": {"quota_remaining": "90%"},
                        "gemini-3-flash-high": {"quota_remaining": "90%"},
                        "gemini-pro-orchestrator": {"quota_remaining": "90%"},
                        "claude-sonnet-4-6-high": {"quota_remaining": "90%"},
                    },
                }
            )
        )
        for coarse_tier in ("inherit", "flash_lite", "flash", "pro"):
            ok, msgs = mm.validate_models(sample_entries, [coarse_tier])
            self.assertFalse(ok, f"Coarse tier {coarse_tier!r} must fail model_matrix.py --validate: {msgs}")

        # 2. Inline `schema={...}` dicts in task-matrices.md parse cleanly as valid JSON Schema dicts
        task_matrices_text = (REFERENCES_DIR / "task-matrices.md").read_text(encoding="utf-8")
        schema_matches = list(re.finditer(r"schema\s*=\s*\{", task_matrices_text))
        self.assertGreaterEqual(len(schema_matches), 2, "Expected inline schema={...} examples in task-matrices.md")
        for m in schema_matches:
            brace_start = m.end() - 1
            raw_dict = _extract_balanced_braces(task_matrices_text, brace_start)
            self.assertIsNotNone(raw_dict, f"Unbalanced schema={{...}} at offset {brace_start}")
            assert raw_dict is not None
            parsed = ast.literal_eval(raw_dict)
            self.assertIsInstance(parsed, dict)
            self.assertIn("type", parsed)
            if parsed.get("type") == "object" and "required" in parsed:
                props = parsed.get("properties", {})
                self.assertIsInstance(props, dict)
                for req_field in parsed["required"]:
                    self.assertIn(req_field, props, f"Schema required field {req_field!r} missing from properties")

        # 3. Every relative markdown link in SKILL.md, references/*.md, and README.md resolves to an existing file
        md_files = [
            SKILL_DIR / "SKILL.md",
            REPO_ROOT / "README.md",
            *sorted(REFERENCES_DIR.glob("*.md")),
        ]
        link_re = re.compile(r"(?<!!)\[[^\]]+\]\(([^)\s]+)\)")
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            # Strip fenced code blocks before checking links
            no_code = re.sub(r"```.*?```", "", content, flags=re.DOTALL)
            for target in link_re.findall(no_code):
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                rel_part = target.split("#", 1)[0]
                if not rel_part:
                    continue
                resolved = (md_file.parent / rel_part).resolve()
                self.assertTrue(
                    resolved.exists(),
                    f"Broken relative markdown link {target!r} in {md_file.relative_to(REPO_ROOT)} -> {resolved}",
                )

    def test_documented_cli_flags_match_help_output(self) -> None:
        mm_help = subprocess.run(
            [sys.executable, str(MODEL_MATRIX_PATH), "--help"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        mm_flags = set(re.findall(r"(?<![A-Za-z0-9-])(--[a-z][a-z0-9-]*|-h)\b", mm_help))

        inst_help = subprocess.run(
            ["bash", str(INSTALL_SCRIPT_PATH), "--help"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout
        inst_flags = set(re.findall(r"(?<![A-Za-z0-9-])(--[a-z][a-z0-9-]*|-h)\b", inst_help))

        doc_files = [
            SKILL_DIR / "SKILL.md",
            REPO_ROOT / "README.md",
            REFERENCES_DIR / "task-matrices.md",
        ]

        found_mm_flags: set[str] = set()
        found_inst_flags: set[str] = set()

        for doc in doc_files:
            text = doc.read_text(encoding="utf-8")

            # Extract flags from explicit model_matrix.py command invocations
            for match in re.finditer(r"model_matrix\.py[\"']?([^\n`]*)", text):
                found_mm_flags.update(re.findall(r"--[a-z][a-z0-9-]*", match.group(1)))

            # Extract flags from explicit install.sh command invocations
            for match in re.finditer(r"install\.sh([^\n`]*)", text):
                found_inst_flags.update(re.findall(r"--[a-z][a-z0-9-]*", match.group(1)))

            # Extract flags from paragraphs mentioning model_matrix.py or install.sh
            for para in re.split(r"\n\s*\n", text):
                if "model_matrix.py" in para and "install.sh" not in para:
                    for token in re.findall(r"`(--[a-z][a-z0-9-]*)(?:[^`]*)`", para):
                        found_mm_flags.add(token)
                elif "install.sh" in para and "model_matrix.py" not in para:
                    for token in re.findall(r"`(--[a-z][a-z0-9-]*)(?:[^`]*)`", para):
                        found_inst_flags.add(token)

        self.assertTrue(found_mm_flags, "Expected documented model_matrix.py flags in docs")
        self.assertTrue(found_inst_flags, "Expected documented install.sh flags in docs")
        self.assertTrue(
            found_mm_flags.issubset(mm_flags),
            f"Undocumented/mismatched model_matrix.py flags in docs: {found_mm_flags - mm_flags}",
        )
        self.assertTrue(
            found_inst_flags.issubset(inst_flags),
            f"Undocumented/mismatched install.sh flags in docs: {found_inst_flags - inst_flags}",
        )

    def test_makefile_and_install_preflight_parity(self) -> None:
        makefile_text = MAKEFILE_PATH.read_text(encoding="utf-8")
        install_text = INSTALL_SCRIPT_PATH.read_text(encoding="utf-8")

        # Both Makefile and install.sh preflight check bash -n and both example JSON files
        self.assertIn("bash -n scripts/install.sh", makefile_text)
        self.assertIn('bash -n "${BASH_SOURCE[0]}"', install_text)
        for json_name in ("swarm-guardrails-plugin.json", "swarm-guardrails-hooks.json"):
            self.assertIn(json_name, makefile_text)
            self.assertIn(json_name, install_text)
        self.assertIn("export PYTHON", makefile_text)
        self.assertIn("INSTALL_FLAGS", makefile_text)

        # Verify empty PYTHON fallback and INSTALL_FLAGS pass-through via make -n (never executes install)
        env_empty_py = os.environ.copy()
        env_empty_py["PYTHON"] = ""
        dry_env = subprocess.run(
            ["make", "-n", "lint-json"],
            cwd=str(REPO_ROOT),
            env=env_empty_py,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn('"python3" -B -m json.tool', dry_env.stdout)

        dry_cli = subprocess.run(
            ["make", "-n", "PYTHON=", "lint-json"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn('"python3" -B -m json.tool', dry_cli.stdout)

        dry_sym = subprocess.run(
            ["make", "-n", "install-symlink", "INSTALL_FLAGS=--force"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("./scripts/install.sh --symlink --skip-tests --force", dry_sym.stdout)

        dry_copy = subprocess.run(
            ["make", "-n", "install", "INSTALL_FLAGS=--force"],
            cwd=str(REPO_ROOT),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("./scripts/install.sh --copy --skip-tests --force", dry_copy.stdout)

    def test_staged_example_plugin_passes_agy_validate_strict(self) -> None:
        if not shutil.which("agy"):
            self.skipTest("agy CLI not installed in PATH")
        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir) / "swarm-guardrails"
            (plugin_dir / "hooks").mkdir(parents=True)
            (plugin_dir / "rules").mkdir(parents=True)
            shutil.copy2(PLUGIN_JSON_PATH, plugin_dir / "plugin.json")
            shutil.copy2(HOOKS_JSON_PATH, plugin_dir / "hooks.json")
            shutil.copy2(HOOK_PATH, plugin_dir / "hooks" / "pretool-guard.py")
            shutil.copy2(AGENTS_MD_PATH, plugin_dir / "rules" / "AGENTS.md")

            proc = subprocess.run(
                ["agy", "plugin", "validate", str(plugin_dir), "--strict"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
