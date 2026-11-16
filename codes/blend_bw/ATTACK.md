# Attack Methodology — `blend_bw`: Time-Toggled Duty-Cycle Policy Steering

This document is the self-contained methodology for the **`blend_bw`** attack on the Pythia
(scooby) L2 prefetcher. It assumes only general familiarity with the shared-DRAM-bandwidth
covert channel the attack family rides on; everything specific to `blend_bw` is here.

---

## 0. The idea in one paragraph

`pband_bw` established that the attacker's lever is an **on/off switch**: the shared DRAM
bucket saturates below ~5 % *instantaneous* duty and Pythia's high-bandwidth gate
(`is_high_bw()`) is a hard threshold, so there is no graded *instantaneous* bandwidth dial.
`blend_bw` recovers a dial anyway by toggling that switch **in time**. If the attacker
flips its traffic on and off faster than the victim's SARSA Q-values can settle, the victim
learns against a **time-average of the two reward tables**, weighted by the fraction of time
the switch is on. The quantity the attacker ultimately controls — the EV-flip break-even
predictability `p*` that decides which PCs keep prefetching — then becomes a **continuous
function of that duty fraction**. A binary switch becomes a dial, and raising the duty
sweeps `p*` upward through the victim's PCs, driving them to abstain. The attacker stays
**blind and open-loop**: it reads nothing about the victim and never confirms the attack.

---

## 1. Threat model

- **Platform:** dual-core ChampSim, shared LLC, a **single shared DRAM channel**
  (`DRAM_CHANNELS = 1` in the 2-core build). Core 0 = victim, core 1 = attacker
  (`-traces victim.xz attacker.xz`).
- **Victim:** runs Pythia (scooby), an RL L2 prefetcher, in a fixed, realistic
  bandwidth-aware configuration. The attacker cannot change the victim's config, read its
  memory, or read its prefetcher state.
- **Attacker:** a co-located **static synthetic trace** — no shared memory, no IPC, no
  runtime feedback, **no victim knowledge**. Its only lever is its own DRAM read rate,
  toggled on a fixed schedule set in advance.
- **Only assumed knowledge:** the *offline, public* architectural fact (Pythia paper +
  open ChampSim source) that Pythia reacts to a DRAM-bandwidth signal that is **global**,
  plus the EV math below. The attacker exploits a design property, not a secret.

---

## 2. The shared channel

Every 256 cycles ChampSim buckets the **aggregate** DRAM read-enqueue count over *all*
cores into a level 0–3 and broadcasts the *same* value to every core's Pythia:

```
src/main.cc:964-978   bucket aggregate rq_enqueue over all cores into level 0..3 each
                      256-cycle epoch (EWMA: epoch = epoch/2 + this_epoch; quartiles)
src/cache.cc:1769     broadcast the level to the L2 prefetcher
prefetcher/scooby.cc  Scooby::update_bw(level) stores bw_level; is_high_bw() == bw_level >= thresh
```

There is **no per-core accounting**: the bucket the victim reads reflects the attacker's
traffic as much as its own. That absence of isolation *is* the channel. `blend_bw` sets
`scooby_high_bw_thresh = 3` (a realistic bandwidth-aware config), so bucket 3 trips the
high-bandwidth (HBW) path.

---

## 3. The mechanism: reward shaping, time-averaged

Pythia modulates its **reward table** by the bandwidth level. The HBW table is harsher on
wrong prefetches and gentler on abstaining:

| reward          | normal | high-bandwidth |
|-----------------|:------:|:--------------:|
| correct_timely  |  +20   |  +20 |
| incorrect       |  −8    |  **−14** |
| none (abstain)  |  −4    |  **−2** |

A PC gambles (prefetches a nonzero delta) when prefetching's expected value beats
abstaining's. For an action correct with probability `p`:

```
EV_gamble  = p·R_correct + (1−p)·R_incorrect ;   EV_abstain = R_none
p*         = (R_none − R_incorrect) / (R_correct − R_incorrect)
```

With the static tables this gives the two fixed numbers **0.143** (normal) and **0.353**
(high-bw). `pband_bw` can only ever place `p*` at one of those two points.

