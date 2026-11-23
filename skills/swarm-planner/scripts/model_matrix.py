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
import re
import subprocess
import sys
from typing import Any

ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
EFFORT_SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<effort>low|medium|high|xhigh|max)$")
DISPLAY_EFFORT_RE = re.compile(r"\s+\((Low|Medium|High|XHigh|Max)\)$", re.IGNORECASE)
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max", "default"]


def split_effort(model_id: str, display_name: str) -> tuple[str, str, str]:
    """Return (family_key, family_label, effort_level) for a model entry."""
    match = EFFORT_SUFFIX_RE.match(model_id)
    if match:
        family_key = f"{match.group('base')}-*"
        effort = match.group("effort").lower()
        family_label = DISPLAY_EFFORT_RE.sub("", display_name).strip()
        return family_key, family_label, effort
    return model_id, display_name.strip(), "default"


def parse_swarm_json(raw: str) -> list[dict[str, Any]]:
    """Parse JSON returned by `swarm{action:'models', all:true}`."""
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("Expected top-level JSON object from swarm models output.")
    models = data.get("models", [])
    display_names = data.get("display_names", {})
    quotas = data.get("quotas", {})
    entries: list[dict[str, Any]] = []
    for model_id in models:
        display_name = display_names.get(model_id, model_id)
        quota_info = quotas.get(model_id, {}) or {}
        family_key, family_label, effort = split_effort(model_id, display_name)
        entries.append(
            {
                "id": model_id,
                "display_name": display_name,
                "family_key": family_key,
                "family_label": family_label,
                "effort": effort,
                "quota_remaining": quota_info.get("quota_remaining"),
                "quota_resets": quota_info.get("quota_resets"),
                "quota_note": quota_info.get("quota_note"),
                "source": "swarm",
            }
        )
    return entries


def parse_agy_output(raw: str) -> list[dict[str, Any]]:
    """Parse text output from `agy models`, stripping spinner ANSI sequences."""
    cleaned = ANSI_CSI_RE.sub("", raw).replace("\r", "\n")
    entries: list[dict[str, Any]] = []
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
        if not MODEL_ID_RE.match(model_id):
            continue
        display_name = parts[1].strip() if len(parts) > 1 else model_id
        family_key, family_label, effort = split_effort(model_id, display_name)
        entries.append(
            {
                "id": model_id,
                "display_name": display_name,
                "family_key": family_key,
                "family_label": family_label,
                "effort": effort,
                "quota_remaining": None,
                "quota_resets": None,
                "quota_note": None,
                "source": "agy",
            }
        )
    return entries


def fetch_from_agy() -> list[dict[str, Any]]:
    """Run `agy models` and parse its output."""
    proc = subprocess.run(
        ["agy", "models"],
        capture_output=True,
        text=True,
        check=False,
    )
    combined = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode != 0:
        raise RuntimeError(f"`agy models` failed (exit {proc.returncode}): {combined.strip()}")
    return parse_agy_output(combined)


def group_by_family(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group model entries into family rows ordered by first appearance."""
    families: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for entry in entries:
        key = entry["family_key"]
        if key not in families:
            families[key] = {
                "family_key": key,
                "family_label": entry["family_label"],
                "efforts": {},
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
    return list(families.values())


def _format_single_quota(q_info: dict[str, Any], include_resets: bool = True) -> str:
    quota = q_info.get("quota_remaining")
    quota_val = quota if quota is not None else "-"
    note = f" ({q_info['quota_note']})" if q_info.get("quota_note") else ""
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
        e.get("quota_remaining") is not None or e.get("quota_note") is not None
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


def _is_exhausted_quota(quota: Any) -> bool:
    """Return True if quota represents 0% or <= 0%."""
    if quota is None:
        return False
    if isinstance(quota, (int, float)):
        return quota <= 0
    if isinstance(quota, str):
        stripped = quota.strip().rstrip("%").strip()
        try:
            return float(stripped) <= 0.0
        except ValueError:
            return False
    return False


def validate_models(
    entries: list[dict[str, Any]],
    targets: list[str],
    require_quota: bool = False,
) -> tuple[bool, list[str]]:
    """Validate comma-separated model IDs or display names against the catalog."""
    by_id = {e["id"]: e for e in entries}
    by_display = {e["display_name"].lower(): e for e in entries}
    messages: list[str] = []
    ok = True
    for raw_target in targets:
        target = raw_target.strip()
        if not target:
            continue
        entry = by_id.get(target) or by_display.get(target.lower())
        if not entry:
            ok = False
            messages.append(f"ERROR: Unknown model '{target}' (not in live catalog).")
            continue
        quota = entry.get("quota_remaining")
        note = entry.get("quota_note")
        source = entry.get("source")
        if _is_exhausted_quota(quota) and not note:
            ok = False
            messages.append(
                f"ERROR: '{entry['id']}' has {quota} quota remaining (resets {entry.get('quota_resets')})."
            )
        elif quota is None:
            unknown_info = (
                "quota=unknown (agy source — existence only)"
                if source == "agy"
                else "quota=unknown (missing from swarm JSON)"
            )
            if require_quota:
                ok = False
                messages.append(
                    f"ERROR: '{entry['id']}' has {unknown_info} (--require-quota)."
                )
            else:
                note_str = f", {note}" if note else ""
                messages.append(f"OK: {entry['id']} -> {entry['display_name']} ({unknown_info}{note_str})")
        else:
            note_str = f", {note}" if note else ""
            messages.append(f"OK: {entry['id']} -> {entry['display_name']} (quota={quota}{note_str})")
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
        help="Fail --validate if any validated model lacks known quota_remaining.",
    )
    args = parser.parse_args()

    try:
        if args.from_swarm_json == "-":
            entries = parse_swarm_json(sys.stdin.read())
        elif args.from_swarm_json:
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
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"Error loading models: {exc}", file=sys.stderr)
        return 2

    if args.validate:
        targets = args.validate.split(",")
        ok, messages = validate_models(entries, targets, require_quota=args.require_quota)
        for msg in messages:
            print(msg)
        return 0 if ok else 1

    if args.format == "json":
        print(json.dumps({"count": len(entries), "families": group_by_family(entries)}, indent=2))
    else:
        print(format_markdown(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
