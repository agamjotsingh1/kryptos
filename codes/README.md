# kryptos attack framework

Co-location attack harness on top of Pythia/ChampSim. A victim runs on core 0,
an attacker on core 1, and we measure how much the attacker degrades victim IPC
under different prefetcher configs (no-prefetch vs Pythia).

## Layout

```
codes/
  _common/idle.c          shared "no attacker" baseline (core 1)
  <attack>/
    config.h              shared #defines for victim + attacker
    victim.c              victim workload   -> core 0
    attacker.c            attacker workload -> core 1
    pythia_config.ini     Pythia knobs evaluated against this attack
    rollup.py             result analysis for this attack
scripts/
  set_env.sh              source this first (sets all env vars)
  gen_trace.sh            compile+PIN-trace one workload (idempotent)
  launch.sh               build + trace + slurm fan-out + rollup
```

## Run

```bash
source scripts/set_env.sh          # must be sourced, not executed
./scripts/launch.sh demo
```

`launch.sh <attack>`:

1. traces `victim.c`, `attacker.c`, `_common/idle.c` (skips any trace already in
   `traces/`), compiling each with `-I codes/<attack>` so `config.h` applies.
2. writes `experiments/<attack>/{<attack>.tlist,.exp,.mfile}`.
3. fans the runs out over Slurm (2 co-location pairs x 2 prefetcher configs = 4
   jobs) via `create_jobfile.pl` + `wrapper.sh`, waits for all.
4. runs `codes/<attack>/rollup.py`, writing `experiments/<attack>/rollup.txt`.

### Output `.out` names (consumed by rollup.py)

```
<attack>_attack_<cfg>.out   victim(core0) + attacker(core1)
<attack>_idle_<cfg>.out     victim(core0) + idle(core1)
```
with `<cfg>` in {`nopref`, `pythia`}. `Core_0_IPC` = victim, `Core_1_IPC` = co-runner.

### Tunables (env, optional)

| var | default | meaning |
|-----|---------|---------|
| `TRACE_INSTR` | 50000000 | instrs traced per workload (after `__champsim_start_trace`) |
| `WARMUP` | 10000000 | champsim warmup instrs |
| `SIM` | 40000000 | champsim simulation instrs |
| `PARTITION` | debug | slurm partition |
| `NCORES` | 2 | cpus per slurm job |

## Add a new attack

```bash
cp -r codes/demo codes/<name>
# edit config.h, victim.c, attacker.c; tweak pythia_config.ini / rollup.py
./scripts/launch.sh <name>
```

Each workload must define `__champsim_start_trace()` and call it once at the
start of the region to trace (see `demo/`). Keep the traced region an
effectively infinite loop; PIN stops after `TRACE_INSTR` instructions.

## Attacks with their own run matrix (manifest)

The default layout (victim + {attacker, idle} x {nopref, pythia}) does not fit
every attack. An attack may drop a `matrix` file in its dir to declare its own
neighbor/config grid; when present, `launch.sh` uses it instead of the default.

```
victim   <source>            [prog-args...]
neighbor <name> <source>     [prog-args...]
config   <name> <ini>
```

- `<source>` resolves against the attack dir first, then `codes/`.
- `[prog-args]` are passed to the workload under PIN (become its `argv`), so one
  source yields several neighbor traces by argument alone.
- `launch.sh` crosses every neighbor with every config; output `.out` files are
  named `<neighbor>_<config>.out` and consumed by the attack's `rollup.py`.

See `degree_bw/` for a worked example: one `attacker.c` steered to
idle/light/medium/heavy by argument, crossed with `bwaware`/`bwblind` scooby
configs. Its `rollup.py` parses scooby's per-core histograms (bandwidth bucket,
selected degree, action distribution), writes `rollup.csv`, a 100% stacked
degree-distribution chart `degree_dist.png` (needs matplotlib; skipped if
absent), and reports PASS/FAIL gates.

## Requirements

- 2-core binary `bin/perceptron-multi-multi-no-ship-2core`
  (`./build_champsim.sh <l1d> scooby <llc> 2`).
- Built PIN tracer under `tracer/obj-intel64/`.
- `PIN_ROOT` pointing at the Intel PIN kit (set in `set_env.sh`).
