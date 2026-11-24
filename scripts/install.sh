#!/usr/bin/env bash
set -euo pipefail

CDPATH=""

resolve_script_dir() {
  local source_path="${BASH_SOURCE[0]}"
  local dir target
  while [[ -L "$source_path" ]]; do
    dir="$(cd -P "$(dirname "$source_path")" && pwd)"
    target="$(readlink "$source_path")"
    if [[ "$target" == /* ]]; then
      source_path="$target"
    else
      source_path="$dir/$target"
    fi
  done
  cd -P "$(dirname "$source_path")" && pwd
}

SCRIPT_DIR="$(resolve_script_dir)"
REPO_ROOT="$(cd -P "$SCRIPT_DIR/.." && pwd)"
SRC_DIR="$REPO_ROOT/skills/swarm-planner"
SKILLS_ROOT="${ANTIGRAVITY_SKILLS_DIR:-$HOME/.gemini/config/skills}"
DEST_DIR="$SKILLS_ROOT/swarm-planner"
PYTHON="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [--copy | --symlink | --status | --uninstall] [--skip-tests] [--force]

Modes (mutually exclusive):
  --copy        Sync skills/swarm-planner into ~/.gemini/config/skills/swarm-planner (default)
  --symlink     Symlink ~/.gemini/config/skills/swarm-planner to this repo's skills/swarm-planner
  --status      Check installed skill status and repo-vs-installed drift (alias: --check)
  --uninstall   Remove ~/.gemini/config/skills/swarm-planner

Modifiers:
  --skip-tests  Skip running JSON lint and unit tests before --copy / --symlink
  --force       Allow --symlink from a linked or dirty git worktree (with warning)
  -h, --help    Show this help message
EOF
}

resolve_abs_path() {
  local p="$1"
  if [[ "$p" != /* ]]; then
    p="$REPO_ROOT/$p"
  fi
  if [[ -d "$p" ]]; then
    (cd -P "$p" && pwd)
  else
    local dir base
    dir="$(dirname "$p")"
    base="$(basename "$p")"
    if [[ -d "$dir" ]]; then
      printf '%s/%s\n' "$(cd -P "$dir" && pwd)" "$base"
    else
      printf '%s\n' "$p"
    fi
  fi
}

IS_GIT_REPO=0
IS_LINKED_WORKTREE=0
IS_DIRTY_WORKTREE=0

detect_git_state() {
  if ! command -v git >/dev/null 2>&1; then
    return
  fi
  if ! git -C "$REPO_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return
  fi
  IS_GIT_REPO=1
  local git_dir git_common_dir abs_git_dir abs_common_dir
  git_dir="$(git -C "$REPO_ROOT" rev-parse --git-dir 2>/dev/null || true)"
  git_common_dir="$(git -C "$REPO_ROOT" rev-parse --git-common-dir 2>/dev/null || true)"
  if [[ -n "$git_dir" && -n "$git_common_dir" ]]; then
    abs_git_dir="$(resolve_abs_path "$git_dir")"
    abs_common_dir="$(resolve_abs_path "$git_common_dir")"
    if [[ "$abs_git_dir" != "$abs_common_dir" ]]; then
      IS_LINKED_WORKTREE=1
    fi
  fi
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain --untracked-files=normal 2>/dev/null || true)" ]]; then
    IS_DIRTY_WORKTREE=1
  fi
}

run_preflight_tests() {
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m json.tool "$SRC_DIR/examples/swarm-guardrails-plugin.json" >/dev/null
  PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m json.tool "$SRC_DIR/examples/swarm-guardrails-hooks.json" >/dev/null
  if [[ -d "$REPO_ROOT/tests" ]]; then
    PYTHONDONTWRITEBYTECODE=1 "$PYTHON" -B -m unittest discover -s "$REPO_ROOT/tests" -v
  fi
}

MODE=""
SKIP_TESTS=0
FORCE=0

set_mode() {
  local new_mode="$1"
  if [[ -n "$MODE" && "$MODE" != "$new_mode" ]]; then
    echo "Conflicting mode flags: --$MODE and --$new_mode" >&2
    usage >&2
    exit 2
  fi
  MODE="$new_mode"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy) set_mode "copy" ;;
    --symlink) set_mode "symlink" ;;
    --status|--check) set_mode "status" ;;
    --uninstall) set_mode "uninstall" ;;
    --skip-tests) SKIP_TESTS=1 ;;
    --force) FORCE=1 ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if [[ -z "$MODE" ]]; then
  MODE="copy"
fi

if [[ "$MODE" == "uninstall" ]]; then
  if [[ -L "$DEST_DIR" || -e "$DEST_DIR" ]]; then
    rm -rf "$DEST_DIR"
    echo "Removed $DEST_DIR"
  else
    echo "Nothing to remove at $DEST_DIR"
  fi
  exit 0
fi

if [[ ! -f "$SRC_DIR/SKILL.md" ]]; then
  echo "Skill source missing at $SRC_DIR/SKILL.md" >&2
  exit 1
fi

detect_git_state

if [[ "$MODE" == "status" ]]; then
  if [[ "$IS_LINKED_WORKTREE" -eq 1 ]]; then
    echo "INFO: Repo checkout is a linked git worktree ($REPO_ROOT)."
  fi
  if [[ ! -L "$DEST_DIR" && ! -e "$DEST_DIR" ]]; then
    echo "MISSING: $DEST_DIR is not installed."
    exit 1
  fi
  if [[ -L "$DEST_DIR" ]]; then
    link_target="$(readlink "$DEST_DIR")"
    if [[ ! -e "$DEST_DIR" ]]; then
      echo "DANGLING: $DEST_DIR -> $link_target (target does not exist)"
      exit 1
    fi
    dest_real="$(cd -P "$DEST_DIR" && pwd)"
    src_real="$(cd -P "$SRC_DIR" && pwd)"
    if [[ "$dest_real" != "$src_real" ]]; then
      echo "DRIFT: $DEST_DIR symlinks to $dest_real (expected $src_real)"
      exit 1
    fi
    if [[ "$IS_LINKED_WORKTREE" -eq 1 ]]; then
      echo "WARNING: $DEST_DIR symlinks into a linked git worktree ($REPO_ROOT); pruning it will dangle the symlink." >&2
    fi
    echo "OK (symlink): $DEST_DIR -> $src_real"
    exit 0
  fi
  if [[ ! -d "$DEST_DIR" ]]; then
    echo "DRIFT: $DEST_DIR exists but is not a directory or symlink."
    exit 1
  fi
  diff_out=""
  if diff_out="$(diff -rq -x '__pycache__' -x '*.pyc' -x '*.pyo' -x '.DS_Store' "$SRC_DIR" "$DEST_DIR" 2>&1)"; then
    echo "OK (copy): $DEST_DIR matches $SRC_DIR"
    exit 0
  else
    echo "DRIFT: $DEST_DIR differs from $SRC_DIR"
    printf '%s\n' "$diff_out"
    exit 1
  fi
fi

if [[ "$SKIP_TESTS" -eq 0 ]]; then
  run_preflight_tests
fi

mkdir -p "$SKILLS_ROOT"

if [[ "$MODE" == "symlink" ]]; then
  if [[ "$IS_LINKED_WORKTREE" -eq 1 || "$IS_DIRTY_WORKTREE" -eq 1 ]]; then
    worktree_reason=""
    if [[ "$IS_LINKED_WORKTREE" -eq 1 && "$IS_DIRTY_WORKTREE" -eq 1 ]]; then
      worktree_reason="linked and dirty git worktree"
    elif [[ "$IS_LINKED_WORKTREE" -eq 1 ]]; then
      worktree_reason="linked git worktree"
    else
      worktree_reason="dirty git working tree"
    fi
    if [[ "$FORCE" -eq 0 ]]; then
      echo "Refusing to --symlink from a $worktree_reason ($REPO_ROOT); removing the worktree leaves a dangling symlink. Use --copy (recommended) or re-run with --symlink --force." >&2
      exit 1
    fi
    echo "WARNING: Symlinking from a $worktree_reason ($REPO_ROOT) due to --force; pruning this worktree will dangle $DEST_DIR." >&2
  fi
  rm -rf "$DEST_DIR"
  ln -s "$SRC_DIR" "$DEST_DIR"
  echo "Symlinked $DEST_DIR -> $SRC_DIR"
  exit 0
fi

TMP_STAGE="$(mktemp -d "$SKILLS_ROOT/.swarm-planner.tmp.XXXXXX")"
BACKUP_DIR=""
cleanup() {
  if [[ -n "${TMP_STAGE:-}" && -e "$TMP_STAGE" ]]; then
    rm -rf "$TMP_STAGE"
  fi
}
trap cleanup EXIT

if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '__pycache__' \
    --exclude '*.pyc' \
    --exclude '*.pyo' \
    --exclude '.DS_Store' \
    "$SRC_DIR/" "$TMP_STAGE/"
else
  cp -Rp "$SRC_DIR/." "$TMP_STAGE/"
  find "$TMP_STAGE" -name '__pycache__' -prune -exec rm -rf {} +
  find "$TMP_STAGE" \( -name '*.pyc' -o -name '*.pyo' -o -name '.DS_Store' \) -delete
fi
chmod +x "$TMP_STAGE/scripts/model_matrix.py" "$TMP_STAGE/examples/pretool-guard.py"

if [[ -L "$DEST_DIR" || -e "$DEST_DIR" ]]; then
  BACKUP_DIR="$SKILLS_ROOT/.swarm-planner.bak.$$"
  rm -rf "$BACKUP_DIR"
  mv "$DEST_DIR" "$BACKUP_DIR"
fi

if mv "$TMP_STAGE" "$DEST_DIR"; then
  TMP_STAGE=""
  if [[ -n "$BACKUP_DIR" && ( -L "$BACKUP_DIR" || -e "$BACKUP_DIR" ) ]]; then
    rm -rf "$BACKUP_DIR"
  fi
else
  if [[ -n "$BACKUP_DIR" && ( -L "$BACKUP_DIR" || -e "$BACKUP_DIR" ) ]]; then
    mv "$BACKUP_DIR" "$DEST_DIR" || true
  fi
  echo "Failed to swap staged install into $DEST_DIR" >&2
  exit 1
fi

echo "Installed skill to $DEST_DIR"
