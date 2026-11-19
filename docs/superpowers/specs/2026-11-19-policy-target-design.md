# Design — `policy_target`: setpoint abstain-fraction control of Pythia

**Status:** design, awaiting approval. Research-only, inside ChampSim (ChampSim + Pythia/scooby),
same threat model as the four attacks in `DOSSIER.md`. Core 0 = victim, core 1 = attacker,
single shared DRAM channel, open-loop attacker with no victim knowledge.
**Date:** 2026-11-19.

---

## 1. Intent and the why

The user asked for a **new, targeted** steering attack that makes "a specific policy chosen,"
with the cleverness on the **attacker side** and no victim knowledge. This design answers that
within the honest limit of the channel (§3).

`blend_bw` proved that a time-toggled neighbor turns the binary bandwidth switch into a
**continuous dial**: the EV break-even `p*(d) = (4+8d)/(28+6d)` moves smoothly from 0.143 to
0.353 as the duty fraction `d` rises, and the victim's abstain fraction follows. But `blend_bw`
only **demonstrates the dial** — it hand-picks three duties, trial-calibrates them per victim,
and then **sweeps and observes** which PCs flip. Its gates reward a *monotone staircase*, not a
hit on a *named* outcome. It never inverts, and it never aims.

`policy_target` closes exactly that gap. The attacker becomes a **controller**: you name the
policy you want the victim to adopt — a target abstain fraction `f0*` on its contestable load —
and a **pre-characterized duty map** emits the traffic schedule that lands it, open-loop, with
no observation of the victim at deploy time. The new claim is **aim**, not sweep.

The **robust headline** is this setpoint hit: `policy_bw`'s raw lever was near-binary (even a
light neighbor nearly saturates the bucket, so only `f0 ≈ 0` or `f0 ≈ 0.81` were reachable),
whereas `policy_target`'s continuous calibrated dial places `f0` at **intermediate** setpoints
`{0.25, 0.50, 0.75}` on target.

A **second, conditional** claim is whether this also **converts `policy_bw`'s failed exact-shape
gate (L1 = 0.371) to a PASS** — measured like-for-like on the same full action histogram (§6 gate
3). This rides on whether a single global scalar can shape the *whole* distribution, not just the
abstain fraction; the spike decides it, and if it cannot pass honestly it is **reported as a
confirmed structural limit, not redefined to pass** (§6 gate 3). The setpoint headline does not
depend on it.

Same root cause (the global un-isolated DRAM-bandwidth bucket), same §6 mitigation. New
*capability*: setpoint control of the victim's policy, not just a push toward abstain.

## 2. The mechanism (reused, verified)

Unchanged from `blend_bw` — the reward-table EV flip under a time-averaged bandwidth signal:

- The shared bucket (`src/main.cc:964-978`) is a global aggregate over all cores; the attacker
  toggles it ON (stream 64 MiB, bucket → 3) / OFF (pure ALU, EWMA decays) on a fixed schedule.
- With `scooby_enable_hbw_reward = true`, each epoch's reward table is chosen by `is_high_bw()`.
  A toggle faster than SARSA's settling time makes the victim learn against the **duty-weighted
  average** of the normal and HBW reward tables (`prefetcher/scooby.cc:722`).
- The break-even is then continuous in the blend fraction `d`:

```
p*(d) = (4 + 8d) / (28 + 6d)            # 0.143 at d=0, 0.353 at d=1   (blend_bw, verified)
```

**The new step — closed-form inversion.** Solving for `d`:

```
d*(p*) = (28·p* − 4) / (8 − 6·p*)       # exact inverse; p*=0.143→d=0, p*=0.353→d=1
```

So a target break-even `p*` maps in closed form to a required blend `d*`. But two of the links in
the chain `f0* → p* → d* → schedule` are **empirical, not closed form**, and the design treats the
analytic `p*(d)/d*(p*)` only as the *explanation* of why a monotone dial exists — the
**operational** map is fitted (builder-check Q2, Q4):

- `f0* → d`: near the break-even the blended `Q(gamble) ≈ Q(abstain)`, so under ε-greedy
  exploration the single-PC policy is **stochastic** and `f0` ramps smoothly (this soft transition
  is `blend_bw` gate B). The ramp is offset and steeper than the analytic crossing (real data,
  §4), so its shape is **characterized once offline** and inverted numerically.