### The blend

Let `d` be the fraction of time the victim effectively experiences the HBW table (the
**blend fraction**). Because SARSA is a slow running average (small `scooby_alpha`), a
toggle faster than its settling time makes the agent learn against the **duty-weighted
average** of the two tables:

```
R_incorrect_eff(d) = (1−d)(−8) + d(−14) = −8 − 6d
R_none_eff(d)      = (1−d)(−4) + d(−2)  = −4 + 2d
R_correct          = +20   (identical in both tables)

              (−4+2d) − (−8−6d)      4 + 8d
p*(d)  =  ───────────────────────  = ────────
              20 − (−8−6d)           28 + 6d
```

| d | 0.00 | 0.25 | 0.50 | 0.75 | 1.00 |
|---|------|------|------|------|------|
| p*(d) | 0.143 | 0.189 | 0.258 | 0.311 | 0.353 |

Endpoints reproduce the two static results. In between, `p*` moves smoothly. Inverting, a
PC of predictability `p` flips gamble→abstain at `d_crit(p) = (28p−4)/(8−6p)`. Since
`d_crit` rises with `p`, raising the blend fraction flips PCs in order of predictability.

---

## 4. The attacker: a time-toggled duty cycle

`attacker.c` alternates two phases and loops (`./attacker <on_lines> <off_iters>`):

- **ON:** stream `on_lines` fresh lines of a 64 MiB region (every load misses LLC → DRAM
  read traffic → pushes the shared bucket to 3). The stream cursor **persists** across ON
  phases, so successive bursts touch fresh lines and keep missing.
- **OFF:** `off_iters` pure register-ALU ops (no loads → no DRAM → the bucket's EWMA
  decays back below the threshold).

The nominal duty is the on:off ratio; the **effective blend fraction `d` is whatever
bw-level histogram the victim actually observes** — `rollup.py` reads it off the victim's
`scooby_bw_level_3` fraction (`bw3`) and treats *that* as `d`. The extremes reproduce
`pband_bw` exactly: `off=0` → pure heavy (`d≈0.94`); `on=0` → pure idle (`d≈0`).

### The window, and why toggling works at all

A stable intermediate exists only if three clocks separate:

```
bucket epoch (256 cyc)  ≪  toggle period  ≪  Q-value settling time
```

Too fast → the bucket's EWMA erases the off-phases (back to a heavy switch, `d≈1`). Too
slow → the victim fully converges each phase (thrashing between two pinned policies, not a
blend). Empirically this window is **non-empty** for Pythia here: short ON/OFF bursts
(hundreds–thousands of iters) produce genuinely graded `d`.

### The reachable-`d` ceiling (an empirical finding)

Any *nonzero* OFF phase caps measured `d` at **≈0.87**, not ≈1. Cause: during ON the
victim is throttled (its IPC drops to ~0.24), so it emits *few* bw-samples per cycle; during
even a short OFF it runs fast and emits *many* samples at bucket 0. The victim therefore
**under-samples its own throttling**, and since the policy is driven by the victim's own
SARSA updates, this is a real limit, not just a measurement artifact — the attack is
**self-limiting**. Only `off=0` (= the `pband_bw` heavy switch) reaches `d≈0.94`. The
reachable duty range via toggling is thus roughly `[0.04, 0.87]`.

The three duties used (calibrated against measured `bw3`):

| neighbor | on_lines | off_iters | measured d |
|----------|:--------:|:---------:|:----------:|
| `atk_d_lo`  | 256  | 2048 | ≈0.30 |
| `atk_d_mid` | 1024 | 2048 | ≈0.60 |
| `atk_d_hi`  | 4096 | 64   | ≈0.89 |

---

## 5. The victim

Same **structure** as the `pband_bw` victim (6 load PCs, each a `noinline` function
`blend_pc_<j>` with one load into its own disjoint 1 MiB region; each advances its cursor
by its signature with probability `p`, else by a non-action noise delta `{7,8,9,13,14}`;
~12 ALU ops/load keep self-bandwidth low). The **predictabilities differ** and are tuned
so the toggle drives *full, isolated* flips:

