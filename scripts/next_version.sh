#!/usr/bin/env bash
# Prints the version the next deploy of a target ships as: MAJOR.MINOR.PATCH.
#
#   next_version.sh <api|spa> [patch|minor|major]      (bump defaults to patch)
#
# Each target counts its own deploys with git tags (api-v1.0.3, spa-v1.2.0), so the backend and the
# frontend version independently. With no tag yet the first version is 1.0.0, whatever the bump.
set -euo pipefail

target="${1:-}"
bump="${2:-patch}"

case "$target" in
  api | spa) ;;
  *) echo "usage: next_version.sh <api|spa> [patch|minor|major]" >&2; exit 1 ;;
esac

# A stale tag list would hand out a version someone already shipped, so a failed fetch is fatal.
git fetch origin --tags --quiet

latest="$(git tag --list "${target}-v[0-9]*.[0-9]*.[0-9]*" --sort=-v:refname | head -n1)"
if [[ -z "$latest" ]]; then
  echo "1.0.0"
  exit 0
fi

IFS=. read -r major minor patch <<<"${latest#"${target}-v"}"
case "$bump" in
  major) echo "$((major + 1)).0.0" ;;
  minor) echo "${major}.$((minor + 1)).0" ;;
  patch) echo "${major}.${minor}.$((patch + 1))" ;;
  *) echo "unknown bump: $bump (use patch, minor or major)" >&2; exit 1 ;;
esac
