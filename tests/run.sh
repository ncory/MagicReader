#!/bin/bash
# Runs the whole suite. No dependencies beyond the standard library, and all
# hardware is stubbed, so this is safe to run on a reader that is driving a
# show. Works with the system python3 or the app's venv.
#
# Pass -v for per-test names, or set MAGICREADER_TEST_VERBOSE=1 to also see the
# app's own log output.
set -uo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$TESTS_DIR")"
PYTHON="${PYTHON:-python3}"
status=0

# Resolve a relative PYTHON before the cd below. "PYTHON=.venv/bin/python" is
# what the README suggests and it points at the repo root, not at tests/ -
# unresolved, the interpreter is not found, the whole Python suite silently
# does not run, and the "OK: 5 checks" the shell tests print at the end reads
# like a pass.
case "$PYTHON" in
    /*) ;;                      # already absolute
    */*)                        # relative, with a directory part
        if [ -x "$PWD/$PYTHON" ]; then
            PYTHON="$PWD/$PYTHON"
        elif [ -x "$REPO_DIR/$PYTHON" ]; then
            PYTHON="$REPO_DIR/$PYTHON"
        fi
        ;;
    *) ;;                       # a bare name, left for PATH lookup
esac

# And fail loudly if it still is not usable, rather than reporting only the
# shell results.
if ! "$PYTHON" -c "pass" 2>/dev/null; then
    echo "ERROR: PYTHON=$PYTHON is not a runnable interpreter." >&2
    exit 1
fi

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
