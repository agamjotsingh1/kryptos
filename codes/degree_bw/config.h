/*
 * config.h - shared parameters for the 'degree_bw' attack.
 *
 * Included by both victim.c and attacker.c so the two workloads agree on the
 * access geometry the trace models. This is a *bandwidth-steering* attack: the
 * attacker's only lever is its own DRAM read rate (set by memory FOOTPRINT),
 * which pushes the shared DRAM-bandwidth bucket that the victim's Pythia
 * (scooby) reads as if it were the victim's own bandwidth level. A high bucket
 * trips scooby's high-bandwidth path and collapses the victim's prefetch DEGREE.
 *
 * Nothing here needs to match ChampSim's LLC geometry exactly; what matters is
 * the *relative* footprint of each attacker intensity vs the shared LLC, so that
 * heavy streams a region far larger than the LLC and always misses to DRAM.
 */
#ifndef KRYPTOS_DEGREE_BW_CONFIG_H
#define KRYPTOS_DEGREE_BW_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride by this so each access hits a new line. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
/* Single load PC advancing +1 line, wrapped to a small region that stays
 * cache-resident after warmup, so steady-state victim self-DRAM traffic is ~0.
 * Pythia trivially learns the constant +1-line delta and ramps its degree. */
#define VICTIM_REGION_BYTES  (1UL << 21)   /* 2 MiB                         */
#define VICTIM_ALU_PER_LOAD  12            /* register-only ops per load    */

/* ---------------------------------------------------------------- attacker -- */
/* Per-intensity streaming footprint. Smaller region => higher LLC hit rate =>
 * lower DRAM rate; region >> LLC => every load misses => saturates the shared
 * DRAM-read bucket. 'idle' does pure ALU and touches no memory. */
#define ATK_REGION_LIGHT   (2048UL * 1024)   /*  2 MiB - mostly LLC-resident  */
#define ATK_REGION_MEDIUM  (3072UL * 1024)   /*  3 MiB - partial residency    */
#define ATK_REGION_HEAVY   (1UL << 26)       /* 64 MiB - always misses LLC    */

/* Largest region the attacker may touch (sizes its static buffer). */
#define ATK_REGION_MAX     ATK_REGION_HEAVY

#endif /* KRYPTOS_DEGREE_BW_CONFIG_H */
