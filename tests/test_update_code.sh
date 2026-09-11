#!/bin/bash
# Exercises update-code.sh's decision: does this update need service-install.sh?
#
# Getting this wrong is either annoying (a password prompt on Trixie for every
# update) or a silent failure (a new systemd unit never installed, which is
# exactly how MagicShutdown.service came to need a manual command).
#
# Only the decision is covered here. Whether the installer itself works, and
# whether the MagicWand restart works, is verified on a real reader.
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

pass=0
fail=0

check() {
    local name="$1" expected="$2" actual="$3"
    if [ "$expected" = "$actual" ]; then
        printf "  ok      %s\n" "$name"
        pass=$((pass + 1))
    else
        printf "  FAILED  %s (expected %s, got %s)\n" "$name" "$expected" "$actual"
        fail=$((fail + 1))
    fi
}

# A fake /etc with everything the installer would have put there.
export MAGICREADER_SYSTEMD_DIR="$WORK/systemd"
export MAGICREADER_SUDOERS_FILE="$WORK/sudoers/magicreader"
mkdir -p "$MAGICREADER_SYSTEMD_DIR" "$WORK/sudoers"
installEverything() {
    local unit
    for unit in MagicReader MagicWand MagicReboot MagicShutdown; do
        touch "$MAGICREADER_SYSTEMD_DIR/$unit.service"
    done
    touch "$MAGICREADER_SUDOERS_FILE"
}
installEverything

# shellcheck source=/dev/null
source "$REPO_DIR/update-code.sh"

run() { needsServiceInstall "$1" "$2" >/dev/null 2>&1 && echo yes || echo no; }

HEAD="$(git -C "$REPO_DIR" rev-parse HEAD)"

echo "Fully installed, nothing pulled:"
check "no installer run needed" "no" "$(run "$HEAD" "$HEAD")"

echo
echo "Something the installer provides is missing:"
rm "$MAGICREADER_SYSTEMD_DIR/MagicShutdown.service"
check "missing unit triggers a run" "yes" "$(run "$HEAD" "$HEAD")"
installEverything
rm "$MAGICREADER_SUDOERS_FILE"
check "missing sudoers grant triggers a run" "yes" "$(run "$HEAD" "$HEAD")"
installEverything

echo
echo "A real commit range:"
# The commit that added MagicShutdown.service and changed service-install.sh.
UNIT_COMMIT="$(git -C "$REPO_DIR" log --format=%H -1 -- MagicShutdown.service 2>/dev/null || true)"
if [ -n "$UNIT_COMMIT" ]; then
    PARENT="$(git -C "$REPO_DIR" rev-parse "$UNIT_COMMIT^" 2>/dev/null || true)"
    check "a commit adding a unit triggers a run" "yes" "$(run "$PARENT" "$UNIT_COMMIT")"
else
    echo "  skipped - MagicShutdown.service has no history yet"
fi

# A commit that changed no unit and no installer must NOT trigger a run - that
# is what keeps the common update password-free on Trixie. Search the history
# for a real one rather than naming a commit that may later change.
NO_UNIT_COMMIT=""
for candidate in $(git -C "$REPO_DIR" log --format=%H -25); do
    parent="$(git -C "$REPO_DIR" rev-parse "$candidate^" 2>/dev/null || true)"
    [ -n "$parent" ] || continue
    hits="$(git -C "$REPO_DIR" diff --name-only "$parent" "$candidate" \
        | grep -cE '^(service-install\.sh|[^/]*\.service(\.template)?)$' || true)"
    if [ "$hits" = "0" ]; then
        NO_UNIT_COMMIT="$candidate"
        NO_UNIT_PARENT="$parent"
        break
    fi
done
if [ -n "$NO_UNIT_COMMIT" ]; then
    echo "  (using $(git -C "$REPO_DIR" log --oneline -1 "$NO_UNIT_COMMIT"))"
    check "a commit touching no units does not trigger a run" "no" \
        "$(run "$NO_UNIT_PARENT" "$NO_UNIT_COMMIT")"
else
    echo "  FAILED  could not find a commit that touched no units"
    fail=$((fail + 1))
fi

echo
if [ "$fail" -gt 0 ]; then
    echo "FAILED: $fail of $((pass + fail))"
    exit 1
fi
echo "OK: $pass checks"
