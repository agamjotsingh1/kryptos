# filltime_steer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `codes/filltime_steer/` — a blind, open-loop co-location attack that steers Pythia's learned prefetch *distance* through the base reward's timely/untimely classification (fill-timing channel), with the DRAM-bandwidth path disabled, plus the rollup gates that prove it.

**Architecture:** A dual-touch victim (each PC demands both `O_short` and `O_long` every iteration, so whichever offset Pythia selects is always correct and only *timeliness* separates them) runs on core 0. A blind attacker on core 1 raises shared-memory fill latency via its own disjoint streaming, moving the timely↔untimely crossover `O* = L/T_line` and steering contestable PCs from short to long offsets. `flat.ini` (untimely reward = timely reward) is the decisive isolation control. The whole thing runs through the existing manifest-matrix launch path; rollup.py asserts gates A–F plus D′ on the scooby stat dumps.

**Tech Stack:** C (victim/attacker traces, `-static -no-pie` via `scripts/gen_trace.sh`), ChampSim 2-core + Pythia/scooby, Python 3 (rollup.py), the existing `scripts/launch.sh` manifest path.

**Spec:** `docs/superpowers/specs/2026-11-16-filltime-steer-design.md`

## Global Constraints

- **No cross-contamination (hard):** attacker references only its own disjoint 64 MiB region and its own PCs; victim references only its own per-PC regions/PCs. No victim address, PC, hot set, or Pythia state appears in the attacker source, or vice versa.
- **Bandwidth path OFF:** every scooby config uses `scooby_high_bw_thresh = 4` (bucket maxes at 3 → `is_high_bw()` never fires). `scooby_enable_hbw_reward` is irrelevant; leave the HBW table untouched/unused.
- **Offsets ∈ `scooby_actions`** (`1,3,4,5,10,11,12,22,23,30,32,-1,-3,-6,0`), **never `1`** (featurewise `+1` fallback attractor), and **globally unique** across all PCs (`reward.dist[action][type]` is aggregated over all PCs — shared offsets destroy per-PC attribution).
- **Base reward values (verbatim):** `correct_timely=20`, `correct_untimely=12`, `incorrect=-8`, `none=-4`. `flat.ini` differs from `aware.ini` in exactly one knob: `scooby_reward_correct_untimely` `12 → 20`.
- **Reuse existing plumbing:** manifest-matrix mode of `scripts/launch.sh` (requires `config.h`, `victim.c`, `rollup.py`, `matrix`), `gen_trace.sh`, the `nm`-on-`build/<trace>.out` per-PC IP→symbol mapping (as in `codes/blend_bw/rollup.py`). No ChampSim/scooby **source** changes — all readouts already exist (`scooby_reward.dist` l.1076, `scooby_predict_action_<O>` l.964, `scooby_per_pc_` l.1023, `scooby_reward_correct_*`/`incorrect`/`no_pref` l.1056-59, `scooby_reward_*_high_bw` l.1066-67).

## Review Focus

- **Offset collision across PCs** → `reward.dist`/`per_pc` misattribution. Expected: any two PCs sharing an offset is a hard error, not silently averaged. *(Test in Task 4: rollup raises if a mapped PC offset is non-unique; Task 1 selftest asserts the configured set is distinct.)*
- **`O_short` never timely even at idle** (victim mistuned) → baseline already picks long, no steering headroom. Expected: at idle, contestable PCs are predominantly short + timely. *(Test in Task 1 selftest bound-check + Task 6 calibration gate.)*
- **Attacker overshoot knocks anchors untimely** (anchor `O_short` too small) → selectivity lost. Expected: anchors stay long-fraction-flat at max intensity. *(Test in Task 5 gate C with an "overshoot" fixture.)*
- **`−8` incorrect contamination** (a dual-touch load skipped, or an offset ≥ reuse horizon) → `flat.ini` stops isolating. Expected: contestable offsets show incorrect-fraction ≈ 0. *(Test in Task 1 selftest "both touched every iter"; Task 5 gate D′ fixture.)*
- **Bucket accidentally live** (`high_bw_thresh ≠ 4` or HBW reward on) → bandwidth confound. Expected: `is_high_bw` never fires; all `*_high_bw` reward counts are 0. *(Test in Task 3 ini-assertion; Task 5 gate E fixture.)*

