/*
 * attacker.c - 'filltime_steer' attacker workload (runs on core 1).
 *
 * Blind streaming RATE dial (spec 6). The attacker's only lever is its own sustained
 * DRAM request rate, which raises shared LLC/DRAM-queue latency and therefore the
 * victim's prefetch FILL latency L. Raising L moves the victim's timely/untimely
 * crossover O* = L/T_line, steering which prefetch distance Pythia learns -- all with
 * the DRAM-bandwidth path OFF (scooby_high_bw_thresh = 4), so the signal reaches Pythia
 * only through the base reward's timely(+20)/untimely(+12) classification.
 *
 * Usage: ./attacker <region_log2> <alu_pad>
 *   region_log2  log2 of the streamed region in bytes (capped at ATK_REGION_LOG2_MAX).
 *                >= ~23 (region >> LLC) => every load misses to DRAM (intensity high);
 *                small (e.g. 18 = 256 KiB) => LLC-resident => DRAM-quiet (benign control).
 *   alu_pad      register-only ALU ops after each streamed line. Higher => lower DRAM
 *                request rate => lower shared-queue latency (the graded intensity dial).
 *
 * This attacker is BLIND and OPEN-LOOP: it references only its own region, reads nothing
 * about the victim, and never observes whether the attack is working.
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions.
 *
 * -DFT_SELFTEST builds a finite-loop variant that prints "loads <n> alu <m>" for the
 * rate-dial check in tests/test_attacker_selftest.py.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

/* full 64 MiB buffer: streaming it (region >> LLC) makes every heavy load miss */
static volatile uint8_t region[ATK_REGION_HEAVY];

int
main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: %s <region_log2> <alu_pad>\n", argv[0]);
        return 2;
    }
    uint64_t region_log2 = strtoull(argv[1], NULL, 0);
    uint64_t alu_pad     = strtoull(argv[2], NULL, 0);
    if (region_log2 > ATK_REGION_LOG2_MAX) region_log2 = ATK_REGION_LOG2_MAX;

    uint64_t size = (1UL << region_log2);          /* effective footprint, power of two */
    uint64_t mask = size - 1UL;

    uint64_t step = 0;                 /* PERSISTENT stream cursor (keeps missing LLC) */
    volatile uint64_t sink = 0;
    uint64_t a = 0x9e3779b97f4a7c15ULL;

#ifdef FT_SELFTEST
    uint64_t loads = 0, alu = 0;
    for (uint64_t it = 0; it < ATK_SELFTEST_ITERS; it++) {
        size_t off = (size_t)((step * LINE_BYTES) & mask);
        sink += region[off];
        step++; loads++;
        for (uint64_t k = 0; k < alu_pad; k++) {
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            sink += (a >> 33); alu++;
        }
    }
    printf("loads %llu alu %llu\n", (unsigned long long)loads, (unsigned long long)alu);
    asm volatile("" : : "r"(sink), "r"(a));
    return 0;
#else
    __champsim_start_trace();
    while (1) {
        size_t off = (size_t)((step * LINE_BYTES) & mask);
        sink += region[off];               /* heavy: misses LLC => DRAM read */
        step++;
        for (uint64_t k = 0; k < alu_pad; k++) {
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            sink += (a >> 33);
        }
    }
    asm volatile("" : : "r"(sink), "r"(a));
    return 0;
#endif
}
