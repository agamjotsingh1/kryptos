/*
 * attacker.c - 'policy_bw' attacker workload (runs on core 1).
 *
 * Identical shared-bandwidth neighbor as degree_bw: a blind / open-loop program
 * whose ONLY lever is its own DRAM read rate, dialed by memory FOOTPRINT (not ALU
 * padding). It reads nothing about the victim; it just streams (or idles):
 *
 *   idle   : pure register ALU, no loads  -> ~0 DRAM, bucket 0
 *   light  : stream  2 MiB region         -> mostly LLC-resident, bucket ~1
 *   medium : stream  3 MiB region         -> partial residency,   bucket ~2-3
 *   heavy  : stream 64 MiB region (>> LLC) -> always misses LLC,   saturates bucket 3
 *
 * Why footprint, not ALU: ALU ops are ~free, so instruction-dilution barely
 * throttles the steady-state load rate. A smaller region raises the LLC hit rate
 * and structurally lowers the DRAM rate; a region >> LLC makes every load a miss
 * and saturates the shared DRAM-read bucket the victim's scooby (wrongly) reads
 * as its own bandwidth level -- which here flips the victim's high-bw REWARD
 * table and steers WHICH action it selects (gamble -> abstain).
 *
 * The intensity is selected by a command-line ARGUMENT, passed through by the
 * trace framework (matrix -> gen_trace.sh ... "<mode>"). The traced region is an
 * effectively infinite loop; PIN starts at __champsim_start_trace() and stops
 * after TRACE_INSTR instructions.
 *
 * Usage: ./attacker <idle|light|medium|heavy>
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

/* Largest region we might touch; one byte per line drives the miss/hit stream,
 * a full buffer gives each line a distinct cache line / set. */
static volatile uint8_t region[ATK_REGION_MAX];

int
main(int argc, char **argv)
{
    if (argc < 2) {
        fprintf(stderr, "usage: %s <idle|light|medium|heavy>\n", argv[0]);
        return 2;
    }
    const char *mode = argv[1];

    unsigned long region_bytes;
    int do_loads;                 /* idle => pure ALU, no DRAM loads */
    if      (!strcmp(mode, "idle"))   { do_loads = 0; region_bytes = ATK_REGION_LIGHT;  }
    else if (!strcmp(mode, "light"))  { do_loads = 1; region_bytes = ATK_REGION_LIGHT;  }
    else if (!strcmp(mode, "medium")) { do_loads = 1; region_bytes = ATK_REGION_MEDIUM; }
    else if (!strcmp(mode, "heavy"))  { do_loads = 1; region_bytes = ATK_REGION_HEAVY;  }
    else { fprintf(stderr, "unknown intensity '%s'\n", mode); return 2; }

    uint64_t step = 0;
    volatile uint64_t sink = 0;
    uint64_t a = 0x9e3779b97f4a7c15ULL;   /* idle-path ALU seed */

    __champsim_start_trace();

    while (1) {
        if (do_loads) {
            /* streaming load: +1 line each step, wrapped to region_bytes.
             * region >> LLC (heavy) => every access misses => DRAM read traffic */
            size_t off = (size_t)((step * LINE_BYTES) % region_bytes);
            sink += region[off];
            step++;
        } else {
            /* idle neighbor: pure register ALU, generates no DRAM traffic */
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            sink += (a >> 33);
        }
    }

    asm volatile("" : : "r"(sink), "r"(a));
    return 0;
}
