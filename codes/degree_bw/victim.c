/*
 * victim.c - 'degree_bw' victim workload (runs on core 0).
 *
 * A single load PC whose address advances by +1 cache line each iteration,
 * wrapped to a small (2 MiB) region, followed by a handful of register-only ALU
 * ops that throttle the issue rate so steady-state self-DRAM traffic stays ~0
 * once the region warms into the cache.
 *
 * Pythia (scooby) trivially learns the constant +1-line delta (action +1) and
 * ramps its prefetch degree. This is the victim being *steered*: a bandwidth-
 * hungry neighbor on core 1 pushes the shared DRAM bucket high enough that the
 * victim's scooby reads it as its own bandwidth level, trips its high-bandwidth
 * path, and collapses the victim's prefetch degree to 1.
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions, so no
 * iteration count is needed.
 */
#include <stdint.h>
#include <stdio.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

/* One byte per line is enough to drive the miss/hit stream, but a full buffer
 * gives each touched line a distinct cache line / set like real addresses. */
static volatile uint8_t region[VICTIM_REGION_BYTES];

int
main(void)
{
    uint64_t it = 0;                              /* drives the +1-line stride */
    volatile uint64_t sink = 0;                   /* consume the load          */
    uint64_t a = 0x9e3779b97f4a7c15ULL, b = 1, c = 3;  /* ALU-op operands      */

    __champsim_start_trace();

    while (1) {
        /* --- single load PC: address advances +1 line, wraps at the region --- */
        size_t off = (size_t)((it * LINE_BYTES) % VICTIM_REGION_BYTES);
        sink += region[off];
        it++;

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
