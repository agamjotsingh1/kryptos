# policy_target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `policy_target`, an attack where a blind open-loop neighbor places the victim Pythia's abstain fraction `f0` on its one contestable load PC at a chosen setpoint `f0* ∈ {0.25,0.50,0.75}` via a pre-calibrated duty-cycle controller.

**Architecture:** Reuse the `blend_bw` scaffold wholesale (time-toggled duty attacker, reward-table EV-flip channel, per-PC readout). Change three things: (1) victim shrinks to two PCs — one contestable target `p≈0.31`, one high anchor `p≈0.55`; (2) `rollup.py` gains a **calibration→inversion** step (fit `f0` vs attacker `on_lines` at fixed period, numerically invert for the three setpoints) and **setpoint/L1/anchor/isolation** gates; (3) the run is two-phase — a calibration sweep that computes the verification schedules, then a multi-seed verification run.

**Tech Stack:** C workloads (PIN-traced), ChampSim + Pythia/scooby, bash launch harness (`scripts/launch.sh`), Python 3 `rollup.py` (+ `pytest` unit tests on synthetic `.out` fixtures), matplotlib.

**Spec:** `docs/superpowers/specs/2026-11-19-policy-target-design.md`

## Global Constraints

- Research-only, in-simulator. Same threat model as `DOSSIER.md`: core 0 victim, core 1 attacker, single shared DRAM channel, attacker open-loop with no victim knowledge.
- Attacker is `blend_bw/attacker.c` **verbatim** (`<on_lines> <off_iters>`). No new attacker lever.
- No ChampSim/Pythia C++ edits. Readout uses existing stats only: `scooby_bw_level_<n>`, `scooby_predict_action_<v>`, per-PC `scooby_per_pc_<ip>` (needs `scooby_enable_per_pc_stats = true`), `scooby_dyn_degree_*`/`deg≥4`, `Core_0_IPC`. First `scooby_*` block = core 0 (victim).
- Reward channel: `aware` = `scooby_enable_hbw_reward = true`; `blind` = `false`. HBW degree curve pinned **equal** to normal (`1,2,4,6`) in both (degree lever dead). Fallback gating inherited from `blend_bw`.
- **Fixed toggle period 80** (`on + off = 80`), as `blend_bw`; the controller sweeps duty along this 1-parameter family so inversion is 1-D (`f0 → on_lines`).
- Contestable `p` must stay above the normal break-even **0.143** (else blind contention flips it and isolation breaks).
- Long run `SIM = 50_000_000` for convergence (10M under-settles — `blend_bw` fact). Spike may run short.
- Verification setpoints `f0* = {0.25, 0.50, 0.75}`; setpoint tolerance `|mean(f0) − f0*| ≤ 0.10` (or ~2σ if the spike shows cross-seed σ ≥ 0.10). ≥ 3 seeds per verification duty.
- `p*(d) = (4+8d)/(28+6d)`, inverse `d*(p*) = (28p*−4)/(8−6p*)` — explanatory backbone only; the operational map is the fitted `f0 → on_lines`.
- Honesty rule (spec §6 gate 3): L1 is over the **full 15-bucket** aggregate histogram, never a 2-bucket collapse; if the full-histogram conversion cannot pass honestly it is **reported as a confirmed structural limit, not redefined to pass**. The setpoint headline (gate 2) stands independently.

## Review Focus

- **Blind-config contention floor at the contestable PC.** If `p≈0.31` abstains under `blind` (reward table off) at high duty, isolation is void. Pinned by Task 5 isolation gate + Task 4 spike baseline (blind `f0 ≈ 0` at all duties).
- **Anchor creep at high duty.** The real `blend_bw` run shows `p=0.45` reaching `f0=0.43` by `d≈0.74`; a verification setpoint of 0.75 may need high duty. Anchor `p=0.55` + Task 5 anchor-holds gate re-checked **at the actual verification duties**, not nominal ones.
- **`f0` snapping 0↔1 (no reachable intermediate).** If the ramp is a step, `{0.25,0.75}` are unreachable. Task 4 spike gate 0 tests this first; remedy = tune `p`/ALU/period before any full run.
- **L1 gate degenerating to a restatement of the setpoint gate.** A 2-bucket collapse makes gate 3 trivial. Task 3 unit test asserts the target vector is full-width (mass only on abstain+signature) and that a realized histogram with noise-bucket leakage yields L1 strictly greater than `2·|f0−f0*|`.
- **Cross-seed variance exceeding tolerance.** Absolute `f0` is what `blend_bw` called unreliable; Task 5 aggregates ≥3 seeds and the gate uses the mean + reported spread, widening tolerance to ~2σ if needed rather than asserting a false ±0.10.

