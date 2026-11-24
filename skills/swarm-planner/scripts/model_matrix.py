#!/usr/bin/env python3
"""Parse, format, and validate Antigravity model & thinking-effort capabilities.

Supports two official discovery sources:
  1. JSON from `swarm{action:"models", all:true}` (--from-swarm-json <path|->)
     Includes orchestrator models and real-time quota_remaining / quota_resets.
  2. Live CLI output from `agy models` (--from-agy)
     Runs standalone in terminal without needing an agent tool call.
"""

from __future__ import annotations

import argparse
from collections import OrderedDict
import json
import math
import re
import subprocess
import sys
from typing import Any

ANSI_ESCAPE_RE = re.compile(
    r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b\[[0-9;?]*[ -/]*[@-~]"
    r"|\x1b[()#][A-Za-z0-9]"
    r"|\x1b[@-Z\\-_]"
)
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
EFFORT_SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<effort>low|medium|high|xhigh|max)$")
DISPLAY_EFFORT_RE = re.compile(r"\s+\((Low|Medium|High|XHigh|Max)\)$", re.IGNORECASE)
VENDOR_SPLIT_RE = re.compile(r"[-_:.]+")
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max", "default"]
VENDOR_ALIASES = {
    "gpt": "openai",
    "o1": "openai",
    "o3": "openai",
    "o4": "openai",
    "chatgpt": "openai",
    "codex": "openai",
}
NON_MODEL_WORDS = {
    "model",
    "models",
    "id",
    "name",
    "alias",
    "tier",
    "status",
    "error",
    "warning",
    "warn",
    "info",
    "note",
    "done",
    "ok",
    "failed",
    "timeout",
    "loading",
    "fetching",
    "none",
    "null",
    "usage",
    "help",
}
HEADER_LABELS = {"display name", "name", "description", "model", "label"}
AGY_TIMEOUT_SECONDS = 15


def infer_vendor(model_id: str) -> str:
    """Return normalized vendor prefix (e.g. 'gemini', 'claude', 'openai')."""
    cleaned = model_id.strip().lower()
    if not cleaned:
        return "unknown"
    parts = VENDOR_SPLIT_RE.split(cleaned, maxsplit=1)
    prefix = parts[0] if parts and parts[0] else cleaned
    return VENDOR_ALIASES.get(prefix, prefix)


def _base_family_key(family_key: str) -> str:
    return family_key[:-2] if family_key.endswith("-*") else family_key


def split_effort(model_id: str, display_name: str | None) -> tuple[str, str, str]:
    """Return (family_key, family_label, effort_level) for a model entry."""
    safe_display = display_name.strip() if isinstance(display_name, str) and display_name.strip() else model_id
    match = EFFORT_SUFFIX_RE.match(model_id)
    if match:
        family_key = f"{match.group('base')}-*"
        effort = match.group("effort").lower()
        family_label = DISPLAY_EFFORT_RE.sub("", safe_display).strip() or model_id
        return family_key, family_label, effort
    return model_id, safe_display, "default"


