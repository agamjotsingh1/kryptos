/*
 * victim.c - 'pband_bw' victim workload (runs on core 0).
 *
 * The MIXED-PREDICTABILITY victim (ATTACK_METHODOLOGY.md §4b). Six load PCs, serviced
 * round-robin. PC j is a pair (p_j, signature_j): each visit advances its own line
 * cursor by signature_j with probability p_j, else by a uniform NON-action noise delta
 * {7,8,9,13,14}; the load is followed by ~12 register-only ALU ops. Each PC has a
 * distinct load IP and a disjoint 1 MiB region.
 *
 *   PC:  (p, signature)
 *    0   (0.30,  3)   contestable  (p below the EV-flip edge ~0.40)
 *    1   (0.33,  4)   contestable
 *    2   (0.45,  5)   predictable  (p above the edge)
 *    3   (0.55, 11)   predictable
 *    4   (0.75, 12)   predictable
 *    5   (0.95, 22)   predictable
 *
 * Under the high-bandwidth reward table (tripped by the attacker saturating the shared
 * DRAM bucket), contestable PCs collapse to abstain (action 0) while predictable PCs
 * keep prefetching their signature: target joint policy at aware-heavy is
 * [abstain, abstain, gamble, gamble, gamble, gamble] (PBAND_TARGET).
 *
 * ---- SIX DISTINCT, NAMED LOAD PCs ----
 * The per-PC readout requires six distinct static load sites, and rollup.py must know
 * which trigger PC is which (p, signature). So each PC lives in its own NOINLINE
 * function pband_pc_<j>() containing exactly one region load. The trace is built from
 * a static, non-PIE binary (gen_trace.sh: -static -no-pie), so the IP PIN records is
 * the link-time address; rollup.py runs `nm` on build/pband_bw_victim.out and maps each
 * scooby_per_pc_<ip> line to the pband_pc_<j> symbol whose body contains <ip>.
 *
 * NOTE on the RNG: the Python reference uses per-PC random.Random(seed+j) (Mersenne
 * Twister); an exact replay is not portable. The attack depends only on the
 * STATISTICAL pattern (per-PC Bernoulli(p) signature vs uniform noise), which
 * independent per-PC LCG streams reproduce. Streams are NOT bit-identical.
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "config.h"

#define LCG_A  6364136223846793005ULL
#define LCG_C  1442695040888963407ULL

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

static const double   P[VICTIM_N_PC]       = VICTIM_PC_P;
static const uint64_t SIG[VICTIM_N_PC]     = VICTIM_PC_SIG;
static const uint64_t NOISE[VICTIM_N_NOISE] = VICTIM_NOISE;

/* one disjoint 1 MiB region per PC (each a distinct cache-line / set range) */
static volatile uint8_t region[VICTIM_N_PC][VICTIM_REGION_BYTES_PER_PC];

/* per-PC state */
static uint64_t rng[VICTIM_N_PC];
static uint64_t line[VICTIM_N_PC];

/* throttle-ALU accumulators (shared, register-only work) */
static uint64_t a = 0x9e3779b97f4a7c15ULL, b = 1, c = 3;
static volatile uint64_t sink = 0;

/* One function = one distinct static region-load site = one named PC j. */
#define DEFINE_PC(j)                                                          \
__attribute__((noinline)) void pband_pc_##j(void)                             \
{                                                                             \
    rng[j] = rng[j] * LCG_A + LCG_C;                                          \
    double u = (double)(rng[j] >> 11) * (1.0 / 9007199254740992.0);          \
    uint64_t d;                                                               \
    if (u < P[j]) {                                                           \
        d = SIG[j];                      /* correct: advance by signature */  \
    } else {                                                                  \
        rng[j] = rng[j] * LCG_A + LCG_C; /* else: a non-action noise delta */ \
        d = NOISE[(rng[j] >> 32) % VICTIM_N_NOISE];                           \
    }                                                                         \
    line[j] = (line[j] + d) % VICTIM_REGION_LINES_PER_PC;                     \
    sink += region[j][line[j] * LINE_BYTES];   /* THE load of PC j */         \
    uint64_t ra = a, rb = b, rc = c;                                          \
    for (int k = 0; k < VICTIM_ALU_ITERS; k++) {                              \
        ra = ra * LCG_A + LCG_C;                                              \
        rb = (rb ^ (ra >> 13)) + rc;                                          \
        rc = (rc << 1) | (rc >> 63);                                          \
    }                                                                         \
    a = ra; b = rb; c = rc;                                                   \
}

DEFINE_PC(0)
DEFINE_PC(1)
DEFINE_PC(2)
DEFINE_PC(3)
DEFINE_PC(4)
DEFINE_PC(5)

int
main(int argc, char **argv)
{
    /* optional seed offset (argv[1]) to vary the streams; per-PC independent */
    uint64_t seed = (argc > 1) ? strtoull(argv[1], NULL, 0) : 0ULL;
    for (int j = 0; j < VICTIM_N_PC; j++) { rng[j] = seed + 1ULL + (uint64_t)j; line[j] = 0; }

    __champsim_start_trace();

    while (1) {
        pband_pc_0();
        pband_pc_1();
        pband_pc_2();
        pband_pc_3();
        pband_pc_4();
        pband_pc_5();
    }

    /* unreachable; defeats dead-code elimination */
    printf("sink=%llu abc=%llu\n", (unsigned long long)sink,
           (unsigned long long)(a ^ b ^ c));
    return 0;
}
