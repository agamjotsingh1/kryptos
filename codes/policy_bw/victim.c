/*
 * victim.c - 'policy_bw' victim workload (runs on core 0).
 *
 * The CONTESTABLE victim (ATTACK_METHODOLOGY.md §4). A single load PC whose line
 * address advances by a delta drawn i.i.d. UNIFORM from {1,3,4,5} cache lines
 * each iteration, wrapped to a 4 MiB region, followed by one register-only ALU
 * op. With four equiprobable deltas and no predictive state, any single Pythia
 * action is correct with probability p ~= 0.25 -- inside the reward EV-flip band
 * (0.143 < p < 0.353):
 *
 *   - under the NORMAL reward table a nonzero delta still wins (prefetch/gamble),
 *   - under the HIGH-BANDWIDTH reward table (harsher 'incorrect', gentler 'none')
 *     abstaining (action 0) wins.
 *
 * So when a bandwidth-hungry neighbor on core 1 saturates the shared DRAM bucket,
 * the victim's scooby reads that bucket as its own level, trips the high-bw reward
 * regime, and this victim collapses from gamble -> abstain. The DEGREE curve is
 * pinned equal in both configs, so any policy movement is reward-shaping alone.
 *
 * NOTE on the RNG: the reference generator uses Python's Mersenne Twister; an
 * exact replay is not portable. The attack only needs the STATISTICAL pattern --
 * i.i.d. uniform over {1,3,4,5}, no exploitable structure -- which a decorrelated
 * LCG stream (top 2 bits) reproduces (any single action correct ~1/4).
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions, so no
 * iteration count is needed. A seed may be passed as argv[1] to vary the stream.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

/* i.i.d.-uniform delta set (all members of scooby_actions). */
static const uint64_t DELTAS[4] = { 1, 3, 4, 5 };

/* One byte per line drives the miss/hit stream, but a full 4 MiB buffer gives
 * each touched line a distinct cache line / set like real addresses. */
static volatile uint8_t region[VICTIM_REGION_BYTES];

int
main(int argc, char **argv)
{
    uint64_t rng  = (argc > 1) ? strtoull(argv[1], NULL, 0) : 1ULL;  /* seed */

    uint64_t line = 0;                            /* advanced by a random delta */
    volatile uint64_t sink = 0;                   /* consume the load           */
    uint64_t a = 0x9e3779b97f4a7c15ULL, b = 1, c = 3;  /* ALU-op operands       */

    __champsim_start_trace();

    while (1) {
        /* --- pick delta i.i.d. uniform from {1,3,4,5} (LCG, top 2 bits) --- */
        rng = rng * 6364136223846793005ULL + 1442695040888963407ULL;
        uint64_t delta = DELTAS[(rng >> 62) & 3];

        /* --- single load PC: line += delta, wrapped to the 4 MiB region --- */
        line = (line + delta) % VICTIM_REGION_LINES;
        size_t off = (size_t)(line * LINE_BYTES);
        sink += region[off];

        /* --- register-only ops: cheap, no memory, just throttle issue rate --- */
        for (int k = 0; k < VICTIM_ALU_PER_LOAD; k++) {
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            b = (b ^ (a >> 13)) + c;
            c = (c << 1) | (c >> 63);
        }
    }

    /* unreachable; defeats dead-code elimination of sink/a/b/c */
    asm volatile("" : : "r"(sink), "r"(a), "r"(b), "r"(c));
    return 0;
}