---

### Task 1: Scaffold `codes/policy_target/` with the two-PC victim

**Files:**
- Create: `codes/policy_target/config.h` (from `codes/blend_bw/config.h`)
- Create: `codes/policy_target/victim.c` (from `codes/blend_bw/victim.c`)
- Create: `codes/policy_target/attacker.c` (copy `codes/blend_bw/attacker.c` verbatim)
- Create: `codes/policy_target/aware.ini`, `blind.ini` (from `codes/blend_bw/aware_blend.ini`, `blind_blend.ini`)
- Create: `codes/policy_target/matrix` (calibration phase)
- Test: manual build+trace smoke check (below)

**Interfaces:**
- Produces: victim binary `build/policy_target_victim.out` exporting two NOINLINE load sites `blend_pc_0` (contestable) and `blend_pc_1` (anchor), mappable by `nm -n`; attacker trace taking `<on_lines> <off_iters>`.

- [ ] **Step 1: Copy the four source/config files** from `codes/blend_bw/` into `codes/policy_target/`, renaming `aware_blend.ini → aware.ini`, `blind_blend.ini → blind.ini`. Leave `attacker.c` byte-identical.

- [ ] **Step 2: Edit `config.h`** — set `VICTIM_N_PC 2`, `VICTIM_PC_P { 0.31, 0.55 }`, `VICTIM_PC_SIG { 4, 11 }`; keep `VICTIM_NOISE {7,8,9,13,14}`, `VICTIM_N_NOISE 5`, `VICTIM_REGION_LINES_PER_PC (1<<14)`, `VICTIM_ALU_ITERS 16`, `ATK_REGION_HEAVY (1<<26)`. Replace the header comment's staircase prose with the two-PC setpoint rationale (contestable `p=0.31` sweeps `f0` across the reachable ramp; anchor `p=0.55` holds).

- [ ] **Step 3: Edit `victim.c`** — reduce the `DEFINE_PC(j)`/`blend_pc_j()` instantiations and the round-robin loop in `main` to PCs 0 and 1 only. Keep the LCG streams, disjoint regions, ALU throttle, `__champsim_start_trace`, and `argv[1]` seed. (The seed arg is load-bearing for Task 5 multi-seed.)

- [ ] **Step 4: Edit `aware.ini`/`blind.ini`** — confirm `scooby_enable_per_pc_stats = true`, HBW degree curve `= 1,2,4,6`, `aware` has `scooby_enable_hbw_reward = true` and `blind` has `false`; otherwise identical. Copy the fallback-gating lines from the `blend_bw` originals unchanged.

- [ ] **Step 5: Write `matrix`** (calibration phase): one victim line `victim victim.c`, and nine calibration neighbors at **fixed period 80**:

```
victim   victim.c
neighbor cal_on08  attacker.c   8  72
neighbor cal_on16  attacker.c  16  64
neighbor cal_on24  attacker.c  24  56
neighbor cal_on32  attacker.c  32  48
neighbor cal_on40  attacker.c  40  40
neighbor cal_on48  attacker.c  48  32
neighbor cal_on56  attacker.c  56  24
neighbor cal_on64  attacker.c  64  16
neighbor cal_on72  attacker.c  72   8
config   aware   aware.ini
config   blind   blind.ini
```

- [ ] **Step 6: Smoke-test build + trace** (short):

Run: `source scripts/set_env.sh && TRACE_INSTR=2000000 WARMUP=500000 SIM=1000000 ./scripts/launch.sh policy_target`
Expected: traces generate, ChampSim runs complete, `nm -n build/policy_target_victim.out | grep blend_pc_` shows exactly `blend_pc_0` and `blend_pc_1`. (rollup.py will error until Task 3 — that is fine here; the gate is "builds, traces, runs, two PCs present.")

