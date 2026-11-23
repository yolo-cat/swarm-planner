#!/usr/bin/env python3
"""Example PreToolUse guard script tailored during swarm-planner pre-session.

Reads Antigravity's hook JSON payload on stdin, resolves paths relative to
`payload["cwd"]` (essential for `/swarm` `workspace:"share"` worktrees), and
enforces deterministic project boundaries in < 100ms.

Unattended-safe by default: never emits `"ask"` or `"force_ask"` unless
`SWARM_GUARD_INTERACTIVE=1` is set for single-session interactive runs.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys

# Customize these rules from Step 3/4 of swarm-planner:
FORBIDDEN_PATH_PATTERNS = [
    r"(^|/)migrations/\d+.*\.(sql|py)$",
    r"(^|/)(generated|openapi-gen)/",
    r"(^|/)\.env(\.(?!example$|sample$|template$)[^/]+)?$",
]
PROTECTED_PATH_PATTERNS = [
    r"(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|Cargo\.lock|uv\.lock)$",
    r"(^|/)src/(auth|billing)/",
]
DENIED_COMMAND_PATTERNS = [
    (r"\bgit\b.*\bpush\b", "Remote push is blocked by project guardrails; ask the user first."),
    (
        r"\bnpm\s+(install|i)\b",
        "Direct `npm install` is blocked by project guardrails; coordinate dependency changes via @coordinator.",
    ),
    (r"\b(prisma\s+db\s+push\s+--force-reset|dropdb)\b", "Destructive DB reset blocked."),
]

# Matches `.env` or `.env.<suffix>` secrets while allowing `.env.example`/`.sample`/`.template`.
ENV_SECRET_CMD_RE = re.compile(
    r"(?:^|[\s'\"`(/=<>:,])(?:\.{1,2}/|[^\s'\"`()=<>]*?/)?\.env"
    r"(?:\.(?!(?:example|sample|template)(?:$|[\s'\"`);&|<>:,]))[A-Za-z0-9._-]+)?"
    r"(?=$|[\s'\"`);&|<>:,])"
)
SEGMENT_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||[;|\n])\s*")
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")

MUTATING_COMMANDS = {
    "tee",
    "rm",
    "mv",
    "cp",
    "chmod",
    "chown",
    "truncate",
    "touch",
    "dd",
}
COMMAND_WRAPPERS = {"sudo", "env", "command", "nohup", "nice", "time", "xargs"}
OUTPUT_REDIR_TOKENS = {">", ">>", "&>", "&>>", ">|", ">&"}
SAFE_SINK_PATHS = {"/dev/null"}


def is_interactive() -> bool:
    """Return True only when interactive prompting is explicitly opted in."""
    return os.environ.get("SWARM_GUARD_INTERACTIVE") == "1"


def _resolve_real(raw_path: str, cwd: str) -> str:
    expanded = os.path.expanduser(raw_path)
    abs_path = expanded if os.path.isabs(expanded) else os.path.join(cwd, expanded)
    return os.path.realpath(abs_path)


def _is_within(path_real: str, root_real: str) -> bool:
    if not root_real:
        return False
    try:
        return os.path.commonpath([path_real, root_real]) == root_real
    except ValueError:
        return False


def normalize_relpath(raw_path: str, cwd: str) -> str:
    """Resolve raw_path against the worker's cwd and return POSIX-style relpath."""
    if not raw_path:
        return ""
    try:
        rel = os.path.relpath(_resolve_real(raw_path, cwd), os.path.realpath(cwd))
    except ValueError:
        rel = raw_path
    return rel.replace(os.sep, "/")


def _tokenize_segment(segment: str) -> list[str]:
    try:
        lexer = shlex.shlex(segment, posix=True, punctuation_chars="><&")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        # Unclosed quotes: fall back to whitespace splitting with > separation
        spaced = re.sub(r"(>>?|&>>?|>&)", r" \1 ", segment)
        return spaced.split()


def _check_shell_target_path(
    raw_target: str,
    cwd: str,
    cwd_real: str,
    *,
    allow_dev_null: bool = False,
) -> dict | None:
    if not raw_target:
        return None
    if allow_dev_null and raw_target in SAFE_SINK_PATHS:
        return None
    target_real = _resolve_real(raw_target, cwd)
    if not _is_within(target_real, cwd_real):
        return {
            "decision": "deny",
            "reason": f"Mutating command targets path outside workspace ({raw_target}).",
        }
    rel_path = os.path.relpath(target_real, cwd_real).replace(os.sep, "/")
    for pattern in FORBIDDEN_PATH_PATTERNS:
        if re.search(pattern, rel_path):
            return {
                "decision": "deny",
                "reason": (
                    f"Protected no-touch path ({rel_path}). "
                    "Coordinate via @coordinator if an exception is needed."
                ),
            }
    return None


def _is_in_place_flag(token: str) -> bool:
    if token == "--in-place" or token.startswith("--in-place="):
        return True
    if token.startswith("-") and not token.startswith("--") and len(token) > 1:
        # Catches -i, -i.bak, -i'', -pi, -pie, etc.
        return "i" in token[1:]
    return False


