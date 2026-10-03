#!/usr/bin/env bash
# commit_push.sh <branch> <commit message> <path> [path...]
#
# Adds the given paths, commits and pushes with retries.  Everything is written
# to transfer/_push_log.txt (inside the repository) so it can be inspected even
# when the Actions log is not readable.
set -u
BRANCH="$1"; MESSAGE="$2"; shift 2
LOG="transfer/_push_log.txt"
mkdir -p transfer
exec > >(tee -a "$LOG") 2>&1

echo "===== $(date -u) commit_push branch=$BRANCH msg=$MESSAGE paths=$*"

git config user.name "piw-mod-helper"
git config user.email "piw-mod-helper@users.noreply.github.com"

for attempt in 1 2 3 4 5; do
  echo "--- attempt $attempt"
  for path in "$@"; do
    if [ -e "$path" ]; then
      git add -A -f "$path"
      echo "  added: $path"
    else
      echo "  MISSING path: $path"
    fi
  done
  echo "--- git status --short (staged+unstaged) ---"
  git status --short | head -40
  if git diff --cached --quiet; then
    echo "nothing staged -> nothing to commit"
    echo "--- git status (full) ---"
    git status | head -30
    exit 0
  fi
  git commit -q -m "$MESSAGE" || { echo "commit failed"; exit 1; }
  echo "--- commit created: $(git log --oneline -1) ---"
  if git push origin "HEAD:$BRANCH"; then
    echo "pushed $BRANCH"
    exit 0
  fi
  echo "push failed, trying to rebase on top of the remote"
  git fetch origin "$BRANCH" || true
  git rebase "origin/$BRANCH" || { git rebase --abort || true; }
  sleep 3
done

echo "::error::could not push to $BRANCH after 5 attempts"
exit 1
