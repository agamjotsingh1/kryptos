#!/bin/bash
#
# Generate a ChampSim trace from a C/C++ source file or a prebuilt binary,
# using the PIN champsim_tracer.
#
# Usage:
#   ./gen_trace.sh <src.c|src.cpp|binary> <trace_name> <total_instr> [include_dir] [prog_args]
#
#   <total_instr>  number of instructions to trace AFTER __champsim_start_trace()
#   [include_dir]  optional dir added to the compiler -I path (holds config.h);
#                  pass "" to skip it while still supplying prog_args.
#   [prog_args]    optional, space-separated args passed to the traced program
#                  under PIN (become its argv). Lets one source yield several
#                  traces by argument, e.g. an attacker's intensity selector.
#
# Output: $TRACES_DIR/<trace_name>.champsimtrace.xz
# Skips work if that compressed trace already exists.

if [[ $# -lt 3 || $# -gt 5 ]]; then
    echo "Usage: $0 <src.c|src.cpp|binary> <trace_name> <total_instr> [include_dir] [prog_args]" >&2
    exit 1
fi

if [[ -z "$KRYPTOS_ENV" ]]; then
    echo "Env variables not set. Source scripts/set_env.sh before running this script!" >&2
    exit 1
fi

INPUT_PATH="$1"
TRACE_NAME="$2"
TOTAL_INSTR="$3"
INCLUDE_DIR="$4"
PROG_ARGS="$5"
START_SYMBOL="__champsim_start_trace"

# Split prog_args into an array (word-split on spaces; empty => no args).
PROG_ARG_ARR=()
[[ -n "$PROG_ARGS" ]] && read -ra PROG_ARG_ARR <<< "$PROG_ARGS"

OUT_XZ="$TRACES_DIR/${TRACE_NAME}.champsimtrace.xz"

# Idempotent: already generated.
if [[ -f "$OUT_XZ" ]]; then
    echo "gen_trace: $OUT_XZ already exists, skipping."
    exit 0
fi

if [[ ! -f "$INPUT_PATH" ]]; then
    echo "Error: Input file '$INPUT_PATH' does not exist!" >&2
    exit 1
fi

INC_FLAGS=()
[[ -n "$INCLUDE_DIR" ]] && INC_FLAGS=(-I "$INCLUDE_DIR")

if [[ "$INPUT_PATH" == *.c || "$INPUT_PATH" == *.cpp ]]; then
    echo "gen_trace: C/C++ source detected. Compiling $INPUT_PATH ..."

    BASENAME=$(basename "$INPUT_PATH")
    BIN_PATH="$BUILD_DIR/${TRACE_NAME}.out"

    if [[ "$INPUT_PATH" == *.cpp ]]; then
        g++ -Wall -static -fno-pie -no-pie -O2 "${INC_FLAGS[@]}" "$INPUT_PATH" -o "$BIN_PATH"
    else
        gcc -Wall -static -fno-pie -no-pie -O2 "${INC_FLAGS[@]}" "$INPUT_PATH" -o "$BIN_PATH"
    fi

    if [[ $? -ne 0 ]]; then
        echo "Error: Compilation failed for $INPUT_PATH!" >&2
        exit 1
    fi
    echo "gen_trace: Compiled to $BIN_PATH"
elif [[ -x "$INPUT_PATH" ]]; then
    BIN_PATH="$INPUT_PATH"
else
    echo "Error: '$INPUT_PATH' is neither an executable nor a C/C++ source file." >&2
    exit 1
fi

cd "$KRYPTOS_HOME" || exit 1
mkdir -p "$BUILD_DIR" "$TRACES_DIR"

if [[ ! -d "$TRACER_DIR/obj-intel64" ]]; then
    echo "gen_trace: tracer not built! Build it under $TRACER_DIR first." >&2
    exit 1
fi

RAW_TRACE="$BUILD_DIR/${TRACE_NAME}.champsimtrace"
[[ -f "$RAW_TRACE" ]] && rm "$RAW_TRACE"

PIN_ARGS=(-t "$TRACER_DIR/obj-intel64/champsim_tracer.so"
    -o "$RAW_TRACE"
    -start_symbol "$START_SYMBOL"
    -t "$TOTAL_INSTR" -- "$BIN_PATH" "${PROG_ARG_ARR[@]}")

if [[ ${#PROG_ARG_ARR[@]} -gt 0 ]]; then
    echo "gen_trace: program args: ${PROG_ARG_ARR[*]}"
fi

# Run under `setarch -R` to disable ASLR for reproducible traces (default).
# Set USE_SETARCH=0 to invoke pin directly, as an escape hatch on kernels where
# the personality change breaks PIN's injector.
if [[ "${USE_SETARCH:-1}" == "1" ]] && command -v setarch >/dev/null 2>&1; then
    setarch x86_64 -R "$PIN_ROOT/pin" "${PIN_ARGS[@]}"
else
    "$PIN_ROOT/pin" "${PIN_ARGS[@]}"
fi

if [[ ! -f "$RAW_TRACE" ]]; then
    echo "Error: pin did not produce a trace!" >&2
    exit 1
fi
echo "gen_trace: Raw trace generated via pin."

xz -T4 -c -6 "$RAW_TRACE" > "$OUT_XZ"
rm "$RAW_TRACE"

echo "gen_trace: Compressed trace written to $OUT_XZ"
