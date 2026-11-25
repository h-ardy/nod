#!/bin/bash
# Try Nod Dot with no key.
#   bash demo.sh       fake requests in this window, your keyboard is the key
#   bash demo.sh key   practice mode for the on-screen key in the Nod Dot app
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
if [ "$1" = "key" ]; then
  echo "practice mode: open Nod Dot and use its Practice key window. Ctrl-C here to stop."
  exec .venv/bin/nod daemon --sim 1
fi
exec .venv/bin/nod demo
