/*
 * attacker.c - 'blend_bw' attacker workload (runs on core 1).
 *
 * TIME-TOGGLED duty-cycle neighbor (blend_bw_methodology). pband_bw showed the
 * attacker's lever is an on/off switch: the shared DRAM bucket saturates at <5%
 * *instantaneous* duty and is_high_bw() is a hard threshold, so there is no graded
 * instantaneous bandwidth dial. blend_bw toggles that switch IN TIME, fast enough that
 * the victim's SARSA Q-values never settle into either regime. The victim then learns
 * against a time-average of the normal and high-bandwidth reward tables, and the
 * EV-flip break-even p*(d) = (4+8d)/(28+6d) becomes a CONTINUOUS function of the blend
 * fraction d (the fraction of time the bucket reads high). A binary switch becomes a
 * dial: raising d sweeps p* upward through the victim's PCs, flipping them to abstain
 * one at a time in order of predictability.
 *
 * This attacker is still BLIND and OPEN-LOOP: it reads nothing about the victim; its
 * only lever is its own DRAM read rate, toggled on a fixed schedule set in advance.
 *
 *   ON  phase: stream `on_lines` fresh 64 MiB-region lines (every load misses LLC ->
 *              DRAM read traffic -> pushes the shared bucket toward 3).
 *   OFF phase: `off_iters` pure register-ALU ops (no loads -> no DRAM -> the bucket's
 *              EWMA decays back below the high-bw threshold).
 * Then repeat. The toggle PERIOD is (on_lines + off_iters) in their own cost units and
 * the nominal duty is on:off; the EFFECTIVE blend fraction d is whatever bw-level
 * histogram the victim actually observes (rollup.py reports it as bw3 and treats THAT
 * as d). The stream cursor PERSISTS across ON phases, so successive bursts touch fresh
 * lines and keep missing (64 MiB >> LLC). The two extremes reproduce pband_bw exactly:
 * off_iters=0 => pure heavy (d~1); on_lines=0 => pure idle (d~0).
 *
 * WINDOW CAVEAT (blend_bw_methodology 4): a STABLE intermediate exists only if
 *     bucket epoch (256 cyc)  <<  toggle period  <<  Q-value settling time.
 *   - Toggle too fast -> the bucket's EWMA erases the off-phases; the gate reads high
 *     continuously and you are back to a heavy switch (d~1). No blend.
 *   - Toggle too slow -> the victim's Q-values fully converge to the HBW policy each ON
 *     phase and fully relearn each OFF phase: thrashing between two pinned policies, not
 *     a stable intermediate. No blend.
 * Whether that window is non-empty for Pythia's learning rate and epoch length is the
 * empirical question this experiment asks. Both on_lines and off_iters are exposed so
 * the period (their magnitude) can be swept independently of the duty (their ratio). An
 * empty window -- every duty collapsing to the pband_bw on/off result -- is itself a
 * reportable negative that hardens the "the lever is binary" claim.
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions.
 *
 * Usage: ./attacker <on_lines> <off_iters>
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

/* full 64 MiB buffer: streaming it (region >> LLC) makes every ON-phase load miss */
static volatile uint8_t region[ATK_REGION_HEAVY];

int
main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <on_lines> <off_iters>\n", argv[0]);
        return 2;
    }
    uint64_t on_lines  = strtoull(argv[1], NULL, 0);   /* heavy burst length (lines) */
    uint64_t off_iters = strtoull(argv[2], NULL, 0);   /* idle burst length  (iters) */

    uint64_t step = 0;                 /* PERSISTENT stream cursor (keeps missing LLC) */
    volatile uint64_t sink = 0;
    uint64_t a = 0x9e3779b97f4a7c15ULL; /* idle-path ALU seed */

    __champsim_start_trace();

    while (1) {
        /* ON: saturate the shared DRAM-read bucket */
        for (uint64_t i = 0; i < on_lines; i++) {
            size_t off = (size_t)((step * LINE_BYTES) % ATK_REGION_HEAVY);
            sink += region[off];       /* every access misses LLC => DRAM read */
            step++;
        }
        /* OFF: no DRAM traffic -> the bucket's EWMA decays below the high-bw threshold */
        for (uint64_t i = 0; i < off_iters; i++) {
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            sink += (a >> 33);
        }
    }

    asm volatile("" : : "r"(sink), "r"(a));
    return 0;
}
