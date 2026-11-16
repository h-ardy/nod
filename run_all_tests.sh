#!/bin/sh
# Runs every Nod test suite (needs python3 with aiohttp, mcp, pillow; g++; git).
set -e
cd "$(dirname "$0")"
(cd firmware/sim && ./build.sh && python3 firmware_test.py)
(cd host && python3 tests/e2e_test.py && python3 tests/chain_test.py)