def _check_command_segment(segment: str, cwd: str, cwd_real: str) -> dict | None:
    if not segment:
        return None

    for pattern, reason in DENIED_COMMAND_PATTERNS:
        if re.search(pattern, segment):
            return {"decision": "deny", "reason": reason}

    if ENV_SECRET_CMD_RE.search(segment):
        return {
            "decision": "deny",
            "reason": (
                "Command references protected .env secrets. "
                "Coordinate via @coordinator if an exception is needed."
            ),
        }

    tokens = _tokenize_segment(segment)
    if not tokens:
        return None

    # 1. Inspect output redirections (`>`, `>>`, `&>`, etc.) and strip them before command inspection.
    non_redir_tokens: list[str] = []
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok in OUTPUT_REDIR_TOKENS:
            next_tok = tokens[idx + 1] if idx + 1 < len(tokens) else ""
            # Handle `2>&1` or `2>&-` fd duplication/close safely
            if tok == ">&" and (next_tok.isdigit() or next_tok == "-"):
                idx += 2
                continue
            if next_tok:
                deny = _check_shell_target_path(
                    next_tok, cwd, cwd_real, allow_dev_null=True
                )
                if deny:
                    return deny
            idx += 2
            continue
        # Drop standalone fd number directly preceding a redirection (e.g. `2` in `2>/dev/null`)
        if tok.isdigit() and idx + 1 < len(tokens) and tokens[idx + 1] in OUTPUT_REDIR_TOKENS:
            idx += 1
            continue
        non_redir_tokens.append(tok)
        idx += 1

    # 2. Identify the effective command after env assignments and wrappers.
    cmd_idx = 0
    while cmd_idx < len(non_redir_tokens):
        tok = non_redir_tokens[cmd_idx]
        if ENV_ASSIGN_RE.match(tok):
            cmd_idx += 1
            continue
        base = os.path.basename(tok)
        if base in COMMAND_WRAPPERS:
            cmd_idx += 1
            # Skip flags belonging to wrapper (e.g. `sudo -u root`, `xargs -0`)
            while cmd_idx < len(non_redir_tokens) and non_redir_tokens[cmd_idx].startswith("-"):
                cmd_idx += 1
            continue
        break

    if cmd_idx >= len(non_redir_tokens):
        return None

    cmd_name = os.path.basename(non_redir_tokens[cmd_idx])
    cmd_args = non_redir_tokens[cmd_idx + 1 :]

    is_mutating = cmd_name in MUTATING_COMMANDS
    if cmd_name in {"sed", "perl"}:
        is_mutating = any(_is_in_place_flag(arg) for arg in cmd_args)

    if not is_mutating:
        return None

    # 3. Inspect target path arguments for mutating commands.
    skip_next = False
    for arg in cmd_args:
        if skip_next:
            skip_next = False
            continue
        if not arg:
            continue
        if cmd_name in {"sed", "perl"} and arg == "-e":
            skip_next = True
            continue
        if cmd_name == "dd":
            if arg.startswith("of="):
                deny = _check_shell_target_path(
                    arg[3:], cwd, cwd_real, allow_dev_null=True
                )
                if deny:
                    return deny
            continue
        if arg.startswith("-"):
            continue
        deny = _check_shell_target_path(
            arg,
            cwd,
            cwd_real,
            allow_dev_null=(cmd_name == "tee"),
        )
        if deny:
            return deny

    return None


def check_tool_call(payload: dict) -> dict:
    """Inspect toolCall name & args and return a valid PreToolUse decision."""
    if not isinstance(payload, dict):
        raise ValueError("Hook payload must be a JSON object.")

    tool_call = payload.get("toolCall") or {}
    tool_name = tool_call.get("name", "")
    args = tool_call.get("args") or {}
    cwd = payload.get("cwd") or os.getcwd()
    cwd_real = os.path.realpath(cwd)

    if tool_name == "run_command":
        cmd = args.get("CommandLine") or args.get("command") or ""
        for segment in SEGMENT_SPLIT_RE.split(cmd):
            deny = _check_command_segment(segment.strip(), cwd, cwd_real)
            if deny:
                return deny
        return {"decision": "allow"}

    target_path = args.get("Path") or args.get("TargetFile") or args.get("path") or ""
    if target_path:
        target_real = _resolve_real(target_path, cwd)
        artifact_dir = payload.get("artifactDirectoryPath") or ""
        artifact_real = os.path.realpath(artifact_dir) if artifact_dir else ""

        in_cwd = _is_within(target_real, cwd_real)
        in_artifact = bool(artifact_real) and _is_within(target_real, artifact_real)

        if not in_cwd and not in_artifact:
            return {
                "decision": "deny",
                "reason": f"Path escapes allowed workspace/artifact directory ({target_path}).",
            }
        if in_artifact and not in_cwd:
            return {"decision": "allow"}

        rel_path = os.path.relpath(target_real, cwd_real).replace(os.sep, "/")
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if re.search(pattern, rel_path):
                return {
                    "decision": "deny",
                    "reason": (
                        f"Protected no-touch path ({rel_path}). "
                        "Coordinate via @coordinator if an exception is needed."
                    ),
                }
        for pattern in PROTECTED_PATH_PATTERNS:
            if re.search(pattern, rel_path):
                if is_interactive():
                    return {
                        "decision": "force_ask",
                        "reason": f"High-impact shared/sensitive file ({rel_path}) requires confirmation.",
                    }
                return {
                    "decision": "deny",
                    "reason": (
                        f"High-impact shared/sensitive file ({rel_path}). "
                        "Coordinate via @coordinator before modifying."
                    ),
                }

    return {"decision": "allow"}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        result = check_tool_call(payload)
    except Exception as exc:
        decision = "ask" if is_interactive() else "deny"
        result = {"decision": decision, "reason": f"Hook guard error: {exc}"}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
