# DOSSIER — Pythia Shared-Bandwidth Steering Attacks

**Scope:** research only. Everything here runs inside the ChampSim microarchitectural
simulator against the Pythia (scooby) RL prefetcher. There is no real-world target; the
"attacks" are simulated co-location experiments that demonstrate a design property of Pythia's
bandwidth signal.

This dossier consolidates **four** cross-core attacks on Pythia, each exploiting the *same*
root cause — a global, un-isolated DRAM-bandwidth signal — through a different Pythia mechanism.
Per-attack deep dives live in `codes/<attack>/ATTACK.md`.

---

## 0. Executive summary

| attack | what it steers | lever | status | per-attack doc |
|--------|----------------|-------|:------:|----------------|
| **`degree_bw`** | prefetch **degree** (aggressiveness 6 → 1) | footprint intensity ramp | ✅ **PASS** (4/4) | `codes/degree_bw/ATTACK.md` |
| **`policy_bw`** | **which action** one contestable PC picks (gamble → abstain) | ~binary (near-saturating) | 🟡 **PARTIAL** (3/4) | `codes/policy_bw/ATTACK.md` |
| **`pband_bw`** | **which PCs** abstain (multi-PC, differentiated) | binary switch (idle/heavy) | ✅ **PASS** (5/5) | `codes/pband_bw/ATTACK.md` |
| **`blend_bw`** | contestable **set**, by a continuous duty dial | time-toggled duty cycle | ✅ **PASS** (6/6) | `codes/blend_bw/ATTACK.md` |

All four share one root cause and one mitigation (§6). The progression is deliberate:
`degree_bw` throttles aggressiveness; `policy_bw` redirects one decision; `pband_bw` makes that
redirection *differentiated* across PCs; `blend_bw` turns the binary lever into a continuous
knob.

---

## 1. Threat model (common to all four)

- **Platform:** dual-core ChampSim, shared LLC, a **single shared DRAM channel**
  (`DRAM_CHANNELS = 1` in the 2-core build). Core 0 = victim, core 1 = attacker.
- **Victim:** runs Pythia (scooby), an RL L2 prefetcher, in a fixed, realistic
  bandwidth-aware config. The attacker cannot change the victim's config, read its memory, or
  read its prefetcher state.
- **Attacker:** a co-located **static synthetic trace** — no shared memory, no IPC, no runtime
  feedback, **no victim knowledge** (not its addresses, hot sets, cache contents, or Pythia
  tables). Its only lever is its own DRAM read rate.
- **Only assumed knowledge:** the *offline, public* architectural fact (Pythia paper + open
  ChampSim source) that Pythia reacts to a DRAM-bandwidth signal that is **global**, plus the
  reward EV math (§3). The attacker exploits a design property, not a secret.
- **Open-loop:** the attacker never observes whether the attack is working. That a neighbor who
  *measures nothing* still steers the victim is what makes the result strong.

---

## 2. The shared channel (the root cause, common to all four)

Every 256 cycles ChampSim buckets the **aggregate** DRAM read-enqueue count over *all* cores
into a level 0–3 and broadcasts the *same* value to every core's Pythia:

```
src/main.cc:964-978   bucket aggregate rq_enqueue over all cores into level 0..3 each
                      256-cycle epoch (EWMA: epoch = epoch/2 + this_epoch; quartiles vs
                      DRAM_DBUS_MAX_CAS)
src/cache.cc:1769     broadcast the level to the L2 prefetcher
prefetcher/scooby.cc  Scooby::update_bw(level) stores bw_level
                      is_high_bw() == (bw_level >= scooby_high_bw_thresh)
```

There is **no per-core accounting**: the bucket the victim reads reflects the attacker's
traffic just as much as its own. That absence of isolation *is* the channel. The attacker
raises the bucket with its own DRAM traffic; the victim's Pythia reads a bucket it did not
cause.

The shipped `config/pythia.ini` leaves `scooby_high_bw_thresh` at its default (4) while the
bucket maxes at 3, so the high-bandwidth (HBW) path ships **dormant**. Every attack enables it
with `scooby_high_bw_thresh = 3` — a realistic bandwidth-aware regime, exactly what the paper's
mechanism is designed for.

