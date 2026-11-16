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
 * The victim keeps pband_bw's STRUCTURE (six mixed-predictability PCs, disjoint 1 MiB
 * regions, non-action noise, ALU density, blend_pc_<j> load sites) but DEVIATES in the
 * per-PC predictabilities, chosen empirically so the time-toggle drives FULL, ISOLATED
 * flips. Two constraints bound the contestable band:
 *   - Upper: pband's p=0.30/0.33 only reach PARTIAL abstention (f0~0.36) because the
 *     measured blend fraction d saturates (~0.78 at 10M, ~0.87 at 50M; a nonzero OFF
 *     phase lets the throttled victim under-sample its own ON phase). p must be low
 *     enough that, at the reachable d, the HBW reward drives f0 past 0.5.
 *   - Lower: p must stay comfortably ABOVE the NORMAL-reward break-even (0.143), or raw
 *     contention tips it to abstain even with the HBW table OFF -- which breaks the
 *     isolation control. (Observed: p=0.16 abstained under the blind config too.)
 * The clean band is ~[0.21, 0.27]. The three contestable PCs use 0.21, 0.24, 0.27, whose
 * formula flip duties d_crit(p)=(28p-4)/(8-6p) are 0.28 / 0.42 / 0.56 -- all below the
 * ~0.87 reachable ceiling. NOTE: full flips need the LONG run (SIM=50M); at 10M the agent
 * under-settles and f0 caps below 0.5. The measurement half (blend_pc_<j>, nm mapping on
 * build/blend_bw_victim.out) is unchanged from pband.
 *
 * Python-reference provenance (STRUCTURE from pband; p-values tuned for blend flips):
 *   PCS   = [(0.21,3),(0.24,4),(0.27,5),(0.45,11),(0.65,12),(0.90,22)]
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
/* IDENTICAL to pband_bw. Six load PCs, one disjoint 1 MiB region each. */
#define VICTIM_N_PC                6
#define VICTIM_REGION_LINES_PER_PC (1UL << 14)                         /* 16384 lines */
#define VICTIM_REGION_BYTES_PER_PC (VICTIM_REGION_LINES_PER_PC * LINE_BYTES) /* 1 MiB */

/* Per-PC (p, signature). Signatures are members of scooby_actions and avoid +1
 * (the featurewise action-fallback attractor). p is the probability the PC advances
 * by its signature; otherwise it advances by a NOISE delta. The three contestable PCs
 * (0.21, 0.24, 0.27) sit in the clean band ~[0.21, 0.27]: low enough that the HBW reward
 * drives f0 past 0.5 at the reachable duty (flip duties d_crit 0.28/0.42/0.56), high
 * enough above the normal break-even (0.143) that raw contention alone does NOT flip them
 * (so the blind isolation control stays flat). The three PCs with p >= 0.45 sit above
 * p*(d) for every reachable d and never abstain -> anchors. (These p's deviate from
 * pband_bw on purpose; see the file header.) */
#define VICTIM_PC_P    { 0.21, 0.24, 0.27, 0.45, 0.65, 0.90 }
#define VICTIM_PC_SIG  {    3,    4,    5,   11,   12,   22 }

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
