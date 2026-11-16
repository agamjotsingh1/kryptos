/*
 * victim.c - 'policy_psweep' victim workload (runs on core 0).
 *
 * A single load PC whose predictability p is set by argv[1]. Each iteration the
 * line address advances by:
 *   - the SIGNATURE delta (VICTIM_SIG_DELTA, a scooby action) with probability p,
 *   - a NON-action NOISE delta otherwise.
 * So Pythia's best possible correctness for this PC is exactly p. By sweeping p
 * across the reward EV-flip band (0.143, 0.353) we trace how the victim's abstain
 * fraction f0 responds to the attacker's bandwidth saturation at each p:
 *
 *   p < 0.143         : abstain wins even under normal reward
 *   0.143 < p < 0.353 : contestable (gamble normally, abstain under HBW reward)
 *   p > 0.353         : gamble wins even under HBW reward (resists)
 *
 * p is passed as INTEGER PER-MILLE (p*1000) so the trace name can encode it
 * cleanly: argv[1]=250 => p=0.250. argv[2] optionally seeds the RNG.
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions.
 *
 * Usage: ./victim <p_permille> [seed]
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

static const uint64_t NOISE[VICTIM_NOISE_N] = VICTIM_NOISE_DELTAS;

/* One byte per line drives the miss/hit stream; a full 4 MiB buffer gives each
 * touched line a distinct cache line / set like real addresses. */
static volatile uint8_t region[VICTIM_REGION_BYTES];

int
main(int argc, char **argv)
{
    /* p in per-mille (0..1000); default 250 => p=0.25. */
    unsigned long p_permille = (argc > 1) ? strtoul(argv[1], NULL, 0) : 250UL;
    if (p_permille > 1000) p_permille = 1000;
    uint64_t rng = (argc > 2) ? strtoull(argv[2], NULL, 0) : 1ULL;

    uint64_t line = 0;                            /* advanced each iteration    */
    uint64_t ni = 0;                              /* noise-delta cursor         */
    volatile uint64_t sink = 0;                   /* consume the load           */
    uint64_t a = 0x9e3779b97f4a7c15ULL, b = 1, c = 3;  /* ALU-op operands       */

    __champsim_start_trace();

    while (1) {
        /* --- Bernoulli(p): signature with prob p, else a non-action noise --- */
        rng = rng * 6364136223846793005ULL + 1442695040888963407ULL;
        uint64_t draw = (rng >> 40) % 1000;       /* uniform 0..999             */
        uint64_t delta;
        if (draw < p_permille) {
            delta = VICTIM_SIG_DELTA;             /* the one learnable action   */
        } else {
            delta = NOISE[ni];                    /* never a scooby action      */
            ni = (ni + 1 == VICTIM_NOISE_N) ? 0 : ni + 1;
        }

        /* --- single load PC: line += delta, wrapped to the 4 MiB region --- */
        line = (line + delta) % VICTIM_REGION_LINES;
        size_t off = (size_t)(line * LINE_BYTES);
        sink += region[off];

        /* --- register-only ops: throttle issue rate, keep self-DRAM low --- */
        for (int k = 0; k < VICTIM_ALU_PER_LOAD; k++) {
            a = a * 6364136223846793005ULL + 1442695040888963407ULL;
            b = (b ^ (a >> 13)) + c;
            c = (c << 1) | (c >> 63);
        }
    }

    /* unreachable; defeats dead-code elimination */
    asm volatile("" : : "r"(sink), "r"(a), "r"(b), "r"(c));
    return 0;
}
