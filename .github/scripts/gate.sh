#!/usr/bin/env bash
# LANDING GATE — the one verification both the `test` job and the
# `finalize` merge gate run. Verified locally 2026-10-21 (175 passed /
# check no issues / no migration drift):
#   1. plugin/tests  — 175 tests (conftest mounts the demo rig itself)
#   2. manage.py check + makemigrations --check in demo-backend
# NOTE: demo-backend has NO own tests on ai/main (the historical
# "151 tests" lived on unmerged task branches) — pytest with zero
# collected tests exits 5, which would red the gate and halt the
# chain; the plugin suite is the honest green baseline.
set -u
FAIL=0
echo "== gate: pytest plugin/tests =="
python -m pytest plugin/tests -p no:cacheprovider -q || FAIL=1
echo "== gate: demo-backend manage.py check =="
( cd demo-backend && python manage.py check ) || FAIL=1
echo "== gate: demo-backend migrations drift =="
( cd demo-backend && python manage.py makemigrations --check --dry-run ) || FAIL=1
if [ "$FAIL" = "0" ]; then echo "GATE: GREEN"; else echo "GATE: RED"; fi
exit "$FAIL"