```
(p, signature) = [(0.21,3), (0.24,4), (0.27,5),   # contestable
                  (0.45,11), (0.65,12), (0.90,22)] # anchors
```

Two constraints bound the contestable band `~[0.21, 0.27]`:

- **Upper bound (the d ceiling).** `pband_bw`'s `p=0.30/0.33` only reach *partial*
  abstention (`f0≈0.36`) because `d` saturates at ~0.87 and the exploration/fallback floor
  caps `f0` (even at `d≈0.94`, pband-heavy reaches only `f0≈0.67`). `p` must be low enough
  that the HBW reward drives `f0` past 0.5 at the reachable `d`.
- **Lower bound (isolation).** `p` must stay comfortably **above the normal break-even
  0.143**, or raw contention-induced timing tips the PC to abstain *even with the HBW table
  off*, breaking the isolation control. (Observed directly: `p=0.16` abstained under the
  blind config too — `f0` rose to 0.58.)

Signatures avoid `+1` (the featurewise action-fallback attractor) and are all in
`scooby_actions`, so Pythia can only ever be *correct* on the signature — a clean per-PC
fingerprint. The non-action noise is never selectable, so a noise step is simply "no action
correct."

---

## 6. Config

Reuses the `pband_bw` reward lever unchanged — `blend_bw` changes only the *attacker*
(it toggles the bucket in time instead of holding it saturated):

- `aware.ini` (the attack): `scooby_high_bw_thresh = 3`, `scooby_enable_hbw_reward = true`,
  HBW degree curve pinned **equal** to normal (`scooby_dyn_degrees_type2_hbw = 1,2,4,6`, so
  the degree lever is off — any movement is reward-shaping alone), `scooby_enable_per_pc_stats = true`.
- `blind.ini` (isolation control): identical **except** `scooby_enable_hbw_reward = false`.
  The bucket still trips (same `bw3`), but the reward table never swaps.

### Per-PC readout

Per-PC behaviour is invisible in the aggregate `scooby_predict_action_*` histogram (the
featurewise `+1` fallback washes it out), so it is read from scooby's **read-only
per-trigger-PC action counter** (`scooby_enable_per_pc_stats`), dumped as
`scooby_per_pc_<hex ip> c0,…,c14,` in `scooby_actions` order. `rollup.py` maps each trigger
IP to a `blend_pc_<j>` via `nm` on the static, non-PIE `build/blend_bw_victim.out`
(fallback: the 6 hottest IPs in address order). The headline metric is the per-PC
**abstain fraction** `f0 = frac(action 0)`.

---

## 7. Results (SIM = 50M)

> **Full flips require the long run.** At SIM=10M the agent under-settles and `f0` caps
> below 0.5 (partial abstention only). SIM=50M lets the blended policy converge *and*
> dilutes the low-`d` startup transient (so `d_hi` reaches ~0.89). Both matter.

Per-PC abstain fraction `f0` (victim = core 0):

| regime | d=bw3 | p=0.21 | p=0.24 | p=0.27 | p=0.45 | p=0.65 | p=0.90 |
|--------|:-----:|:------:|:------:|:------:|:------:|:------:|:------:|
| aware `d_lo`  | 0.30 | 0.21 | 0.25 | 0.27 | 0.00 | 0.00 | 0.00 |
| aware `d_mid` | 0.60 | 0.43 | 0.46 | 0.49 | 0.00 | 0.00 | 0.00 |
| **aware `d_hi`** | **0.89** | **0.71** | **0.74** | **0.76** | 0.03 | 0.00 | 0.00 |
| blind `d_lo`  | 0.31 | 0.02 | 0.01 | 0.01 | 0.00 | 0.00 | 0.00 |
| blind `d_mid` | 0.61 | 0.02 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |
| blind `d_hi`  | 0.86 | 0.02 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |

- **The dial.** As the attacker raises its duty, every contestable PC's abstain fraction
  rises monotonically (≈+0.50 each) and **crosses the 0.5 line** at `d_hi` — a continuous
  duty cycle drives a decided verdict flip. Anchors (`p≥0.45`) never move; the degree
  distribution (`deg≥4`) is held across duties, so the movement is action-selection, not
  degree.
