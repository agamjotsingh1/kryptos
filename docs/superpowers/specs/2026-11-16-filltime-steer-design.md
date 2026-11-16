# Design — `filltime_steer`: fill-timing prefetch-distance steering of Pythia (no bandwidth channel)

**Status:** design, awaiting approval. Research-only, in-simulator (ChampSim + Pythia/scooby).
**Date:** 2026-11-16.

## 1. Intent and why

The four attacks in `DOSSIER.md` all steer Pythia through **one** channel: the global
DRAM-bandwidth bucket (`src/main.cc:964`), and all four require turning the HBW path **on**
(`scooby_high_bw_thresh = 3`), a feature the stock config ships dormant. A reviewer can fairly
say: one root cause, one enabled-feature precondition.

This attack opens a **second, independent channel** that needs the bandwidth path **off**, and
that is live in a realistic base config. Pythia's base reward assigns a prefetch `+20` if it
filled before its demand (**timely**) and `+12` if it filled after (**untimely**) — purely a
**timing** classification (`prefetcher/scooby.cc:655`). Fill timing is set by memory latency,
which a co-located neighbor controls through shared-LLC / DRAM-queue contention **without
touching Pythia's bandwidth signal**. By modulating that latency the attacker moves the
timely↔untimely crossover and steers *which prefetch distance* Pythia's SARSA agent learns to
prefer — a targeted, graded steer on a new channel.

The point the attack proves: Pythia is steerable through its **timeliness reward classification**,
not only through its bandwidth-indexed reward/degree tables — so the bandwidth mitigation in
§6 of the dossier does **not** close this. Same threat model, orthogonal mechanism, opposite
config switch.

## 2. Goals

- A **targeted** steer: the attacker selects *which offset distance* the victim's Pythia learns
  to prefetch (short → long), per victim load-PC, by its own blind contention intensity.
- **Graded**: an intensity dial (idle → heavy) moves the chosen distance monotonically.
- **Selective / staircase**: with a multi-PC victim spanning a spread of offset geometries, the
  attacker flips PCs in a defined order; designated **anchor** PCs never flip (proves it is a
  selector, not a blanket slowdown).
- **Decisive isolation**: a control config that holds contention identical but removes the
  timing *reward distinction* must show **no** steer — proving the signal is the reward
  classification, not raw slowdown or eviction.
- **Bandwidth-orthogonal**: run with `scooby_high_bw_thresh = 4` (bucket ignored). Confirm via
  stats that `is_high_bw()` never fires and the HBW reward/degree tables are never used.

## 3. Non-goals / anti-goals

- **Not** an abstain/denial attack. Untimely is `+12` (still positive); for a single-offset PC it
  never drives Pythia to no-prefetch. Claiming "attacker makes victim abstain via fill timing"
  would be false — the `−8 incorrect` sign-flip needs PT (prefetch-tracker) eviction-before-demand,
  which is counted in *prefetch insertions* (`scooby.cc:526`), a victim-stream-geometry quantity,
  not something attacker wall-clock latency moves. See §5-B; kept explicitly out of the core claim.
- **No victim knowledge, either direction.** The attacker trace references only its own disjoint
  64 MiB region and its own PCs; the victim references only its own regions/PCs. No victim
  address, hot set, PC, or Pythia state is used in the attacker (or vice-versa). This is a hard
  constraint, not a default.
- **Not** a real-world target; no detection evasion; co-location is simulated.
- **Not** a reuse of the bandwidth bucket under another name. If the only way to show the effect
  were a saturated bucket, the attack fails its own isolation gate.

## 4. Constraints

- Dual-core ChampSim, shared LLC, single DRAM channel (existing 2-core build). Core 0 victim,
  core 1 attacker.
- Attacker = static synthetic trace, blind, open-loop (same discipline as `blend_bw/attacker.c`).
- Must reuse existing plumbing: `gen_trace.sh` (`-static -no-pie`), `scripts/launch.sh`, the
  `nm`-based per-PC IP→symbol mapping, and the existing scooby stat dumps
  (`scooby_reward.dist[action][type]` l.1076, `scooby_predict_action_<O>` l.964,
  `scooby_per_pc_` l.1023). No ChampSim/scooby **source** changes required for the core attack;
  the readouts already exist. (`scooby_enable_per_pc_stats` is a read-only counter, as in pband.)
- Config distinction from all four prior attacks: **`scooby_high_bw_thresh = 4`** (bandwidth path
  dead). `scooby_enable_hbw_reward` irrelevant/off.

## 5. Approaches considered

### A — Fill-timing distance steering (CHOSEN)

Mechanism. A prefetch for offset `O`, triggered at victim-stream position `t`, is demanded at
`≈ t + O·T_line` (T_line = victim time to advance one line of that PC's substream, set by its
ALU density and its own miss stalls). It fills at `t + L` (L = memory latency). Pythia scores it
**timely** iff `L < O·T_line`, i.e. iff `O > L / T_line`. So there is a crossover offset
`O* = L / T_line`: offsets above it fill in time (`+20`), below it fill late (`+12`).

