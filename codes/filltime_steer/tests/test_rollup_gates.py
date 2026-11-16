"""Task 5: filltime_steer gates A-F + D' on synthetic metrics.

evaluate_gates consumes {(neighbor, config): parsed} + {(neighbor, config): {pc: ip}} and
returns {gate: (passed, detail)}. We feed hand-built scenarios (no ChampSim) and assert the
gates both PASS on a clean steering run and CATCH each failure mode from the plan's Review
Focus: flat-leaks (D/D' catch -8 contamination), overshoot (C catches an anchor moving),
bucket-live (E catches the bandwidth path firing).

Run: python3 -m unittest -v (from codes/filltime_steer/tests/)
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ATTACK_DIR = os.path.dirname(HERE)
sys.path.insert(0, ATTACK_DIR)

import rollup  # noqa: E402

INTENS = ["idle", "atk_lo", "atk_mid", "atk_hi"]


def mk_run(long_by_pc, short_timely_by_pc, long_timely_by_pc,
           short_incorrect_by_pc=None, high_bw=0):
    """Fabricate a parsed dict + its pcmap from desired per-PC long-fraction and
    per-offset timely/incorrect fractions (counts out of 100)."""
    short_incorrect_by_pc = short_incorrect_by_pc or [0] * rollup.N_PC
    per_pc, reward_dist, pcmap = {}, {}, {}
    for j in range(rollup.N_PC):
        ip = 0x1000 + j
        pcmap[j] = ip
        lf = long_by_pc[j]
        counts = [0] * len(rollup.ACTIONS)
        # scale to 1000 so offsets clear rollup.MIN_OFFSET_SAMPLES (fractions unchanged)
        counts[rollup.ACTIONS.index(rollup.OSHORT[j])] = int(round((1 - lf) * 1000))
        counts[rollup.ACTIONS.index(rollup.OLONG[j])] = int(round(lf * 1000))
        per_pc[ip] = dict(zip(rollup.ACTIONS, counts))
        st, inc = short_timely_by_pc[j] * 10, short_incorrect_by_pc[j] * 10
        reward_dist[rollup.OSHORT[j]] = {"none": 0, "incorrect": inc,
                                         "untimely": max(0, 1000 - st - inc),
                                         "timely": st, "oob": 0, "tracker": 0}
        lt = long_timely_by_pc[j] * 10
        reward_dist[rollup.OLONG[j]] = {"none": 0, "incorrect": 0,
                                        "untimely": max(0, 1000 - lt), "timely": lt,
                                        "oob": 0, "tracker": 0}
    parsed = {"per_pc": per_pc, "reward_dist": reward_dist,
              "is_high_bw_fired": high_bw > 0, "reward_high_bw_total": high_bw,
              "Core_0_IPC": 1.0, "deg_dist": {1: 10}}
    return parsed, pcmap


def steering_scenario(flat_leaks=False, anchor_moves=False, bucket_live=False):
    """A clean steering run (aware: contestable PCs flip short->long with intensity,
    anchors hold, incorrect ~0; flat: no movement), with optional injected defects."""
    runs, pcmap = {}, {}
    # aware intensity ladder: contestable long-fraction and short-timely sweep; anchors flat.
    ladders = {
        # per intensity: long_by_pc, short_timely_by_pc, long_timely_by_pc
        "idle":    ([0.05, 0.05, 0.05, 0.05, 0.05], [95, 95, 95, 95, 95], [95, 95, 95, 95, 95]),
        "atk_lo":  ([0.45, 0.20, 0.10, 0.05, 0.05], [55, 80, 90, 95, 95], [92, 92, 92, 95, 95]),
        "atk_mid": ([0.75, 0.60, 0.35, 0.06, 0.05], [30, 45, 65, 94, 95], [90, 90, 90, 95, 95]),
        "atk_hi":  ([0.85, 0.80, 0.70, 0.07, 0.05], [18, 22, 30, 93, 95], [88, 88, 88, 95, 95]),
    }
    inc = [0, 0, 0, 0, 0]
    for nb in INTENS:
        lb, st, lt = ladders[nb]
        hb = 0
        if anchor_moves and nb == "atk_hi":
            lb = lb[:3] + [0.60, 0.05]       # anchor PC3 jumps -> gate C must fail
        if bucket_live and nb == "atk_hi":
            hb = 500                         # high-bw fired -> gate E must fail
        if flat_leaks and nb == "atk_hi":
            inc = [40, 40, 40, 0, 0]         # contestable flipped via -8, not lateness
        parsed, pm = mk_run(lb, st, lt, short_incorrect_by_pc=inc, high_bw=hb)
        runs[(nb, "aware")] = parsed
        pcmap[(nb, "aware")] = pm
    # benign ~ idle
    parsed, pm = mk_run(*ladders["idle"][:1], ladders["idle"][1], ladders["idle"][2])
    runs[("benign", "aware")] = parsed
    pcmap[("benign", "aware")] = pm
    # flat: idle and atk_hi -- no movement UNLESS flat_leaks (then the -8 path moves it)
    flat_idle = ([0.05] * 5, [95] * 5, [95] * 5)
    flat_hi = ([0.80, 0.80, 0.70, 0.05, 0.05], [95] * 5, [95] * 5) if flat_leaks else flat_idle
    for nb, spec in (("idle", flat_idle), ("atk_hi", flat_hi)):
        parsed, pm = mk_run(*spec)
        runs[(nb, "flat")] = parsed
        pcmap[(nb, "flat")] = pm
    return runs, pcmap


class TestGates(unittest.TestCase):
    def _gates(self, **kw):
        runs, pcmap = steering_scenario(**kw)
        return rollup.evaluate_gates(runs, pcmap)

    def test_clean_steering_passes_all(self):
        g = self._gates()
        for name in ("A", "B", "C", "D", "D'", "E", "F"):
            self.assertTrue(g[name][0], f"gate {name} should pass on clean steering: {g[name][1]}")

    def test_flat_leaks_fails_D_and_Dprime(self):
        g = self._gates(flat_leaks=True)
        self.assertFalse(g["D"][0], "flat moved -> isolation gate D must fail")
        self.assertFalse(g["D'"][0], "-8 contamination -> gate D' must fail")

    def test_overshoot_fails_C(self):
        g = self._gates(anchor_moves=True)
        self.assertFalse(g["C"][0], "anchor moved -> selectivity gate C must fail")

    def test_bucket_live_fails_E(self):
        g = self._gates(bucket_live=True)
        self.assertFalse(g["E"][0], "high-bw fired -> bandwidth-orthogonal gate E must fail")


if __name__ == "__main__":
    unittest.main()
