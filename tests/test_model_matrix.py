from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = REPO_ROOT / "skills" / "swarm-planner" / "scripts" / "model_matrix.py"


def load_module():
    spec = importlib.util.spec_from_file_location("model_matrix", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mm = load_module()

SAMPLE_SWARM_PAYLOAD = {
    "models": [
        "gemini-pro-orchestrator",
        "gemini-pro-orchestrator-argon",
        "gemini-3-flash-low",
        "gemini-3-flash-high",
        "claude-sonnet-4-6-low",
        "claude-sonnet-4-6-high",
        "gpt-5-4-xhigh",
        "exhausted-model-medium",
        "unlimited-preview-low",
        "no-quota-entry-high",
    ],
    "display_names": {
        "gemini-pro-orchestrator": "Gemini Pro Orchestrator",
        "gemini-pro-orchestrator-argon": "Gemini Pro Orchestrator Argon",
        "gemini-3-flash-low": "Gemini 3 Flash (Low)",
        "gemini-3-flash-high": "Gemini 3 Flash (High)",
        "claude-sonnet-4-6-low": "Claude Sonnet 4.6 (Low)",
        "claude-sonnet-4-6-high": "Claude Sonnet 4.6 (High)",
        "gpt-5-4-xhigh": "GPT-5.4 (XHigh)",
        "exhausted-model-medium": "Exhausted Model (Medium)",
        "unlimited-preview-low": "Unlimited Preview (Low)",
        "no-quota-entry-high": "No Quota Entry (High)",
    },
    "quotas": {
        "gemini-pro-orchestrator": {"quota_remaining": "90%", "quota_resets": "1h"},
        "gemini-pro-orchestrator-argon": {"quota_remaining": "85%", "quota_resets": "1h"},
        "gemini-3-flash-low": {"quota_remaining": "100%", "quota_resets": "2h"},
        "gemini-3-flash-high": {"quota_remaining": "100%", "quota_resets": "2h"},
        "claude-sonnet-4-6-low": {"quota_remaining": "20%", "quota_resets": "3h"},
        "claude-sonnet-4-6-high": {"quota_remaining": "0%", "quota_resets": "3h"},
        "gpt-5-4-xhigh": {"quota_remaining": "80%", "quota_resets": "4h"},
        "exhausted-model-medium": {"quota_remaining": "0%", "quota_resets": "5h"},
        "unlimited-preview-low": {
            "quota_remaining": "0%",
            "quota_resets": None,
            "quota_note": "Preview exempt",
        },
    },
}


class ModelMatrixTests(unittest.TestCase):
    def test_parse_swarm_json_orchestrators_and_per_variant_quotas(self) -> None:
        entries = mm.parse_swarm_json(json.dumps(SAMPLE_SWARM_PAYLOAD))
        self.assertEqual(len(entries), 10)
        self.assertTrue(all(e["source"] == "swarm" for e in entries))

        orch = next(e for e in entries if e["id"] == "gemini-pro-orchestrator")
        self.assertEqual(orch["effort"], "default")
        self.assertEqual(orch["family_key"], "gemini-pro-orchestrator")
        self.assertEqual(orch["family_label"], "Gemini Pro Orchestrator")

        families = mm.group_by_family(entries)
        flash = next(f for f in families if f["family_key"] == "gemini-3-flash-*")
        self.assertEqual(flash["family_label"], "Gemini 3 Flash")
        self.assertEqual(set(flash["efforts"].keys()), {"low", "high"})
        self.assertEqual(flash["quotas_by_effort"]["low"]["quota_remaining"], "100%")
        self.assertEqual(flash["quotas_by_effort"]["high"]["quota_remaining"], "100%")

        claude = next(f for f in families if f["family_key"] == "claude-sonnet-4-6-*")
        self.assertEqual(claude["quotas_by_effort"]["low"]["quota_remaining"], "20%")
        self.assertEqual(claude["quotas_by_effort"]["high"]["quota_remaining"], "0%")

        md = mm.format_markdown(entries)
        self.assertIn("| Model Family | Pattern / ID | Thinking Efforts | Quota |", md)
        self.assertIn("**Gemini Pro Orchestrator** | `gemini-pro-orchestrator` | `default` | 90% resets 1h |", md)
        # Uniform variants render compact single string
        self.assertIn("**Gemini 3 Flash** | `gemini-3-flash-*` | `low, high` | 100% resets 2h |", md)
        # Mixed variants never mask 0% sibling
        self.assertIn("low: 20%, high: 0%", md)

    def test_format_markdown_mixed_quotas_with_notes_and_note_only_column(self) -> None:
        payload = {
            "models": ["model-a-high", "model-a-low"],
            "display_names": {
                "model-a-high": "Model A (High)",
                "model-a-low": "Model A (Low)",
            },
            "quotas": {
                "model-a-high": {"quota_remaining": None, "quota_note": "Unlimited"},
                "model-a-low": {"quota_remaining": "0%", "quota_note": "Preview"},
            },
        }
        entries = mm.parse_swarm_json(json.dumps(payload))
        md = mm.format_markdown(entries)
        self.assertIn("| Quota |", md)
        # Ordered by EFFORT_ORDER (low before high) even though high appeared first
        self.assertIn("low: 0% (Preview), high: - (Unlimited)", md)

    def test_parse_agy_output_handles_pty_cr_spinner_and_slug_filter(self) -> None:
        raw = (
            "\x1b[2K\r⠋ Fetching available models...\r"
            "gemini-pro-orchestrator\tGemini Pro Orchestrator\n"
            "ID   Display Name\n"
            "---\n"
            "⠹ gemini-3-flash-low\tGemini 3 Flash (Low)\r\n"
            "claude-sonnet-4-6-high   Claude Sonnet 4.6 (High)\n"
            "plain-default-model\n"
        )
        entries = mm.parse_agy_output(raw)
        self.assertEqual(
            [e["id"] for e in entries],
            [
                "gemini-pro-orchestrator",
                "gemini-3-flash-low",
                "claude-sonnet-4-6-high",
                "plain-default-model",
            ],
        )
        self.assertTrue(all(e["source"] == "agy" for e in entries))
        self.assertEqual(entries[0]["effort"], "default")
        self.assertEqual(entries[1]["effort"], "low")
        self.assertEqual(entries[2]["family_label"], "Claude Sonnet 4.6")
        self.assertEqual(entries[3]["effort"], "default")
        md = mm.format_markdown(entries)
        self.assertNotIn("| Quota |", md)

    def test_validate_models_and_unknown_quota_sources(self) -> None:
        swarm_entries = mm.parse_swarm_json(json.dumps(SAMPLE_SWARM_PAYLOAD))

        ok, msgs = mm.validate_models(
            swarm_entries,
            [
                "gemini-pro-orchestrator",
                "claude sonnet 4.6 (low)",
                "unlimited-preview-low",
                "no-quota-entry-high",
            ],
        )
        self.assertTrue(ok, msgs)
        self.assertEqual(len(msgs), 4)
        self.assertIn("quota=unknown (missing from swarm JSON)", msgs[3])

        # --require-quota fails when swarm JSON lacks quota entry
        ok_req, msgs_req = mm.validate_models(
            swarm_entries, ["no-quota-entry-high"], require_quota=True
        )
        self.assertFalse(ok_req)
        self.assertIn("quota=unknown (missing from swarm JSON)", msgs_req[0])

        # Unknown model fails
        ok_unknown, msgs_unknown = mm.validate_models(swarm_entries, ["nonexistent-model"])
        self.assertFalse(ok_unknown)
        self.assertIn("Unknown model", msgs_unknown[0])

        # 0% quota without note fails
        ok_zero, msgs_zero = mm.validate_models(swarm_entries, ["exhausted-model-medium"])
        self.assertFalse(ok_zero)
        self.assertIn("0% quota remaining", msgs_zero[0])

        # agy source unknown quota wording + --require-quota failure
        agy_entries = mm.parse_agy_output("gemini-3-flash-high\tGemini 3 Flash (High)\n")
        ok_agy, msgs_agy = mm.validate_models(agy_entries, ["gemini-3-flash-high"])
        self.assertTrue(ok_agy)
        self.assertIn("quota=unknown (agy source — existence only)", msgs_agy[0])

        ok_agy_req, msgs_agy_req = mm.validate_models(
            agy_entries, ["gemini-3-flash-high"], require_quota=True
        )
        self.assertFalse(ok_agy_req)
        self.assertIn("quota=unknown (agy source — existence only)", msgs_agy_req[0])

    def test_cli_stdin_validation_and_require_quota_exit_codes(self) -> None:
        raw_json = json.dumps(SAMPLE_SWARM_PAYLOAD)
        ok_proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gpt-5-4-xhigh,gemini-pro-orchestrator",
                "--require-quota",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ok_proc.returncode, 0, ok_proc.stderr)
        self.assertIn("OK: gpt-5-4-xhigh", ok_proc.stdout)
        self.assertIn("OK: gemini-pro-orchestrator", ok_proc.stdout)

        bad_proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "exhausted-model-medium",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(bad_proc.returncode, 1)
        self.assertIn("0% quota remaining", bad_proc.stdout)

        req_fail = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "no-quota-entry-high",
                "--require-quota",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(req_fail.returncode, 1)
        self.assertIn("missing from swarm JSON", req_fail.stdout)

        # Explicit --from-swarm-json - with empty stdin must exit 2
        empty_explicit = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", "-"],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(empty_explicit.returncode, 2)

        # JSON output preserves quotas_by_effort
        json_proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", "-", "--format", "json"],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(json_proc.returncode, 0, json_proc.stderr)
        parsed = json.loads(json_proc.stdout)
        self.assertEqual(parsed["count"], 10)
        claude = next(f for f in parsed["families"] if f["family_key"] == "claude-sonnet-4-6-*")
        self.assertIn("quotas_by_effort", claude)
        self.assertEqual(claude["quotas_by_effort"]["high"]["quota_remaining"], "0%")

    def test_cli_empty_non_tty_stdin_falls_back_to_agy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_bin = Path(tmpdir)
            fake_agy = fake_bin / "agy"
            fake_agy.write_text(
                "#!/bin/sh\n"
                "printf '\\r⠋ Fetching available models...\\r'\n"
                "printf 'gemini-pro-orchestrator\\tGemini Pro Orchestrator\\n'\n"
                "printf 'gemini-3-flash-low\\tGemini 3 Flash (Low)\\n'\n",
                encoding="utf-8",
            )
            fake_agy.chmod(fake_agy.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH)],
                input="",
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn("gemini-pro-orchestrator", proc.stdout)
            self.assertIn("gemini-3-flash-*", proc.stdout)

            # --validate with --require-quota fails against agy fallback
            val_proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--validate", "gemini-3-flash-low", "--require-quota"],
                input="",
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(val_proc.returncode, 1)
            self.assertIn("agy source — existence only", val_proc.stdout)


if __name__ == "__main__":
    unittest.main()
