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

ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
MODEL_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]*$")
EFFORT_SUFFIX_RE = re.compile(r"^(?P<base>.+)-(?P<effort>low|medium|high|xhigh|max)$")
DISPLAY_EFFORT_RE = re.compile(r"\s+\((Low|Medium|High|XHigh|Max)\)$", re.IGNORECASE)
VENDOR_SPLIT_RE = re.compile(r"[-_:.]+")
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max", "default"]


def infer_vendor(model_id: str) -> str:
    """Return normalized vendor prefix (e.g. 'gemini', 'claude', 'gpt')."""
    cleaned = model_id.strip().lower()
    if not cleaned:
        return "unknown"
    parts = VENDOR_SPLIT_RE.split(cleaned, maxsplit=1)
    return parts[0] if parts and parts[0] else cleaned


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
    for item in models:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("Every entry in 'models' must be a non-empty string.")

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
            display_name = raw_display
        else:
            display_name = model_id

        raw_quota = quotas.get(model_id)
        if raw_quota is None:
            quota_info: dict[str, Any] = {}
        elif isinstance(raw_quota, dict):
            quota_info = raw_quota
        else:
            raise ValueError(f"'quotas[{model_id!r}]' must be a JSON object or null.")

        family_key, family_label, effort = split_effort(model_id, display_name)
        entries.append(
            {
                "id": model_id,
                "display_name": display_name,
                "family_key": family_key,
                "family_label": family_label,
                "vendor": infer_vendor(model_id),
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
        if model_id.endswith(":") or not MODEL_ID_RE.match(model_id):
            continue
        display_name = parts[1].strip() if len(parts) > 1 else model_id
        family_key, family_label, effort = split_effort(model_id, display_name)
        entries.append(
            {
                "id": model_id,
                "display_name": display_name,
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


def fetch_from_agy() -> list[dict[str, Any]]:
    """Run `agy models` and parse its output."""
    proc = subprocess.run(
        ["agy", "models"],
        capture_output=True,
        text=True,
        check=False,
    )
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


def _resolve_allowed_pool(
    entries: list[dict[str, Any]],
    allowed_pool: list[str],
) -> tuple[bool, set[str], list[str]]:
    """Resolve --allowed-pool tokens to concrete model IDs."""
    by_id = {e["id"]: e for e in entries}
    by_display = {e["display_name"].lower(): e for e in entries}
    by_family: dict[str, list[str]] = {}
    for e in entries:
        by_family.setdefault(e["family_key"], []).append(e["id"])

    cleaned = [t.strip() for t in allowed_pool if t.strip()]
    if not cleaned:
        return False, set(), ["ERROR: --allowed-pool requires at least one non-empty model ID or pattern."]

    allowed_ids: set[str] = set()
    for token in cleaned:
        entry = by_id.get(token) or by_display.get(token.lower())
        if entry:
            allowed_ids.add(entry["id"])
        elif token in by_family:
            allowed_ids.update(by_family[token])
        else:
            # Keep raw token so typos don't silently open the pool; exact match check still enforces it.
            allowed_ids.add(token)
    return True, allowed_ids, []


def classify_pool_diversity(
    entries: list[dict[str, Any]],
    targets: list[str],
) -> dict[str, Any]:
    """Classify diversity across resolved validated targets."""
    by_id = {e["id"]: e for e in entries}
    by_display = {e["display_name"].lower(): e for e in entries}
    resolved: list[dict[str, Any]] = []
    for raw_target in targets:
        target = raw_target.strip()
        if not target:
            continue
        entry = by_id.get(target) or by_display.get(target.lower())
        if entry:
            resolved.append(entry)

    vendors = list(dict.fromkeys(e.get("vendor") or infer_vendor(e["id"]) for e in resolved))
    families = list(dict.fromkeys(e["family_key"] for e in resolved))
    ids = list(dict.fromkeys(e["id"] for e in resolved))

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
        "count": len(resolved),
        "unique_ids": ids,
        "vendors": vendors,
        "families": families,
        "tier": tier,
        "diverse": diverse,
    }


def validate_models(
    entries: list[dict[str, Any]],
    targets: list[str],
    require_quota: bool = False,
    allowed_pool: list[str] | None = None,
) -> tuple[bool, list[str]]:
    """Validate comma-separated model IDs or display names against the catalog."""
    cleaned_targets = [t.strip() for t in targets if t.strip()]
    if not cleaned_targets:
        return False, ["ERROR: --validate requires at least one non-empty model ID or display name."]

    allowed_ids: set[str] | None = None
    if allowed_pool is not None:
        pool_ok, allowed_ids, pool_msgs = _resolve_allowed_pool(entries, allowed_pool)
        if not pool_ok:
            return False, pool_msgs

    by_id = {e["id"]: e for e in entries}
    by_display = {e["display_name"].lower(): e for e in entries}
    by_family: dict[str, list[str]] = {}
    for e in entries:
        by_family.setdefault(e["family_key"], []).append(e["id"])

    messages: list[str] = []
    ok = True
    for target in cleaned_targets:
        entry = by_id.get(target) or by_display.get(target.lower())
        if not entry:
            ok = False
            suggestions = by_family.get(target)
            if suggestions:
                messages.append(
                    f"ERROR: Unknown model '{target}' (family wildcard; choose a concrete ID: {', '.join(suggestions)})."
                )
            else:
                messages.append(f"ERROR: Unknown model '{target}' (not in live catalog).")
            continue

        if allowed_ids is not None and entry["id"] not in allowed_ids:
            ok = False
            messages.append(
                f"ERROR: '{entry['id']}' is outside --allowed-pool."
            )
            continue

        quota = entry.get("quota_remaining")
        note = entry.get("quota_note")
        source = entry.get("source")
        numeric_quota = _parse_numeric_quota(quota)

        if numeric_quota is not None and numeric_quota <= 0.0 and not note:
            ok = False
            messages.append(
                f"ERROR: '{entry['id']}' has {quota} quota remaining (resets {entry.get('quota_resets')})."
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
        ok, messages = validate_models(
            entries,
            targets,
            require_quota=args.require_quota,
            allowed_pool=allowed_pool,
        )
        for msg in messages:
            print(msg)

        diversity = classify_pool_diversity(entries, targets)
        if diversity["count"] >= 2:
            tier = diversity["tier"]
            if tier == "cross-vendor":
                print(
                    f"POOL DIVERSITY: cross-vendor "
                    f"(vendors: {', '.join(diversity['vendors'])}; families: {', '.join(diversity['families'])})"
                )
            elif tier == "single-vendor cross-variant":
                print(
                    f"POOL DIVERSITY: single-vendor cross-variant "
                    f"(vendor: {diversity['vendors'][0]}; families: {', '.join(diversity['families'])})"
                )
            else:
                fam_label = diversity["families"][0] if diversity["families"] else "unknown"
                if args.require_diverse:
                    ok = False
                    print(
                        f"ERROR: POOL DIVERSITY: single-variant "
                        f"(all validated models share family '{fam_label}'; --require-diverse requires cross-vendor or single-vendor cross-variant coverage)."
                    )
                else:
                    print(
                        f"WARNING: POOL DIVERSITY: single-variant "
                        f"(all validated models share family '{fam_label}'; prefer cross-vendor or distinct-variant pairing)."
                    )
        elif args.require_diverse:
            ok = False
            print(
                "ERROR: POOL DIVERSITY: --require-diverse requires at least 2 validated models."
            )

        return 0 if ok else 1

    if args.format == "json":
        print(json.dumps({"count": len(entries), "families": group_by_family(entries)}, indent=2))
    else:
        print(format_markdown(entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
