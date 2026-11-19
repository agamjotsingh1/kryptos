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
 * per-PC predictabilities. Prior attempts: three clustered contestable PCs
 * (0.21/0.24/0.27) flipped together as a BLOCK (no staircase; ATTACK.md 8), and two PCs
 * at the band extremes (0.21, 0.33) still flipped together (the +1 fallback washes out
 * per-PC learnability). The staircase is not resolvable here, so the CURRENT goal is to
 * cleanly VISUALISE the duty dial instead: FIVE contestable PCs densely sampling the
 * reachable band, read out as one line per duty. Two constraints bound the band:
 *   - Upper: p < p*(d=1)=0.353, and the measured blend fraction d saturates (~0.78 at
 *     10M, ~0.89 at 50M; a nonzero OFF phase lets the throttled victim under-sample its
 *     own ON phase). p=0.33 sits just under the ceiling.
 *   - Lower: p must stay comfortably ABOVE the NORMAL-reward break-even (0.143), or raw
 *     contention tips it to abstain even with the HBW table OFF -- which breaks the
 *     isolation control. (Observed: p=0.16 abstained under the blind config too.)
 * NOTE: full flips (f0 > 0.5) need the LONG run (SIM=50M); at 10M the agent under-settles
 * and absolute f0 is lower, but the three duty lines still separate (the dial is a
 * relative effect). The measurement half (blend_pc_<j>, nm mapping on
 * build/blend_bw_victim.out) is unchanged from pband.
 *
 * Reference provenance (STRUCTURE from pband; p-values bracket the p*(d) cutoffs):
 *   PCS   = [(0.185,3),(0.20,4),(0.225,5),(0.25,10),(0.275,11),(0.295,12),(0.325,22),(0.40,23)]
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
/* TWO load PCs, one disjoint 1 MiB region each (policy_target setpoint controller).
 * PC0 = the CONTESTABLE TARGET (p=0.31): its abstain fraction f0 sweeps smoothly across
 * the reachable duty ramp, so a calibrated duty PLACES f0 at a chosen setpoint. PC1 =
 * the ANCHOR (p=0.55, above the max reachable p*(d)=0.353): never abstains, proving the
 * controller aims at the contestable load, not a blanket slowdown. Operating point fixed
 * from the realized blend_bw 50M ramp (p=0.24 was too steep; 0.30-0.32 is gentle). */
#define VICTIM_N_PC                2
#define VICTIM_REGION_LINES_PER_PC (1UL << 14)                         /* 16384 lines */
#define VICTIM_REGION_BYTES_PER_PC (VICTIM_REGION_LINES_PER_PC * LINE_BYTES) /* 1 MiB */

/* Per-PC (p, signature). Signatures are members of scooby_actions and avoid +1
 * (the featurewise action-fallback attractor). p is the probability the PC advances
 * by its signature; otherwise it advances by a NOISE delta.
 *
 * STAIRCASE BY p*(d) BRACKETING (current). The abstain cutoff at blend fraction d is
 * p*(d) = (4+8d)/(28+6d). At the three measured duties d ~ 0.27 / 0.53 / 0.76 the cutoffs
 * are p* ~ 0.208 / 0.264 / 0.310. A PC abstains at duty d iff its p < p*(d). Placing TWO
 * PCs in each band between consecutive cutoffs makes the sweep resolve as a +2 staircase:
 *   band              PCs (p)        abstains at
 *   p  < 0.208        0.185, 0.200   all three duties (lo, mid, hi)
 *   0.208..0.264      0.225, 0.250   mid and hi
 *   0.264..0.310      0.275, 0.295   hi only
 *   p  > 0.310        0.325, 0.400   never (reachable d) -> anchors
 * So d_lo should flip 2 PCs, d_mid 4, d_hi 6: each higher duty line crosses the abstain
 * threshold two PCs further right. Lower bound caveat: 0.185 sits only ~0.025 above the
 * isolation floor (p=0.16 abstained even blind) -- watch the blind control there. NOTE:
 * at SIM=10M the agent under-settles (absolute f0 lower than at 50M), so the lines may
 * sit below 0.5 even where the model predicts a flip; the staircase ORDER is the readout.
 * The plot draws each duty's predicted cutoff p*(bw3) as a vertical line in that duty's
 * colour, so observed vs predicted flip is visible directly. */
/* PC0 contestable p=0.31 (above the NORMAL break-even 0.143, so blind/normal-reward
 * gambles -> f0~0, isolation clean; sweeps f0 low->high across reachable d). PC1 anchor
 * p=0.55 (above max reachable p*(d), holds). Signatures 4,11 are members of scooby_actions
 * and avoid +1. Exact p (0.30-0.32) / anchor p / ALU fixed in the spike against the ramp. */
#define VICTIM_PC_P    { 0.31, 0.55 }
#define VICTIM_PC_SIG  {    4,   11 }

/* Non-action noise deltas: deliberately NOT in scooby_actions, so Pythia can only
 * ever be correct on the signature -> a clean per-PC fingerprint. */
#define VICTIM_NOISE   { 7, 8, 9, 13, 14 }
#define VICTIM_N_NOISE 5

/* Register-only ALU work after each load. Beyond keeping victim self-bandwidth low, the
 * ALU density sets the victim's Q-update RATE relative to the attacker's toggle: MORE ALU
 * -> fewer triggers per toggle period -> each phase contributes fewer SARSA updates -> Q
 * integrates across MORE phases -> the blended-Q crossover tracks p*(d) with a smaller
 * over-abstention offset (lever 3, orthogonal to the attacker period). Raised 2 -> 16 to
 * shrink the residual offset the fast-toggle sweep bottomed out at. */
#define VICTIM_ALU_ITERS 16

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
