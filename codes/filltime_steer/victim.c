/*
 * victim.c - 'filltime_steer' victim workload (runs on core 0).
 *
 * DUAL-TOUCH victim (spec 5-A; see config.h). Five load PCs ft_pc_<j>, each with its own
 * disjoint 1 MiB region. Every period, PC j demands THREE lines from one static load
 * site: base, base+O_short[j], base+O_long[j], then advances base by PERIOD[j] =
 * O_long[j] + GAP. From the `base` trigger, BOTH O_short and O_long are future demands
 * within the reuse window, so whichever offset Pythia prefetches is always correct and
 * only fill TIMING separates them. The attacker (core 1) raises shared-memory fill
 * latency, moving the timely/untimely crossover O* = L/T_line; contestable PCs (small
 * O_short) flip short->long, anchors (large O_short) stay timely.
 *
 * ---- FIVE DISTINCT, NAMED LOAD PCs ----
 * Per-PC readout needs five distinct static load sites; rollup.py maps each
 * scooby_per_pc_<ip> to the ft_pc_<j> symbol whose body contains <ip> via `nm` on the
 * static, non-PIE binary (gen_trace.sh: -static -no-pie). So each PC lives in its own
 * NOINLINE function ft_pc_<j> containing exactly one region-load instruction (executed
 * three times per period over an offset table).
 *
 * The traced region is an effectively infinite loop; PIN starts at
 * __champsim_start_trace() and stops after TRACE_INSTR instructions.
 *
 * -DFT_SELFTEST builds a finite-loop variant that records each PC's access
 * line-positions and prints them as "pc <j> pos <p0,p1,...>" for the dual-touch
 * invariant check in tests/test_victim_selftest.py.
 */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

static const uint64_t OSHORT[VICTIM_N_PC] = VICTIM_PC_OSHORT;
static const uint64_t OLONG[VICTIM_N_PC]  = VICTIM_PC_OLONG;
static const int      ALU[VICTIM_N_PC]    = VICTIM_PC_ALU;

/* one disjoint 1 MiB region per PC */
static volatile uint8_t region[VICTIM_N_PC][VICTIM_REGION_BYTES_PER_PC];

/* per-PC cursor */
static uint64_t base[VICTIM_N_PC];

/* throttle-ALU accumulators (shared, register-only work) */
static uint64_t a = 0x9e3779b97f4a7c15ULL, b = 1, c = 3;
static volatile uint64_t sink = 0;

#ifdef FT_SELFTEST
/* record access line-positions per PC (bounded) */
#define LOG_CAP (FT_SELFTEST_ITERS * 3 + 8)
static uint64_t poslog[VICTIM_N_PC][LOG_CAP];
static uint64_t poslen[VICTIM_N_PC];
#define RECORD(j, l) do { if (poslen[j] < LOG_CAP) poslog[j][poslen[j]++] = (l); } while (0)
#else
#define RECORD(j, l) do { } while (0)
#endif

/* One function = one distinct static region-load site = one named PC j. */
#define DEFINE_PC(j)                                                          \
__attribute__((noinline)) void ft_pc_##j(void)                                \
{                                                                             \
    const uint64_t os = OSHORT[j], ol = OLONG[j];                             \
    const uint64_t period = ol + VICTIM_PERIOD_GAP;                           \
    const uint64_t offs[3] = { 0, os, ol };                                   \
    for (int k = 0; k < 3; k++) {                                             \
        uint64_t line = (base[j] + offs[k]) % VICTIM_REGION_LINES_PER_PC;     \
        sink += region[j][line * LINE_BYTES];   /* THE load of PC j */        \
        RECORD(j, line);                                                      \
    }                                                                         \
    base[j] += period;                                                        \
    uint64_t ra = a, rb = b, rc = c;                                          \
    for (int t = 0; t < ALU[j]; t++) {                                        \
        ra = ra * 6364136223846793005ULL + 1442695040888963407ULL;           \
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

typedef void (*pcfn)(void);
static const pcfn PCS[VICTIM_N_PC] = { ft_pc_0, ft_pc_1, ft_pc_2, ft_pc_3, ft_pc_4 };

int
main(int argc, char **argv)
{
    uint64_t seed = (argc > 1) ? strtoull(argv[1], NULL, 0) : 0ULL;
    for (int j = 0; j < VICTIM_N_PC; j++) base[j] = (seed + 1ULL + (uint64_t)j) % VICTIM_REGION_LINES_PER_PC;

#ifdef FT_SELFTEST
    for (uint64_t it = 0; it < FT_SELFTEST_ITERS; it++)
        for (int j = 0; j < VICTIM_N_PC; j++) PCS[j]();
    for (int j = 0; j < VICTIM_N_PC; j++) {
        printf("pc %d pos ", j);
        for (uint64_t i = 0; i < poslen[j]; i++)
            printf("%llu%s", (unsigned long long)poslog[j][i], (i + 1 < poslen[j]) ? "," : "");
        printf("\n");
    }
    return 0;
#else
    __champsim_start_trace();
    while (1)
        for (int j = 0; j < VICTIM_N_PC; j++) PCS[j]();

    /* unreachable; defeats dead-code elimination */
    printf("sink=%llu abc=%llu\n", (unsigned long long)sink,
           (unsigned long long)(a ^ b ^ c));
    return 0;
#endif
}
