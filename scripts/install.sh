#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_ROOT/skills/swarm-planner"
SKILLS_ROOT="${ANTIGRAVITY_SKILLS_DIR:-$HOME/.gemini/config/skills}"
DEST_DIR="$SKILLS_ROOT/swarm-planner"

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [--copy | --symlink | --uninstall]

Options:
  --copy       Sync skills/swarm-planner into ~/.gemini/config/skills/swarm-planner (default)
  --symlink    Symlink ~/.gemini/config/skills/swarm-planner to this repo's skills/swarm-planner
  --uninstall  Remove ~/.gemini/config/skills/swarm-planner
EOF
}

MODE="copy"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --copy) MODE="copy" ;;
    --symlink) MODE="symlink" ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

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

mkdir -p "$SKILLS_ROOT"

if [[ "$MODE" == "symlink" ]]; then
  rm -rf "$DEST_DIR"
  ln -s "$SRC_DIR" "$DEST_DIR"
  echo "Symlinked $DEST_DIR -> $SRC_DIR"
  exit 0
fi

rm -rf "$DEST_DIR"
mkdir -p "$DEST_DIR"
if command -v rsync >/dev/null 2>&1; then
  rsync -a --exclude '__pycache__' --exclude '*.pyc' "$SRC_DIR/" "$DEST_DIR/"
else
  cp -R "$SRC_DIR/." "$DEST_DIR/"
  find "$DEST_DIR" -name '__pycache__' -prune -exec rm -rf {} +
  find "$DEST_DIR" -name '*.pyc' -delete
fi
chmod +x "$DEST_DIR/scripts/model_matrix.py" "$DEST_DIR/examples/pretool-guard.py"
echo "Installed skill to $DEST_DIR"