def parse_swarm_json(raw: str) -> list[dict[str, Any]]:
    """Parse JSON returned by `swarm{action:'models', all:true}`."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object from swarm models output.")

    models = data.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("Expected non-empty 'models' list in swarm models JSON.")
    seen_models: set[str] = set()
    for item in models:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Every entry in 'models' must be a non-empty string.")
        if item != item.strip():
            raise ValueError(f"Model ID {item!r} in 'models' must not contain leading or trailing whitespace.")
        if "*" in item:
            raise ValueError(f"Model ID {item!r} in 'models' must be a concrete ID, not a wildcard.")
        if item in seen_models:
            raise ValueError(f"Duplicate model ID {item!r} in 'models'.")
        seen_models.add(item)

    if "display_names" in data:
        display_names = data["display_names"]
        if not isinstance(display_names, dict):
            raise ValueError("'display_names' must be a JSON object when present.")
    else:
        display_names = {}

    if "quotas" in data:
        quotas = data["quotas"]
        if not isinstance(quotas, dict):
            raise ValueError("'quotas' must be a JSON object when present.")
    else:
        quotas = {}

    entries: list[dict[str, Any]] = []
    for model_id in models:
        if model_id in display_names:
            raw_display = display_names[model_id]
            if not isinstance(raw_display, str) or not raw_display.strip():
                raise ValueError(
                    f"'display_names[{model_id!r}]' must be a non-empty string when present."
                )
            display_name = raw_display.strip()
            has_explicit_display = True
        else:
            display_name = model_id
            has_explicit_display = False

        raw_quota = quotas.get(model_id)
        if raw_quota is None:
            quota_info: dict[str, Any] = {}
        elif isinstance(raw_quota, dict):
            quota_info = raw_quota
        else:
            raise ValueError(f"'quotas[{model_id!r}]' must be a JSON object or null.")

        quota_resets = quota_info.get("quota_resets")
        if quota_resets is not None and not isinstance(quota_resets, str):
            raise ValueError(f"'quotas[{model_id!r}].quota_resets' must be a string or null.")
        quota_note = quota_info.get("quota_note")
        if quota_note is not None and not isinstance(quota_note, str):
            raise ValueError(f"'quotas[{model_id!r}].quota_note' must be a string or null.")

        family_key, family_label, effort = split_effort(model_id, display_name)
        entries.append(
            {
                "id": model_id,
                "display_name": display_name,
                "has_explicit_display": has_explicit_display,
                "family_key": family_key,
                "family_label": family_label,
                "vendor": infer_vendor(model_id),
                "effort": effort,
                "quota_remaining": quota_info.get("quota_remaining"),
                "quota_resets": quota_resets,
                "quota_note": quota_note,
                "source": "swarm",
            }
        )
    return entries


def parse_agy_output(raw: str) -> list[dict[str, Any]]:
    """Parse text output from `agy models`, stripping ANSI/OSC/charset sequences."""
    cleaned = ANSI_ESCAPE_RE.sub("", raw).replace("\r", "\n")
    entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for line in cleaned.splitlines():
        line = line.strip()
        if not line or "Fetching available models" in line:
            continue
        # Remove optional braille spinner prefix if left over
        line = line.lstrip("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ ").strip()
        if not line or "Fetching available models" in line:
            continue
        parts = re.split(r"\t+|\s{2,}", line, maxsplit=1)
        if not parts or not parts[0]:
            continue
        model_id = parts[0]
        if model_id.endswith(":") or not MODEL_ID_RE.match(model_id):
            continue
        if model_id.isdigit() or model_id.lower() in NON_MODEL_WORDS:
            continue
        has_display = len(parts) > 1 and bool(parts[1].strip())
        if has_display and parts[1].strip().lower() in HEADER_LABELS:
            continue
        if not has_display and not re.search(r"[-_.:0-9]", model_id):
            continue
        if model_id in seen_ids:
            continue
        seen_ids.add(model_id)

        display_name = parts[1].strip() if has_display else model_id
        family_key, family_label, effort = split_effort(model_id, display_name)
        entries.append(
            {
                "id": model_id,
                "display_name": display_name,
                "has_explicit_display": has_display,
                "family_key": family_key,
                "family_label": family_label,
                "vendor": infer_vendor(model_id),
                "effort": effort,
                "quota_remaining": None,
                "quota_resets": None,
                "quota_note": None,
                "source": "agy",
            }
        )
    return entries


def fetch_from_agy(timeout: int = AGY_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    """Run `agy models` and parse its output."""
    try:
        proc = subprocess.run(
            ["agy", "models"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"`agy models` timed out after {timeout}s.") from exc

    if proc.returncode != 0:
        combined = f"{proc.stdout}\n{proc.stderr}".strip()
        raise RuntimeError(f"`agy models` failed (exit {proc.returncode}): {combined}")

    entries = parse_agy_output(proc.stdout)
    if not entries and not proc.stdout.strip():
        entries = parse_agy_output(proc.stderr)
    if not entries:
        raise ValueError("No models parsed from `agy models` output.")
    return entries


def group_by_family(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group model entries into family rows ordered by first appearance."""
    families: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for entry in entries:
        key = entry["family_key"]
        if key not in families:
            families[key] = {
                "family_key": key,
                "family_label": entry["family_label"],
                "vendor": entry.get("vendor") or infer_vendor(entry["id"]),
                "efforts": {},
                "quota_uniform": True,
                "quota_remaining": entry["quota_remaining"],
                "quota_resets": entry["quota_resets"],
                "quota_note": entry["quota_note"],
                "quotas_by_effort": {},
            }
        effort = entry["effort"]
        families[key]["efforts"][effort] = entry["id"]
        families[key]["quotas_by_effort"][effort] = {
            "quota_remaining": entry["quota_remaining"],
            "quota_resets": entry["quota_resets"],
            "quota_note": entry["quota_note"],
        }

    for fam in families.values():
        unique_tuples = {
            (q.get("quota_remaining"), q.get("quota_resets"), q.get("quota_note"))
            for q in fam["quotas_by_effort"].values()
        }
        if len(unique_tuples) <= 1:
            fam["quota_uniform"] = True
        else:
            fam["quota_uniform"] = False
            fam["quota_remaining"] = None
            fam["quota_resets"] = None
            fam["quota_note"] = None

    return list(families.values())