- `d → schedule (on_lines, off_iters)`: `d` is the **measured** `bw3`, not a settable quantity —
  `blend_bw`'s matrix shows nominal duty `12/68 = 0.15` realizes `d = 0.238`, i.e. schedule→`d` is
  nonlinear and victim-dependent. This is **also** fitted from the calibration sweep.

To avoid the two-stage error stack, the operational controller fits **`f0` directly against the
attacker schedule `(on_lines, off_iters)`** (with realized `d`=`bw3` reported alongside for
interpretability). The closed-form `d*(p*)` stays in the doc as the mechanism's backbone, not as
the lookup. The controller is: target `f0*` → (fitted inverse) → schedule, calibrated **once**,
emitted **open-loop** at deploy.

## 3. Goals / non-goals / anti-goals / honest ceiling

**Goals**
- A single contestable victim load PC whose **abstain fraction `f0` is placed at a chosen
  setpoint** `f0*` by a duty computed from the offline map — open-loop, no per-run victim
  observation.
- Hit three setpoints `{0.25, 0.50, 0.75}` within tolerance; monotone and ordered.
- **Test** whether this also converts `policy_bw`'s failed exact-shape gate (full-histogram
  L1 = 0.371) to a PASS at the mid setpoint — like-for-like, honestly, demoted to a reported
  negative if the scalar cannot shape the full histogram (§6 gate 3).
- **Decisive isolation:** a blind control with `enable_hbw_reward = false` at the same duties
  sees the same `bw3` and does **not** move `f0`.
- **Specificity:** a high-`p` anchor PC never abstains at any target duty — proves the controller
  aims at the contestable load, not a blanket slowdown.

**Non-goals**
- No per-PC differentiated staircase (`pband_bw`/`blend_bw` already do that).
- No new Pythia mechanism — this is the reward channel, reused. No C++ edits.
- No claim of zero-calibration transfer across victims (that was the "ambitious" option, declined
  — the offline characterization is explicitly part of the method).

**Anti-goals (failure even if it "runs")**
- `f0` snaps 0↔1 with no reachable intermediate plateau ⇒ no setpoint to hit ⇒ the attack
  degrades to `policy_bw`. The verification spike (§6, gate 0) tests this **first**.
- A setpoint "hit" that also appears under `enable_hbw_reward = false` ⇒ it was contention, not
  the reward signal. Isolation must separate them.
- The anchor also moves ⇒ not specific; blanket effect.

**Honest ceiling (stated up front, documented in `ATTACK.md`).**
- One global scalar ⇒ the cut-point is **monotone in `p`** ⇒ only a single contestable PC's
  fraction is being placed here; a *non-nested* multi-PC target is unreachable by this channel
  (would need per-PC knowledge the attacker lacks). Setpoint-only is the scope the user picked.
- The `f0*→d*` map is characterized offline on the same victim class; "open-loop" means **no
  observation at deploy**, not zero prior calibration. The duty is computed, never tuned against
  the live victim.

## 4. The decisive victim constraint

Reuse `blend_bw`'s single-region-per-PC machinery, but **two PCs only**. The operating point is
fixed **from the realized ramp, not the analytic break-even** (builder-check Q1): the real
`blend_bw` 50M run on the identical scaffold measured `f0(d)` for several `p`, and the ramp is
offset and steep relative to the analytic `p*(d)` crossing. Measured on that run:

| `p` | f0 @ d≈0.24 | f0 @ d≈0.49 | f0 @ d≈0.74 | verdict for 3 setpoints |
|-----|:-----------:|:-----------:|:-----------:|-------------------------|
| 0.24 | 0.43 | 0.77 | 0.83 | **bad** — 0.25 below floor, 0.50 inside a 0.43→0.77 jump |
| 0.30 | 0.20 | 0.62 | 0.82 | **good** — gentle monotone ramp through 0.25/0.50/0.75 |
| 0.32 | 0.14 | 0.58 | 0.81 | **good** |

So `p=0.24` (my first draft) is the wrong operating point; the target PC is set to **`p≈0.31`**,
where the realized ramp passes through all three setpoints with margin. The analytic crossing
`d≈0.415` is **not** where the realized `f0=0.5` sits (~`d≈0.42` on the measured curve by luck for
`p≈0.31`, but the point stands: duties are chosen from the fit, §6, not the formula).

