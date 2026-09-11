#!/bin/bash
set -euo pipefail

# Pulls the latest code and restarts the app, re-running the service installer
# only when it is actually needed.
#
# The old version pulled and restarted, which quietly missed new or changed
# systemd units - that is why adding MagicShutdown.service needed a longer
# command by hand. But always re-running service-install.sh is not free either:
# it writes /etc/sudoers.d/magicreader, and on Trixie that means a password
# prompt on every single update. So check first.

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Overridable so the test suite can point them at a scratch directory. In
# normal use the defaults are what matter.
SYSTEMD_DIR="${MAGICREADER_SYSTEMD_DIR:-/etc/systemd/system}"
SUDOERS_FILE="${MAGICREADER_SUDOERS_FILE:-/etc/sudoers.d/magicreader}"

UNITS=(MagicReader MagicWand MagicReboot MagicShutdown)

# Returns 0 (run the installer) if anything it installs is missing, or if this
# update changed the installer or any unit. $1 and $2 are the commits before
# and after the pull; pass them equal to mean "nothing was pulled".
needsServiceInstall() {
    local before="$1" after="$2" unit changed
    for unit in "${UNITS[@]}"; do
        if [ ! -f "$SYSTEMD_DIR/$unit.service" ]; then
            echo "  $unit.service is not installed"
            return 0
        fi
    done
    if [ ! -f "$SUDOERS_FILE" ]; then
        echo "  the sudoers grant is not installed"
        return 0
    fi
    if [ "$before" != "$after" ]; then
        changed="$(git -C "$REPO_DIR" diff --name-only "$before" "$after" \
            | grep -E '^(service-install\.sh|[^/]*\.service(\.template)?)$' || true)"
        if [ -n "$changed" ]; then
            echo "  changed in this update:"
            echo "$changed" | sed 's/^/    /'
            return 0
        fi
    fi
    return 1
}

main() {
    cd "$REPO_DIR"
    local before after
    before="$(git rev-parse HEAD)"
    git pull origin main
    after="$(git rev-parse HEAD)"

    echo
    if needsServiceInstall "$before" "$after"; then
        echo "Running service-install.sh."
        echo "This needs sudo - on Trixie it will ask for your password."
        ./service-install.sh
    else
        echo "Service definitions are unchanged and fully installed - restarting the app."
        # Go through MagicWand rather than restarting MagicReader directly:
        # that is the unit the sudoers grant covers, so this stays
        # password-free on Trixie.
        sudo systemctl start MagicWand.service
        echo "Restarted MagicReader.service"
    fi
}

# Only run when executed, so the tests can source this and call the function.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
