/*
 * config.h - shared parameters for the 'demo' attack.
 *
 * Included by both victim.c and attacker.c so the two workloads agree on the
 * modeled cache geometry. Values mirror the 2-core ChampSim LLC config.
 */
#ifndef KRYPTOS_DEMO_CONFIG_H
#define KRYPTOS_DEMO_CONFIG_H

#include <stdint.h>

/* --- ChampSim 2-core LLC geometry --- */
#define NUM_CPUS      2
#define BLOCK_SIZE    64
#define LLC_SET       (NUM_CPUS * 2048)
#define LLC_WAY       16
#define PAGE_SIZE     4096

/* Total shared LLC capacity in bytes. */
#define LLC_SIZE      (LLC_SET * LLC_WAY * BLOCK_SIZE)

/* How much the attacker streams through, relative to the LLC. Oversizing the
 * footprint forces capacity evictions of the victim's lines. */
#define FOOTPRINT     (4 * LLC_SIZE)
#define BUF_SIZE      (2 * FOOTPRINT)

/* Cache-block alignment helpers. */
#define BLK_MASK      (~(uintptr_t)(BLOCK_SIZE - 1))
#define BLOCK(addr)   ((volatile uint8_t *)((uintptr_t)(addr) & BLK_MASK))

/* Victim working set: fits comfortably in the LLC when uncontended. */
#define VICTIM_SET    (LLC_SIZE / 4)

#endif /* KRYPTOS_DEMO_CONFIG_H */