### The attacker's intensity dial

Intensity is set by **footprint**, not ALU padding (ALU ops are ~free and do not throttle the
steady-state DRAM rate). A small region is LLC-resident (little DRAM traffic); a large region
always misses (saturates DRAM).

| intensity | region | shared bucket |
|-----------|--------|---------------|
| idle | tiny / pure ALU | ~0 |
| light | 2 MiB | partial |
| medium | 3 MiB | partial |
| heavy | 64 MiB | saturates bucket 3 |

**Key empirical fact:** the bucket saturates (`bw3 ≥ 0.82`) below ~5 % *instantaneous* duty,
and `is_high_bw()` is a hard threshold — so instantaneously the lever is an **on/off switch**,
not a smooth dial. `blend_bw` recovers a dial by toggling the switch *in time* (§4.4).

---

## 3. The two Pythia mechanisms exploited

### 3a. The degree curve (used by `degree_bw`)

Pythia picks how many lines to prefetch per trigger from a **degree curve**, keyed by the
bandwidth level:

```
scooby_dyn_degrees_type2     = 1,2,4,6     # normal curve
scooby_dyn_degrees_type2_hbw = 1,1,1,1     # high-bw curve (degree_bw pins it to 1)
```

High bucket → HBW curve → degree collapses to 1. The victim keeps predicting the same action;
only *how many* lines it runs ahead changes.

### 3b. The reward table (used by `policy_bw`, `pband_bw`, `blend_bw`)

Pythia swaps its **reward table** by bandwidth level. The HBW table punishes wrong prefetches
harder and makes abstaining cheaper:

| reward          | normal | high-bandwidth |
|-----------------|:------:|:--------------:|
| correct_timely  |  +20   |  +20 |
| incorrect       |  −8    |  **−14** |
| none (abstain)  |  −4    |  **−2** |

**The EV-flip band.** For an action correct with probability `p`, prefetching beats abstaining
when `EV_gamble > EV_abstain`:

- normal reward: `28p − 8 > −4` ⇒ `p > 0.143`
- high-bw reward: `34p − 14 > −2` ⇒ `p > 0.353`

So for **`p ∈ (0.143, 0.353)`** the same workload flips: normal-reward Pythia prefetches,
HBW-reward Pythia **abstains**. That band is the engine behind all three policy attacks. A
trivially predictable victim (`p ≈ 1`) is *not* steerable this way — its action stays correct
and the harsher penalty never bites. The victim must be **contestable**.

The break-even `p* = (R_none − R_incorrect) / (R_correct − R_incorrect)` is **0.143** (normal)
and **0.353** (HBW). A static switch can only ever place `p*` at those two points; `blend_bw`
makes it continuous.

---

## 4. The four attacks

### 4.1 `degree_bw` — degree steering ✅ PASS (4/4)

**Made up of:** attack config pins the HBW degree curve to `1,1,1,1` and sets
`scooby_high_bw_thresh = 3`; victim is a trivially predictable **+1-line-stride** stream (so
only the degree lever can move, not the reward lever); attacker is the footprint intensity dial
(idle/light/medium/heavy) plus a `benign_cache` co-location control. Isolation control
`bwblind.ini` sets `scooby_high_bw_thresh = 4` so the HBW path never trips.

**Results (bwaware, victim = core 0):**

| neighbor | bw3 | deg1 | deg≥4 | IPC |
|----------|:---:|:----:|:-----:|:---:|
| idle | 0.000 | 0.049 | 0.920 | 1.425 |
| light | 0.216 | 0.197 | 0.776 | 1.346 |
| medium | 0.603 | 0.544 | 0.440 | 1.361 |
| **heavy** | **0.915** | **0.848** | **0.147** | 1.338 |
| benign_cache | 0.000 | 0.049 | 0.920 | 1.425 |

**Isolation (decisive):** bwblind under heavy sees the *same* `bw3 = 0.905` yet `deg≥4` stays
0.920 (unmoved). Identical contention, opposite outcome ⇒ steering is the signal, not slowdown.
`benign_cache` ≈ idle ⇒ mere co-location does nothing.