---

### Task 1: Victim (dual-touch) + config.h + selftest

**Files:**
- Create: `codes/filltime_steer/config.h`
- Create: `codes/filltime_steer/victim.c`
- Test: `codes/filltime_steer/tests/test_victim_selftest.py`

**Interfaces:**
- Produces: `config.h` macros consumed by victim.c and attacker.c — `LINE_BYTES=64`, `VICTIM_N_PC`, `VICTIM_PC_OSHORT[]`, `VICTIM_PC_OLONG[]`, `VICTIM_PC_STRIDE[]`, `VICTIM_PC_ALU[]`, `VICTIM_REGION_LINES_PER_PC`, plus attacker macros (filled in Task 2).
- Produces: a victim binary whose per-PC load sites are named `ft_pc_<j>` (NOINLINE), so Task 4's `nm` mapping can resolve each trigger IP to its `(O_short, O_long)`.
- Produces (selftest): compiling victim.c with `-DFT_SELFTEST` yields a binary that runs `FT_SELFTEST_ITERS` iterations and prints, per PC, the set of access deltas it generated, as lines `pc <j> deltas <d1,d2,...>`.

**Invariant the victim must satisfy (the correctness crux, spec §5-A):** every Pythia trigger at `ft_pc_<j>` is followed within the reuse window by demands to **both** `line+O_short[j]` and `line+O_long[j]`; both ∈ `scooby_actions`; the trigger's delta-history state is stationary across iterations. Suggested (non-binding) per-PC cycle the builder may use or improve — each iteration of `ft_pc_j`: `load(base+O_short)`, `load(base+O_long)`, `base += STRIDE[j]`; choose `STRIDE[j]` so the inter-trigger delta stream is periodic. The selftest, not this sketch, is the arbiter.

**Chosen parameters** (globally-unique offsets; contestable = small `O_short`, anchor = large `O_short`):

| PC | role | O_short | O_long | note |
|----|------|:-------:|:------:|------|
| 0 | contestable | 3 | 10 | flips first |
| 1 | contestable | 4 | 11 | |
| 2 | contestable | 5 | 12 | flips last |
| 3 | anchor | 22 | 30 | `O_short` large → always timely |
| 4 | anchor | 23 | 32 | |

`VICTIM_PC_ALU[j]` (per-PC ALU iterations, sets `T_line[j]`) and `VICTIM_PC_STRIDE[j]` are tuned in Task 7; start all ALU at the `blend_bw` value (2) and strides so the cycle is periodic.

- [ ] **Step 1: Write the failing selftest** `codes/filltime_steer/tests/test_victim_selftest.py`

```python
# compiles victim.c with -DFT_SELFTEST, runs it, parses "pc <j> deltas <...>"
def test_both_offsets_touched_every_pc():
    deltas = run_selftest()                      # {pc_j: set(int deltas)}
    OSHORT = [3,4,5,22,23]; OLONG = [10,11,12,30,32]
    for j in range(5):
        assert OSHORT[j] in deltas[j], f"PC{j} never demands O_short"
        assert OLONG[j]  in deltas[j], f"PC{j} never demands O_long"

def test_offsets_globally_unique():
    allo = [3,10,4,11,5,12,22,30,23,32]
    assert len(set(allo)) == len(allo)
    assert 1 not in allo                          # +1 fallback attractor excluded
```

