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

DIVERSITY_PAYLOAD = {
    "models": [
        "gemini-4-neon-low",
        "gemini-4-neon-high",
        "gemini-4-neon-xhigh",
        "gemini-4-neon-max",
        "gemini-4-hydrogen-high",
        "claude-sonnet-5-5-high",
    ],
    "display_names": {
        "gemini-4-neon-low": "Gemini 4 Neon (Low)",
        "gemini-4-neon-high": "Gemini 4 Neon (High)",
        "gemini-4-neon-xhigh": "Gemini 4 Neon (XHigh)",
        "gemini-4-neon-max": "Gemini 4 Neon (Max)",
        "gemini-4-hydrogen-high": "Gemini 4 Hydrogen (High)",
        "claude-sonnet-5-5-high": "Claude Sonnet 5.5 (High)",
    },
    "quotas": {
        "gemini-4-neon-low": {"quota_remaining": "80%", "quota_resets": "2h"},
        "gemini-4-neon-high": {"quota_remaining": "80%", "quota_resets": "2h"},
        "gemini-4-neon-xhigh": {"quota_remaining": "80%", "quota_resets": "2h"},
        "gemini-4-neon-max": {"quota_remaining": "75%", "quota_resets": "2h"},
        "gemini-4-hydrogen-high": {"quota_remaining": "90%", "quota_resets": "2h"},
        "claude-sonnet-5-5-high": {"quota_remaining": "70%", "quota_resets": "3h"},
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
        self.assertEqual(orch["vendor"], "gemini")

        families = mm.group_by_family(entries)
        flash = next(f for f in families if f["family_key"] == "gemini-3-flash-*")
        self.assertEqual(flash["family_label"], "Gemini 3 Flash")
        self.assertEqual(flash["vendor"], "gemini")
        self.assertTrue(flash["quota_uniform"])
        self.assertEqual(flash["quota_remaining"], "100%")
        self.assertEqual(set(flash["efforts"].keys()), {"low", "high"})
        self.assertEqual(flash["quotas_by_effort"]["low"]["quota_remaining"], "100%")
        self.assertEqual(flash["quotas_by_effort"]["high"]["quota_remaining"], "100%")

        claude = next(f for f in families if f["family_key"] == "claude-sonnet-4-6-*")
        self.assertEqual(claude["vendor"], "claude")
        self.assertFalse(claude["quota_uniform"])
        self.assertIsNone(claude["quota_remaining"])
        self.assertIsNone(claude["quota_resets"])
        self.assertIsNone(claude["quota_note"])
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
            "warning:   rate limit notice\n"
            "note:   ignored diagnostic\n"
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

        # Wildcard family pattern suggests concrete IDs
        ok_wild, msgs_wild = mm.validate_models(swarm_entries, ["gemini-3-flash-*"])
        self.assertFalse(ok_wild)
        self.assertIn("gemini-3-flash-low, gemini-3-flash-high", msgs_wild[0])

        # Empty or whitespace-only target list fails explicitly
        for empty_targets in ([""], [" ", "  "]):
            ok_empty, msgs_empty = mm.validate_models(swarm_entries, empty_targets)
            self.assertFalse(ok_empty)
            self.assertIn("requires at least one non-empty model", msgs_empty[0])

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

    def test_strict_quota_parsing_sentinels_numeric_exhaustion_and_max_suffix(self) -> None:
        payload = {
            "models": [
                "m-empty-quota-low",
                "m-unknown-quota-low",
                "m-dash-quota-low",
                "m-na-quota-low",
                "m-bool-quota-low",
                "m-zero-int-low",
                "m-zero-float-low",
                "m-zero-pct-low",
                "gemini-4-neon-max",
            ],
            "quotas": {
                "m-empty-quota-low": {"quota_remaining": ""},
                "m-unknown-quota-low": {"quota_remaining": "unknown"},
                "m-dash-quota-low": {"quota_remaining": "-"},
                "m-na-quota-low": {"quota_remaining": "N/A"},
                "m-bool-quota-low": {"quota_remaining": True},
                "m-zero-int-low": {"quota_remaining": 0},
                "m-zero-float-low": {"quota_remaining": 0.0},
                "m-zero-pct-low": {"quota_remaining": "0.0%"},
                "gemini-4-neon-max": {"quota_remaining": 75},
            },
        }
        entries = mm.parse_swarm_json(json.dumps(payload))

        # Non-numeric sentinels fail --require-quota
        for model_id in (
            "m-empty-quota-low",
            "m-unknown-quota-low",
            "m-dash-quota-low",
            "m-na-quota-low",
            "m-bool-quota-low",
        ):
            ok_req, msgs_req = mm.validate_models(entries, [model_id], require_quota=True)
            self.assertFalse(ok_req, f"Expected failure for sentinel {model_id}: {msgs_req}")
            self.assertIn("non-numeric quota value", msgs_req[0])

        # Numeric 0 / 0.0 / "0.0%" fail validation even without --require-quota
        for model_id in ("m-zero-int-low", "m-zero-float-low", "m-zero-pct-low"):
            ok_zero, msgs_zero = mm.validate_models(entries, [model_id])
            self.assertFalse(ok_zero, f"Expected exhaustion for {model_id}: {msgs_zero}")
            self.assertIn("quota remaining", msgs_zero[0])

        # *-max suffix parses and validates cleanly
        max_entry = next(e for e in entries if e["id"] == "gemini-4-neon-max")
        self.assertEqual(max_entry["effort"], "max")
        self.assertEqual(max_entry["family_key"], "gemini-4-neon-*")
        ok_max, msgs_max = mm.validate_models(entries, ["gemini-4-neon-max"], require_quota=True)
        self.assertTrue(ok_max, msgs_max)

    def test_cli_stdin_file_implicit_pipe_and_validation_edge_cases(self) -> None:
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
        self.assertIn("POOL DIVERSITY: cross-vendor", ok_proc.stdout)

        # --validate "" and --validate " , " must exit 1 (never print table & exit 0)
        for empty_arg in ("", " , "):
            empty_val = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", "-", "--validate", empty_arg],
                input=raw_json,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(empty_val.returncode, 1, empty_val.stdout)
            self.assertIn("ERROR:", empty_val.stdout)

        # --from-swarm-json "" must exit 2
        empty_path = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", ""],
            input="",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(empty_path.returncode, 2)
        self.assertIn("Error loading models:", empty_path.stderr)

        # --from-swarm-json <file_path>
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "models.json"
            json_file.write_text(raw_json, encoding="utf-8")
            file_proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", str(json_file), "--format", "json"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(file_proc.returncode, 0, file_proc.stderr)
            parsed_file = json.loads(file_proc.stdout)
            self.assertEqual(parsed_file["count"], 10)

            # Missing file -> exit 2
            missing_proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", str(Path(tmpdir) / "nope.json")],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(missing_proc.returncode, 2)

        # Implicit non-empty piped stdin without --from-swarm-json flag
        pipe_proc = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--validate", "gpt-5-4-xhigh", "--require-quota"],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(pipe_proc.returncode, 0, pipe_proc.stderr)
        self.assertIn("OK: gpt-5-4-xhigh", pipe_proc.stdout)

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

        # JSON output preserves quotas_by_effort and normalizes mixed top-level quota + vendor
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
        self.assertEqual(claude["vendor"], "claude")
        self.assertFalse(claude["quota_uniform"])
        self.assertIsNone(claude["quota_remaining"])
        self.assertIsNone(claude["quota_resets"])
        self.assertIn("quotas_by_effort", claude)
        self.assertEqual(claude["quotas_by_effort"]["high"]["quota_remaining"], "0%")

    def test_malformed_swarm_payloads_exit_2_without_traceback(self) -> None:
        bad_payloads = [
            "{not-json",
            "[]",
            json.dumps({"models": None}),
            json.dumps({"models": []}),
            json.dumps({"models": [123]}),
            json.dumps({"models": ["m"], "quotas": None}),
            json.dumps({"models": ["m"], "display_names": None}),
            json.dumps({"models": ["m"], "display_names": {"m": None}}),
            json.dumps({"models": ["m"], "quotas": {"m": "bad"}}),
        ]
        for payload in bad_payloads:
            proc = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-swarm-json", "-"],
                input=payload,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 2, f"Expected exit 2 for {payload}: {proc.stderr}")
            self.assertNotIn("Traceback", proc.stderr)
            self.assertIn("Error loading models:", proc.stderr)

    def test_pool_diversity_require_diverse_and_allowed_pool(self) -> None:
        raw_json = json.dumps(DIVERSITY_PAYLOAD)

        # Cross-vendor passes --require-diverse
        cross_proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gemini-4-neon-high,claude-sonnet-5-5-high",
                "--require-quota",
                "--require-diverse",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(cross_proc.returncode, 0, cross_proc.stdout + cross_proc.stderr)
        self.assertIn("POOL DIVERSITY: cross-vendor", cross_proc.stdout)

        # Single-vendor cross-variant passes --require-diverse and --allowed-pool
        sv_cv_proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gemini-4-neon-high,gemini-4-hydrogen-high",
                "--require-quota",
                "--require-diverse",
                "--allowed-pool",
                "gemini-4-neon-*,gemini-4-hydrogen-high",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(sv_cv_proc.returncode, 0, sv_cv_proc.stdout + sv_cv_proc.stderr)
        self.assertIn("POOL DIVERSITY: single-vendor cross-variant", sv_cv_proc.stdout)

        # Single-variant warns by default (exit 0) and fails with --require-diverse (exit 1)
        sv_warn = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gemini-4-neon-xhigh,gemini-4-neon-low",
                "--require-quota",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(sv_warn.returncode, 0, sv_warn.stdout)
        self.assertIn("WARNING: POOL DIVERSITY: single-variant", sv_warn.stdout)

        sv_fail = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gemini-4-neon-xhigh,gemini-4-neon-low",
                "--require-quota",
                "--require-diverse",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(sv_fail.returncode, 1, sv_fail.stdout)
        self.assertIn("ERROR: POOL DIVERSITY: single-variant", sv_fail.stdout)

        # Single target with --require-diverse fails
        single_fail = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gemini-4-neon-max",
                "--require-diverse",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(single_fail.returncode, 1)
        self.assertIn("requires at least 2 validated models", single_fail.stdout)

        # Out-of-pool fallback rejected by --allowed-pool
        out_of_pool = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_PATH),
                "--from-swarm-json",
                "-",
                "--validate",
                "gemini-4-neon-high,claude-sonnet-5-5-high",
                "--allowed-pool",
                "gemini-4-neon-high,gemini-4-hydrogen-high",
            ],
            input=raw_json,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(out_of_pool.returncode, 1)
        self.assertIn("outside --allowed-pool", out_of_pool.stdout)

    def test_cli_agy_explicit_fallback_stderr_filtering_and_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_bin = Path(tmpdir)
            fake_agy = fake_bin / "agy"
            fake_agy.write_text(
                "#!/bin/sh\n"
                "printf 'warning:  rate limit approaching\\n' >&2\n"
                "printf '\\r⠋ Fetching available models...\\r'\n"
                "printf 'gemini-pro-orchestrator\\tGemini Pro Orchestrator\\n'\n"
                "printf 'gemini-3-flash-low\\tGemini 3 Flash (Low)\\n'\n",
                encoding="utf-8",
            )
            fake_agy.chmod(fake_agy.stat().st_mode | stat.S_IEXEC)

            env = os.environ.copy()
            env["PATH"] = f"{fake_bin}{os.pathsep}{env.get('PATH', '')}"

            # Empty non-tty stdin falls back to agy and ignores stderr warning
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
            self.assertNotIn("warning:", proc.stdout)

            # Explicit --from-agy
            explicit_agy = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-agy", "--format", "json"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(explicit_agy.returncode, 0, explicit_agy.stderr)
            parsed = json.loads(explicit_agy.stdout)
            self.assertEqual(parsed["count"], 2)

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

            # agy returning 0 with "No models found" -> exit 2
            fake_agy.write_text("#!/bin/sh\nprintf 'No models found\\n'\n", encoding="utf-8")
            empty_agy = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-agy"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(empty_agy.returncode, 2)
            self.assertIn("No models parsed", empty_agy.stderr)

            # agy failing with non-zero -> exit 2
            fake_agy.write_text("#!/bin/sh\nprintf 'auth failed\\n' >&2\nexit 1\n", encoding="utf-8")
            fail_agy = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-agy"],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(fail_agy.returncode, 2)
            self.assertIn("`agy models` failed", fail_agy.stderr)

            # Missing agy binary on PATH -> exit 2
            empty_path_env = env.copy()
            empty_path_env["PATH"] = str(Path(tmpdir) / "empty-bin")
            Path(empty_path_env["PATH"]).mkdir()
            missing_agy = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--from-agy"],
                text=True,
                capture_output=True,
                env=empty_path_env,
                check=False,
            )
            self.assertEqual(missing_agy.returncode, 2)


if __name__ == "__main__":
    unittest.main()
