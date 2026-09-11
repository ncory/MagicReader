#!/bin/bash
# Runs the whole suite. No dependencies beyond the standard library, and all
# hardware is stubbed, so this is safe to run on a reader that is driving a
# show. Works with the system python3 or the app's venv.
#
# Pass -v for per-test names, or set MAGICREADER_TEST_VERBOSE=1 to also see the
# app's own log output.
set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
status=0

cd "$TESTS_DIR"
"$PYTHON" -m unittest discover --start-directory . --pattern "test_*.py" "$@" || status=1

# Shell tests are not discoverable by unittest, so run them explicitly - one
# that is never run is worse than one that does not exist.
for script in "$TESTS_DIR"/test_*.sh; do
    [ -e "$script" ] || continue
    echo
    echo "=== $(basename "$script") ==="
    bash "$script" || status=1
done

exit "$status"
