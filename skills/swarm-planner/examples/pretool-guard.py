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
ENV_SECRET_PATH_PATTERN = r"(^|/)\.env(\.(?!example$|sample$|template$)[^/]+)?$"
FORBIDDEN_PATH_PATTERNS = [
    r"(^|/)migrations/\d+.*\.(sql|py)$",
    r"(^|/)(generated|openapi-gen)/",
    ENV_SECRET_PATH_PATTERN,
]
PROTECTED_PATH_PATTERNS = [
    r"(^|/)(package\.json|package-lock\.json|pnpm-lock\.yaml|Cargo\.lock|uv\.lock)$",
    r"(^|/)src/(auth|billing)/",
]
DENIED_COMMAND_PATTERNS = [
    (r"\bgit\b.*\bpush\b", "Remote push is blocked by project guardrails; ask the user first."),
    (
        r"\bnpm\b.*(?<!-)\b(install|i)\b",
        "Direct `npm install` is blocked by project guardrails; coordinate dependency changes via @coordinator.",
    ),
    (r"\b(prisma\s+db\s+push\s+--force-reset|dropdb)\b", "Destructive DB reset blocked."),
]

# Matches `.env` or `.env.<suffix>` secrets while allowing `.env.example`/`.sample`/`.template`.
ENV_SECRET_CMD_PATTERN = (
    r"(?:^|[\s'\"`(/=<>:,])(?:\.{1,2}/|[^\s'\"`()=<>]*?/)?\.env"
    r"(?:\.(?!(?:example|sample|template)(?:$|[\s'\"`);&|<>:,]))[A-Za-z0-9._-]+)?"
    r"(?=$|[\s'\"`);&|<>:,])"
)
SEGMENT_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||;|\n|(?<!>)\||(?<![&>])&(?![&>]))\s*")
ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=.*$")
SHELL_VAR_RE = re.compile(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*[^}]*\}|[A-Za-z_][A-Za-z0-9_]*|\()")

READ_TOOLS = {"read_file", "view_file"}
WRITE_TOOLS = {
    "write_file",
    "edit_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}

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
    "ln",
    "install",
    "unlink",
    "rsync",
    "patch",
}
INLINE_SHELLS = {"sh", "bash", "zsh", "dash", "ksh", "ash"}
COMMAND_WRAPPERS = {
    "sudo",
    "env",
    "command",
    "nohup",
    "nice",
    "time",
    "xargs",
    "timeout",
    "stdbuf",
    "doas",
    "ionice",
}
WRAPPER_VALUE_FLAGS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-T", "-U"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir"},
    "nice": {"-n", "--adjustment"},
    "xargs": {
        "-n",
        "-L",
        "-l",
        "-I",
        "-i",
        "-P",
        "-s",
        "-d",
        "-E",
        "-e",
        "-a",
        "--max-args",
        "--max-lines",
        "--replace",
        "--max-procs",
        "--max-chars",
        "--delimiter",
        "--eof",
        "--arg-file",
    },
    "timeout": {"-k", "-s", "--kill-after", "--signal"},
    "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
    "doas": {"-u", "-C"},
    "ionice": {"-c", "-n", "-p", "-P", "-u", "--class", "--classdata"},
    "time": {"-f", "-o", "--format", "--output"},
}
OUTPUT_REDIR_TOKENS = {">", ">>", "&>", "&>>", ">|", "<>", ">&"}
SAFE_SINK_PATHS = {"/dev/null"}
MAX_RECURSION_DEPTH = 4


def is_interactive() -> bool:
    """Return True only when interactive prompting is explicitly opted in."""
    return os.environ.get("SWARM_GUARD_INTERACTIVE") == "1"


def _is_case_insensitive_fs() -> bool:
    if os.environ.get("SWARM_GUARD_CASE_INSENSITIVE") == "1":
        return True
    return sys.platform in {"darwin", "win32"}


def _path_regex_flags() -> int:
    return re.IGNORECASE if _is_case_insensitive_fs() else 0


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