The attacker raises `L` via shared-LLC/DRAM-queue contention (streaming its own 64 MiB region,
every access an LLC miss → DRAM queue pressure → longer victim fills). Raising `L` raises `O*`.

**The victim must be DUAL-TOUCH, not single-cursor.** This is the correctness crux (builder
check, 2026-11-16). For timing to be the *only* differentiator between the two offsets, both
`line+O_short` AND `line+O_long` must be genuinely demanded **every iteration** — not one-or-the-
other. A single cursor that advances by `O_short` with prob `q` else `O_long` demands only one of
them per step; the skipped line's prefetch is PT-evicted-before-demand and scored `−8 incorrect`
(`scooby.cc:684`), so each action's value becomes `p·(timely|untimely) + (1−p)·(−8)` — a
branch-probability EV flip, i.e. the *same* channel as policy/pband/blend, not a timing channel.
With dual-touch, whichever offset Pythia selects as its action is **always** demand-reused
(always correct); contention can only make the chosen action *late* (untimely `+12`), never
*wrong* (incorrect `−8`). Timing is then the sole separator.

So: raising `O*` past `O_short` makes the short action chronically untimely (`+12`) while the long
action stays timely (`+20`). SARSA's argmax then steers that PC from `O_short` to `O_long`.
Lowering intensity reverses it. A graded, targeted dial on learned prefetch **distance**, with the
bandwidth bucket ignored and the `−8` path structurally absent.

Why it is targeted, not blanket: each victim PC gets its own `(O_short, O_long, T_line)`, so each
has its own crossover-in-intensity. Attacker intensity sweeps a threshold across PCs → a staircase
in offset-geometry space. Anchor PCs are given `O_short` already large enough to stay timely even
at max reachable `L` → they never flip, isolating the effect from generic contention.

Readout: `scooby_reward.dist[action][type]` directly shows each offset's timely-vs-untimely split
collapsing at the crossover; `scooby_predict_action_<O>` and `scooby_per_pc_` show the resulting
shift in chosen offset. Headline metric: per-PC **long-offset fraction** vs attacker intensity.

### B — PT-horizon abstain (stretch; out of core claim)

Pushing a correct prefetch to `−8 incorrect` (hence to abstain, since `−8 < −4 none`) requires its
PT entry to be evicted before its demand. PT is a FIFO in insertion count; the attacker's latency
does not move the insertion/demand ratio. A *possible* indirect path: attacker LLC eviction makes
the victim re-miss its own lines → extra demand triggers → faster PT churn per unit victim progress
→ large-`O` prefetches fall off the PT horizon → `incorrect` → abstain. Attacker-controllability
of this is an **open empirical question**, not a claim. If the experiment happens to show it, it is
a bonus reported as such; the design does not depend on it.

### C — LLC set-conflict on specific offset bands (REJECTED)

Evicting *specific* victim offset bands would need the victim's physical addresses → violates the
no-victim-knowledge constraint. Dropped.

## 6. The design, as decided

- **Name / layout:** `codes/filltime_steer/` with `victim.c`, `attacker.c`, `config.h`,
  `aware.ini`, `flat.ini`, `rollup.py`, `ATTACK.md`; results in `experiments/filltime_steer/`.
  (Name overridable by the user; chosen to break the `_bw` convention on purpose — this is not a
  bandwidth attack.)

