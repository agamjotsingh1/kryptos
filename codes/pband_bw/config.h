/*
 * config.h - shared parameters for the 'pband_bw' attack.
 *
 * Multi-PC p-band policy steering (ATTACK_METHODOLOGY.md §4b). Same shared channel
 * and reward lever as policy_bw: the attacker's only lever is its own DRAM read rate,
 * which pushes the global DRAM-bandwidth bucket the victim's Pythia (scooby) reads as
 * its own level. Under the aware config, bucket 3 swaps in the high-bandwidth reward
 * table (harsher 'incorrect', gentler 'none').
 *
 * What differs from policy_bw is the VICTIM: six load PCs of differing predictability.
 * Each PC's fate is decided by its realized correctness vs the EV-flip edge
 * (p ~= 0.35-0.40): contestable PCs collapse to abstain, predictable PCs keep
 * prefetching their signature. One blind, BINARY switch (idle/heavy) therefore drives
 * a differentiated per-PC joint policy.
 *
 * Python-reference provenance (keep in lockstep with ~/ACA/Pythia/experiments/codes):
 *   PBAND_PCS   = [(0.30,3),(0.33,4),(0.45,5),(0.55,11),(0.75,12),(0.95,22)]
 *   PBAND_NOISE = (7, 8, 9, 13, 14)
 *   PBAND_ALU   = 12
 *   region_lines_per_pc = 1<<14
 *   attacker = gen_attacker_dutycycle(duty in {0.0, 1.0}, heavy_region_bytes=1<<26)
 */
#ifndef KRYPTOS_PBAND_BW_CONFIG_H
#define KRYPTOS_PBAND_BW_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride in multiples of this. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
#define VICTIM_N_PC                6
#define VICTIM_REGION_LINES_PER_PC (1UL << 14)                         /* 16384 lines */
#define VICTIM_REGION_BYTES_PER_PC (VICTIM_REGION_LINES_PER_PC * LINE_BYTES) /* 1 MiB */

/* Per-PC (p, signature). Signatures are members of scooby_actions and avoid +1
 * (the featurewise action-fallback attractor). The p column is the probability the
 * PC advances by its signature; otherwise it advances by a NOISE delta. */
#define VICTIM_PC_P    { 0.30, 0.33, 0.45, 0.55, 0.75, 0.95 }
#define VICTIM_PC_SIG  {    3,    4,    5,   11,   12,   22 }

/* Non-action noise deltas: deliberately NOT in scooby_actions, so Pythia can only
 * ever be correct on the signature -> a clean per-PC fingerprint. */
#define VICTIM_NOISE   { 7, 8, 9, 13, 14 }
#define VICTIM_N_NOISE 5

/* Register-only ALU work after each load. The Python trace emits PBAND_ALU = 12
 * single ALU instructions per load; one iteration of the C throttle loop compiles to
 * ~6 register ops (imul/add/shr/xor/add/rol), so 2 iterations reproduce the trace's
 * ~12-instruction-per-load density. This keeps the victim's own DRAM traffic low so
 * the attacker-idle baseline is clean (bw3 ~= 0). */
#define VICTIM_ALU_ITERS 2

/* ---------------------------------------------------------------- attacker -- */
/* BINARY switch (spike finding: the bucket saturates at <5% duty and is_high_bw()
 * is a single threshold, so intermediate intensities give no gradation).
 *   idle  (duty 0.0): pure register ALU, no loads   -> bucket ~0
 *   heavy (duty 1.0): stream 64 MiB (>> LLC)        -> saturates bucket 3 */
#define ATK_REGION_HEAVY   (1UL << 26)       /* 64 MiB - always misses LLC */

#endif /* KRYPTOS_PBAND_BW_CONFIG_H */
