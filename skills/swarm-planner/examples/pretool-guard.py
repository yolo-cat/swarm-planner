#!/usr/bin/env python3
"""Example PreToolUse guard script tailored during swarm-planner pre-session.

Reads Antigravity's hook JSON payload on stdin, resolves paths relative to
`payload["cwd"]` (essential for `/swarm` `workspace:"share"` worktrees), and
enforces deterministic project boundaries in < 100ms.
"""

from __future__ import annotations

import json
import os
import re
import sys

# Customize these rules from Step 3/4 of swarm-planner:
FORBIDDEN_PATH_PATTERNS = [
    r"(^|/)migrations/\d+.*\.(sql|py)$",
    r"(^|/)(generated|openapi-gen)/",
    r"(^|/)\.env(\..+)?$",
]
ASK_PATH_PATTERNS = [
    r"(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|Cargo\.lock|uv\.lock)$",
    r"(^|/)src/(auth|billing)/",
]
DENIED_COMMAND_PATTERNS = [
    (r"\bgit\s+push\b", "Remote push is blocked by project guardrails; ask the user first."),
    (r"\bnpm\s+install\b", "This repo uses pnpm; run `pnpm install` instead."),
    (r"\b(prisma\s+db\s+push\s+--force-reset|dropdb)\b", "Destructive DB reset blocked."),
]


def normalize_relpath(raw_path: str, cwd: str) -> str:
    """Resolve raw_path against the worker's cwd and return POSIX-style relpath."""
    if not raw_path:
        return ""
    abs_path = raw_path if os.path.isabs(raw_path) else os.path.join(cwd, raw_path)
    try:
        rel = os.path.relpath(os.path.realpath(abs_path), os.path.realpath(cwd))
    except ValueError:
        rel = raw_path
    return rel.replace(os.sep, "/")


def check_tool_call(payload: dict) -> dict:
    """Inspect toolCall name & args and return a valid PreToolUse decision."""
    tool_call = payload.get("toolCall", {})
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args", {}) or {}
    cwd = payload.get("cwd") or os.getcwd()

    if tool_name == "run_command":
        cmd = args.get("CommandLine") or args.get("command") or ""
        for pattern, reason in DENIED_COMMAND_PATTERNS:
            if re.search(pattern, cmd):
                return {"decision": "deny", "reason": reason}
        return {"decision": "allow"}

    target_path = args.get("Path") or args.get("TargetFile") or args.get("path") or ""
    rel_path = normalize_relpath(target_path, cwd)
    if rel_path:
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if re.search(pattern, rel_path):
                return {
                    "decision": "deny",
                    "reason": f"Protected no-touch path ({rel_path}). Edit source schema or coordinate via @coordinator.",
                }
        for pattern in ASK_PATH_PATTERNS:
            if re.search(pattern, rel_path):
                return {
                    "decision": "force_ask",
                    "reason": f"High-impact shared/sensitive file ({rel_path}) requires confirmation.",
                }

    return {"decision": "allow"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        result = check_tool_call(payload)
    except Exception as exc:  # Fail-safe to 'ask' on malformed input rather than crashing silently
        result = {"decision": "ask", "reason": f"Hook guard error: {exc}"}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
