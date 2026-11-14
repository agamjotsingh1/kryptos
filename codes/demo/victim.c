/*
 * victim.c - 'demo' victim workload (runs on core 0).
 *
 * A simple cache-resident streaming kernel: it repeatedly walks a working set
 * that fits in the shared LLC. Run alone (or against idle.c) it enjoys high hit
 * rates and high IPC. Co-located with attacker.c, its lines get evicted and its
 * IPC drops; the prefetcher under test may recover some of that loss.
 */
#include <stdlib.h>
#include <string.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

int
main(void)
{
    volatile uint8_t *buf = aligned_alloc(BLOCK_SIZE, VICTIM_SET);
    if (!buf) return 1;
    memset((uint8_t *)buf, 0x5A, VICTIM_SET);

    volatile uint64_t sink = 0;

    __champsim_start_trace();

    while (1) {
        /* sequential, prefetch-friendly sweep over the working set */
        for (uint64_t off = 0; off < VICTIM_SET; off += BLOCK_SIZE) {
            sink += *BLOCK(buf + off);
        }
    }

    asm volatile("" : : "r"(sink));
    free((void *)buf);
    return 0;
}
