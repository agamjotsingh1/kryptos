/*
 * config.h - shared parameters for the 'policy_psweep' experiment.
 *
 * This sweeps the victim's PREDICTABILITY p (the probability its best action is
 * correct) across and around the reward EV-flip band (0.143, 0.353) from
 * ATTACK_METHODOLOGY.md §4, and measures the resulting abstain fraction f0 at
 * each attacker intensity (each a different shared-DRAM bucket saturation bw3).
 *
 * The attacker is the SAME blind bandwidth neighbor as policy_bw/degree_bw: its
 * only lever is its DRAM read rate, dialed by footprint. Only the VICTIM changes
 * here -- its single load PC hits its SIGNATURE delta (a scooby action) with
 * probability p, else a NON-action noise delta, so Pythia's best possible
 * correctness for that PC is exactly p. Theory (§4) predicts:
 *   p < 0.143         : abstain wins even under normal reward  -> f0 high always
 *   0.143 < p < 0.353 : CONTESTABLE -> gamble normally, abstain under HBW reward
 *   p > 0.353         : gamble wins even under HBW reward       -> f0 ~0 (resists)
 */
#ifndef KRYPTOS_POLICY_PSWEEP_CONFIG_H
#define KRYPTOS_POLICY_PSWEEP_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride in multiples of this. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
/* Single load PC over a 4 MiB region. With probability p the line advances by
 * the SIGNATURE delta (a member of scooby_actions, NOT +1 to dodge the
 * featurewise fallback attractor); otherwise by a NOISE delta that is not any
 * scooby action, so Pythia can only ever be correct on the signature => the best
 * action's realized correctness is exactly p. A high ALU-per-load keeps the
 * victim's self-DRAM low so the attacker-idle baseline is clean (bw3 ~= 0). */
#define VICTIM_REGION_LINES  (1UL << 16)                       /* 65536 lines   */
#define VICTIM_REGION_BYTES  (VICTIM_REGION_LINES * LINE_BYTES) /* 4 MiB        */
#define VICTIM_ALU_PER_LOAD  12            /* register-only ops per load         */
#define VICTIM_SIG_DELTA     5             /* signature stride (a scooby action) */

/* Non-action noise deltas (none are members of scooby_actions). */
#define VICTIM_NOISE_N       5
#define VICTIM_NOISE_DELTAS  { 7, 8, 9, 13, 14 }

/* ---------------------------------------------------------------- attacker -- */
/* Per-intensity streaming footprint (identical to policy_bw/degree_bw). */
#define ATK_REGION_LIGHT   (2048UL * 1024)   /*  2 MiB - mostly LLC-resident  */
#define ATK_REGION_MEDIUM  (3072UL * 1024)   /*  3 MiB - partial residency    */
#define ATK_REGION_HEAVY   (1UL << 26)       /* 64 MiB - always misses LLC    */
#define ATK_REGION_MAX     ATK_REGION_HEAVY

#endif /* KRYPTOS_POLICY_PSWEEP_CONFIG_H */
