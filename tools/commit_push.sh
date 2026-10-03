#!/usr/bin/env bash
# commit_push.sh <branch> <commit message> <path> [path...]
#
# Adds the given paths, commits and pushes with retries.  Any git error is
# echoed to stdout (which is visible in the workflow run page) so nothing fails
# silently.
set -u
BRANCH="$1"; MESSAGE="$2"; shift 2

git config user.name "piw-mod-helper"
git config user.email "piw-mod-helper@users.noreply.github.com"

for attempt in 1 2 3 4 5; do
  echo "--- attempt $attempt"
  for path in "$@"; do
    if [ -e "$path" ]; then
      git add -A -f "$path"
    else
      echo "  (missing path: $path)"
    fi
  done
  if git diff --cached --quiet; then
    echo "nothing to commit"
    exit 0
  fi
  git commit -q -m "$MESSAGE" || { echo "commit failed"; exit 1; }
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