| PC | (p, signature) | role | grounding |
|----|----------------|------|-----------|
| 0  | (**0.31**, 4)  | **contestable target** | realized `f0` sweeps ~0.17 → ~0.82 across reachable `d`; brackets all three setpoints |
| 1  | (**0.55**, 11) | **anchor** | raised from 0.45: the real run shows `p=0.45` reaches `f0=0.43` by `d≈0.74` (near flipping), so a stronger anchor is needed if the target needs high duty to reach `f0*=0.75`. `p=0.55` stays flat across the reachable band |

- `p=0.31` is above the **normal** break-even 0.143, so under the blind/normal-reward table the
  target PC **gambles** (`f0 ≈ 0`) — the isolation control is clean and contention alone cannot
  flip it.
- Region geometry copies `blend_bw` (disjoint ~1 MiB region per PC, L2-missing, one ALU burst per
  load). Noise deltas from the non-action set `{7,8,9,13,14}`; signature deltas `{4, 11}` are
  members of `scooby_actions`. Exact `p` (0.30–0.32), anchor `p`, and ALU-iter count are fixed in
  the spike (§6) against the realized ramp, and the anchor-holds gate (4) is re-checked at the
  actual verification duties.

## 5. Approaches considered

**(A1) Single contestable PC + offline `f0(d)` characterization, chosen.** Sweep duty once, fit
the monotone `f0(d)` ramp, invert to pick duties for `{0.25,0.50,0.75}`, verify on fresh runs.
Headline = setpoint accuracy + the `policy_bw` L1 gate passing. **Why chosen:** it is the minimal,
cleanest realization of "name a policy, hit it," it reuses the entire `blend_bw` scaffold, and it
turns a documented PARTIAL into a PASS — a concrete, checkable new result.

**(A2) Analytic-only (no characterization): assume `f0` steps at `p*(d)=p`.** Rejected: only
reaches `f0≈0.5` reliably; the `0.25` and `0.75` setpoints depend on the empirical ramp width,
so an offline fit is required. Keeping A2 would overclaim.

**(A3) Multi-PC named-set controller (the declined "Both" option).** Out of scope by the user's
choice; noted as the natural follow-on.

**Attacker: reuse `blend_bw/attacker.c` verbatim** (toggle `<on_lines> <off_iters>`). The only
lever is DRAM read rate toggled on a fixed schedule. Add nothing.

## 6. The how, as decided

**Victim** (`victim.c`): copy `blend_bw/victim.c`, reduce to `VICTIM_N_PC = 2` (PC0 contestable
`p=0.24 sig=4`, PC1 anchor `p=0.45 sig=11`), keep the per-PC NOINLINE load sites, LCG streams,
disjoint 1 MiB regions, ALU throttle, and the `nm`-based IP→PC mapping. `config.h` updated for the
new PC table and documented.

**Attacker** (`attacker.c`) + toggle schedule: copied from `blend_bw` unchanged.

**`aware.ini`** (the attack): copy `blend_bw/aware_blend.ini` — `scooby_enable_hbw_reward = true`,
the HBW degree curve pinned **equal** to normal (`1,2,4,6`, degree lever dead), fallback gating
held as `blend_bw` set it. `scooby_enable_per_pc_stats = true` (read-only per-PC counter).

**`blind.ini`** (isolation): identical except `scooby_enable_hbw_reward = false`.

**`matrix`**: victim × configs {aware, blind} × duties, split into:
- **Calibration duties** (≥ 6, spanning `d≈0.1 … 0.85`) — used once to fit `f0` vs schedule.
- **Verification duties** — the three `(on,off)` schedules the controller computes for
  `f0* ∈ {0.25,0.50,0.75}` from the fit; **interpolated, not identical to calibration points**, so
  the hit is a genuine open-loop prediction, not a lookup.
- **Replicate seeds (builder-check Q3).** `blend_bw` trusted only the staircase *order* and called
  absolute `f0` unreliable; `policy_target`'s claim is *absolute* `f0` within ±0.10, so run-to-run
  variance must be measured, not assumed. Each **verification** duty runs with **≥ 3 seeds**
  (victim `argv[1]`); the gate uses the mean and reports the spread. The spike (§6) sets the final
  tolerance from the measured spread: if cross-seed σ(f0) ≥ 0.10 the tolerance widens to ~2σ and
  the doc says so (an honest widen beats a false ±0.10). Calibration duties stay single-seed.

