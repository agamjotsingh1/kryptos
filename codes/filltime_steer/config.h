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
 * ---- DUAL-TOUCH VICTIM: SINGLE-LOAD CONSTANT-STRIDE MARCH (spec 5-A; Task 6 ruling) ----
 * Each PC j is ONE load site ft_pc_<j> that marches a cursor by a constant stride S[j]:
 *     load(line);  line += S[j]
 * So EVERY access is a Pythia trigger, and from any trigger at line X the future demands
 * are X+S, X+2S, X+3S, ...  We choose O_short[j] and O_long[j] to be two multiples of
 * S[j] that are members of scooby_actions. Both are therefore ALWAYS future demands from
 * every trigger -> whichever offset Pythia selects is always correct; contention can only
 * make the chosen action LATE (untimely +12), never WRONG (incorrect -8). Timing is the
 * sole separator -- a timing channel, not a branch-probability EV flip.
 *
 * (The earlier 3-loads-per-period design made only 1/3 of triggers clean; the other
 * accesses were triggers in states whose correct delta was a non-action -> 98% incorrect
 * + heavy out-of-bounds. The single-load march makes every trigger a clean dual-touch.)
 *
 * ---- PER-PC TABLE (O_short, O_long multiples of S; globally unique; never offset 1) ----
 *   PC  role         S   O_short  O_long   note
 *    0  contestable  5      5       10     O_short=S, O_long=2S
 *    1  contestable  4      4       12     O_long=3S
 *    2  contestable 11     11       22     O_long=2S
 *    3  anchor       3      3       30     O_long=10S; HIGH ALU. (Empirically PC3 never
 *                                          flips -- but see ATTACK.md: it stays short
 *                                          because O_long is under-explored/OOB, NOT because
 *                                          O_short is timely; offset 3 is in fact the LEAST
 *                                          timely offset. The whole attack is a NEGATIVE.)
 * All eight offsets are in scooby_actions (1,3,4,5,10,11,12,22,23,30,32,...) and globally
 * unique, so reward.dist[action][type] (aggregated over all PCs) is per-PC attributable.
 * Offset 1 excluded (featurewise +1 fallback attractor). Offsets tiny vs scooby_pt_size
 * (256) -> prefetch-tracker never evicts them before demand -> -8 path structurally absent.
 *
 * Anchor-ness is set by T_line (ALU density), not offset magnitude: the action set is too
 * sparse for large-O_short anchors. Per-PC ALU is the crossover knob O*=L/T_line (spec 6);
 * tuned in Task 7 against the gates.
 */
#ifndef KRYPTOS_FILLTIME_STEER_CONFIG_H
#define KRYPTOS_FILLTIME_STEER_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride in multiples of this. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
#define VICTIM_N_PC                4
#define VICTIM_REGION_LINES_PER_PC (1UL << 14)                          /* 16384 lines */
#define VICTIM_REGION_BYTES_PER_PC (VICTIM_REGION_LINES_PER_PC * LINE_BYTES) /* 1 MiB */

/* Per-PC constant stride S, and (O_short, O_long) = two multiples of S that are
 * scooby_actions. Globally unique; never 1. Contestable PCs 0,1,2; anchor PC3. */
#define VICTIM_PC_STRIDE { 5, 4, 11, 3 }
#define VICTIM_PC_OSHORT { 5, 4, 11, 3 }
#define VICTIM_PC_OLONG  { 10, 12, 22, 30 }

/* Register-only ALU iterations after each access; sets T_line, hence the crossover O*.
 * Contestable PCs: low ALU (short T_line -> O_short flips to untimely under contention).
 * Anchor PC3: HIGH ALU (long T_line -> O_short stays timely at every intensity). Tuned
 * in Task 7. */
#define VICTIM_PC_ALU { 14, 14, 14, 60 }

/* Selftest only: periods per PC to emit for the dual-touch invariant check. */
#define FT_SELFTEST_ITERS 300

/* ---------------------------------------------------------------- attacker -- */
/* Blind streaming rate dial (spec 6). Usage: ./attacker <region_log2> <alu_pad>.
 * Each iteration streams one fresh line of a 2^region_log2-byte region (persistent
 * cursor -> keeps missing LLC when region >> LLC) then does alu_pad register-only ops.
 * Lower alu_pad -> higher sustained DRAM request rate -> higher shared-queue latency ->
 * longer victim fills (the graded intensity dial). region_log2 small (e.g. 18 = 256 KiB)
 * -> LLC-resident -> DRAM-quiet (the `benign` co-location control).
 * The attacker references ONLY its own region; it is blind and open-loop. */
#define ATK_REGION_LOG2_MAX 26
#define ATK_REGION_HEAVY    (1UL << ATK_REGION_LOG2_MAX)   /* 64 MiB - always misses LLC */

/* Selftest only: streaming iterations to count for the rate-dial check. */
#define ATK_SELFTEST_ITERS 200000UL

#endif /* KRYPTOS_FILLTIME_STEER_CONFIG_H */