**Gates:** monotone bw3 ✅; degree collapse (deg≥4 0.92 → 0.15) ✅; isolation ✅; benign ≈ idle
✅.

---

### 4.2 `policy_bw` — policy (action-distribution) steering 🟡 PARTIAL (3/4)

**Made up of:** reuses the *same attacker* as `degree_bw`; attack config `aware.ini` sets
`scooby_enable_hbw_reward = true`, `scooby_high_bw_thresh = 3`, and pins the HBW degree curve
**equal** to normal (`1,2,4,6`) — so the degree lever is off and any movement is reward-shaping
alone. Victim is **contestable**: deltas drawn i.i.d. uniform over `{1,3,4,5}` (any single
action correct `p ≈ 0.25`, inside the flip band). Predefined target `PI_ABSTAIN = {0:0.84,
1:0.16}`. Isolation control `blind.ini` sets `scooby_enable_hbw_reward = false`.

**Results (aware, victim = core 0):**

| neighbor | bw3 | abstain f0 | top action | L1 to target | deg≥4 |
|----------|:---:|:----------:|:----------:|:------------:|:-----:|
| idle | 0.043 | 0.000 | 5 (gamble) | 1.679 | 0.689 |
| light | 0.692 | 0.396 | 5 (gamble) | 1.193 | 0.688 |
| medium | 0.742 | 0.788 | 0 (abstain) | 0.420 | 0.689 |
| **heavy** | 0.924 | **0.814** | 0 (abstain) | **0.371** | 0.691 |

**Isolation (decisive):** blind under heavy sees `bw3 = 0.934` yet `f0 = 0.000` (never
abstains, top action stays 5). Abstain collapse only with the reward signal live.

**Gates:** steering (f0 0.00 → 0.81) ✅; **target hit L1 < 0.3 ❌ (L1 = 0.371, narrowly over)**;
isolation ✅; degree held (|Δdeg≥4| = 0.002) ✅.

**Why PARTIAL, not FAIL:** the victim *did* collapse to abstain (f0 = 0.81, top action 0) and
all three decisive gates pass; only the exact-target-shape gate is narrowly missed. The lever
is near-binary (even a light attacker nearly saturates the bucket), so hitting an exact
distribution shape is hard — which is precisely the honest-scope limit the attack documents.

---

### 4.3 `pband_bw` — multi-PC p-band steering ✅ PASS (5/5)

**Made up of:** reuses the `policy_bw` reward lever unchanged, plus a **read-only per-PC action
counter** (`scooby_enable_per_pc_stats = true`) — needed because Pythia's featurewise `+1`
fallback washes per-PC behaviour out of the aggregate histogram. The counter is pure
measurement; it changes no prefetch decision. Victim has **6 load PCs of differing
predictability** `(p, sig) = [(0.30,3),(0.33,4),(0.45,5),(0.55,11),(0.75,12),(0.95,22)]`;
contestable = `p < 0.4`. Attacker is a **binary switch** (idle/heavy only — intermediate duties
give no gradation). Predefined target `PBAND_TARGET = [abstain, abstain, gamble, gamble,
gamble, gamble]`.

**Results (per-PC abstain fraction f0, victim = core 0):**

| regime | bw3 | p=0.30 | p=0.33 | p=0.45 | p=0.55 | p=0.75 | p=0.95 |
|--------|:---:|:------:|:------:|:------:|:------:|:------:|:------:|
| aware idle | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **aware heavy** | 0.875 | **0.68** | **0.74** | 0.00 | 0.00 | 0.00 | 0.00 |
| blind heavy | 0.867 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Contestable PCs collapse (signature-gamble drops 0.95/0.99 → 0.19/0.20); the four predictable
PCs hold signature ≈ 0.99–1.00. A clean **step** at the EV-flip edge — a staircase in p-space.

**Isolation (decisive):** blind-heavy same `bw3 = 0.867` yet no PC abstains.

**Gates:** differentiated steering ✅; staircase step (0.68 > 0.4) ✅; named joint-target hit
✅; isolation ✅; degree held ✅.

---

### 4.4 `blend_bw` — time-toggled duty-cycle steering ✅ PASS (6/6)

