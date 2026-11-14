/*
 * idle.c - shared co-location baseline.
 *
 * Does the minimum amount of memory work so the second core produces a valid
 * trace while contending for almost nothing. Co-locating the victim against
 * this trace gives the "no attacker" reference IPC; the attack's effect is the
 * victim-IPC gap between the attack run and this idle run.
 */
#include <stdint.h>

__attribute__((noinline)) void __champsim_start_trace(void) { asm volatile(""); }

int
main(void)
{
    volatile uint64_t x = 0;

    __champsim_start_trace();

    /* tight compute-only loop: no cache/DRAM pressure on the shared LLC */
    while (1) {
        x += 1;
        asm volatile("" : "+r"(x));
    }

    return (int)x;
}