def _format_single_quota(q_info: dict[str, Any], include_resets: bool = True) -> str:
    quota = q_info.get("quota_remaining")
    quota_val = quota if quota is not None else "-"
    raw_note = q_info.get("quota_note")
    clean_note = raw_note.strip() if isinstance(raw_note, str) else ""
    note = f" ({clean_note})" if clean_note else ""
    resets = f" resets {q_info['quota_resets']}" if include_resets and q_info.get("quota_resets") else ""
    return f"{quota_val}{note}{resets}"


def _format_family_quota(fam: dict[str, Any], ordered_efforts: list[str]) -> str:
    quotas_by_effort = fam.get("quotas_by_effort", {})
    tuples = []
    for effort in ordered_efforts:
        q = quotas_by_effort.get(effort, {})
        tuples.append((q.get("quota_remaining"), q.get("quota_resets"), q.get("quota_note")))

    if len(set(tuples)) <= 1:
        first = quotas_by_effort.get(ordered_efforts[0], fam) if ordered_efforts else fam
        return _format_single_quota(first, include_resets=True)

    resets_values = {t[1] for t in tuples if t[1] is not None}
    all_have_same_reset = len(resets_values) == 1 and all(t[1] is not None for t in tuples)

    parts = []
    for effort in ordered_efforts:
        q = quotas_by_effort.get(effort, {})
        item = _format_single_quota(q, include_resets=not all_have_same_reset)
        parts.append(f"{effort}: {item}")

    summary = ", ".join(parts)
    if all_have_same_reset:
        common_reset = next(iter(resets_values))
        return f"{summary} resets {common_reset}"
    return summary


def format_markdown(entries: list[dict[str, Any]]) -> str:
    """Render a compact Markdown Model x Thinking-Effort table."""
    families = group_by_family(entries)
    has_quota = any(
        e.get("quota_remaining") is not None
        or (isinstance(e.get("quota_note"), str) and e["quota_note"].strip())
        for e in entries
    )
    lines = [
        "| Model Family | Pattern / ID | Thinking Efforts | Quota |"
        if has_quota
        else "| Model Family | Pattern / ID | Thinking Efforts |",
        "| :--- | :--- | :--- | :--- |"
        if has_quota
        else "| :--- | :--- | :--- |",
    ]
    for fam in families:
        ordered_efforts = [e for e in EFFORT_ORDER if e in fam["efforts"]]
        extra_efforts = [e for e in fam["efforts"] if e not in EFFORT_ORDER]
        ordered_efforts.extend(extra_efforts)
        effort_str = ", ".join(ordered_efforts)
        if has_quota:
            quota_str = _format_family_quota(fam, ordered_efforts)
            lines.append(
                f"| **{fam['family_label']}** | `{fam['family_key']}` | `{effort_str}` | {quota_str} |"
            )
        else:
            lines.append(f"| **{fam['family_label']}** | `{fam['family_key']}` | `{effort_str}` |")
    return "\n".join(lines)


