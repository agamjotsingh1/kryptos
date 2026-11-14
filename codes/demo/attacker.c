/*
 * attacker.c - 'demo' attacker workload (runs on core 1).
 *
 * A capacity-eviction / LLC-thrashing attacker. It streams through a buffer far
 * larger than the LLC with a stride pattern designed to (a) evict the victim's
 * cache-resident working set and (b) look structured enough to bait a learning
 * prefetcher (Pythia) into issuing aggressive, bandwidth-stealing prefetches.
 *
 * Each distinct trigger_* function gives the accesses distinct PCs, which the
 * prefetcher keys on.
 */
#include <stdlib.h>
#include <string.h>
#include "config.h"

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

#define DEF_TRIGGER(n)                                   \
    __attribute__((noinline)) void                       \
    trigger_##n(volatile uint8_t *addr)                  \
    {                                                    \
        *addr = 0xAA;                                    \
    }
#define TRIGGER(n, addr) trigger_##n(addr)

DEF_TRIGGER(1)
DEF_TRIGGER(2)
DEF_TRIGGER(3)
DEF_TRIGGER(4)

int
main(void)
{
    volatile uint8_t *buf = aligned_alloc(BLOCK_SIZE, BUF_SIZE);
    if (!buf) return 1;
    memset((uint8_t *)buf, 0xFF, BUF_SIZE);

    __champsim_start_trace();

    while (1) {
        for (uint64_t b = 0; b < FOOTPRINT; b += BLOCK_SIZE) {
            volatile uint8_t *base = buf + b;
            TRIGGER(1, BLOCK(base));
            TRIGGER(2, BLOCK(base + 1  * BLOCK_SIZE));
            TRIGGER(3, BLOCK(base + 11 * BLOCK_SIZE));
            TRIGGER(4, BLOCK(base + 23 * BLOCK_SIZE));
        }
    }

    free((void *)buf);
    return 0;
}
