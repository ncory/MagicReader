#!/bin/bash
# Runs the whole suite. No dependencies beyond the standard library, and all
# hardware is stubbed, so this is safe to run on a reader that is driving a
# show. Works with the system python3 or the app's venv.
set -euo pipefail
TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
cd "$TESTS_DIR"
# Pass -v for per-test names, or set MAGICREADER_TEST_VERBOSE=1 to also see
# the app's own log output.
exec "$PYTHON" -m unittest discover --start-directory . --pattern "test_*.py" "$@"