**`rollup.py`**: adapt `blend_bw/rollup.py`. Read per-PC `f0` for PC0 (contestable) and PC1
(anchor), `bw3` as realized `d`, the aggregate action distribution, and `deg≥4`. Fit `f0(d)`
(monotone, e.g. isotonic or logistic), report the inversion, and compute per-setpoint error.
Gates (final numeric thresholds set from the verification run; numbers always printed):

0. **(GATING, spike) reachable intermediate plateau:** `f0(d)` is a smooth monotone ramp that
   takes stable values away from `{0,1}` across the duty sweep — a real setpoint space exists. If
   it snaps, tune `p`/ALU/period before proceeding.
1. **Monotone dial:** PC0 `f0` rises monotonically with realized `d`.
2. **Setpoint accuracy (headline):** for each `f0* ∈ {0.25,0.50,0.75}`, the computed duty lands
   the cross-seed mean realized `f0` within tolerance (target `|mean(f0) − f0*| ≤ 0.10`, or ~2σ if
   the spike shows larger variance — Q3).
3. **Exact-shape L1 (the `policy_bw` gate, converted — like-for-like, builder-check Q2):** L1 is
   computed over the **same full aggregate `scooby_predict_action_*` 15-bucket histogram** that
   `policy_bw` used (L1 = 0.371 there), **not** a 2-bucket collapse. A 2-bucket collapse would
   degenerate to `2·|f0−f0*|` — a restatement of gate 2, trivially passed, and **not** a rebuttal
   of `policy_bw`'s full-histogram miss; that is explicitly disallowed. The named target is the
   full distribution the setpoint implies: `abstain = f0*`, the signature action `= (1−f0*)·p`
   expected-hit mass, the remainder spread over the noise/off-by-one buckets as the victim's own
   stream dictates (rollup derives it from the victim's `(p, signature, noise)`, not hand-set).
   PASS = L1 `< 0.30` at the mid setpoint. **If the spike shows this cannot pass honestly**
   (the single global scalar genuinely cannot shape the full histogram), the conversion claim is
   **demoted from headline to a reported negative** — "the setpoint on `f0` is hit, but the full
   15-bucket shape is not controllable, confirming `policy_bw`'s structural limit" — rather than
   redefining the gate to pass. (Flagged to the user as a headline-affecting call.)
4. **Anchor holds:** PC1 (`p=0.45`) never abstains at any verification duty.
5. **Isolation (decisive):** blind at the same duties → same `bw3` → PC0 `f0 ≈ 0` (unmoved).
6. **Degree held:** `deg≥4` ≈ constant across duties; the movement is reward-shaping alone.

**`ATTACK.md`**: per-attack deep dive in the house style, leading with the honest ceiling (§3).
`DOSSIER.md` gains a `policy_target` row and a short section once results land, and the stale
`blend_bw` "flip together" text is corrected to the staircase the current code actually runs.

**Run length:** reuse `blend_bw`'s long run (`SIM=50M`) — the blended policy must converge and the
intermediate `f0` plateaus must be stable; `blend_bw` under-settled at 10M, so 50M is the default
here. Confirmed/adjusted by the spike.

**Verification spike (first step of the plan).** A short `./scripts/launch.sh policy_target` run to
confirm from the `.out`: (0) `f0(d)` ramp is smooth with reachable intermediate plateaus (the
gating anti-goal); (a) blind PC0 `f0 ≈ 0` (isolation baseline); (b) anchor never abstains; (c) the
reachable `d` range brackets PC0's crossing on both sides. Remedies: snapping ⇒ tune `p` toward the
reachable mid-band / lengthen period / adjust ALU; crossing not bracketed ⇒ shift `p`.

## 7. Left to the builder

- Final numeric gate thresholds and the `f0(d)` fit family (isotonic vs logistic), from the spike.
- Exact victim `p`, ALU-iter count, and region size inside the spike's bracketing constraint.
- The six-plus calibration duties and the three computed verification schedules (`rollup.py` prints
  the inversion so the computed-vs-realized duty is auditable).
- `TRACE_INSTR/WARMUP/SIM` (reuse the `blend_bw` 50M default unless the spike shows otherwise).
- `rollup.py` parsing/plot details, following `blend_bw/rollup.py` (add an `f0`-vs-`d` curve with
  the three setpoints marked).
