#!/bin/bash
#
# Sets up all environment variables for the kryptos attack framework.
# Source this (do NOT execute) from the repo root:
#
#     source scripts/set_env.sh
#
# Every other script in scripts/ checks for $KRYPTOS_ENV and refuses to run
# unless this file has been sourced first.

# Resolve the repo root as the parent of this script's directory, regardless
# of where the user sources it from.
_KRYPTOS_SELF="${BASH_SOURCE[0]:-$0}"
_KRYPTOS_SCRIPTS_DIR="$(cd "$(dirname "$_KRYPTOS_SELF")" && pwd)"

export KRYPTOS_ENV=1
export KRYPTOS_HOME="$(cd "$_KRYPTOS_SCRIPTS_DIR/.." && pwd)"

# Pythia / ChampSim lives in the same repo (kryptos IS the simulator).
export PYTHIA_HOME="$KRYPTOS_HOME"

# Layout
export CODES_DIR="$KRYPTOS_HOME/codes"
export SCRIPTS_DIR="$KRYPTOS_HOME/scripts"
export TRACER_DIR="$KRYPTOS_HOME/tracer"
export BUILD_DIR="$KRYPTOS_HOME/build"
export TRACES_DIR="$KRYPTOS_HOME/traces"
export EXP_ROOT="$KRYPTOS_HOME/experiments"

# 2-core ChampSim binary used for co-location (victim core 0 + attacker core 1).
export EXE="$KRYPTOS_HOME/bin/perceptron-multi-multi-no-ship-2core"

# Intel PIN (the tracer front-end). Pinned to the known-good kit; set
# KRYPTOS_PIN_ROOT before sourcing to override. Note: a stray PIN_ROOT in your
# shell profile (e.g. /opt/pin) is deliberately ignored, since a mismatched kit
# yields "Failure to execute pind, Permission denied".
export PIN_ROOT="${KRYPTOS_PIN_ROOT:-$HOME/pin-external-4.3-99850-gce5652921-gcc-linux}"

# Perl modules used by create_jobfile.pl / rollup.pl
export PERL5LIB="$PERL5LIB:$KRYPTOS_HOME/scripts"

mkdir -p "$BUILD_DIR" "$TRACES_DIR"

echo "kryptos env set."
echo "  KRYPTOS_HOME = $KRYPTOS_HOME"
echo "  EXE          = $EXE"
echo "  PIN_ROOT     = $PIN_ROOT"