- **Isolation (decisive).** The blind victim sees the *same* graded `bw3` (0.31/0.61/0.86)
  yet **no contestable PC abstains at any duty** (`f0 ≈ 0.01`). The flips are the reward
  *signal*, not the contention the toggle also produces.

---

## 8. What is steered — and the honest scope

The attacker drives the victim's contestable PCs from **gamble to abstain** by a continuous
knob (duty cycle), with full flips reachable at high duty — richer than `pband_bw`'s single
binary step, and isolated from contention.

**It is a continuous collapse of the contestable *set*, not a per-PC selector.** Two limits:

1. **Ordering is not resolved.** In the reachable range the three contestable PCs flip
   **together** (between `d≈0.60` and `d≈0.89`); `f0` barely scales with `p`, so there is no
   staggered per-`p` staircase. The per-PC flip order is further confounded by the
   featurewise `+1` **fallback washout**: low-`p` PCs route their gambles to `+1` regardless
   of signature, so their flip timing is governed by learnability, not by `d_crit(p)`.
2. **The reachable set is 1-D.** The lever is one scalar (the global bucket), thresholded to
   one bit, so the attacker chooses *how far up the duty axis to push* the whole contestable
   set — not an arbitrary per-PC subset. `blend_bw` sharpens the *resolution* of
   `pband_bw`'s single step into a continuous ramp; it does not add dimensions.

The contestable band is also **narrow** (`~[0.21, 0.27]`): below it, isolation breaks (raw
contention flips the PC); above it, the `d≈0.87` ceiling + exploration floor keep `f0` under
0.5. The attack still lands cleanly inside that band.

---

## 9. Success gates (`rollup.py`)

1. **Dial (A):** each contestable PC's `f0` rises monotonically with duty (rise > 0.25).
2. **Stable intermediate (B):** `bw3` is genuinely graded across the three duties (low not
   already saturated; consecutive gaps separated) and a contestable PC sits strictly
   between its low/high `f0` at the mid duty — a real middle, not snapped to 0/1.
3. **Ordered staircase (C):** lower-`p` contestable flips at a duty ≤ a higher-`p` one.
   *(Passes trivially here — the set flips together; see §8.)*
4. **Anchors hold (D):** `p≥0.45` keep gambling their signature at every duty.
5. **Isolation (E):** blind has the same `bw3` at each duty, yet no contestable PC abstains.
6. **Degree held (F):** `deg≥4` (among gambling prefetches) stable across the aware duties.

All six pass on the SIM=50M run above.

---

## 10. Root cause and mitigation

Root cause (shared with the whole family): **Pythia consumes a system-wide bandwidth signal
with no per-core isolation**, so a neighbor's traffic enters the victim's decision loop.
`blend_bw` shows that even a *graded, time-shaped* version of that signal — a blind
neighbor's duty cycle — is enough to drive the victim's RL agent continuously from
prefetching to abstaining.

**Mitigation:** derive Pythia's bandwidth level from **per-core** DRAM accounting rather
than the single global counter (`src/main.cc:964-978`). The blend fraction `d` is then
pinned to whatever the victim itself induces, and a lever with no reachable input controls
nothing — the same fix that closes `pband_bw` closes its graded form.

---

## 11. How to run

```bash
source scripts/set_env.sh
# full flips need the long run:
TRACE_INSTR=65000000 WARMUP=10000000 SIM=50000000 ./scripts/launch.sh blend_bw
```

Outputs land in `experiments/blend_bw/`: `<neighbor>_<cfg>.out` (6 runs = 3 duties ×
aware/blind), `rollup.txt`, `rollup.csv`, `degree_dist.png` (the per-PC duty-sweep chart)
and `degree_dist_isolation.png`. To re-tune duties, edit the `on_lines/off_iters` in
`matrix` (delete the changed `traces/blend_bw_*` to force a re-trace) and target `bw3`
≈ 0.3 / 0.6 / 0.9.
