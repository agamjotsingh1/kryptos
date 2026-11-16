/*
 * config.h - shared parameters for the 'filltime_steer' attack.
 *
 * Fill-timing prefetch-distance steering (spec: docs/superpowers/specs/
 * 2026-11-16-filltime-steer-design.md). UNLIKE the four bandwidth attacks, the
 * DRAM-bandwidth path is OFF here (every scooby ini uses scooby_high_bw_thresh = 4,
 * so the bucket maxes at 3 and is_high_bw() never fires). The only way the attacker's
 * contention reaches the victim's Pythia is through the BASE reward's timely(+20) vs
 * untimely(+12) classification -- a pure timing signal.
 *
 * ---- DUAL-TOUCH VICTIM (the correctness crux, spec 5-A) ----
 * Each PC demands BOTH line+O_short AND line+O_long every period, from a common trigger
 * (the `base` access). So whichever offset Pythia selects as its action is ALWAYS
 * demand-reused (always correct); contention can only make the chosen action LATE
 * (untimely +12), never WRONG (incorrect -8). Timing is the sole separator -- that is
 * what makes this a timing channel and not another branch-probability EV flip.
 *
 * Per period, the load site ft_pc_<j> issues three loads:
 *     load(base), load(base+O_short), load(base+O_long);  base += PERIOD[j]
 * with PERIOD[j] = O_long[j] + GAP (GAP not in scooby_actions, so the non-base triggers
 * have no correct action in the set and contribute a constant background -- they do not
 * confound the short-vs-long signal, which lives in the base-trigger state).
 *
 * ---- PER-PC OFFSET TABLE (globally unique; never offset 1) ----
 *   PC  role          O_short  O_long   note
 *    0  contestable      3       10     small O_short -> flips short->long first
 *    1  contestable      4       11
 *    2  contestable      5       12     flips last
 *    3  anchor          22       30     large O_short -> stays timely at max L
 *    4  anchor          23       32
 * All ten offsets are members of scooby_actions (1,3,4,5,10,11,12,22,23,30,32,...) and
 * globally unique, so reward.dist[action][type] (aggregated over all PCs) is per-PC
 * attributable. Offset 1 is excluded (featurewise +1 fallback attractor).
 *
 * O_short/O_long tiny vs scooby_pt_size (256) -> the prefetch-tracker never evicts them
 * before their demand -> the -8 incorrect path is structurally absent (gate D').
 *
 * ALU and PERIOD-gap are tuning knobs (set T_line, hence the crossover O*=L/T_line);
 * tuned in Task 7 against the gates. Start from the blend_bw ALU density (2).
 */
#ifndef KRYPTOS_FILLTIME_STEER_CONFIG_H
#define KRYPTOS_FILLTIME_STEER_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride in multiples of this. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
#define VICTIM_N_PC                5
#define VICTIM_REGION_LINES_PER_PC (1UL << 14)                          /* 16384 lines */
#define VICTIM_REGION_BYTES_PER_PC (VICTIM_REGION_LINES_PER_PC * LINE_BYTES) /* 1 MiB */

/* Per-PC (O_short, O_long). Both in scooby_actions; globally unique; never 1.
 * Contestable PCs (0,1,2) have small O_short; anchors (3,4) large O_short. */
#define VICTIM_PC_OSHORT { 3, 4, 5, 22, 23 }
#define VICTIM_PC_OLONG  { 10, 11, 12, 30, 32 }

/* PERIOD[j] = O_long[j] + GAP. GAP is NOT a scooby action (so the base+O_short and
 * base+O_long triggers, reached by non-action deltas, have no correct action and stay a
 * constant background). */
#define VICTIM_PERIOD_GAP 2

/* Register-only ALU iterations after each period; sets T_line, hence the crossover O*.
 * Per-PC so each PC's crossover can be placed at a distinct attacker intensity (Task 7). */
#define VICTIM_PC_ALU { 2, 2, 2, 2, 2 }

/* Selftest only: periods per PC to emit for the dual-touch invariant check. */
#define FT_SELFTEST_ITERS 300

/* ---------------------------------------------------------------- attacker -- */
/* Filled in Task 2. */

#endif /* KRYPTOS_FILLTIME_STEER_CONFIG_H */