- [ ] **Step 7: Commit**

```bash
git add codes/policy_target
git commit -m "feat(policy_target): scaffold two-PC victim + calibration matrix"
```

---

### Task 2: `rollup.py` — parse + calibration fit + inversion

**Files:**
- Create: `codes/policy_target/rollup.py` (from `codes/blend_bw/rollup.py`)
- Create: `codes/policy_target/test_rollup.py`

**Interfaces:**
- Consumes: `.out` files named `<neighbor>_<config>.out` (calibration) and `<victim>_<neighbor>_<config>.out` (verification, Task 5).
- Produces:
  - `parse_run(path) -> dict` with keys `bw` (level→count), `per_pc` (ip→{action:count}), `agg` (action→count, from `scooby_predict_action_*`), `deg_ge4` (float).
  - `fit_invert(cal_points: list[tuple[int,float]], targets: list[float]) -> dict[float,int]` — `cal_points` is `(on_lines, f0_contestable)`; returns `{target_f0: on_lines}` by monotone interpolation of `on_lines` as a function of `f0`.

- [ ] **Step 1: Write failing tests** in `test_rollup.py`:

```python
def test_parse_run_reads_agg_and_perpc(tmp_path):
    out = tmp_path/"cal_on40_aware.out"
    out.write_text(SYNTH_OUT)              # fixture: bw_level_*, per_pc_*, predict_action_* lines
    r = parse_run(str(out))
    assert r["agg"][0] == 84 and r["agg"][4] == 16      # abstain + signature counts
    assert abs(pc_f0(next(iter(r["per_pc"].values()))) - 0.5) < 1e-9

def test_fit_invert_monotone_interpolation():
    pts = [(8,0.12),(24,0.30),(40,0.52),(56,0.70),(72,0.84)]   # f0 rises with on
    got = fit_invert(pts, [0.25,0.50,0.75])
    assert 16 < got[0.25] < 32 and 32 < got[0.50] < 48 and 56 < got[0.75] < 72
    assert got[0.25] < got[0.50] < got[0.75]                   # order preserved
```

