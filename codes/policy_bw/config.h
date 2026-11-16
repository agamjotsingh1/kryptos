/*
 * config.h - shared parameters for the 'policy_bw' attack.
 *
 * Included by both victim.c and attacker.c so the two workloads agree on the
 * access geometry the trace models. This is the *policy* (action-distribution)
 * bandwidth-steering attack (ATTACK_METHODOLOGY.md §4): the attacker's only lever
 * is its own DRAM read rate (set by memory FOOTPRINT), which pushes the shared
 * DRAM-bandwidth bucket that the victim's Pythia (scooby) reads as if it were the
 * victim's own level. A high bucket trips scooby's high-bandwidth REWARD table
 * (harsher 'incorrect', gentler 'none'), which flips a *contestable* victim from
 * gamble (prefetch a nonzero delta) to abstain (action 0) -- WHICH action it
 * selects, not how many lines (degree is pinned equal in both configs).
 *
 * The attacker here is identical to the degree_bw attacker (same shared channel,
 * same footprint dial). Only the VICTIM differs: it is contestable rather than
 * trivially predictable.
 */
#ifndef KRYPTOS_POLICY_BW_CONFIG_H
#define KRYPTOS_POLICY_BW_CONFIG_H

#include <stdint.h>

/* One cache line; both workloads stride in multiples of this. */
#define LINE_BYTES   64UL

/* ------------------------------------------------------------------ victim -- */
/* A single load PC whose line address advances by a delta drawn i.i.d. UNIFORM
 * from {1,3,4,5} cache lines each iteration, wrapped to a 65536-line (4 MiB)
 * region, followed by one register-only ALU op. With 4 equiprobable deltas and
 * no predictive structure, any single Pythia action is correct p ~= 1/4 = 0.25,
 * which lands INSIDE the reward EV-flip band (0.143 < p < 0.353): normal-reward
 * Pythia prefetches, high-bw-reward Pythia abstains. That is what gets steered.
 * All four deltas are members of scooby_actions, so a correct guess is a named
 * action. */
#define VICTIM_REGION_LINES  (1UL << 16)                       /* 65536 lines   */
#define VICTIM_REGION_BYTES  (VICTIM_REGION_LINES * LINE_BYTES) /* 4 MiB        */
#define VICTIM_ALU_PER_LOAD  1             /* register-only ops per load         */

/* ---------------------------------------------------------------- attacker -- */
/* Per-intensity streaming footprint (identical to degree_bw). Smaller region =>
 * higher LLC hit rate => lower DRAM rate; region >> LLC => every load misses =>
 * saturates the shared DRAM-read bucket. 'idle' does pure ALU, touches no mem. */
#define ATK_REGION_LIGHT   (2048UL * 1024)   /*  2 MiB - mostly LLC-resident  */
#define ATK_REGION_MEDIUM  (3072UL * 1024)   /*  3 MiB - partial residency    */
#define ATK_REGION_HEAVY   (1UL << 26)       /* 64 MiB - always misses LLC    */

/* Largest region the attacker may touch (sizes its static buffer). */
#define ATK_REGION_MAX     ATK_REGION_HEAVY

#endif /* KRYPTOS_POLICY_BW_CONFIG_H */
