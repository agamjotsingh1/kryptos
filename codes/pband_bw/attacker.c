/*
 * attacker.c - 'pband_bw' attacker workload (runs on core 1).
 *
 * A blind / open-loop BINARY switch (ATTACK_METHODOLOGY.md §4b). It reads nothing
 * about the victim, has no feedback, and its only lever is its own DRAM read rate:
 *
 *   idle  (duty 0.0): pure register ALU, no loads           -> ~0 DRAM, bucket ~0
 *   heavy (duty 1.0): stream a 64 MiB region (>> LLC)       -> every load misses,
 *                     saturates the shared DRAM-read bucket (bw3 ~ 0.94)
 *
 * Why only two settings: the design spike showed the shared bucket saturates at <5%
 * duty and is_high_bw() is a single threshold, so intermediate intensities give no
 * gradation. The attacker's lever is an on/off switch, not a dial.
 *
 * The mode is selected by a command-line ARGUMENT, passed through by the trace
 * framework (matrix -> gen_trace.sh ... "<mode>"). The traced region is an
 * effectively infinite loop; PIN starts at __champsim_start_trace() and stops after
 * TRACE_INSTR instructions.
 *
 * Usage: ./attacker <idle|heavy>
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

/* full 64 MiB buffer: streaming it (region >> LLC) makes every load a miss */
static volatile uint8_t region[ATK_REGION_HEAVY];

int
main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <idle|heavy>\n", argv[0]);
        return 2;
    }
    const char *mode = argv[1];

    int do_loads;
    if      (!strcmp(mode, "idle"))  do_loads = 0;   /* duty 0.0 */
    else if (!strcmp(mode, "heavy")) do_loads = 1;   /* duty 1.0 */
    else { fprintf(stderr, "unknown mode '%s' (want idle|heavy)\n", mode); return 2; }

    uint64_t step = 0;
    volatile uint64_t sink = 0;
    uint64_t a = 0x9e3779b97f4a7c15ULL;   /* idle-path ALU seed */

    __champsim_start_trace();

    while (1) {
        if (do_loads) {
            /* heavy: +1 line each step, wrapped to 64 MiB => every access misses
             * LLC => DRAM read traffic that saturates the shared bucket */
            size_t off = (size_t)((step * LINE_BYTES) % ATK_REGION_HEAVY);
            sink += region[off];
            step++;
        } else {
            /* idle: pure register ALU, generates no DRAM traffic */
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            sink += (a >> 33);
        }
    }

    asm volatile("" : : "r"(sink), "r"(a));
    return 0;
}