**Made up of:** reuses the `pband_bw` reward lever **unchanged** — the only change is the
*attacker*. `attacker.c` toggles its traffic ON/OFF on a fixed schedule
(`<on_lines> <off_iters>`): ON streams fresh 64 MiB lines (saturates the bucket), OFF does
pure-ALU ops (lets the bucket's EWMA decay). Because SARSA is a slow running average, a toggle
faster than its settling time makes the victim learn against the **duty-weighted average** of
the two reward tables. The break-even then becomes a *continuous* function of the blend
fraction `d`:

```
p*(d) = (4 + 8d) / (28 + 6d)      # 0.143 at d=0, 0.353 at d=1
```

A binary switch becomes a dial; raising `d` sweeps `p*` upward through the victim's PCs. Victim
is `pband_bw`'s mixed-`p` structure but **tuned** so the toggle drives full flips:
`(p, sig) = [(0.21,3),(0.24,4),(0.27,5),(0.45,11),(0.65,12),(0.90,22)]`. Three duties
(`atk_d_lo/mid/hi`) target `d ≈ 0.3 / 0.6 / 0.9`. Run long (SIM = 50M) so the blended policy
converges.

**Results (per-PC abstain fraction f0, aware, victim = core 0):**

| regime | d=bw3 | p=0.21 | p=0.24 | p=0.27 | p=0.45 | p=0.65 | p=0.90 |
|--------|:-----:|:------:|:------:|:------:|:------:|:------:|:------:|
| aware d_lo | 0.30 | 0.21 | 0.25 | 0.27 | 0.00 | 0.00 | 0.00 |
| aware d_mid | 0.60 | 0.43 | 0.46 | 0.49 | 0.00 | 0.00 | 0.00 |
| **aware d_hi** | **0.885** | **0.71** | **0.74** | **0.76** | 0.03 | 0.00 | 0.00 |
| blind d_lo | 0.31 | 0.02 | 0.01 | 0.01 | 0.00 | 0.00 | 0.00 |
| blind d_hi | 0.86 | 0.02 | 0.01 | 0.00 | 0.00 | 0.00 | 0.00 |

Each contestable PC's `f0` rises monotonically (≈ +0.50) with duty and crosses 0.5 at `d_hi` —
a continuous knob driving a decided flip. Anchors (`p ≥ 0.45`) never move.

**Isolation (decisive):** blind sees the *same* graded `bw3` (0.31/0.61/0.86) yet no
contestable PC abstains at any duty (`f0 ≈ 0.01`).

**Gates:** dial (A) ✅; stable intermediate (B) ✅; ordered staircase (C) ✅ (trivially — the
set flips together); anchors hold (D) ✅; isolation (E) ✅; degree held (F) ✅.

**Honest scope:** a continuous collapse of the contestable *set*, not a per-PC selector — in
the reachable range the three contestable PCs flip together, and the reachable duty tops out at
`d ≈ 0.87` for any nonzero OFF phase (the throttled victim under-samples its own ON phase).
`blend_bw` sharpens `pband_bw`'s single step into a continuous ramp; it does not add dimensions.

> Note: an earlier run (commit `blend_bw failed`) under-settled at SIM=10M and capped `f0`
> below 0.5. The current `experiments/blend_bw/rollup.txt` (SIM=50M) passes all six gates.

---

## 5. The four attacks side by side

| | `degree_bw` | `policy_bw` | `pband_bw` | `blend_bw` |
|---|---|---|---|---|
| Channel | global DRAM-bw bucket | global DRAM-bw bucket | global DRAM-bw bucket | global DRAM-bw bucket |
| Pythia mechanism | HBW **degree curve** | HBW **reward table** | HBW **reward table** | HBW **reward table** |
| Config lever | `dyn_degrees_type2_hbw=1,1,1,1` | `enable_hbw_reward=true`, degree pinned | `+ per_pc_stats` | `+ per_pc_stats` (attacker toggles) |
| Victim | predictable +1 stride | contestable i.i.d. {1,3,4,5} | multi-PC, mixed `p` 0.30–0.95 | multi-PC, mixed `p` 0.21–0.90 |
| What moves | degree 6 → 1 | action gamble → abstain | **which PCs** abstain | contestable **set**, by duty |
| Attacker lever | intensity ramp | ~binary | binary switch | **time-toggled duty cycle** |
| Readout | degree histogram | aggregate action dist | **per-PC** action counter | **per-PC** action counter |
| Headline metric | deg1 fraction | abstain f0 | per-PC f0 | per-PC f0 vs duty |
| Isolation control | `high_bw_thresh=4` | `enable_hbw_reward=false` | `enable_hbw_reward=false` | `enable_hbw_reward=false` |
| Victim knowledge | none | none | none | none |
| **Status** | ✅ 4/4 | 🟡 3/4 | ✅ 5/5 | ✅ 6/6 |

Every attack's decisive **isolation** gate passes: same bucket saturation under the blind
config, opposite outcome ⇒ the steering is the *signal*, not raw contention.

---

## 6. Root cause and mitigation (common to all four)

**Root cause:** Pythia consumes a **system-wide bandwidth signal with no per-core isolation**
(`src/main.cc:964-978`), so a neighbor's traffic enters the victim's decision loop. The degree
attack shows this can throttle the victim's aggressiveness; the policy attacks show it can
**redirect what the victim's RL agent learns to do** — and select *which* PCs lose their
prefetcher, down a continuous duty dial.

**Mitigation:** derive Pythia's bandwidth level from **per-core** DRAM accounting rather than
the single global counter. The bandwidth level a victim sees is then pinned to what the victim
itself induces, and a lever with no reachable input controls nothing — one fix closes the whole
family (degree curve *and* reward table, binary switch *and* graded form).

---

## 6.5 A studied channel that does **not** work — `filltime_steer`

A fifth experiment (`codes/filltime_steer/`, spec
`docs/superpowers/specs/2026-11-16-filltime-steer-design.md`) attacked a **different** Pythia
surface: the base reward's **timely (+20) / untimely (+12)** classification, with the
bandwidth path turned **off** (`scooby_high_bw_thresh = 4`). The attacker raises the victim's
prefetch **fill latency** `L` by shared-LLC/DRAM contention, aiming to move the timeliness
crossover `O* = L / T_line` and steer which prefetch **distance** a (dual-touch) victim learns.

**Result: a clean negative.** The channel is real and bandwidth-independent *structurally* —
`scooby_high_bw_thresh = 4 > max bucket level 3`, so `is_high_bw()` can never fire even though
the bucket saturates under attack (L3 fraction 0→0.92) — and the dual-touch victim works
(`incorrect` ≈ 0.009). But the attacker **cannot steer it**: although it
contends measurably (victim IPC 1.39→1.25, bucket 0→saturated), the victim's timely-fraction is
**invariant** (0.396→0.390 at default degree; 1.00→0.98 at pinned degree=1). No offset ever
flips (2 of 7 gates — the steering gates — fail by reality, not tuning).

**Why, and why it matters for the four above.** A prefetch of offset `O` is timely iff
`L < O·T_line`, but the memory-bound victim's per-line time `T_line ≈ L` (its demands miss to the
*same* shared memory the prefetch fills from), so `O* = L / T_line` is **contention-invariant** —
raising `L` lengthens the victim's lead-time in lock-step. The fill-timing channel carries a
latency **ratio**, which self-cancels; the bandwidth channel (§2) carries an **absolute** bucket,
which does not. **That is the sharper statement of why the four attacks work:** Pythia is
steerable through signals it reads in *absolute* terms (the bandwidth bucket), not through ones
that reach it only as a *ratio* of two quantities the attacker moves together. The §6 per-core
mitigation is unaffected — this channel needed no fix because it was never weaponizable.

## 7. How to run

```bash
source scripts/set_env.sh
./scripts/launch.sh degree_bw      # or policy_bw / pband_bw
# blend_bw needs the long run:
TRACE_INSTR=65000000 WARMUP=10000000 SIM=50000000 ./scripts/launch.sh blend_bw
```

Each attack writes `experiments/<attack>/`: per-run `.out` files, `rollup.txt` (gates +
tables), `rollup.csv`, and chart(s). Per-attack detail: `codes/<attack>/ATTACK.md`.
