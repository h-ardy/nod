#!/bin/bash
# Try Nod Dot with no key: ./demo.sh  (from the host folder)
set -e
cd "$(dirname "$0")"
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null && "$c" -c 'import sys; sys.exit(sys.version_info < (3,10))'; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "Nod needs Python 3.10 or newer. Install it with: brew install python"
  exit 1
fi
if [ ! -x .venv/bin/nod ]; then
  echo "first run: setting up (about a minute)"
  "$PY" -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -e .
fi
exec .venv/bin/nod demo
