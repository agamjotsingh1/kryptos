# LAUNCH.md — running the kryptos attack framework

This guide is written so a fresh agent (or human) can run the co-location attack
framework end to end without prior context. Read it top to bottom once before
running anything.

## What this framework does

It evaluates **micro-architectural co-location attacks** on the Pythia/ChampSim
simulator. Two workloads run together on a 2-core ChampSim:

- **victim** → core 0 (the program being attacked)
- **attacker** → core 1 (the program trying to degrade the victim)

For each attack we measure the victim's IPC when co-located with the attacker vs
when co-located with an idle baseline, under two prefetcher configs (no-prefetch
and Pythia). The difference is the attack's impact, and comparing configs shows
whether the Pythia prefetcher amplifies or mitigates the attack.

ChampSim is trace-driven, so each workload is first compiled and run under Intel
PIN to produce a `.champsimtrace.xz`. Co-location = feeding two traces to the
2-core binary.

## Repository layout

```
kryptos/
  bin/perceptron-multi-multi-no-ship-2core   2-core ChampSim binary (must exist)
  tracer/obj-intel64/champsim_tracer.so      PIN tracer (must be built)
  config/                                    stock prefetcher .ini files
  traces/                                     generated traces land here
  build/                                      compiled workload binaries + raw traces
  experiments/<attack>/                       per-attack run dir (auto-created)
  wrapper.sh                                  slurm run wrapper (used by jobfile)
  scripts/
    set_env.sh        source first; sets all env vars
    gen_trace.sh      compile + PIN-trace one workload (idempotent)
    launch.sh         full pipeline: trace -> slurm fan-out -> rollup
    create_jobfile.pl rollup.pl ...          existing Pythia tooling
  codes/
    README.md                                 framework reference
    _common/idle.c                            shared "no attacker" baseline
    <attack>/
      config.h            shared #defines for victim + attacker
      victim.c            victim workload  -> core 0
      attacker.c          attacker workload -> core 1
      pythia_config.ini   Pythia knobs evaluated for this attack
      rollup.py           result analysis for this attack
  codes/demo/             worked example attack (LLC capacity-thrash)
```

## Prerequisites (check these first)

1. **2-core binary exists and is executable**
   ```bash
   ls -l bin/perceptron-multi-multi-no-ship-2core
   ```
   If missing, build it: `./build_champsim.sh <l1d_pref> scooby <llc_pref> 2`
   (e.g. `./build_champsim.sh bop scooby no 2`).

2. **PIN tracer is built** — `tracer/obj-intel64/champsim_tracer.so` must exist.
   If not, build it under `tracer/` (its `Makefile`).

3. **Intel PIN kit is present** at `~/pin-external-4.3-99850-gce5652921-gcc-linux`.

4. **Slurm is available** (`sbatch`, `squeue`, `sacct` on PATH) for `launch.sh`.
   The trace step does **not** need Slurm; only the simulation fan-out does.

## ⚠️ Critical gotcha: PIN_ROOT

There is a stray `PIN_ROOT=/opt/pin` exported in the user's shell profile. That
kit is broken — using it makes PIN fail with:

```
LAUNCHER ERROR: Failure to execute pind, errno= Permission denied
```

`scripts/set_env.sh` **deliberately ignores** any inherited `PIN_ROOT` and pins
it to the known-good home kit. So:

- **Always `source scripts/set_env.sh`** in a fresh shell before running
  anything, and confirm the printed line reads:
  ```
  PIN_ROOT = /home/<user>/pin-external-4.3-99850-gce5652921-gcc-linux
  ```
  If it still shows `/opt/pin`, you did not source `set_env.sh` (or an old shell
  is cached). Re-source it.
- To point at a different kit, set `KRYPTOS_PIN_ROOT` **before** sourcing:
  ```bash
  KRYPTOS_PIN_ROOT=/path/to/pin source scripts/set_env.sh
  ```

## Running an attack

From the repo root (`kryptos/`):

```bash
source scripts/set_env.sh      # sets env + prints PIN_ROOT/EXE — verify these
./scripts/launch.sh demo       # run the example attack
```

`launch.sh <attack>` does, in order:

1. **Trace** `victim.c`, `attacker.c`, and `_common/idle.c` via `gen_trace.sh`,
   compiling each with `-I codes/<attack>` so `config.h` applies. Existing traces
   in `traces/` are **skipped** (idempotent) — delete them to force a rebuild.
2. **Write** `experiments/<attack>/<attack>.{tlist,exp,mfile}`.
3. **Fan out** over Slurm: `create_jobfile.pl` generates one `sbatch` line per
   (co-location pair × prefetcher config) = 2 × 2 = **4 jobs**, submits them, and
   polls `squeue`/`sacct` until all finish.
4. **Roll up**: runs `codes/<attack>/rollup.py`, writing
   `experiments/<attack>/rollup.txt`.

### Tunable env vars (optional)

