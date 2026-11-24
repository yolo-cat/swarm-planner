#!/usr/bin/env python3
"""Example PreToolUse guard script tailored during swarm-planner pre-session.

Reads Antigravity's hook JSON payload on stdin, resolves paths relative to
`payload["cwd"]` (falling back to `payload["workspacePaths"][0]`, essential for
`/swarm` `workspace:"share"` worktrees), and enforces deterministic project
boundaries in < 100ms.

Unattended-safe by default: never emits `"ask"` or `"force_ask"` unless
`SWARM_GUARD_INTERACTIVE=1` is set for single-session interactive runs.
"""

from __future__ import annotations

import fnmatch
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

# Matches `.env`, `.env.<suffix>`, or `.env*` globs while allowing `.env.example`/`.sample`/`.template`.
ENV_SECRET_CMD_PATTERN = (
    r"(?:^|[\s'\"`(/=<>:,{])(?:\.{1,2}/|[^\s'\"`()=<>,{}]*?/)?\.env"
    r"(?:\.(?!(?:example|sample|template)(?:$|[\s'\"`);&|<>,:}]))[A-Za-z0-9._*?\[\]-]+|[*?\[][^\s'\"`);&|<>,:}]*)?"
    r"(?=$|[\s'\"`);&|<>,:}])"
)
ENV_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=.*$")
SHELL_VAR_RE = re.compile(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*[^}]*\}|[A-Za-z_][A-Za-z0-9_]*|\(|[0-9@*#?$!-])")
SIMPLE_VAR_TOKEN_RE = re.compile(r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))")

READ_TOOLS = {"read_file", "view_file"}
WRITE_TOOLS = {
    "write_file",
    "edit_file",
    "write_to_file",
    "replace_file_content",
    "multi_replace_file_content",
}
PATH_ARG_KEYS = (
    "Path",
    "TargetFile",
    "AbsolutePath",
    "path",
    "file_path",
    "absolute_path",
    "filePath",
)
CMD_ARG_KEYS = ("CommandLine", "command", "commandLine")

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
SHELL_CONTROL_PREFIXES = {
    "{",
    "}",
    "if",
    "then",
    "elif",
    "else",
    "fi",
    "do",
    "done",
    "while",
    "until",
    "!",
    "builtin",
    "coproc",
}
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
    "exec",
}
WRAPPER_VALUE_FLAGS: dict[str, set[str]] = {
    "sudo": {"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-T", "-U", "--chdir"},
    "env": {"-u", "-C", "-S", "--unset", "--chdir", "--split-string"},
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
    "exec": {"-a"},
}
MUTATING_LONG_PATH_FLAGS = {
    "--target-directory",
    "--output",
    "--directory",
    "--backup-dir",
    "--reject-file",
    "--temp-dir",
    "--partial-dir",
}
MUTATING_SHORT_PATH_FLAGS: dict[str, set[str]] = {
    "cp": {"t"},
    "mv": {"t"},
    "ln": {"t"},
    "install": {"t"},
    "patch": {"o", "d", "r"},
}
OUTPUT_REDIR_TOKENS = {">", ">>", "&>", "&>>", ">|", "<>", ">&"}
INPUT_REDIR_TOKENS = {"<", "<<", "<<<"}
SAFE_SINK_PATHS = {"/dev/null"}
MAX_RECURSION_DEPTH = 4
SAFE_ENV_SUFFIXES = {"example", "sample", "template"}


def is_interactive() -> bool:
    """Return True only when interactive prompting is explicitly opted in."""
    return os.environ.get("SWARM_GUARD_INTERACTIVE") == "1"


def _is_case_insensitive_fs() -> bool:
    override = os.environ.get("SWARM_GUARD_CASE_INSENSITIVE")
    if override == "1":
        return True
    if override == "0":
        return False
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


def _expand_braces(token: str, limit: int = 32) -> list[str]:
    """Expand top-level shell brace expressions like `{.env,README.md}` safely."""
    results = [token]
    for _ in range(4):
        next_results: list[str] = []
        changed = False
        for item in results:
            start = item.find("{")
            if start == -1:
                next_results.append(item)
                continue
            depth = 0
            end = -1
            commas: list[int] = []
            for idx in range(start, len(item)):
                ch = item[idx]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        end = idx
                        break
                elif ch == "," and depth == 1:
                    commas.append(idx)
            if end == -1 or not commas:
                next_results.append(item)
                continue
            changed = True
            prefix = item[:start]
            suffix = item[end + 1 :]
            parts: list[str] = []
            prev = start + 1
            for c_idx in commas:
                parts.append(item[prev:c_idx])
                prev = c_idx + 1
            parts.append(item[prev:end])
            for part in parts:
                next_results.append(f"{prefix}{part}{suffix}")
                if len(next_results) >= limit:
                    return next_results
        results = next_results
        if not changed:
            break
    return results


def _basename_is_env_secret(base: str) -> bool:
    if not base:
        return False
    ci = _is_case_insensitive_fs()
    check = base.lower() if ci else base

    if check == ".env":
        return True
    if check.startswith(".env."):
        suffix = check[5:]
        if not suffix:
            return True
        return suffix not in SAFE_ENV_SUFFIXES

    if any(ch in check for ch in "*?["):
        if check.startswith(".env"):
            return True
        probe_targets = (".env", ".env.local", ".env1")
        benign_probes = (".gitignore", "foo.txt", "README.md")
        matches_env = any(fnmatch.fnmatchcase(p, check) for p in probe_targets)
        matches_benign = any(fnmatch.fnmatchcase(p, check) for p in benign_probes)
        if matches_env and not matches_benign:
            return True
    return False


