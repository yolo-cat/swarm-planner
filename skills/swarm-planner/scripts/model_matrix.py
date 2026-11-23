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

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\r")
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
    models = data.get("models", [])
    display_names = data.get("display_names", {})
    quotas = data.get("quotas", {})
    entries: list[dict[str, Any]] = []
    for model_id in models:
        display_name = display_names.get(model_id, model_id)
        quota_info = quotas.get(model_id, {})
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
            }
        )
    return entries


def parse_agy_output(raw: str) -> list[dict[str, Any]]:
    """Parse text output from `agy models`, stripping spinner ANSI sequences."""
    cleaned = ANSI_RE.sub("", raw)
    entries: list[dict[str, Any]] = []
    for line in cleaned.splitlines():
        line = line.strip()
        if not line or "Fetching available models" in line:
            continue
        # Remove optional braille spinner prefix if left over
        line = line.lstrip("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏ ").strip()
        parts = re.split(r"\t+|\s{2,}", line, maxsplit=1)
        if not parts or not parts[0]:
            continue
        model_id = parts[0]
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
            }
        families[key]["efforts"][entry["effort"]] = entry["id"]
    return list(families.values())


def format_markdown(entries: list[dict[str, Any]]) -> str:
    """Render a compact Markdown Model x Thinking-Effort table."""
    families = group_by_family(entries)
    has_quota = any(e["quota_remaining"] is not None for e in entries)
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
        effort_str = ", ".join(ordered_efforts)
        if has_quota:
            quota = fam["quota_remaining"] or "-"
            note = f" ({fam['quota_note']})" if fam["quota_note"] else ""
            resets = f" resets {fam['quota_resets']}" if fam["quota_resets"] else ""
            quota_str = f"{quota}{note}{resets}"
            lines.append(
                f"| **{fam['family_label']}** | `{fam['family_key']}` | `{effort_str}` | {quota_str} |"
            )
        else:
            lines.append(f"| **{fam['family_label']}** | `{fam['family_key']}` | `{effort_str}` |")
    return "\n".join(lines)


def validate_models(entries: list[dict[str, Any]], targets: list[str]) -> tuple[bool, list[str]]:
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
        quota = entry["quota_remaining"]
        if quota == "0%" and not entry["quota_note"]:
            ok = False
            messages.append(
                f"ERROR: '{entry['id']}' has 0% quota remaining (resets {entry['quota_resets']})."
            )
        else:
            q_info = f"quota={quota}" if quota is not None else "quota=unknown (agy source)"
            messages.append(f"OK: {entry['id']} -> {entry['display_name']} ({q_info})")
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
    args = parser.parse_args()

    try:
        if args.from_swarm_json == "-" or (
            not args.from_swarm_json and not args.from_agy and not sys.stdin.isatty()
        ):
            entries = parse_swarm_json(sys.stdin.read())
        elif args.from_swarm_json:
            with open(args.from_swarm_json, encoding="utf-8") as fh:
                entries = parse_swarm_json(fh.read())
        else:
            entries = fetch_from_agy()
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"Error loading models: {exc}", file=sys.stderr)
        return 2

    if args.validate:
        targets = args.validate.split(",")
        ok, messages = validate_models(entries, targets)
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
