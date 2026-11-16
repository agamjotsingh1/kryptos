"""Task 1 selftest: the filltime_steer victim is DUAL-TOUCH.

The attack's correctness crux (spec 5-A): from a common trigger, BOTH O_short and
O_long must be demanded, so whichever offset Pythia selects is always correct and only
*timeliness* separates them. A single-cursor stream where only one of the two is the
next demand would score the other -8 incorrect, collapsing the channel into the
existing EV-flip family.

We verify the invariant directly from the victim's own access stream: compile victim.c
with -DFT_SELFTEST (finite loop that prints each PC's access line-positions in order),
then check that a substantial fraction of accesses X have BOTH X+O_short and X+O_long
appearing in the near-forward window -- i.e. both offsets are genuine future demands
from a common point. This is Pythia's reward semantics (demand-reuse of the prefetched
line) without hand-modeling its state hash.

Run: python3 -m unittest -v (from codes/filltime_steer/tests/)
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ATTACK_DIR = os.path.dirname(HERE)
VICTIM_C = os.path.join(ATTACK_DIR, "victim.c")

# Mirror of config.h VICTIM_PC_OSHORT / VICTIM_PC_OLONG (kept in sync by hand; the
# uniqueness test below is what guards a typo).
OSHORT = [3, 4, 5, 22, 23]
OLONG = [10, 11, 12, 30, 32]
N_PC = 5
WINDOW = 8                 # forward reuse window (accesses)
MIN_DUAL_FRACTION = 0.15   # at least the base-trigger share demands both offsets


def _build_and_run():
    binpath = os.path.join(HERE, "victim_selftest.out")
    r = subprocess.run(
        ["gcc", "-Wall", "-O2", "-DFT_SELFTEST", "-I", ATTACK_DIR, VICTIM_C, "-o", binpath],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"victim selftest build failed:\n{r.stderr}"
    out = subprocess.run([binpath], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, f"victim selftest run failed:\n{out.stderr}"
    pos = {}
    for line in out.stdout.splitlines():
        m = re.match(r"pc (\d+) pos (.+)", line)
        if m:
            pos[int(m.group(1))] = [int(x) for x in m.group(2).split(",") if x != ""]
    return pos


def _dual_reuse_fraction(positions, oshort, olong, window=WINDOW):
    if not positions:
        return 0.0
    n = len(positions)
    hits = 0
    for i in range(n):
        fwd = set(positions[i + 1 : i + 1 + window])
        if (positions[i] + oshort) in fwd and (positions[i] + olong) in fwd:
            hits += 1
    return hits / n


class TestVictimDualTouch(unittest.TestCase):
    def test_offsets_globally_unique(self):
        allo = [v for pair in zip(OSHORT, OLONG) for v in pair]
        self.assertEqual(len(set(allo)), len(allo), f"offsets not unique: {allo}")
        self.assertNotIn(1, allo, "offset 1 is the featurewise +1 fallback attractor; forbidden")

    def test_both_offsets_reused_from_common_trigger(self):
        pos = _build_and_run()
        self.assertEqual(set(pos.keys()), set(range(N_PC)), f"missing PCs: {sorted(pos.keys())}")
        for j in range(N_PC):
            frac = _dual_reuse_fraction(pos[j], OSHORT[j], OLONG[j])
            self.assertGreaterEqual(
                frac, MIN_DUAL_FRACTION,
                f"PC{j} dual-reuse fraction {frac:.3f} < {MIN_DUAL_FRACTION}: "
                f"O_short={OSHORT[j]} and O_long={OLONG[j]} are not both demanded from a "
                f"common trigger -- victim is not dual-touch",
            )


if __name__ == "__main__":
    unittest.main()