def _token_references_env_secret(tok: str) -> bool:
    if not tok:
        return False
    candidates = _expand_braces(tok)
    for cand in candidates:
        sub_cands = [cand]
        if "=" in cand:
            sub_cands.append(cand.split("=", 1)[1])
        for item in sub_cands:
            cleaned = item.replace("\\", "/")
            base = cleaned.rsplit("/", 1)[-1]
            if _basename_is_env_secret(base):
                return True
    return False


def _consume_paren_subst(cmd: str, open_paren_idx: int) -> int | None:
    """Return index right after the matching ')' for a `$(...)`/`<(...)`/`>(...)` group, or None."""
    n = len(cmd)
    i = open_paren_idx + 1
    depth = 1
    in_single = False
    in_double = False
    in_backtick = False
    while i < n and depth > 0:
        ch = cmd[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == '"':
                in_double = False
                i += 1
                continue
            if ch == "$" and i + 1 < n and cmd[i + 1] == "(":
                end = _consume_paren_subst(cmd, i + 1)
                if end is None:
                    return None
                i = end
                continue
            if ch == "`":
                j = i + 1
                while j < n and cmd[j] != "`":
                    if cmd[j] == "\\" and j + 1 < n:
                        j += 2
                        continue
                    j += 1
                if j >= n:
                    return None
                i = j + 1
                continue
            i += 1
            continue
        if in_backtick:
            if ch == "\\" and i + 1 < n:
                i += 2
                continue
            if ch == "`":
                in_backtick = False
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "`":
            in_backtick = True
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        i += 1
    if depth != 0 or in_single or in_double or in_backtick:
        return None
    return i


def _split_shell_segments(cmd: str) -> tuple[list[tuple[str, str | None]], str | None]:
    """Quote- and backslash-aware split on unquoted shell control operators.

    Returns ([(segment_text, preceding_operator), ...], error_reason_or_none).
    Fails closed on unclosed quotes/substitutions and ANSI-C `$'...'` quoting.
    """
    segments: list[tuple[str, str | None]] = []
    buf: list[str] = []
    prev_op: str | None = None
    n = len(cmd)
    i = 0
    in_single = False
    in_double = False
    in_backtick = False

    def flush(next_op: str) -> None:
        nonlocal prev_op
        text = "".join(buf).strip()
        if text:
            segments.append((text, prev_op))
        buf.clear()
        prev_op = next_op

    while i < n:
        ch = cmd[i]
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == "\\" and i + 1 < n:
                buf.append(cmd[i : i + 2])
                i += 2
                continue
            if ch == '"':
                buf.append(ch)
                in_double = False
                i += 1
                continue
            if ch == "$" and i + 1 < n and cmd[i + 1] == "(":
                end = _consume_paren_subst(cmd, i + 1)
                if end is None:
                    return [], "Unclosed $(...) command substitution (fail-closed)."
                buf.append(cmd[i:end])
                i = end
                continue
            if ch == "`":
                j = i + 1
                while j < n and cmd[j] != "`":
                    if cmd[j] == "\\" and j + 1 < n:
                        j += 2
                        continue
                    j += 1
                if j >= n:
                    return [], "Unclosed backtick command substitution (fail-closed)."
                buf.append(cmd[i : j + 1])
                i = j + 1
                continue
            buf.append(ch)
            i += 1
            continue
        if in_backtick:
            if ch == "\\" and i + 1 < n:
                buf.append(cmd[i : i + 2])
                i += 2
                continue
            buf.append(ch)
            if ch == "`":
                in_backtick = False
            i += 1
            continue

        # Unquoted context
        if ch == "\\" and i + 1 < n:
            buf.append(cmd[i : i + 2])
            i += 2
            continue
        if ch == "$" and i + 1 < n and cmd[i + 1] == "'":
            return [], "ANSI-C quoting ($'...') is blocked by project guardrails (fail-closed)."
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == "`":
            in_backtick = True
            buf.append(ch)
            i += 1
            continue
        if cmd[i : i + 2] in {"$(", ">(", "<("}:
            end = _consume_paren_subst(cmd, i + 1)
            if end is None:
                return [], f"Unclosed {cmd[i:i+2]}...) substitution (fail-closed)."
            buf.append(cmd[i:end])
            i = end
            continue
        if cmd[i : i + 3] in {"&>>", "<<<"}:
            buf.append(cmd[i : i + 3])
            i += 3
            continue
        if cmd[i : i + 2] in {"&>", ">&", "<&", ">|", "<>", "<<"}:
            buf.append(cmd[i : i + 2])
            i += 2
            continue
        if cmd[i : i + 2] == "|&":
            flush("|")
            i += 2
            continue
        if cmd[i : i + 2] == "&&":
            flush("&&")
            i += 2
            continue
        if cmd[i : i + 2] == "||":
            flush("||")
            i += 2
            continue
        if ch in ";\n":
            flush(";")
            i += 1
            continue
        if ch == "|":
            flush("|")
            i += 1
            continue
        if ch == "&":
            flush("&")
            i += 1
            continue
        buf.append(ch)
        i += 1

    if in_single or in_double or in_backtick:
        return [], "Unclosed quote or command substitution (fail-closed)."

    tail = "".join(buf).strip()
    if tail:
        segments.append((tail, prev_op))
    return segments, None


def _extract_command_substitutions(cmd: str) -> list[str]:
    """Extract inner commands from $(...), <(...), >(...), and backtick substitutions."""
    results: list[str] = []
    n = len(cmd)
    i = 0
    in_single = False
    in_double = False
    while i < n:
        ch = cmd[i]
        if in_single:
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            i += 2
            continue
        if not in_double and ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = not in_double
            i += 1
            continue
        if (ch == "$" and i + 1 < n and cmd[i + 1] == "(") or (
            not in_double and ch in {">", "<"} and i + 1 < n and cmd[i + 1] == "("
        ):
            end = _consume_paren_subst(cmd, i + 1)
            inner_end = (end - 1) if end is not None else n
            inner = cmd[i + 2 : inner_end].strip()
            if inner:
                results.append(inner)
            i = end if end is not None else n
            continue
        if ch == "`":
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


def _tokenize_segment(segment: str) -> tuple[list[str], str | None]:
    try:
        lexer = shlex.shlex(segment, posix=True, punctuation_chars="><&|()")
        lexer.whitespace_split = True
        return list(lexer), None
    except ValueError as exc:
        return [], f"Malformed shell quoting in command ({exc}; fail-closed)."


def _expand_shell_vars(
    candidate: str,
    seg_cwd: str,
    old_cwd: str | None,
    assigned_vars: set[str],
) -> str | None:
    """Expand known shell vars against tracked seg_cwd; return None if dynamic/unknown."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2) or ""
        if name in assigned_vars:
            return f"${{{name}}}"
        if name == "PWD":
            return seg_cwd
        if name == "OLDPWD":
            return old_cwd if old_cwd is not None else "${OLDPWD}"
        val = os.environ.get(name)
        return val if val is not None else f"${{{name}}}"

    expanded = SIMPLE_VAR_TOKEN_RE.sub(repl, candidate)
    if "$" in expanded:
        return None
    return expanded


def _check_shell_target_path(
    raw_target: str,
    seg_cwd: str,
    workspace_real: str,
    *,
    allow_dev_null: bool = False,
    old_cwd: str | None = None,
    assigned_vars: set[str] | None = None,
) -> dict | None:
    if not raw_target:
        return None
    if allow_dev_null and raw_target in SAFE_SINK_PATHS:
        return None

    candidate = raw_target
    if "$" in candidate or SHELL_VAR_RE.search(candidate):
        expanded = _expand_shell_vars(candidate, seg_cwd, old_cwd, assigned_vars or set())
        if expanded is None:
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
        return "i" in token[1:]
    return False


def _is_paren_only(tok: str) -> bool:
    return bool(tok) and all(ch in "()" for ch in tok)


def _parse_sed_script_writes(script: str) -> tuple[list[str], bool]:
    """Extract target filenames from `sed` `w`/`W` commands and `s///w` flags; flag GNU `e` exec."""
    targets: list[str] = []
    has_exec = False
    for raw_part in re.split(r"[;\n]", script):
        part = raw_part.strip()
        if not part:
            continue
        # Strip leading braces/negations/addresses (numbers, $, /regex/, ranges)
        while True:
            prev = part
            part = re.sub(r"^(?:[\s{}!]+|\d+|\$|/[^/\\]*(?:\\.[^/\\]*)*/|,)+", "", part).strip()
            if part == prev:
                break
        if not part:
            continue
        cmd_ch = part[0]
        if cmd_ch in {"w", "W"}:
            target = part[1:].strip()
            targets.append(target)
            continue
        if cmd_ch == "e":
            has_exec = True
            continue
        if cmd_ch == "s" and len(part) >= 4:
            delim = part[1]
            # Walk through 3 unescaped occurrences of delim to reach flags
            idx = 2
            delims_seen = 1
            while idx < len(part) and delims_seen < 3:
                if part[idx] == "\\" and idx + 1 < len(part):
                    idx += 2
                    continue
                if part[idx] == delim:
                    delims_seen += 1
                idx += 1
            if delims_seen == 3:
                flags_str = part[idx:]
                w_idx = flags_str.find("w")
                if w_idx != -1:
                    targets.append(flags_str[w_idx + 1 :].strip())
                    flags_before_w = flags_str[:w_idx]
                else:
                    flags_before_w = flags_str
                if "e" in flags_before_w:
                    has_exec = True
    return targets, has_exec


def _check_sed_scripts(
    cmd_args: list[str],
    seg_cwd: str,
    workspace_real: str,
    old_cwd: str | None,
    assigned_vars: set[str],
) -> tuple[dict | None, set[int]]:
    """Inspect sed expressions for `w`/`W`/`s///w` file writes and GNU `e` execution.

    Returns (deny_decision_or_none, set_of_script_arg_indices_to_skip_as_file_targets).
    """
    scripts: list[str] = []
    skip_indices: set[int] = set()
    has_explicit_script = False
    i = 0
    while i < len(cmd_args):
        arg = cmd_args[i]
        if arg == "--":
            skip_indices.add(i)
            i += 1
            break
        if arg in {"-e", "--expression"}:
            has_explicit_script = True
            skip_indices.add(i)
            if i + 1 < len(cmd_args):
                scripts.append(cmd_args[i + 1])
                skip_indices.add(i + 1)
                i += 2
            else:
                i += 1
            continue
        if arg.startswith("--expression="):
            has_explicit_script = True
            scripts.append(arg.split("=", 1)[1])
            skip_indices.add(i)
            i += 1
            continue
        if arg.startswith("-e") and len(arg) > 2:
            has_explicit_script = True
            scripts.append(arg[2:])
            skip_indices.add(i)
            i += 1
            continue
        if arg in {"-f", "--file"} or arg.startswith("--file=") or (arg.startswith("-f") and len(arg) > 2):
            return (
                {
                    "decision": "deny",
                    "reason": "External `sed -f` script file is blocked (cannot statically verify writes).",
                },
                skip_indices,
            )
        if arg == "-i" and i + 1 < len(cmd_args) and cmd_args[i + 1] == "":
            # BSD sed empty backup suffix: `sed -i '' '<script>' <file>`
            skip_indices.add(i)
            skip_indices.add(i + 1)
            i += 2
            continue
        if arg.startswith("-") and arg != "-":
            i += 1
            continue
        if not has_explicit_script:
            has_explicit_script = True
            scripts.append(arg)
            skip_indices.add(i)
        i += 1

    if not has_explicit_script and i < len(cmd_args):
        scripts.append(cmd_args[i])
        skip_indices.add(i)

    for script in scripts:
        w_targets, has_exec = _parse_sed_script_writes(script)
        if has_exec:
            return (
                {
                    "decision": "deny",
                    "reason": "GNU `sed` command execution (`e`) is blocked by project guardrails.",
                },
                skip_indices,
            )
        for target in w_targets:
            if not target:
                return (
                    {
                        "decision": "deny",
                        "reason": "`sed` write command (`w`) with unparseable target is blocked.",
                    },
                    skip_indices,
                )
            deny = _check_shell_target_path(
                target,
                seg_cwd,
                workspace_real,
                allow_dev_null=True,
                old_cwd=old_cwd,
                assigned_vars=assigned_vars,
            )
            if deny:
                return deny, skip_indices

    return None, skip_indices


def _perl_has_inline_code_flag(cmd_args: list[str]) -> bool:
    for arg in cmd_args:
        if arg == "--":
            break
        if arg in {"-e", "-E"}:
            return True
        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            if "e" in arg[1:] or "E" in arg[1:]:
                return True
    return False


def _resolve_dir_arg(
    raw_dir: str,
    base_cwd: str,
    old_cwd: str | None,
    assigned_vars: set[str],
) -> tuple[str | None, dict | None]:
    target_dir = raw_dir
    if "$" in target_dir or SHELL_VAR_RE.search(target_dir):
        expanded = _expand_shell_vars(target_dir, base_cwd, old_cwd, assigned_vars)
        if expanded is None:
            return None, {
                "decision": "deny",
                "reason": f"Directory change targets dynamic variable path ({raw_dir}).",
            }
        target_dir = expanded
    return _resolve_real(target_dir, base_cwd), None


def _check_inline_shell(
    cmd_name: str,
    cmd_args: list[str],
    cmd_cwd: str,
    workspace_real: str,
    depth: int,
    prev_op: str | None,
    has_input_redir: bool,
) -> dict | None:
    if prev_op == "|":
        return {
            "decision": "deny",
            "reason": (
                f"Piped input into inline shell `{cmd_name}` is blocked "
                "because stdin commands cannot be statically confined."
            ),
        }

    safe_long_flags = {
        "--login",
        "--norc",
        "--noprofile",
        "--posix",
        "--verbose",
        "--noediting",
        "--restricted",
        "--version",
        "--help",
    }
    saw_c = False
    saw_s = False
    idx = 0
    while idx < len(cmd_args):
        arg = cmd_args[idx]
        if arg in {"--", "-"}:
            idx += 1
            break
        if arg in {"--rcfile", "--init-file"} or arg.startswith(("--rcfile=", "--init-file=")):
            return {
                "decision": "deny",
                "reason": f"Inline shell `{cmd_name}` init/rcfile override is blocked.",
            }
        if arg in {"-o", "+o", "-O", "+O"}:
            idx += 2
            continue
        if arg.startswith("--"):
            if arg in safe_long_flags:
                idx += 1
                continue
            return {
                "decision": "deny",
                "reason": f"Unrecognized inline shell long flag `{arg}` on `{cmd_name}` (fail-closed).",
            }
        if len(arg) > 1 and arg[0] in {"-", "+"}:
            sign = arg[0]
            flags_body = arg[1:]
            if not all(ch.isalpha() for ch in flags_body):
                return {
                    "decision": "deny",
                    "reason": f"Unrecognized inline shell flag `{arg}` on `{cmd_name}` (fail-closed).",
                }
            if any(ch in {"o", "O"} for ch in flags_body[:-1]):
                return {
                    "decision": "deny",
                    "reason": f"Ambiguous bundled inline shell option `{arg}` on `{cmd_name}` (fail-closed).",
                }
            if sign == "-":
                if "c" in flags_body:
                    saw_c = True
                if "s" in flags_body:
                    saw_s = True
            if flags_body.endswith(("o", "O")):
                idx += 2
            else:
                idx += 1
            continue
        break

    if saw_c:
        if idx >= len(cmd_args):
            return {
                "decision": "deny",
                "reason": f"Inline shell `{cmd_name} -c` missing command string.",
            }
        return _check_command(cmd_args[idx], cmd_cwd, workspace_real, depth + 1)

    if has_input_redir or saw_s:
        return {
            "decision": "deny",
            "reason": (
                f"Inline shell `{cmd_name}` reading commands from stdin/here-string is blocked."
            ),
        }
    return None


def _check_command_segment(
    segment: str,
    seg_cwd: str,
    workspace_real: str,
    dir_stack: list[str],
    old_cwd: str | None,
    assigned_vars: set[str],
    depth: int,
    prev_op: str | None = None,
) -> tuple[dict | None, str, str | None]:
    if not segment:
        return None, seg_cwd, old_cwd

    # Inspect any command/process substitutions ($(...), `...`, >(...), <(...)) using current seg_cwd.
    for sub_cmd in _extract_command_substitutions(segment):
        deny = _check_command(sub_cmd, seg_cwd, workspace_real, depth + 1)
        if deny:
            return deny, seg_cwd, old_cwd

    flags = _path_regex_flags()
    for pattern, reason in DENIED_COMMAND_PATTERNS:
        if re.search(pattern, segment):
            return {"decision": "deny", "reason": reason}, seg_cwd, old_cwd

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
            old_cwd,
        )

    tokens, tok_err = _tokenize_segment(segment)
    if tok_err:
        return {"decision": "deny", "reason": tok_err}, seg_cwd, old_cwd
    if not tokens:
        return None, seg_cwd, old_cwd

    # Re-check denied command patterns and .env secrets against shlex-dequoted tokens
    # (catches quote-splitting like `git p""ush`, backslash escapes like `cat \.env`, globs, and braces).
    joined_tokens = " ".join(tokens)
    for pattern, reason in DENIED_COMMAND_PATTERNS:
        if re.search(pattern, joined_tokens):
            return {"decision": "deny", "reason": reason}, seg_cwd, old_cwd

    for tok in tokens:
        if _token_references_env_secret(tok):
            return (
                {
                    "decision": "deny",
                    "reason": (
                        "Command references protected .env secrets. "
                        "Coordinate via @coordinator if an exception is needed."
                    ),
                },
                seg_cwd,
                old_cwd,
            )

    # 1. Inspect output redirections (`>`, `>>`, `&>`, `>|`, `<>`, etc.) and track input redirections.
    non_redir_tokens: list[str] = []
    has_input_redir = False
    idx = 0
    while idx < len(tokens):
        tok = tokens[idx]
        if tok in OUTPUT_REDIR_TOKENS:
            next_tok = tokens[idx + 1] if idx + 1 < len(tokens) else ""
            # Handle `2>&1` or `2>&-` fd duplication/close safely
            if tok == ">&" and (next_tok.isdigit() or next_tok == "-"):
                idx += 2
                continue
            if next_tok in {">(", "<("}:
                idx += 1
                continue
            if next_tok:
                deny = _check_shell_target_path(
                    next_tok,
                    seg_cwd,
                    workspace_real,
                    allow_dev_null=True,
                    old_cwd=old_cwd,
                    assigned_vars=assigned_vars,
                )
                if deny:
                    return deny, seg_cwd, old_cwd
            idx += 2
            continue
        if tok in INPUT_REDIR_TOKENS:
            has_input_redir = True
            idx += 2
            continue
        # Drop standalone fd number directly preceding a redirection (e.g. `2` in `2>/dev/null`)
        if (
            tok.isdigit()
            and idx + 1 < len(tokens)
            and tokens[idx + 1] in (OUTPUT_REDIR_TOKENS | INPUT_REDIR_TOKENS)
        ):
            idx += 1
            continue
        non_redir_tokens.append(tok)
        idx += 1

    # Strip trailing closing subshell/brace tokens (e.g. `)` from `(rm ../outside)` or `}` from `{ rm ...; }`)
    while non_redir_tokens and (
        _is_paren_only(non_redir_tokens[-1]) or non_redir_tokens[-1] == "}"
    ):
        non_redir_tokens.pop()

    # 2. Identify the effective command after structural keywords, env assignments, and wrappers.
    cmd_idx = 0
    saw_xargs = False
    cmd_cwd = seg_cwd
    while cmd_idx < len(non_redir_tokens):
        tok = non_redir_tokens[cmd_idx]
        if tok in SHELL_CONTROL_PREFIXES or _is_paren_only(tok):
            cmd_idx += 1
            continue
        assign_match = ENV_ASSIGN_RE.match(tok)
        if assign_match:
            assigned_vars.add(assign_match.group(1))
            cmd_idx += 1
            continue
        base = os.path.basename(tok)
        if base in COMMAND_WRAPPERS:
            if base == "xargs":
                saw_xargs = True
            cmd_idx += 1
            value_flags = WRAPPER_VALUE_FLAGS.get(base, set())
            short_val_letters = {f[1] for f in value_flags if len(f) == 2 and f.startswith("-")}
            long_val_flags = {f for f in value_flags if f.startswith("--")}

            while cmd_idx < len(non_redir_tokens):
                flag_tok = non_redir_tokens[cmd_idx]
                if flag_tok == "--":
                    cmd_idx += 1
                    break
                if not flag_tok.startswith("-") or flag_tok == "-":
                    break

                opt_name = flag_tok
                opt_val: str | None = None
                if flag_tok.startswith("--"):
                    if "=" in flag_tok:
                        opt_name, opt_val = flag_tok.split("=", 1)
                        cmd_idx += 1
                    elif flag_tok in long_val_flags:
                        opt_val = (
                            non_redir_tokens[cmd_idx + 1]
                            if cmd_idx + 1 < len(non_redir_tokens)
                            else ""
                        )
                        cmd_idx += 2
                    else:
                        cmd_idx += 1
                else:
                    # Short flag (possibly bundled, e.g. `-rn 1`, `-vk 5`, `-C..`, `-iC ..`)
                    body = flag_tok[1:]
                    matched_val = False
                    for pos, ch in enumerate(body):
                        if ch in short_val_letters:
                            opt_name = f"-{ch}"
                            rest = body[pos + 1 :]
                            if rest:
                                opt_val = rest
                                cmd_idx += 1
                            else:
                                opt_val = (
                                    non_redir_tokens[cmd_idx + 1]
                                    if cmd_idx + 1 < len(non_redir_tokens)
                                    else ""
                                )
                                cmd_idx += 2
                            matched_val = True
                            break
                    if not matched_val:
                        cmd_idx += 1

                # Handle wrapper directory switches (`env -C`, `env --chdir`, `sudo -D`, `sudo --chdir`)
                if (base == "env" and opt_name in {"-C", "--chdir"}) or (
                    base == "sudo" and opt_name in {"-D", "--chdir"}
                ):
                    if not opt_val:
                        return (
                            {"decision": "deny", "reason": f"`{base} {opt_name}` missing directory argument."},
                            seg_cwd,
                            old_cwd,
                        )
                    resolved_dir, dir_deny = _resolve_dir_arg(
                        opt_val, cmd_cwd, old_cwd, assigned_vars
                    )
                    if dir_deny or resolved_dir is None:
                        return dir_deny, seg_cwd, old_cwd
                    cmd_cwd = resolved_dir

                # Handle `env -S` / `env --split-string`
                if base == "env" and opt_name in {"-S", "--split-string"}:
                    if not opt_val:
                        return (
                            {"decision": "deny", "reason": f"`env {opt_name}` missing command string."},
                            seg_cwd,
                            old_cwd,
                        )
                    rest_tokens = non_redir_tokens[cmd_idx:]
                    combined_split = " ".join([opt_val, *rest_tokens]).strip()
                    deny = _check_command(combined_split, cmd_cwd, workspace_real, depth + 1)
                    if deny:
                        return deny, seg_cwd, old_cwd
                    return None, seg_cwd, old_cwd

            if base == "timeout" and cmd_idx < len(non_redir_tokens):
                # Skip mandatory DURATION positional argument
                cmd_idx += 1
            continue
        break

    if cmd_idx >= len(non_redir_tokens):
        return None, seg_cwd, old_cwd

    cmd_name = os.path.basename(non_redir_tokens[cmd_idx])
    cmd_args = non_redir_tokens[cmd_idx + 1 :]

    # Track directory changes across chained segments (`cd .. && rm outside`, `cd migrations && rm 001_init.sql`)
    if cmd_name in {"cd", "pushd"}:
        target_dir = ""
        after_dash = False
        for arg in cmd_args:
            if not after_dash and arg == "--":
                after_dash = True
                continue
            if not after_dash and arg.startswith("-") and arg != "-":
                continue
            target_dir = arg
            break
        if not target_dir:
            next_cwd = _resolve_real(os.path.expanduser("~"), cmd_cwd)
        elif target_dir == "-":
            if old_cwd is not None:
                next_cwd = old_cwd
            elif dir_stack:
                next_cwd = dir_stack[-1]
            else:
                return (
                    {
                        "decision": "deny",
                        "reason": "Directory change `cd -` with unknown prior working directory (fail-closed).",
                    },
                    seg_cwd,
                    old_cwd,
                )
        else:
            resolved_dir, dir_deny = _resolve_dir_arg(target_dir, cmd_cwd, old_cwd, assigned_vars)
            if dir_deny or resolved_dir is None:
                return dir_deny, seg_cwd, old_cwd
            next_cwd = resolved_dir
        if cmd_name == "pushd":
            dir_stack.append(seg_cwd)
        return None, next_cwd, seg_cwd

    if cmd_name == "popd":
        next_cwd = dir_stack.pop() if dir_stack else seg_cwd
        return None, next_cwd, seg_cwd

    # Enforce `xargs` block before inline shells / eval / mutating commands.
    if saw_xargs and (cmd_name in INLINE_SHELLS or cmd_name == "eval"):
        return (
            {
                "decision": "deny",
                "reason": (
                    f"Inline shell/eval via `xargs` (`{cmd_name}`) is blocked "
                    "because stdin arguments cannot be statically confined."
                ),
            },
            seg_cwd,
            old_cwd,
        )

    # Inspect inline shell execution (`sh -c "..."`, `bash -lc "..."`, `bash <<< "..."`, `... | sh`)
    if cmd_name in INLINE_SHELLS:
        deny = _check_inline_shell(
            cmd_name,
            cmd_args,
            cmd_cwd,
            workspace_real,
            depth,
            prev_op,
            has_input_redir,
        )
        if deny:
            return deny, seg_cwd, old_cwd
        return None, seg_cwd, old_cwd

    if cmd_name == "eval":
        eval_args = cmd_args[1:] if cmd_args and cmd_args[0] == "--" else cmd_args
        inline_cmd = " ".join(eval_args).strip()
        if inline_cmd:
            deny = _check_command(inline_cmd, cmd_cwd, workspace_real, depth + 1)
            if deny:
                return deny, seg_cwd, old_cwd
        return None, seg_cwd, old_cwd

    # Inspect `sed` write scripts (`w`, `W`, `s///w`, GNU `e`) even without `-i`.
    sed_skip_indices: set[int] = set()
    if cmd_name == "sed":
        sed_deny, sed_skip_indices = _check_sed_scripts(
            cmd_args, cmd_cwd, workspace_real, old_cwd, assigned_vars
        )
        if sed_deny:
            return sed_deny, seg_cwd, old_cwd

    is_mutating = cmd_name in MUTATING_COMMANDS
    if cmd_name in {"sed", "perl"}:
        is_mutating = any(_is_in_place_flag(arg) for arg in cmd_args)

    # Check non-in-place `perl -e` / `-E` (can unlink/open/rename arbitrary files).
    if cmd_name == "perl" and not is_mutating and _perl_has_inline_code_flag(cmd_args):
        return (
            {
                "decision": "deny",
                "reason": "Inline `perl -e`/`-E` execution is blocked because file mutations cannot be statically confined.",
            },
            seg_cwd,
            old_cwd,
        )

    if not is_mutating:
        return None, seg_cwd, old_cwd

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
            old_cwd,
        )

    # 3. Inspect target path arguments (including `--option=PATH` / `-oPATH` / `-tPATH` / `-dPATH`) for mutating commands.
    skip_next = False
    expect_path_opt: str | None = None
    after_double_dash = False
    positional_args: list[str] = []
    target_dir_override: str | None = None
    effective_cwd = cmd_cwd
    short_path_letters = MUTATING_SHORT_PATH_FLAGS.get(cmd_name, set())

    for arg_idx, arg in enumerate(cmd_args):
        if arg_idx in sed_skip_indices:
            continue
        if skip_next:
            skip_next = False
            continue
        if expect_path_opt is not None:
            opt = expect_path_opt
            expect_path_opt = None
            deny = _check_shell_target_path(
                arg,
                effective_cwd,
                workspace_real,
                allow_dev_null=(cmd_name == "patch" and opt in {"-o", "--output", "-r", "--reject-file"}),
                old_cwd=old_cwd,
                assigned_vars=assigned_vars,
            )
            if deny:
                return deny, seg_cwd, old_cwd
            if opt in {"-t", "--target-directory"}:
                target_dir_override = arg
            elif cmd_name == "patch" and opt in {"-d", "--directory"}:
                resolved_dir, dir_deny = _resolve_dir_arg(
                    arg, effective_cwd, old_cwd, assigned_vars
                )
                if dir_deny or resolved_dir is None:
                    return dir_deny, seg_cwd, old_cwd
                effective_cwd = resolved_dir
            continue
        if not arg:
            continue
        if not after_double_dash and arg == "--":
            after_double_dash = True
            continue
        if cmd_name == "perl" and not after_double_dash and arg in {"-e", "-E"}:
            skip_next = True
            continue
        if cmd_name == "dd":
            if arg.startswith("of="):
                deny = _check_shell_target_path(
                    arg[3:],
                    effective_cwd,
                    workspace_real,
                    allow_dev_null=True,
                    old_cwd=old_cwd,
                    assigned_vars=assigned_vars,
                )
                if deny:
                    return deny, seg_cwd, old_cwd
            continue
        if not after_double_dash and arg.startswith("--"):
            if "=" in arg:
                opt_name, opt_val = arg.split("=", 1)
                if opt_name in MUTATING_LONG_PATH_FLAGS:
                    deny = _check_shell_target_path(
                        opt_val,
                        effective_cwd,
                        workspace_real,
                        allow_dev_null=(cmd_name == "patch" and opt_name in {"--output", "--reject-file"}),
                        old_cwd=old_cwd,
                        assigned_vars=assigned_vars,
                    )
                    if deny:
                        return deny, seg_cwd, old_cwd
                    if opt_name == "--target-directory":
                        target_dir_override = opt_val
                    elif cmd_name == "patch" and opt_name == "--directory":
                        resolved_dir, dir_deny = _resolve_dir_arg(
                            opt_val, effective_cwd, old_cwd, assigned_vars
                        )
                        if dir_deny or resolved_dir is None:
                            return dir_deny, seg_cwd, old_cwd
                        effective_cwd = resolved_dir
            elif arg in MUTATING_LONG_PATH_FLAGS:
                expect_path_opt = arg
            continue
        if not after_double_dash and arg.startswith("-") and arg != "-":
            # Check short path-taking options like `-o../outside`, `-d..`, `-t../outside`, or bundled `-st ../outside`
            if short_path_letters:
                body = arg[1:]
                for pos, ch in enumerate(body):
                    if ch in short_path_letters:
                        opt_name = f"-{ch}"
                        rest = body[pos + 1 :]
                        if rest:
                            deny = _check_shell_target_path(
                                rest,
                                effective_cwd,
                                workspace_real,
                                allow_dev_null=(cmd_name == "patch" and ch in {"o", "r"}),
                                old_cwd=old_cwd,
                                assigned_vars=assigned_vars,
                            )
                            if deny:
                                return deny, seg_cwd, old_cwd
                            if ch == "t":
                                target_dir_override = rest
                            elif cmd_name == "patch" and ch == "d":
                                resolved_dir, dir_deny = _resolve_dir_arg(
                                    rest, effective_cwd, old_cwd, assigned_vars
                                )
                                if dir_deny or resolved_dir is None:
                                    return dir_deny, seg_cwd, old_cwd
                                effective_cwd = resolved_dir
                        else:
                            expect_path_opt = opt_name
                        break
            continue
        positional_args.append(arg)
        deny = _check_shell_target_path(
            arg,
            effective_cwd,
            workspace_real,
            allow_dev_null=(cmd_name == "tee"),
            old_cwd=old_cwd,
            assigned_vars=assigned_vars,
        )
        if deny:
            return deny, seg_cwd, old_cwd

    # If in-place perl also uses `-e`/`-E`, block arbitrary inline Perl code after checking targets.
    if cmd_name == "perl" and _perl_has_inline_code_flag(cmd_args):
        return (
            {
                "decision": "deny",
                "reason": "Inline `perl -e`/`-E` execution is blocked because file mutations cannot be statically confined.",
            },
            seg_cwd,
            old_cwd,
        )

    # Extra check for `ln`: verify link target(s) resolved relative to link destination directory too.
    if cmd_name == "ln":
        if target_dir_override is not None and positional_args:
            dest_dir = _resolve_real(target_dir_override, effective_cwd)
            for link_target in positional_args:
                deny = _check_shell_target_path(
                    link_target,
                    dest_dir,
                    workspace_real,
                    old_cwd=old_cwd,
                    assigned_vars=assigned_vars,
                )
                if deny:
                    return deny, seg_cwd, old_cwd
        elif len(positional_args) >= 2:
            link_dest = positional_args[-1]
            link_dest_real = _resolve_real(link_dest, effective_cwd)
            dest_dir = (
                link_dest_real if os.path.isdir(link_dest_real) else os.path.dirname(link_dest_real)
            )
            for link_target in positional_args[:-1]:
                deny = _check_shell_target_path(
                    link_target,
                    dest_dir,
                    workspace_real,
                    old_cwd=old_cwd,
                    assigned_vars=assigned_vars,
                )
                if deny:
                    return deny, seg_cwd, old_cwd

    return None, seg_cwd, old_cwd


def _check_command(cmd: str, cwd: str, workspace_real: str, depth: int = 0) -> dict | None:
    if depth > MAX_RECURSION_DEPTH:
        return {
            "decision": "deny",
            "reason": "Command nesting depth exceeded guardrail inspection limit.",
        }

    # Join POSIX backslash-newline continuations before splitting segments.
    normalized_cmd = re.sub(r"\\\r?\n", "", cmd)

    segments, split_err = _split_shell_segments(normalized_cmd)
    if split_err:
        return {"decision": "deny", "reason": split_err}

    seg_cwd = cwd
    old_cwd: str | None = None
    dir_stack: list[str] = []
    assigned_vars: set[str] = set()
    for segment, prev_op in segments:
        deny, seg_cwd, old_cwd = _check_command_segment(
            segment,
            seg_cwd,
            workspace_real,
            dir_stack,
            old_cwd,
            assigned_vars,
            depth,
            prev_op=prev_op,
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


def _extract_first_str_arg(args: dict, keys: tuple[str, ...]) -> tuple[str, bool]:
    """Return (first_non_empty_stripped_str, saw_invalid_non_string_value)."""
    saw_invalid = False
    for key in keys:
        if key not in args:
            continue
        val = args[key]
        if val is None:
            continue
        if not isinstance(val, str):
            saw_invalid = True
            continue
        stripped = val.strip()
        if stripped:
            return stripped, saw_invalid
    return "", saw_invalid


def _resolve_payload_cwd(payload: dict) -> str:
    raw_cwd = payload.get("cwd")
    if isinstance(raw_cwd, str) and raw_cwd.strip():
        return raw_cwd.strip()
    ws_paths = payload.get("workspacePaths")
    if isinstance(ws_paths, list) and ws_paths:
        first_ws = ws_paths[0]
        if isinstance(first_ws, str) and first_ws.strip():
            return first_ws.strip()
    return os.getcwd()


def check_tool_call(payload: dict) -> dict:
    """Inspect toolCall name & args and return a valid PreToolUse decision."""
    if not isinstance(payload, dict):
        raise ValueError("Hook payload must be a JSON object.")

    raw_tool_call = payload.get("toolCall")
    if raw_tool_call is None:
        tool_call: dict = {}
    elif isinstance(raw_tool_call, dict):
        tool_call = raw_tool_call
    else:
        raise ValueError("Hook payload 'toolCall' must be a JSON object.")

    tool_name = tool_call.get("name", "")
    if not isinstance(tool_name, str):
        raise ValueError("Hook payload 'toolCall.name' must be a string.")

    raw_args = tool_call.get("args")
    if raw_args is None:
        args: dict = {}
    elif isinstance(raw_args, dict):
        args = raw_args
    else:
        raise ValueError("Hook payload 'toolCall.args' must be a JSON object.")

    cwd = _resolve_payload_cwd(payload)
    cwd_real = os.path.realpath(cwd)

    if tool_name == "run_command":
        cmd, bad_cmd = _extract_first_str_arg(args, CMD_ARG_KEYS)
        if bad_cmd:
            return {
                "decision": "deny",
                "reason": "Command argument must be a string (fail-closed).",
            }
        deny = _check_command(cmd, cwd, cwd_real)
        return deny if deny else {"decision": "allow"}

    target_path, bad_path = _extract_first_str_arg(args, PATH_ARG_KEYS)

    if tool_name in READ_TOOLS:
        if bad_path or not target_path:
            return {
                "decision": "deny",
                "reason": f"Read tool '{tool_name}' missing or invalid target file path (fail-closed).",
            }
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

    if tool_name in WRITE_TOOLS and (bad_path or not target_path):
        return {
            "decision": "deny",
            "reason": f"Write/edit tool '{tool_name}' missing or invalid target file path (fail-closed).",
        }

    if target_path:
        target_real = _resolve_real(target_path, cwd)
        raw_artifact = payload.get("artifactDirectoryPath")
        artifact_dir = raw_artifact.strip() if isinstance(raw_artifact, str) else ""
        artifact_real = _resolve_real(artifact_dir, cwd) if artifact_dir else ""

        in_cwd = _is_within(target_real, cwd_real)
        in_artifact = bool(artifact_real) and _is_within(target_real, artifact_real)

        if not in_cwd and not in_artifact:
            return {
                "decision": "deny",
                "reason": f"Path escapes allowed workspace/artifact directory ({target_path}).",
            }
        if _is_env_secret_path(target_path, target_real):
            return {
                "decision": "deny",
                "reason": (
                    f"Protected no-touch path ({target_path}). "
                    "Coordinate via @coordinator if an exception is needed."
                ),
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