def _parse_numeric_quota(quota: Any) -> float | None:
    """Parse numeric quota value (e.g. 80, 0.0, '80%', '0.0%'), returning None for non-numeric/bool."""
    if quota is None or isinstance(quota, bool):
        return None
    if isinstance(quota, (int, float)):
        val = float(quota)
        return None if (math.isnan(val) or math.isinf(val)) else val
    if isinstance(quota, str):
        stripped = quota.strip()
        if stripped.endswith("%"):
            stripped = stripped[:-1].strip()
        if not stripped:
            return None
        try:
            val = float(stripped)
        except ValueError:
            return None
        return None if (math.isnan(val) or math.isinf(val)) else val
    return None


def _is_exhausted_quota(quota: Any) -> bool:
    """Return True if quota represents numeric <= 0%."""
    parsed = _parse_numeric_quota(quota)
    return parsed is not None and parsed <= 0.0


def _build_lookup_tables(
    entries: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Build exact ID/family lookups plus case-insensitive display-name lookup."""
    by_id = {e["id"]: e for e in entries}
    by_display: dict[str, dict[str, Any]] = {}
    by_family: dict[str, list[str]] = {}
    for e in entries:
        by_family.setdefault(e["family_key"], []).append(e["id"])
        has_explicit = e.get("has_explicit_display")
        if has_explicit is None:
            has_explicit = e["display_name"] != e["id"]
        if has_explicit:
            by_display[e["display_name"].strip().lower()] = e
    return by_id, by_display, by_family


def _lookup_entry(
    token: str,
    by_id: dict[str, dict[str, Any]],
    by_display: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    return by_id.get(token) or by_display.get(token.lower())


def _resolve_allowed_pool(
    entries: list[dict[str, Any]],
    allowed_pool: list[str],
) -> tuple[bool, set[str], list[str]]:
    """Resolve --allowed-pool tokens to concrete model IDs, rejecting unknown tokens."""
    by_id, by_display, by_family = _build_lookup_tables(entries)

    cleaned = [t.strip() for t in allowed_pool if t.strip()]
    if not cleaned:
        return False, set(), ["ERROR: --allowed-pool requires at least one non-empty model ID or pattern."]

    allowed_ids: set[str] = set()
    unknown_errors: list[str] = []
    for token in cleaned:
        entry = _lookup_entry(token, by_id, by_display)
        if entry:
            allowed_ids.add(entry["id"])
        elif token in by_family:
            allowed_ids.update(by_family[token])
        else:
            unknown_errors.append(
                f"ERROR: Unknown model or family pattern '{token}' in --allowed-pool."
            )
    if unknown_errors:
        return False, set(), unknown_errors
    return True, allowed_ids, []


def classify_pool_diversity(
    entries: list[dict[str, Any]],
    targets: list[str],
) -> dict[str, Any]:
    """Classify diversity across unique resolved targets."""
    by_id, by_display, _ = _build_lookup_tables(entries)
    unique_resolved: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_target in targets:
        target = raw_target.strip()
        if not target:
            continue
        entry = _lookup_entry(target, by_id, by_display)
        if entry and entry["id"] not in seen_ids:
            seen_ids.add(entry["id"])
            unique_resolved.append(entry)

    vendors = list(dict.fromkeys(e.get("vendor") or infer_vendor(e["id"]) for e in unique_resolved))
    families = list(dict.fromkeys(_base_family_key(e["family_key"]) for e in unique_resolved))
    ids = [e["id"] for e in unique_resolved]

    if len(vendors) >= 2:
        tier = "cross-vendor"
        diverse = True
    elif len(families) >= 2:
        tier = "single-vendor cross-variant"
        diverse = True
    else:
        tier = "single-variant"
        diverse = False

    return {
        "count": len(ids),
        "unique_ids": ids,
        "vendors": vendors,
        "families": families,
        "tier": tier,
        "diverse": diverse,
    }


def validate_models_detailed(
    entries: list[dict[str, Any]],
    targets: list[str],
    require_quota: bool = False,
    allowed_pool: list[str] | None = None,
) -> tuple[bool, list[str], list[dict[str, Any]], list[str]]:
    """Validate targets and return (ok, messages, per_target_results, passed_ids)."""
    cleaned_targets = [t.strip() for t in targets if t.strip()]
    if not cleaned_targets:
        msg = "ERROR: --validate requires at least one non-empty model ID or display name."
        return False, [msg], [], []

    allowed_ids: set[str] | None = None
    if allowed_pool is not None:
        pool_ok, allowed_ids, pool_msgs = _resolve_allowed_pool(entries, allowed_pool)
        if not pool_ok:
            return False, pool_msgs, [], []

    by_id, by_display, by_family = _build_lookup_tables(entries)

    messages: list[str] = []
    results: list[dict[str, Any]] = []
    passed_ids: list[str] = []
    ok = True

    for target in cleaned_targets:
        entry = _lookup_entry(target, by_id, by_display)
        if not entry:
            ok = False
            suggestions = by_family.get(target)
            if suggestions:
                msg = (
                    f"ERROR: Unknown model '{target}' "
                    f"(family wildcard; choose a concrete ID: {', '.join(suggestions)})."
                )
            else:
                msg = f"ERROR: Unknown model '{target}' (not in live catalog)."
            messages.append(msg)
            results.append(
                {
                    "target": target,
                    "ok": False,
                    "id": None,
                    "display_name": None,
                    "vendor": None,
                    "family_key": None,
                    "quota_remaining": None,
                    "quota_resets": None,
                    "quota_note": None,
                    "source": None,
                    "message": msg,
                }
            )
            continue

        quota = entry.get("quota_remaining")
        raw_note = entry.get("quota_note")
        note = raw_note.strip() if isinstance(raw_note, str) else ""
        source = entry.get("source")
        numeric_quota = _parse_numeric_quota(quota)

        def record(target_ok: bool, msg: str) -> None:
            messages.append(msg)
            results.append(
                {
                    "target": target,
                    "ok": target_ok,
                    "id": entry["id"],
                    "display_name": entry["display_name"],
                    "vendor": entry.get("vendor") or infer_vendor(entry["id"]),
                    "family_key": entry["family_key"],
                    "quota_remaining": quota,
                    "quota_resets": entry.get("quota_resets"),
                    "quota_note": note or None,
                    "source": source,
                    "message": msg,
                }
            )
            if target_ok:
                passed_ids.append(entry["id"])

        if allowed_ids is not None and entry["id"] not in allowed_ids:
            ok = False
            record(False, f"ERROR: '{entry['id']}' is outside --allowed-pool.")
            continue

        if numeric_quota is not None and numeric_quota <= 0.0 and not note:
            ok = False
            record(
                False,
                f"ERROR: '{entry['id']}' has {quota} quota remaining (resets {entry.get('quota_resets')}).",
            )
        elif numeric_quota is None:
            if quota is None:
                unknown_info = (
                    "quota=unknown (agy source — existence only)"
                    if source == "agy"
                    else "quota=unknown (missing from swarm JSON)"
                )
            else:
                unknown_info = f"quota=unknown (non-numeric quota value {quota!r})"
            if require_quota:
                ok = False
                record(False, f"ERROR: '{entry['id']}' has {unknown_info} (--require-quota).")
            else:
                note_str = f", {note}" if note else ""
                record(
                    True,
                    f"OK: {entry['id']} -> {entry['display_name']} ({unknown_info}{note_str})",
                )
        else:
            note_str = f", {note}" if note else ""
            record(True, f"OK: {entry['id']} -> {entry['display_name']} (quota={quota}{note_str})")

    return ok, messages, results, passed_ids


def validate_models(
    entries: list[dict[str, Any]],
    targets: list[str],
    require_quota: bool = False,
    allowed_pool: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate comma-separated model IDs or display names against the catalog."""
    ok, messages, _, _ = validate_models_detailed(
        entries,
        targets,
        require_quota=require_quota,
        allowed_pool=allowed_pool,
    )
    return ok, messages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Antigravity models + thinking efforts and validate Launch Prompt choices."
    )
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--from-swarm-json",
        metavar="PATH",
        help="Path to JSON file from `swarm{action:'models', all:true}`, or '-' for stdin.",
    )
    source_group.add_argument(
        "--from-agy",
        action="store_true",
        help="Query live models by running `agy models`.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format (default: markdown).",
    )
    parser.add_argument(
        "--validate",
        metavar="MODELS",
        help="Comma-separated model IDs or display names to verify before launch.",
    )
    parser.add_argument(
        "--require-quota",
        action="store_true",
        help="Fail --validate if any validated model lacks numeric usable quota_remaining.",
    )
    parser.add_argument(
        "--require-diverse",
        action="store_true",
        help="Fail --validate unless validated targets span cross-vendor or single-vendor cross-variant families.",
    )
    parser.add_argument(
        "--allowed-pool",
        metavar="MODELS",
        help="Comma-separated allowlist of approved model IDs, display names, or family patterns.",
    )
    args = parser.parse_args()

    if args.validate is None:
        misplaced: list[str] = []
        if args.allowed_pool is not None:
            misplaced.append("--allowed-pool")
        if args.require_diverse:
            misplaced.append("--require-diverse")
        if args.require_quota:
            misplaced.append("--require-quota")
        if misplaced:
            parser.error(f"{', '.join(misplaced)} require --validate.")

    try:
        if args.from_swarm_json is not None:
            if not args.from_swarm_json.strip():
                raise ValueError("--from-swarm-json requires a file path or '-'.")
            if args.from_swarm_json == "-":
                entries = parse_swarm_json(sys.stdin.read())
            else:
                with open(args.from_swarm_json, encoding="utf-8") as fh:
                    entries = parse_swarm_json(fh.read())
        elif args.from_agy:
            entries = fetch_from_agy()
        elif not sys.stdin.isatty():
            raw = sys.stdin.read()
            if raw.strip():
                entries = parse_swarm_json(raw)
            else:
                entries = fetch_from_agy()
        else:
            entries = fetch_from_agy()

        if not entries:
            raise ValueError("No models found in catalog.")
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"Error loading models: {exc}", file=sys.stderr)
        return 2

    if args.validate is not None:
        targets = args.validate.split(",")
        allowed_pool = args.allowed_pool.split(",") if args.allowed_pool is not None else None
        ok, messages, results, passed_ids = validate_models_detailed(
            entries,
            targets,
            require_quota=args.require_quota,
            allowed_pool=allowed_pool,
        )
        errors = [m for m in messages if m.startswith("ERROR:")]
        warnings: list[str] = []
        text_lines = list(messages)

        diversity = classify_pool_diversity(entries, passed_ids)
        if diversity["count"] >= 2:
            tier = diversity["tier"]
            if tier == "cross-vendor":
                text_lines.append(
                    f"POOL DIVERSITY: cross-vendor "
                    f"(vendors: {', '.join(diversity['vendors'])}; families: {', '.join(diversity['families'])})"
                )
            elif tier == "single-vendor cross-variant":
                text_lines.append(
                    f"POOL DIVERSITY: single-vendor cross-variant "
                    f"(vendor: {diversity['vendors'][0]}; families: {', '.join(diversity['families'])})"
                )
            else:
                fam_label = diversity["families"][0] if diversity["families"] else "unknown"
                if args.require_diverse:
                    ok = False
                    err_msg = (
                        f"ERROR: POOL DIVERSITY: single-variant "
                        f"(all validated models share family '{fam_label}'; --require-diverse requires cross-vendor or single-vendor cross-variant coverage)."
                    )
                    errors.append(err_msg)
                    text_lines.append(err_msg)
                else:
                    warn_msg = (
                        f"WARNING: POOL DIVERSITY: single-variant "
                        f"(all validated models share family '{fam_label}'; prefer cross-vendor or distinct-variant pairing)."
                    )
                    warnings.append(warn_msg)
                    text_lines.append(warn_msg)
        elif args.require_diverse:
            ok = False
            err_msg = (
                "ERROR: POOL DIVERSITY: --require-diverse requires at least 2 validated models "
                f"(found {diversity['count']} unique)."
            )
            errors.append(err_msg)
            text_lines.append(err_msg)

        if args.format == "json":
            print(
                json.dumps(
                    {
                        "valid": ok,
                        "results": results,
                        "diversity": diversity,
                        "errors": errors,
                        "warnings": warnings,
                    },
                    indent=2,
                )
            )
        else:
            for line in text_lines:
                print(line)

        return 0 if ok else 1

    if args.format == "json":
        print(json.dumps({"count": len(entries), "families": group_by_family(entries)}, indent=2))
    else:
        print(format_markdown(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