| var          | default    | meaning                                            |
|--------------|------------|----------------------------------------------------|
| `TRACE_INSTR`| 50000000   | instrs traced per workload (after start symbol)    |
| `WARMUP`     | 10000000   | ChampSim warmup instructions                       |
| `SIM`        | 40000000   | ChampSim simulation instructions                   |
| `PARTITION`  | debug      | Slurm partition                                    |
| `NCORES`     | 2          | cpus per Slurm job                                 |
| `USE_SETARCH`| 1          | run PIN under `setarch -R` (ASLR off); set 0 to skip |

Example quick smoke run (short traces/sim):
```bash
TRACE_INSTR=2000000 WARMUP=1000000 SIM=2000000 ./scripts/launch.sh demo
```

## Output and interpretation

Per run, ChampSim writes `experiments/<attack>/<name>_<cfg>.out`:

```
<attack>_attack_nopref.out   victim + attacker, no prefetcher
<attack>_attack_pythia.out   victim + attacker, Pythia
<attack>_idle_nopref.out     victim + idle,     no prefetcher
<attack>_idle_pythia.out     victim + idle,     Pythia
```

In each `.out`: `Core_0_IPC` = victim, `Core_1_IPC` = co-runner.

`rollup.py` prints a table per config:

```
config      vIPC idle  vIPC attack     aIPC  slowdown   impact%
nopref         3.0000       1.5000   0.5000     2.000    50.00%
pythia         3.2000       1.0000   0.7000     3.200    68.75%

Pythia amplifies the attack: slowdown 2.000 (nopref) -> 3.200 (pythia), delta +1.200
```

- `slowdown` = victim_IPC(idle) / victim_IPC(attack); higher = worse attack.
- `impact%`  = victim IPC loss caused by the attacker.
- final line = whether Pythia makes it worse (`amplifies`) or better (`mitigates`).

`rollup.py` exits non-zero if any expected `.out` is missing.

## Adding a new attack

```bash
cp -r codes/demo codes/<name>
# edit codes/<name>/config.h, victim.c, attacker.c
# adjust codes/<name>/pythia_config.ini and rollup.py if needed
source scripts/set_env.sh
./scripts/launch.sh <name>
```

Requirements for each workload (`victim.c`, `attacker.c`):

- Define and call `__champsim_start_trace()` once, right before the region to
  trace (PIN starts tracing at this symbol). See `codes/demo/victim.c`.
- Keep the traced region an effectively infinite loop; PIN stops after
  `TRACE_INSTR` instructions.
- Share cache/geometry constants via `config.h`.

### Attacks with a custom run matrix (`matrix` manifest)

If an attack needs more than the default victim + {attacker, idle} x {nopref,
pythia} grid, drop a `matrix` file in `codes/<attack>/`. When present, `launch.sh`
builds the grid from it instead:

```
victim   <source>            [prog-args...]
neighbor <name> <source>     [prog-args...]
config   <name> <ini>
```

`<source>` resolves against the attack dir then `codes/`; `[prog-args]` go to the
workload under PIN (its `argv`), so one source yields several neighbor traces by
argument. Every neighbor is crossed with every config; outputs are
`<neighbor>_<config>.out`. See `codes/degree_bw/` — one `attacker.c` steered to
idle/light/medium/heavy by argument, crossed with `bwaware`/`bwblind` scooby
configs; its `rollup.py` parses scooby histograms, writes `rollup.csv`, and
reports PASS/FAIL success gates.

## Just generate a trace (no simulation)

```bash
source scripts/set_env.sh
./scripts/gen_trace.sh <src.c|binary> <trace_name> <total_instr> [include_dir] [prog_args]
# -> traces/<trace_name>.champsimtrace.xz   (skipped if it already exists)
```

`[prog_args]` (optional, space-separated) are passed to the traced program under
PIN as its `argv`. Pass `""` for `[include_dir]` if you only need `prog_args`.
This lets one source yield several traces by argument, e.g.:

```bash
./scripts/gen_trace.sh codes/degree_bw/attacker.c degree_bw_atk_heavy \
    "$TRACE_INSTR" codes/degree_bw "heavy"
```

## Troubleshooting

- **`Failure to execute pind, Permission denied`** → wrong PIN kit. Confirm
  `set_env.sh` was sourced and `PIN_ROOT` points at the home kit, not `/opt/pin`.
- **`pin did not produce a trace`** → check the start symbol is present in the
  binary (`nm build/<name>.out | grep champsim_start_trace`) and that the tracer
  `.so` exists.
- **`2-core ChampSim binary not found`** → build it (see Prerequisites).
- **No jobs submitted / Slurm errors** → confirm `sbatch` works and `PARTITION`
  exists (`sinfo`). The trace step still works without Slurm.
- **`Env variables not set`** → you forgot to `source scripts/set_env.sh`.
- **Forcing a fresh trace** → `rm traces/<name>.champsimtrace.xz` then re-run.
- **`setarch` breaks PIN on some kernel** → re-run with `USE_SETARCH=0`.