def _check_relpath_rules(rel_path: str) -> dict | None:
    flags = _path_regex_flags()
    for pattern in FORBIDDEN_PATH_PATTERNS:
        if re.search(pattern, rel_path, flags=flags):
            return {
                "decision": "deny",
                "reason": (
                    f"Protected no-touch path ({rel_path}). "
                    "Coordinate via @coordinator if an exception is needed."
                ),
            }
    for pattern in PROTECTED_PATH_PATTERNS:
        if re.search(pattern, rel_path, flags=flags):
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
    return None


def _tokenize_segment(segment: str) -> list[str]:
    try:
        lexer = shlex.shlex(segment, posix=True, punctuation_chars="><&|")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        # Unclosed quotes: fall back to whitespace splitting with longest redir tokens first
        spaced = re.sub(r"(&>>|&>|>>|>\||<>|>&|>)", r" \1 ", segment)
        return spaced.split()


def _check_shell_target_path(
    raw_target: str,
    seg_cwd: str,
    workspace_real: str,
    *,
    allow_dev_null: bool = False,
) -> dict | None:
    if not raw_target:
        return None
    if allow_dev_null and raw_target in SAFE_SINK_PATHS:
        return None

    candidate = raw_target
    if "$" in candidate or SHELL_VAR_RE.search(candidate):
        expanded = os.path.expandvars(candidate)
        if "$" in expanded:
            return {
                "decision": "deny",
                "reason": f"Mutating command targets dynamic shell variable path ({raw_target}).",
            }
        candidate = expanded

    target_real = _resolve_real(candidate, seg_cwd)
    if not _is_within(target_real, workspace_real):
        return {
            "decision": "deny",
            "reason": f"Mutating command targets path outside workspace ({raw_target}).",
        }
    rel_path = os.path.relpath(target_real, workspace_real).replace(os.sep, "/")
    return _check_relpath_rules(rel_path)


def _is_in_place_flag(token: str) -> bool:
    if token == "--in-place" or token.startswith("--in-place="):
        return True
    if token.startswith("-") and not token.startswith("--") and len(token) > 1:
        # Catches -i, -i.bak, -i'', -pi, -pie, etc.
        return "i" in token[1:]
    return False


def _strip_subshell_parens(segment: str) -> str:
    s = segment.strip()
    stripped_open = False
    while s.startswith("("):
        s = s[1:].strip()
        stripped_open = True
    while s.endswith(")") and (stripped_open or s.count(")") > s.count("(")):
        s = s[:-1].strip()
    return s