- [ ] **Step 2: Run the test, verify it fails** (no victim.c yet). Expected: FAIL (compile error / missing binary).
- [ ] **Step 3: Write `config.h` and `victim.c`** satisfying the invariant and the parameter table. Mirror `codes/blend_bw/victim.c` skeleton (per-PC LCG, disjoint regions, `__champsim_start_trace`, NOINLINE `ft_pc_<j>`); add the `#ifdef FT_SELFTEST` finite-loop + per-PC delta print.
- [ ] **Step 4: Run the test, verify it passes.** Expected: PASS.
- [ ] **Step 5: Commit** (`feat(filltime_steer): dual-touch victim + config.h + selftest`).

---

### Task 2: Attacker (steady latency dial) + benign control + selftest

**Files:**
- Create: `codes/filltime_steer/attacker.c`
- Modify: `codes/filltime_steer/config.h` (add attacker macros)
- Test: `codes/filltime_steer/tests/test_attacker_selftest.py`

**Interfaces:**
- Consumes: `config.h` `LINE_BYTES`, `ATK_REGION_LOG2_MAX` (=26, 64 MiB).
- Produces: `attacker` binary, `usage: ./attacker <region_log2> <alu_pad>`. Each iteration: load one fresh line of a `2^region_log2`-byte region (cursor persists → keeps missing when region ≫ LLC), then `alu_pad` register-only ALU ops. Lower `alu_pad` → higher sustained DRAM request rate → higher shared-queue latency (the graded intensity dial). `region_log2` small (e.g. 18 = 256 KiB) → LLC-resident → DRAM-quiet (the `benign` control). Blind: references only its own region.
- Produces (selftest): `-DFT_SELFTEST` prints `loads <n> alu <m>` after a fixed iteration count, so the test can confirm the load/ALU ratio tracks `alu_pad`.

- [ ] **Step 1: Write the failing selftest** asserting (a) `alu_pad=0` gives loads ≫ with no padding, (b) larger `alu_pad` lowers the load:instruction ratio monotonically, (c) the source contains no victim symbols/addresses (grep assertion).
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Write `attacker.c`** (reuse `codes/blend_bw/attacker.c` streaming body; replace the on/off toggle with the `region_log2`+`alu_pad` dial).
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** (`feat(filltime_steer): steady-rate attacker + benign control`).

---

### Task 3: Configs (`aware.ini`, `flat.ini`) + `matrix` + ini assertions

**Files:**
- Create: `codes/filltime_steer/aware.ini`, `codes/filltime_steer/flat.ini`, `codes/filltime_steer/matrix`
- Test: `codes/filltime_steer/tests/test_configs.py`

**Interfaces:**
- Produces: `aware.ini` = `codes/blend_bw/aware.ini` base **but** `scooby_high_bw_thresh = 4`, `scooby_enable_hbw_reward = false`, `scooby_reward_correct_untimely = 12`, `scooby_enable_per_pc_stats = true`, `scooby_actions` unchanged. `flat.ini` = identical except `scooby_reward_correct_untimely = 20`.
- Produces: `matrix` (manifest) crossing one victim × neighbors × configs:
  ```
  victim   victim.c
  neighbor idle    _common/idle.c
  neighbor benign  attacker.c  18 64
  neighbor atk_lo  attacker.c  26 24
  neighbor atk_mid attacker.c  26 6
  neighbor atk_hi  attacker.c  26 0
  config   aware   aware.ini
  config   flat    flat.ini
  ```
  (`alu_pad` values 24/6/0 are provisional; Task 6 calibration sets the final ladder.)

- [ ] **Step 1: Write the failing test** `test_configs.py`:

```python
def test_bandwidth_path_off():
    for ini in ["aware.ini","flat.ini"]:
        k = parse_ini(ini)
        assert k["scooby_high_bw_thresh"] == "4"
        assert k["scooby_enable_hbw_reward"] == "false"
        assert k["scooby_enable_per_pc_stats"] == "true"

def test_flat_differs_only_in_untimely():
    a, f = parse_ini("aware.ini"), parse_ini("flat.ini")
    assert a["scooby_reward_correct_untimely"] == "12"
    assert f["scooby_reward_correct_untimely"] == "20"
    diff = {k for k in a|f if a.get(k)!=f.get(k)}
    assert diff == {"scooby_reward_correct_untimely"}
```

- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Write the two inis and the matrix.**
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** (`feat(filltime_steer): aware/flat configs + matrix`).

---

### Task 4: rollup.py — parsing, nm mapping, per-PC/per-offset metrics

**Files:**
- Create: `codes/filltime_steer/rollup.py`
- Test: `codes/filltime_steer/tests/test_rollup_parse.py` + fixtures `codes/filltime_steer/tests/fixtures/*.out`

**Interfaces:**
- Consumes: the `.out` files in `--exp-dir` (single-victim manifest path → one block per neighbor, so names follow `<neighbor>_<config>.out` — confirm against `codes/blend_bw/rollup.py`'s actual discovery and reuse it), and `build/filltime_steer_victim.out` for `nm`.
- Produces (importable functions, so Task 5 can unit-test gates):
  - `parse_out(path) -> dict` with `reward_timely/untimely/incorrect/no_pref`, `reward_dist[offset][type]`, `predict_action[offset]`, `per_pc[ip][offset]`, `reward_high_bw_total`, `is_high_bw_fired`, `deg_dist`, `Core_0_IPC`.
  - `map_pc_offsets(nm_path, config) -> {ip: pc_index}` reusing the `blend_bw` nm-over-symbol-body approach; **raises** if two PCs resolve to a shared offset (Review Focus item 1).
  - `per_pc_long_fraction(parsed, mapping) -> {pc_index: float}` = long-offset selections / (short+long) for that PC.
  - `offset_timely_fraction(parsed, offset) -> float` from `reward_dist`.
  - `offset_incorrect_fraction(parsed, offset) -> float`.

- [ ] **Step 1: Write failing parse tests** against two hand-written fixture `.out` files (one idle-ish, one heavy-ish) asserting the parsed dicts match known values, and that a fixture with a duplicated offset mapping raises.
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement the parsing/mapping/metric functions.**
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** (`feat(filltime_steer): rollup parsing + per-PC metrics`).

---

### Task 5: rollup.py — gates A–F + D′ and the verdict table

**Files:**
- Modify: `codes/filltime_steer/rollup.py` (add gate functions + CLI `--exp-dir --attack --manifest --csv --plot`, matching `launch.sh`'s manifest invocation)
- Test: `codes/filltime_steer/tests/test_rollup_gates.py` + synthetic metric fixtures

**Interfaces:**
- Consumes: Task 4's metric functions.
- Produces: `evaluate_gates(metrics_by_run) -> {gate: (bool, detail)}` and a printed table + `rollup.csv`. Gates:
  - **A. Distance steer:** per contestable PC, long-fraction rises monotonically idle → atk_lo → atk_mid → atk_hi (tolerance param).
  - **B. Crossover:** contestable `O_short` timely-fraction falls while `O_long` timely-fraction holds, as intensity rises.
  - **C. Selectivity:** contestable PCs cross 0.5 long-fraction in `O_short` order; anchor PCs' long-fraction |Δ| ≤ ε across all intensities.
  - **D. Isolation (decisive):** under `flat` at atk_hi, contestable long-fraction unmoved vs idle.
  - **D′. No `−8` contamination:** contestable-offset incorrect-fraction ≤ ε at every intensity.
  - **E. Bandwidth-orthogonal:** `is_high_bw_fired == False` and `reward_high_bw_total == 0` in every run.
  - **F. Benign ≈ idle:** `benign` neighbor long-fractions ≈ idle.

- [ ] **Step 1: Write failing gate tests** with synthetic `metrics_by_run` fixtures: a "steering" set (passes A,B,C,D,D′,E,F); a "flat-leaks" set where contention flips via incorrect (D′ fails, and D fails) — asserts the gates *catch* it; an "overshoot" set where an anchor moves (C fails); a "bucket-live" set (E fails).
- [ ] **Step 2: Run, verify fail.**
- [ ] **Step 3: Implement `evaluate_gates` + table/CSV/plot.**
- [ ] **Step 4: Run, verify pass.**
- [ ] **Step 5: Commit** (`feat(filltime_steer): gates A–F + D′`).

---

### Task 6: Calibration run — decide steady dial vs toggle fallback

*(Experiment task — the deliverable is a measured decision, not a unit test. Requires the 2-core ChampSim `$EXE` and PIN tracer built; `LOCAL=1` is allowed.)*

**Files:**
- Modify (maybe): `codes/filltime_steer/attacker.c`, `codes/filltime_steer/matrix` (only if the decision is "toggle")

- [ ] **Step 1:** `source scripts/set_env.sh`; run a short calibration: `TRACE_INSTR=... WARMUP=... SIM=<short> LOCAL=1 ./scripts/launch.sh filltime_steer`.
- [ ] **Step 2:** From the `aware` runs, read each intensity's victim fill-timeliness proxy (global `reward_timely/(timely+untimely)` and `Core_0_IPC`) across idle → atk_lo → atk_mid → atk_hi.
- [ ] **Step 3: Decision.** If timely-fraction varies **monotonically and gradually** across the ladder → steady dial works, keep Task 2/3 as-is. If it **saturates near-binary** (idle vs all-heavy, nothing between) → swap in a `blend_bw`-style time-toggled attacker (`<on_lines> <off_iters>`), make duty the graded axis, and update `matrix` neighbors to three duties. Record the decision and the numbers in `codes/filltime_steer/ATTACK.md` (created in Task 7).
- [ ] **Step 4: Commit** whatever changed (`chore(filltime_steer): calibrate intensity axis`), or an empty-tree note if nothing changed.

---

### Task 7: Full run, victim tuning loop, final gates + ATTACK.md

*(Experiment task. Iterative tuning against the Task 5 gates; converged state is the deliverable.)*

**Files:**
- Modify: `codes/filltime_steer/config.h` (per-PC `ALU`/`STRIDE`/offsets as tuning requires, preserving the Global Constraints)
- Create: `codes/filltime_steer/ATTACK.md`, `experiments/filltime_steer/rollup.txt` (+ `rollup.csv`, plot)

- [ ] **Step 1:** Run the full experiment at the `blend_bw` budget (`TRACE_INSTR=65000000 WARMUP=10000000 SIM=50000000`, `LOCAL=1` if no Slurm): `./scripts/launch.sh filltime_steer`.
- [ ] **Step 2:** Read `experiments/filltime_steer/rollup.txt`. **Tuning loop:** if a contestable PC does not cross (margin too weak), lower its `ALU` (shrink `T_line` → raise `O*` sensitivity) or lower its `O_short`; if an anchor moves, raise its `O_short`; re-run. Keep offsets in `scooby_actions`, unique, never `1`. Document each change's rationale in `config.h` comments (as `blend_bw/config.h` does).
- [ ] **Step 3:** Confirm the final rollup: gates A,B,C,D,D′,E,F — record PASS/PARTIAL/FAIL honestly (a PARTIAL or a documented negative on the convergence/dial questions is an acceptable, reportable outcome per spec §8, not a failure to hide).
- [ ] **Step 4:** Write `ATTACK.md` (deep dive, mirroring `codes/blend_bw/ATTACK.md`): mechanism, the dual-touch necessity, the `flat.ini` control, the calibration decision, the gate table, honest scope (steers distance, not abstain; the `−8` tail stays a labeled stretch).
- [ ] **Step 5: Commit** (`feat(filltime_steer): full run, gates, ATTACK.md`).

---

### Task 8 (optional): DOSSIER entry

- [ ] Add a `filltime_steer` row to `DOSSIER.md` §0 and a §4.5 subsection, and note in §6 that this attack's channel is **orthogonal** to bandwidth (survives `high_bw_thresh=4`), so the per-core-bandwidth mitigation does not close it — the timeliness-reward classification needs its own fix. Commit (`docs: add filltime_steer to dossier`).