- **Victim (`victim.c`, core 0):** same skeleton as `blend_bw/victim.c` (named NOINLINE per-PC
  load sites `ft_pc_<j>`, disjoint regions, per-PC LCG, `__champsim_start_trace`). Each PC `j` is
  a **DUAL-TOUCH stride** stream (per §5-A): every iteration it demands **both** `line+O_short[j]`
  and `line+O_long[j]`, then advances its cursor (e.g. by `O_long[j]`, so the long touch chains
  into the next trigger and the delta-history state stays stable). Both offsets are in
  `scooby_actions` and both are demanded every step, so whichever Pythia selects is always correct
  — contention can only make it late, never wrong. `T_line[j]` is tuned via per-PC ALU-iteration
  count so each PC's `O*` crossover sits at a *different* attacker intensity.
  Contestable PCs: small `O_short` (flips to `O_long` under contention). Anchor PCs: `O_short`
  large (stays timely at max `L`). **Offset-attribution constraint (builder check #4):**
  `reward.dist[action][type]` is global per-offset, aggregated over all PCs, and the per-PC
  counter carries no reward type — so every PC's `(O_short, O_long)` pair must use **globally
  unique** offset values (disjoint across all PCs and anchors) for gate B to be per-PC
  attributable. Exact `(O_short, O_long, q, ALU, #PCs)` tuning is left to the builder (§7),
  bounded by the two-sided constraint: `O_short` small enough that reachable `L` makes it
  untimely, large enough that at idle it is timely (so the idle baseline prefers short).

- **Attacker (`attacker.c`, core 1):** reuse `blend_bw/attacker.c`'s blind streaming body;
  disjoint 64 MiB region, no victim refs. **Intensity axis is an open question, not settled**
  (builder check #3): the dossier's bucket saturates near-binary below ~5% duty, but DRAM-queue
  *latency* vs offered load is a different curve (queue delay rises continuously toward
  utilization 1), so a steady footprint dial (idle/light/medium/heavy) *may* stay graded where
  the bucket did not. **Primary:** steady footprint dial. **Fallback (if victim fill latency also
  saturates near-binary):** adopt `blend_bw`'s time-toggled attacker — toggle contention ON/OFF at
  a duty `d`, so the victim learns against a duty-weighted *average* fill latency and `d` becomes
  the graded axis. The first experiment measures latency-vs-intensity to decide which attacker
  ships; gates A/C are defined on whichever axis proves graded.

- **Configs:**
  - `aware.ini`: base reward on, `scooby_reward_correct_timely = 20`,
    `scooby_reward_correct_untimely = 12`, `scooby_high_bw_thresh = 4` (bucket ignored),
    `scooby_enable_hbw_reward = false`, `scooby_enable_per_pc_stats = true`.
  - `flat.ini` (**decisive isolation control**): identical to `aware.ini` **except**
    `scooby_reward_correct_untimely = 20` (= timely). Timing classification collapses; the
    crossover disappears while contention is *byte-for-byte identical*. If the steer vanishes
    under `flat.ini`, it is the timing reward distinction — not slowdown, eviction, or the bucket.

- **Gates (rollup.py):**
  - **A. Distance steer:** per-PC long-offset fraction rises monotonically idle→heavy on
    contestable PCs.
  - **B. Crossover visible:** `reward.dist` shows contestable `O_short` timely-fraction collapsing
    while `O_long` timely-fraction holds, as intensity rises.
  - **C. Selectivity:** contestable PCs flip in `O_short` order; anchor PCs' long-fraction stays
    put (|Δ| small).
  - **D. Isolation (decisive):** `flat.ini` heavy — same contention, long-fraction unmoved.
  - **D′. No `−8` contamination (guards D):** on contestable offsets the `incorrect` column of
    `reward.dist` stays ≈ 0 across all intensities — proving the crossover is provably
    timely↔untimely (dual-touch holding), so `flat.ini`'s untimely-only knob genuinely isolates
    the cause. A non-trivial `incorrect` fraction would mean the flip leaks through a
    knob-independent path and gate D is not clean (builder check #2).
  - **E. Bandwidth-orthogonal:** `is_high_bw()` never fires; `scooby_reward_*_high_bw` counts are
    all 0; degree distribution held. (If the bucket were doing the work, this gate fails.)
  - **F. Benign co-location control:** an LLC-resident (non-DRAM) neighbor ≈ idle (mere
    co-location does nothing).

## 7. Left to the builder

- Victim parameter tuning so each PC's `O*` crossover lands at a distinct, reachable attacker
  intensity (the central tuning loop; mirror how `blend_bw/config.h` documents its band
  rationale). Expect iteration: measure `reward.dist` timely-fraction vs intensity, adjust
  `O_short/O_long/ALU`.
- Number of PCs (suggest 4–6: 2–3 contestable spanning the intensity range + 2 anchors).
- Attacker intensity levels (footprint sizes) and whether a 4th "very heavy" level is needed to
  push the top contestable PC's crossover.
- Gate numeric thresholds (monotonicity tolerance, anchor |Δ| bound, timely-fraction collapse
  cutoff), in the style of the existing `rollup.py` gate blocks.
- Run length: start at the `blend_bw` SIM budget; confirm SARSA settles the argmax flip (the
  `+20` vs `+12` 8-point margin is the open convergence question — document the settling budget
  found, as `blend_bw` documented its 50M).
- Whether the stretch PT-horizon abstain (B) shows up; if so, report as a bonus, clearly labelled.

## 8. Open empirical questions (honest scope)

1. Is the `+20/+12` 8-point margin enough for SARSA's argmax to flip reliably at reachable `L`?
   (Comparable to the `−4/−8` 4-point margin pband exploited successfully, so plausible — but to
   be shown, not assumed.)
2. Does the attacker's steady LLC/DRAM contention raise victim *fill* latency enough to cross
   `O*` for the contestable PCs without the victim's own throttling (MSHR-full prefetch drops)
   confounding it? `flat.ini` isolates the reward-classification cause **only** while gate D′
   holds (incorrect ≈ 0); dual-touch is what keeps D′ true, so #1 and this are one risk.
3. Is the intensity→fill-latency relationship graded or near-binary (builder check #3)? Decides
   steady-footprint vs time-toggled attacker; measured in experiment 1 before gates A/C are set.
4. Reachable crossover range — which `(O_short, O_long)` spreads are actually flippable within
   the intensity/duty the single DRAM channel allows.

A negative on (1)/(2) is still reportable: it would sharpen the claim that Pythia's *timeliness*
reward is harder to weaponize than its *bandwidth-indexed* reward — a useful boundary on the
dossier's thesis.