(`SYNTH_OUT` is a module-level string of ~10 representative `.out` lines, including one `scooby_per_pc_<ip>` line with counts summing so `f0=0.5`, and `scooby_predict_action_0 84` / `scooby_predict_action_4 16`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest codes/policy_target/test_rollup.py -v`
Expected: FAIL (`parse_run` missing `agg`; `fit_invert` not defined).

- [ ] **Step 3: Implement `parse_run` and `fit_invert`** in `rollup.py`. Reuse `blend_bw`'s `RE_BW`, `RE_ACT`, `RE_PERPC`, `pc_f0`, `pc_symbols`, `map_pcs`. Extend `parse_run` to return the aggregate action histogram `agg` (from `RE_ACT`) and `deg_ge4`. Implement `fit_invert` with a monotone 1-D interpolant of `on_lines(f0)` (sort `cal_points` by `f0`, enforce monotonicity, `numpy.interp`), rounding the result to the nearest integer `on_lines`; clamp targets outside the sampled `f0` range and record the clamp in the return.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest codes/policy_target/test_rollup.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add codes/policy_target/rollup.py codes/policy_target/test_rollup.py
git commit -m "feat(policy_target): rollup parse + calibration inversion"
```

---

### Task 3: `rollup.py` — gates (setpoint, full-histogram L1, anchor, isolation, degree, monotone)

**Files:**
- Modify: `codes/policy_target/rollup.py`
- Modify: `codes/policy_target/test_rollup.py`

**Interfaces:**
- Consumes: `parse_run`, `pc_f0`, `fit_invert` (Task 2).
- Produces:
  - `build_target_dist(f0star: float, signature: int) -> dict[int,float]` — the clean named target: `{0: f0star, signature: 1-f0star}`, all other actions 0.
  - `l1_full(agg_counts: dict[int,float], target: dict[int,float]) -> float` — L1 over the union of action buckets, both normalized to sum 1.
  - `gates(...) -> list[tuple[str,bool,str]]` — (name, passed, detail) for the six gates.

- [ ] **Step 1: Write failing tests**:

```python
def test_l1_full_is_not_degenerate_under_noise_leak():
    # realized abstains 0.50 (matches f0*), but gamble mass leaks to noise buckets 7,8
    agg = {0:50, 4:30, 7:12, 8:8}
    tgt = build_target_dist(0.50, signature=4)          # {0:0.5, 4:0.5}
    l1 = l1_full(agg, tgt)
    assert l1 > 2*abs(0.50-0.50) + 1e-6                 # strictly exceeds the 2-bucket collapse
    assert abs(l1 - (abs(0.5-0.5)+abs(0.30-0.5)+0.12+0.08)) < 1e-9

def test_setpoint_gate_uses_cross_seed_mean():
    passed, detail = setpoint_gate({0.50:[0.47,0.52,0.55]}, tol=0.10)[0.50]
    assert passed                                       # mean 0.513 within 0.10

def test_anchor_gate_checks_verification_duties_only():
    assert anchor_gate({ "on40":0.05, "on64":0.08 }, thresh=0.5) is True
    assert anchor_gate({ "on40":0.05, "on64":0.60 }, thresh=0.5) is False

def test_isolation_gate_flat_under_blind():
    assert isolation_gate(blind_f0_by_duty={"on40":0.03,"on64":0.06}, thresh=0.15) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest codes/policy_target/test_rollup.py -v`
Expected: FAIL (functions undefined).

- [ ] **Step 3: Implement `build_target_dist`, `l1_full`, and the gate functions**, plus a `gates(...)` aggregator producing:
  1. **monotone** — contestable `f0` non-decreasing across calibration `on_lines`.
  2. **setpoint** — for each `f0*`, `|mean_seeds(f0) − f0*| ≤ tol` (tol from Global Constraints / Task 5 spread).
  3. **l1_full** — at the mid setpoint, `l1_full(realized_agg, build_target_dist(0.5, sig)) < 0.30`; the detail string also prints `2·|f0−f0*|` so a degenerate pass is visible. Mark PASS/FAIL **and** annotate "structural-limit" if `f0` is on target but L1 fails (spec §6 gate 3 honesty rule).
  4. **anchor** — anchor `f0 < 0.5` at **every verification duty**.
  5. **isolation** — blind contestable `f0 < 0.15` at every verification duty, same `bw3` as aware.
  6. **degree** — `deg_ge4` spread across duties `< 0.05`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest codes/policy_target/test_rollup.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `main()`** — adapt `blend_bw`'s `main`/`argparse` to: read all `.out`, map PCs via `nm` on `--victim-bin`, split neighbors into `cal_*` vs verification, run `fit_invert` on the aware calibration points, print the computed verification schedules, and when verification `.out` are present emit the gate table + `rollup.txt`, `rollup.csv`, and an `f0`-vs-`on_lines` plot with the three setpoints and their inverted duties marked. Add `--emit-matrix` to print neighbor lines for the computed verification duties (Task 5 consumes this).

- [ ] **Step 5b: Add Review-Focus regression** — keep `test_l1_full_is_not_degenerate_under_noise_leak` (the degeneracy guard) and add `test_fit_invert_clamps_out_of_range_target` asserting an out-of-range `f0*` returns a clamped `on` flagged in the result.

- [ ] **Step 6: Commit**

```bash
git add codes/policy_target/rollup.py codes/policy_target/test_rollup.py
git commit -m "feat(policy_target): setpoint/L1/anchor/isolation gates + main"
```

---

### Task 4: Verification spike — confirm a reachable intermediate ramp (gate 0)

**Files:**
- Modify (if spike demands): `codes/policy_target/config.h` (victim `p`/ALU), `codes/policy_target/matrix`
- Create: `experiments/policy_target/spike-notes.md`

**Interfaces:**
- Consumes: Task 1 scaffold, Task 2–3 rollup.
- Produces: a tuned victim whose contestable `f0(on_lines)` is a smooth monotone ramp bracketing `{0.25,0.50,0.75}`, and a clean blind baseline.

- [ ] **Step 1: Run the calibration matrix at spike length**

Run: `source scripts/set_env.sh && TRACE_INSTR=65000000 WARMUP=10000000 SIM=10000000 ./scripts/launch.sh policy_target`
(10M is a fast settle-check; absolute `f0` will read low but the ramp shape and baselines are the spike's questions.)

- [ ] **Step 2: Inspect the spike gates from `rollup.txt` / the `.out` files** and record in `spike-notes.md`:
  - **(0, gating) ramp:** aware contestable `f0` rises monotonically across `on_lines` and takes intermediate values away from `{0,1}` (a real setpoint space). If it snaps, **remedy** (Step 3) before proceeding.
  - **(a) blind baseline:** blind contestable `f0 ≈ 0` at all duties (isolation floor clean).
  - **(b) anchor:** anchor `f0 ≈ 0` at all duties.
  - **(c) bracketing:** the reachable `f0` range spans below 0.25 and above 0.75 across the nine duties.

- [ ] **Step 3: If any spike gate fails, tune and re-run Step 1.** Remedies (spec §6): snapping → move `p` toward the reachable mid-band (0.30–0.32) / lengthen period beyond 80 / raise `VICTIM_ALU_ITERS`; range not bracketing `{0.25,0.75}` → shift `p`; blind floor nonzero → raise contestable `p` slightly (stay >0.143) ; anchor creeps → raise anchor `p`. Re-run until (0),(a),(b),(c) hold. Record the final `(p_contestable, p_anchor, ALU, period)`.

- [ ] **Step 4: Commit** the tuned config + spike notes

```bash
git add codes/policy_target/config.h codes/policy_target/matrix experiments/policy_target/spike-notes.md
git commit -m "spike(policy_target): tune victim to a reachable f0 ramp"
```

---

### Task 5: Full calibration + multi-seed verification run (50M)

**Files:**
- Modify: `codes/policy_target/matrix` (append verification phase)
- Create: `experiments/policy_target/{rollup.txt, rollup.csv, f0_vs_duty.png}` (produced by the run)

**Interfaces:**
- Consumes: tuned scaffold (Task 4), rollup gates (Task 3).
- Produces: the evaluated attack result (all six gates printed, PASS/FAIL honest).

- [ ] **Step 1: Full calibration run**

Run: `source scripts/set_env.sh && TRACE_INSTR=65000000 WARMUP=10000000 SIM=50000000 ./scripts/launch.sh policy_target`
Then: `python codes/policy_target/rollup.py --victim-bin build/policy_target_victim.out --emit-matrix`
Expected: prints three computed verification schedules `(on_lines, off_lines=80−on)` for `f0* ∈ {0.25,0.50,0.75}`.

- [ ] **Step 2: Append the verification phase to `matrix`** — three verification neighbors (the computed duties, named `ver_f25/ver_f50/ver_f75`) and **three seeded victims** so the harness multi-victim sweep runs each duty × seed:

```
victim   v_s0  victim.c  0
victim   v_s1  victim.c  1
victim   v_s2  victim.c  2
neighbor ver_f25  attacker.c  <on25>  <80-on25>
neighbor ver_f50  attacker.c  <on50>  <80-on50>
neighbor ver_f75  attacker.c  <on75>  <80-on75>
```

(Keep the nine `cal_*` neighbors so calibration and verification are one coherent manifest; with ≥2 victim lines the harness names outputs `<victim>_<neighbor>_<config>.out`, which rollup aggregates by neighbor across seeds.)

- [ ] **Step 3: Full verification run** (same env as Step 1), then evaluate:

Run: `python codes/policy_target/rollup.py --victim-bin build/policy_target_victim.out`
Expected: `rollup.txt` prints the six-gate table. Record cross-seed σ(f0); if σ ≥ 0.10, set the setpoint tolerance to ~2σ in the gate and note it (Global Constraints).

- [ ] **Step 4: Verify the headline and honesty gates**
  - Gate 2 (setpoint) PASS for all three setpoints at the recorded tolerance — the headline.
  - Gate 3 (L1) reported like-for-like; if it fails, the detail line reads "structural-limit: f0 on target, full-histogram shape not controllable" — **not** a redefinition. Either outcome is acceptable to ship (spec §1: conditional claim); a degenerate pass is not.
  - Gates 1,4,5,6 PASS. If isolation (5) fails (blind flips), stop — the result is void until the contestable `p` is lifted off the floor (back to Task 4).

- [ ] **Step 5: Commit** the experiment artifacts + final matrix

```bash
git add codes/policy_target/matrix experiments/policy_target/rollup.txt experiments/policy_target/rollup.csv experiments/policy_target/f0_vs_duty.png
git commit -m "run(policy_target): 50M calibration + multi-seed verification, gates"
```

---

### Task 6: `ATTACK.md` + `DOSSIER.md` write-up

**Files:**
- Create: `codes/policy_target/ATTACK.md`
- Modify: `DOSSIER.md`

**Interfaces:**
- Consumes: the Task 5 result tables.

- [ ] **Step 1: Write `codes/policy_target/ATTACK.md`** in the house style of `codes/blend_bw/ATTACK.md`, **leading with the honest ceiling** (spec §3): single scalar ⇒ monotone cut ⇒ setpoint-on-one-PC only, non-nested unreachable; offline calibration required, "open-loop" = no deploy-time observation. Then: the controller (`f0* → on_lines` fitted inverse, `d*(p*)` as backbone), the two-PC victim with the real-data operating-point rationale, the calibration→verification method, and the six-gate results table with the actual numbers from Task 5. State the L1/policy_bw-conversion outcome as it actually landed (PASS or reported structural limit).

- [ ] **Step 2: Update `DOSSIER.md`** — add a `policy_target` row to the §0 executive-summary table (what it steers: "victim's abstain fraction to a chosen setpoint"; lever: "pre-calibrated duty controller"; status from Task 5); add a short §4.5 section; and **correct the stale `blend_bw` text** in §4.4/§5 that says the contestable PCs "flip together" — the current `blend_bw` code resolves a +2 staircase, which `policy_target` extends into a named-setpoint controller.

- [ ] **Step 3: Commit**

```bash
git add codes/policy_target/ATTACK.md DOSSIER.md
git commit -m "docs(policy_target): ATTACK.md deep-dive + DOSSIER row and blend_bw correction"
```

---

## Self-Review

**1. Spec coverage.** §1 intent (controller, conditional policy_bw conversion) → Tasks 2,3,5,6. §2 mechanism + fitted map → Task 2 (`fit_invert`), §2 backbone noted in Task 6. §3 goals (setpoint hit, L1 test, isolation, anchor/specificity) → Task 3 gates, Task 5. §3 honest ceilings → Task 6 Step 1, Global Constraints. §4 victim (`p=0.31`/`0.55`, real-data operating point) → Task 1 Steps 2–3, Task 4 tuning. §5 attacker verbatim → Task 1 Step 1, Global Constraints. §6 how (files, matrix, rollup, gates 0–6, spike, 50M) → Tasks 1–5. §7 builder-left (thresholds, fit family, duties, run length) → resolved in Tasks 2–5. No gaps.

**2. Step scan.** Each code step gives a signature or an exact file+value; each test step gives named assertions with spec values; each run step gives a command + expected output. Tuning/threshold decisions live in the spike (Task 4) and Task 5, not as "TBD" lines.

**3. Type consistency.** `parse_run` returns `agg`/`per_pc`/`bw`/`deg_ge4` (Task 2) — consumed under those keys in Task 3 gates and Task 5. `fit_invert(cal_points, targets) -> {f0:on}` (Task 2) consumed in Task 3 tests and Task 5 Step 1. `build_target_dist(f0star, signature)`/`l1_full(agg, target)` consistent between Task 3 definition and its tests. PC names `blend_pc_0/1` consistent Task 1 ↔ rollup `nm` mapping.

**4. Review Focus.** Five listed; each pinned to a task's test/gate (blind floor → Task 5 gate 5 + Task 4(a); anchor creep → Task 3 `anchor_gate` test + Task 5 gate 4 at verification duties; snapping → Task 4 gate 0; L1 degeneracy → Task 3 `test_l1_full_is_not_degenerate_under_noise_leak`; variance → Task 5 Step 3 + `setpoint_gate` cross-seed test).

**5. Proportion.** Plan is close to the spec's length; code blocks are test assertions, the one non-obvious target construction, and matrix literals — not function bodies. The implementer writes `parse_run`, `fit_invert`, the gates, and the C edits from signatures + the reused `blend_bw` scaffold.