def _extract_command_substitutions(cmd: str) -> list[str]:
    """Extract inner commands from $(...) and backtick substitutions."""
    results: list[str] = []
    n = len(cmd)
    i = 0
    while i < n:
        if cmd[i] == "\\" and i + 1 < n:
            i += 2
            continue
        if cmd[i] == "$" and i + 1 < n and cmd[i + 1] == "(":
            depth = 1
            start = i + 2
            j = start
            while j < n and depth > 0:
                if cmd[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if cmd[j] == "(":
                    depth += 1
                elif cmd[j] == ")":
                    depth -= 1
                j += 1
            end = j - 1 if depth == 0 else n
            inner = cmd[start:end].strip()
            if inner:
                results.append(inner)
            i = j
            continue
        if cmd[i] == "`":
            start = i + 1
            j = start
            while j < n and cmd[j] != "`":
                if cmd[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                j += 1
            inner = cmd[start:j].strip()
            if inner:
                results.append(inner)
            i = j + 1
            continue
        i += 1
    return results


def _has_short_flag(token: str, letter: str) -> bool:
    return token.startswith("-") and not token.startswith("--") and len(token) > 1 and letter in token[1:]


def _check_command_segment(
    segment: str,
    seg_cwd: str,
    workspace_real: str,
    dir_stack: list[str],
    depth: int,
) -> tuple[dict | None, str]:
    segment = _strip_subshell_parens(segment)
    if not segment:
        return None, seg_cwd

    flags = _path_regex_flags()
    for pattern, reason in DENIED_COMMAND_PATTERNS:
        if re.search(pattern, segment):
            return {"decision": "deny", "reason": reason}, seg_cwd

    if re.search(ENV_SECRET_CMD_PATTERN, segment, flags=flags):
        return (
            {
                "decision": "deny",
                "reason": (
                    "Command references protected .env secrets. "
                    "Coordinate via @coordinator if an exception is needed."
                ),
            },
            seg_cwd,
        )

    tokens = _tokenize_segment(segment)
    if not tokens:
        return None, seg_cwd

    # 1. Inspect output redirections (`>`, `>>`, `&>`, `>|`, `<>`, etc.) and strip them before command inspection.
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
                    next_tok, seg_cwd, workspace_real, allow_dev_null=True
                )
                if deny:
                    return deny, seg_cwd
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
    saw_xargs = False
    while cmd_idx < len(non_redir_tokens):
        tok = non_redir_tokens[cmd_idx]
        if ENV_ASSIGN_RE.match(tok):
            cmd_idx += 1
            continue
        base = os.path.basename(tok)
        if base in COMMAND_WRAPPERS:
            if base == "xargs":
                saw_xargs = True
            cmd_idx += 1
            value_flags = WRAPPER_VALUE_FLAGS.get(base, set())
            while cmd_idx < len(non_redir_tokens):
                flag_tok = non_redir_tokens[cmd_idx]
                if flag_tok == "--":
                    cmd_idx += 1
                    break
                if not flag_tok.startswith("-"):
                    break
                cmd_idx += 1
                if "=" not in flag_tok and flag_tok in value_flags and cmd_idx < len(non_redir_tokens):
                    cmd_idx += 1
            if base == "timeout" and cmd_idx < len(non_redir_tokens):
                # Skip mandatory DURATION positional argument
                cmd_idx += 1
            continue
        break

    if cmd_idx >= len(non_redir_tokens):
        return None, seg_cwd

    cmd_name = os.path.basename(non_redir_tokens[cmd_idx])
    cmd_args = non_redir_tokens[cmd_idx + 1 :]

    # Track directory changes across chained segments (`cd .. && rm outside`, `cd migrations && rm 001_init.sql`)
    if cmd_name in {"cd", "pushd"}:
        target_dir = ""
        for arg in cmd_args:
            if arg == "--":
                continue
            if arg.startswith("-") and arg != "-":
                continue
            target_dir = arg
            break
        if not target_dir:
            target_dir = os.path.expanduser("~")
        elif target_dir == "-":
            target_dir = dir_stack[-1] if dir_stack else seg_cwd
        elif "$" in target_dir:
            expanded_dir = os.path.expandvars(target_dir)
            if "$" in expanded_dir:
                return (
                    {
                        "decision": "deny",
                        "reason": f"Directory change targets dynamic variable path ({target_dir}).",
                    },
                    seg_cwd,
                )
            target_dir = expanded_dir
        next_cwd = _resolve_real(target_dir, seg_cwd)
        if cmd_name == "pushd":
            dir_stack.append(seg_cwd)
        return None, next_cwd

    if cmd_name == "popd":
        next_cwd = dir_stack.pop() if dir_stack else seg_cwd
        return None, next_cwd

    # Inspect inline shell execution (`sh -c "..."`, `bash -lc "..."`, `eval ...`)
    if cmd_name in INLINE_SHELLS:
        for i, arg in enumerate(cmd_args):
            if arg == "-c" or _has_short_flag(arg, "c"):
                if i + 1 >= len(cmd_args):
                    return (
                        {"decision": "deny", "reason": f"Inline shell `{cmd_name} -c` missing command string."},
                        seg_cwd,
                    )
                deny = _check_command(cmd_args[i + 1], seg_cwd, workspace_real, depth + 1)
                if deny:
                    return deny, seg_cwd
                return None, seg_cwd
        return None, seg_cwd

    if cmd_name == "eval":
        inline_cmd = " ".join(cmd_args).strip()
        if inline_cmd:
            deny = _check_command(inline_cmd, seg_cwd, workspace_real, depth + 1)
            if deny:
                return deny, seg_cwd
        return None, seg_cwd

    is_mutating = cmd_name in MUTATING_COMMANDS
    if cmd_name in {"sed", "perl"}:
        is_mutating = any(_is_in_place_flag(arg) for arg in cmd_args)

    if not is_mutating:
        return None, seg_cwd

    if saw_xargs:
        return (
            {
                "decision": "deny",
                "reason": (
                    f"Mutating command via `xargs` (`{cmd_name}`) is blocked "
                    "because stdin targets cannot be statically confined."
                ),
            },
            seg_cwd,
        )

    # 3. Inspect target path arguments for mutating commands.
    skip_next = False
    positional_args: list[str] = []
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
                    arg[3:], seg_cwd, workspace_real, allow_dev_null=True
                )
                if deny:
                    return deny, seg_cwd
            continue
        if arg.startswith("-"):
            continue
        positional_args.append(arg)
        deny = _check_shell_target_path(
            arg,
            seg_cwd,
            workspace_real,
            allow_dev_null=(cmd_name == "tee"),
        )
        if deny:
            return deny, seg_cwd

    # Extra check for `ln`: verify link target resolved relative to link destination directory too.
    if cmd_name == "ln" and len(positional_args) >= 2:
        link_target = positional_args[0]
        link_dest = positional_args[-1]
        dest_dir = os.path.dirname(_resolve_real(link_dest, seg_cwd))
        deny = _check_shell_target_path(link_target, dest_dir, workspace_real)
        if deny:
            return deny, seg_cwd

    return None, seg_cwd


