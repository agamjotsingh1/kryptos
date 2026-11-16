/*
 * config.h - shared parameters for the 'blend_bw' attack.
 *
 * Time-toggled duty-cycle policy steering (blend_bw_methodology). Same shared channel
 * and reward lever as pband_bw: the attacker's only lever is its own DRAM read rate,
 * which pushes the global DRAM-bandwidth bucket the victim's Pythia (scooby) reads as
 * its own level. Under the aware config, bucket 3 swaps in the high-bandwidth reward
 * table (harsher 'incorrect', gentler 'none').
 *
 * What differs from pband_bw is the ATTACKER. pband showed the instantaneous lever is
 * an on/off switch (bucket saturates at <5% instantaneous duty, is_high_bw() is a hard
 * threshold). blend_bw toggles that switch IN TIME, fast enough that the victim's SARSA
 * Q-values never settle into either regime. The victim then learns against a
 * time-average of the normal and high-bw reward tables, so the EV-flip break-even
 *
 *     p*(d) = (4 + 8d) / (28 + 6d)
 *
 * (d = blend fraction = fraction of time the bucket reads high) becomes CONTINUOUS.
 * Raising d sweeps p* from 0.143 (d=0) up to 0.353 (d=1), crossing the victim's PCs in
 * predictability order: a binary switch becomes a dial.
 *
 * The victim keeps pband_bw's STRUCTURE (mixed-predictability PCs, disjoint 1 MiB
 * regions, non-action noise, ALU density, blend_pc_<j> load sites) but DEVIATES in the
 * per-PC predictabilities. The FIRST blend_bw attempt clustered three contestable PCs at
 * 0.21/0.24/0.27 (a 0.06-wide band); they flipped together as a BLOCK -- the ordered
 * staircase never resolved (ATTACK.md 8). ROOT CAUSE: the featurewise +1 action-fallback
 * washes out per-PC learnability, so p's 0.03 apart are indistinguishable, and the
 * observed flip duty lags the EV model by ~+0.5 (all PCs pile at the d ceiling). The
 * REDESIGN uses only TWO contestable PCs at the band EXTREMES (0.21, 0.33) for maximum
 * p-separation. Two constraints still bound the band:
 *   - Upper: p < p*(d=1)=0.353, and the measured blend fraction d saturates (~0.78 at
 *     10M, ~0.89 at 50M; a nonzero OFF phase lets the throttled victim under-sample its
 *     own ON phase). p=0.33 sits just under the ceiling -> flips only near max duty.
 *   - Lower: p must stay comfortably ABOVE the NORMAL-reward break-even (0.143), or raw
 *     contention tips it to abstain even with the HBW table OFF -- which breaks the
 *     isolation control. (Observed: p=0.16 abstained under the blind config too.)
 * d_crit(p)=(28p-4)/(8-6p): 0.21->0.28, 0.33->0.87. NOTE: full flips need the LONG run
 * (SIM=50M); at 10M the agent under-settles and f0 caps below 0.5. The measurement half
 * (blend_pc_<j>, nm mapping on build/blend_bw_victim.out) is unchanged from pband.
 *
 * Reference provenance (STRUCTURE from pband; p-values tuned for a 2-step staircase):
 *   PCS   = [(0.21,3),(0.33,5),(0.45,11),(0.65,12),(0.90,22)]
 *   NOISE = (7, 8, 9, 13, 14)
 *   ALU   = 12
 *   region_lines_per_pc = 1<<14
 */
#ifndef KRYPTOS_BLEND_BW_CONFIG_H
#define KRYPTOS_BLEND_BW_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride in multiples of this. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
/* FIVE load PCs, one disjoint 1 MiB region each. (pband_bw used six; blend_bw drops
 * to TWO contestable PCs so the staircase has the widest possible p-separation.) */
#define VICTIM_N_PC                5
#define VICTIM_REGION_LINES_PER_PC (1UL << 14)                         /* 16384 lines */
#define VICTIM_REGION_BYTES_PER_PC (VICTIM_REGION_LINES_PER_PC * LINE_BYTES) /* 1 MiB */

/* Per-PC (p, signature). Signatures are members of scooby_actions and avoid +1
 * (the featurewise action-fallback attractor). p is the probability the PC advances
 * by its signature; otherwise it advances by a NOISE delta.
 *
 * STAIRCASE REDESIGN. The earlier triplet (0.21, 0.24, 0.27) was clustered in a
 * 0.06-wide band: all three flipped together as a BLOCK (no ordered staircase; see
 * ATTACK.md 8). The featurewise +1 fallback washes out per-PC learnability, so three
 * p's 0.03 apart cannot resolve. We now use only TWO contestable PCs at the EXTREMES of
 * the clean band ~[0.21, 0.33]:
 *   PC0 p=0.21  d_crit=(28p-4)/(8-6p)=0.28  -> should flip at a LOW duty
 *   PC1 p=0.33  d_crit=0.87                 -> should flip only near the ceiling
 * Max separation gives the best chance of a visible 2-step staircase (PC0 before PC1).
 * Lower bound 0.21: below it raw contention flips the PC even blind (isolation breaks).
 * Upper bound 0.33 < p*(d=1)=0.353: still contestable, but near the reachable d ceiling
 * (~0.89), so PC1 may only flip marginally -- the open empirical question this re-run
 * tests. The PCs with p >= 0.45 sit above p*(d) for every reachable d -> anchors. */
#define VICTIM_PC_P    { 0.21, 0.33, 0.45, 0.65, 0.90 }
#define VICTIM_PC_SIG  {    3,    5,   11,   12,   22 }

/* Non-action noise deltas: deliberately NOT in scooby_actions, so Pythia can only
 * ever be correct on the signature -> a clean per-PC fingerprint. */
#define VICTIM_NOISE   { 7, 8, 9, 13, 14 }
#define VICTIM_N_NOISE 5

/* Register-only ALU work after each load (keeps victim self-bandwidth low so the
 * low-duty baseline is clean). 2 C iterations ~= the reference's 12 ALU instr/load. */
#define VICTIM_ALU_ITERS 2

/* ---------------------------------------------------------------- attacker -- */
/* TIME-TOGGLED duty cycle (blend_bw_methodology). The attacker alternates:
 *   ON  phase: stream `on_lines` fresh lines of a 64 MiB region (every load misses
 *              LLC -> DRAM read traffic -> pushes the shared bucket toward 3).
 *   OFF phase: `off_iters` pure register-ALU ops (no loads -> no DRAM -> the bucket's
 *              EWMA decays back below the high-bw threshold).
 * on_lines/off_iters are passed as argv (matrix -> gen_trace -> program args), so the
 * toggle PERIOD and DUTY are both tunable without recompiling. The EFFECTIVE blend
 * fraction d is whatever bw-level histogram the victim actually observes; rollup.py
 * reports it as bw3 and uses THAT as d (not the nominal on:off ratio). The two
 * extremes reproduce pband_bw exactly: off_iters=0 => pure heavy (d~1), on_lines=0 =>
 * pure idle (d~0). */
#define ATK_REGION_HEAVY   (1UL << 26)       /* 64 MiB - always misses LLC */

#endif /* KRYPTOS_BLEND_BW_CONFIG_H */
