/*
 * attacker_onoff.c - single ON-then-OFF attacker for the persistence/decay experiment.
 *
 * ON  phase: stream `on_iters` fresh 64 MiB-region lines (every load misses LLC ->
 *            DRAM read traffic -> fakes a busy-memory signal -> victim's Pythia learns
 *            to abstain on its contestable PC).
 * OFF phase: pure register-ALU ops forever (no loads -> no DRAM -> the shared bucket
 *            decays). We then watch (via the scooby timed dump) how long the victim
 *            KEEPS abstaining after the attacker goes quiet.
 *
 * One ON->OFF step (not the periodic toggle of attacker.c). argv[1] = on_iters.
 */
#include <stdint.h>
#include <stdlib.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

static volatile uint8_t region[ATK_REGION_HEAVY];     /* 64 MiB - streaming it misses LLC */
static volatile uint64_t sink = 0;

int
main(int argc, char **argv)
{
    uint64_t on_iters = (argc > 1) ? strtoull(argv[1], NULL, 0) : 3000000ULL;

    __champsim_start_trace();

    /* ON: stream line-by-line through the 64 MiB region (wraps; every touch misses). */
    uint64_t idx = 0;
    for (uint64_t i = 0; i < on_iters; i++) {
        sink += region[idx];
        idx += LINE_BYTES;
        if (idx >= ATK_REGION_HEAVY) idx = 0;
    }

    /* OFF: pure register-ALU, no memory traffic, forever (trace stops at TRACE_INSTR). */
    uint64_t ra = 0x9e3779b97f4a7c15ULL, rb = 1, rc = 3;
    while (1) {
        ra = ra * 6364136223846793005ULL + 1442695040888963407ULL;
        rb = (rb ^ (ra >> 13)) + rc;
        rc = (rc << 1) | (rc >> 63);
        sink ^= (rb & 1);
    }
    return 0;
}