def _check_command(cmd: str, cwd: str, workspace_real: str, depth: int = 0) -> dict | None:
    if depth > MAX_RECURSION_DEPTH:
        return {
            "decision": "deny",
            "reason": "Command nesting depth exceeded guardrail inspection limit.",
        }

    # Join POSIX backslash-newline continuations before splitting segments.
    normalized_cmd = re.sub(r"\\\r?\n", "", cmd)

    # Inspect any command substitutions $(...) or `...` recursively.
    for sub_cmd in _extract_command_substitutions(normalized_cmd):
        deny = _check_command(sub_cmd, cwd, workspace_real, depth + 1)
        if deny:
            return deny

    seg_cwd = cwd
    dir_stack: list[str] = []
    for segment in SEGMENT_SPLIT_RE.split(normalized_cmd):
        deny, seg_cwd = _check_command_segment(
            segment.strip(), seg_cwd, workspace_real, dir_stack, depth
        )
        if deny:
            return deny
    return None


def _is_env_secret_path(raw_path: str, resolved_path: str) -> bool:
    flags = _path_regex_flags()
    for candidate in (raw_path.replace(os.sep, "/"), resolved_path.replace(os.sep, "/")):
        if candidate and re.search(ENV_SECRET_PATH_PATTERN, candidate, flags=flags):
            return True
    return False


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
        deny = _check_command(cmd, cwd, cwd_real)
        return deny if deny else {"decision": "allow"}

    target_path = (
        args.get("Path")
        or args.get("TargetFile")
        or args.get("path")
        or args.get("file_path")
        or ""
    )

    if tool_name in READ_TOOLS:
        if isinstance(target_path, str) and target_path.strip():
            target_real = _resolve_real(target_path, cwd)
            if _is_env_secret_path(target_path, target_real):
                return {
                    "decision": "deny",
                    "reason": (
                        f"Reading protected .env secret ({target_path}) is blocked. "
                        "Coordinate via @coordinator if an exception is needed."
                    ),
                }
        return {"decision": "allow"}

    if tool_name in WRITE_TOOLS and (not isinstance(target_path, str) or not target_path.strip()):
        return {
            "decision": "deny",
            "reason": f"Write/edit tool '{tool_name}' missing target file path (fail-closed).",
        }

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
        rule_decision = _check_relpath_rules(rel_path)
        if rule_decision:
            return rule_decision

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
