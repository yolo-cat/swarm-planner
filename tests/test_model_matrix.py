from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
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
        "gemini-pro-orchestrator-high",
        "gemini-3-flash-low",
        "gemini-3-flash-high",
        "claude-sonnet-4-6-high",
        "gpt-5-4-xhigh",
        "exhausted-model-medium",
        "unlimited-preview-low",
    ],
    "display_names": {
        "gemini-pro-orchestrator-high": "Gemini Pro Orchestrator (High)",
        "gemini-3-flash-low": "Gemini 3 Flash (Low)",
        "gemini-3-flash-high": "Gemini 3 Flash (High)",
        "claude-sonnet-4-6-high": "Claude Sonnet 4.6 (High)",
        "gpt-5-4-xhigh": "GPT-5.4 (XHigh)",
        "exhausted-model-medium": "Exhausted Model (Medium)",
        "unlimited-preview-low": "Unlimited Preview (Low)",
    },
    "quotas": {
        "gemini-pro-orchestrator-high": {"quota_remaining": "90%", "quota_resets": "1h"},
        "gemini-3-flash-low": {"quota_remaining": "100%", "quota_resets": "2h"},
        "gemini-3-flash-high": {"quota_remaining": "100%", "quota_resets": "2h"},
        "claude-sonnet-4-6-high": {"quota_remaining": "60%", "quota_resets": "3h"},
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
    def test_parse_swarm_json_and_grouping(self) -> None:
        entries = mm.parse_swarm_json(json.dumps(SAMPLE_SWARM_PAYLOAD))
        self.assertEqual(len(entries), 7)
        families = mm.group_by_family(entries)
        flash = next(f for f in families if f["family_key"] == "gemini-3-flash-*")
        self.assertEqual(flash["family_label"], "Gemini 3 Flash")
        self.assertEqual(set(flash["efforts"].keys()), {"low", "high"})

        md = mm.format_markdown(entries)
        self.assertIn("| Model Family | Pattern / ID | Thinking Efforts | Quota |", md)
        self.assertIn("`low, high`", md)
        self.assertIn("**Gemini Pro Orchestrator**", md)

    def test_parse_agy_output_handles_tabs_spaces_and_ansi(self) -> None:
        raw = (
            "\x1b[2K⠋ Fetching available models...\n"
            "gemini-3-flash-low\tGemini 3 Flash (Low)\n"
            "claude-sonnet-4-6-high   Claude Sonnet 4.6 (High)\n"
            "plain-default-model\n"
        )
        entries = mm.parse_agy_output(raw)
        self.assertEqual(
            [e["id"] for e in entries],
            ["gemini-3-flash-low", "claude-sonnet-4-6-high", "plain-default-model"],
        )
        self.assertEqual(entries[0]["effort"], "low")
        self.assertEqual(entries[1]["family_label"], "Claude Sonnet 4.6")
        self.assertEqual(entries[2]["effort"], "default")
        md = mm.format_markdown(entries)
        self.assertNotIn("| Quota |", md)

    def test_validate_models(self) -> None:
        entries = mm.parse_swarm_json(json.dumps(SAMPLE_SWARM_PAYLOAD))

        ok, msgs = mm.validate_models(
            entries,
            ["gemini-3-flash-high", "claude sonnet 4.6 (high)", "unlimited-preview-low"],
        )
        self.assertTrue(ok, msgs)
        self.assertEqual(len(msgs), 3)

        ok_unknown, msgs_unknown = mm.validate_models(entries, ["nonexistent-model"])
        self.assertFalse(ok_unknown)
        self.assertIn("Unknown model", msgs_unknown[0])

        ok_zero, msgs_zero = mm.validate_models(entries, ["exhausted-model-medium"])
        self.assertFalse(ok_zero)
        self.assertIn("0% quota remaining", msgs_zero[0])

    def test_cli_stdin_validation_exit_codes(self) -> None:
        raw_json = json.dumps(SAMPLE_SWARM_PAYLOAD)
        ok_proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", "-", "--validate", "gpt-5-4-xhigh"],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(ok_proc.returncode, 0, ok_proc.stderr)
        self.assertIn("OK: gpt-5-4-xhigh", ok_proc.stdout)

        bad_proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", "-", "--validate", "exhausted-model-medium"],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(bad_proc.returncode, 1)
        self.assertIn("0% quota remaining", bad_proc.stdout)


if __name__ == "__main__":
    unittest.main()
