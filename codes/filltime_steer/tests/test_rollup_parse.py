"""Task 4: rollup.py parsing, nm PC-mapping, and per-PC / per-offset metrics.

Validates the readout layer the gates (Task 5) sit on:
  - parse_out: pulls the VICTIM scooby block (first of the two per .out) -- reward totals,
    per-action reward.dist matrix (columns [none,incorrect,untimely,timely,oob,tracker]),
    predict_action histogram, per_pc action counts, high-bw reward total, degree dist, IPC.
  - map_pc_offsets: nm on the static victim binary -> {pc_index: trigger ip}; raises if the
    victim's O_short/O_long table is not globally unique (would break attribution).
  - per_pc_long_fraction / offset_timely_fraction / offset_incorrect_fraction.

Run: python3 -m unittest -v (from codes/filltime_steer/tests/)
"""
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ATTACK_DIR = os.path.dirname(HERE)
FIX = os.path.join(HERE, "fixtures")
sys.path.insert(0, ATTACK_DIR)

import rollup  # noqa: E402


class TestParse(unittest.TestCase):
    def setUp(self):
        self.p = rollup.parse_out(os.path.join(FIX, "steer.fixture"))

    def test_uses_first_block_as_victim(self):
        # victim block has correct_timely 80; the attacker block's 999 must be ignored
        self.assertEqual(self.p["reward_timely"], 80)
        self.assertEqual(self.p["reward_untimely"], 28)
        self.assertEqual(self.p["reward_incorrect"], 2)
        self.assertEqual(self.p["reward_no_pref"], 5)

    def test_reward_dist_matrix(self):
        # scooby_reward_5 = 0,1,8,40,0,0 -> none0 incorrect1 untimely8 timely40
        d = self.p["reward_dist"][5]
        self.assertEqual((d["none"], d["incorrect"], d["untimely"], d["timely"]), (0, 1, 8, 40))

    def test_predict_action_and_per_pc(self):
        self.assertEqual(self.p["predict_action"][5], 70)
        self.assertEqual(self.p["predict_action"][10], 30)
        pc = self.p["per_pc"][0x401136]
        self.assertEqual(pc[5], 70)
        self.assertEqual(pc[10], 30)

    def test_high_bw_total_zero_and_not_fired(self):
        self.assertEqual(self.p["reward_high_bw_total"], 0)
        self.assertFalse(self.p["is_high_bw_fired"])

    def test_degree_and_ipc(self):
        self.assertEqual(self.p["deg_dist"][4], 10)
        self.assertAlmostEqual(self.p["Core_0_IPC"], 1.23)


class TestMetrics(unittest.TestCase):
    def setUp(self):
        self.p = rollup.parse_out(os.path.join(FIX, "steer.fixture"))

    def test_offset_timely_fraction(self):
        # offset 5: timely40 / (timely40+untimely8+incorrect1) = 40/49
        self.assertAlmostEqual(rollup.offset_timely_fraction(self.p, 5), 40 / 49)
        # offset 10: 20 / (20+20+0)
        self.assertAlmostEqual(rollup.offset_timely_fraction(self.p, 10), 0.5)

    def test_offset_incorrect_fraction(self):
        self.assertAlmostEqual(rollup.offset_incorrect_fraction(self.p, 5), 1 / 49)
        self.assertAlmostEqual(rollup.offset_incorrect_fraction(self.p, 10), 0.0)

    def test_per_pc_long_fraction(self):
        mapping = {0: 0x401136}
        lf = rollup.per_pc_long_fraction(self.p, mapping)
        # PC0: O_short=3 (count70), O_long=10 (count30) -> 30/100
        self.assertAlmostEqual(lf[0], 0.30)


class TestPcMapping(unittest.TestCase):
    def test_table_is_unique(self):
        # the shipped victim table must be globally unique (no raise)
        rollup.assert_offsets_unique(rollup.OSHORT, rollup.OLONG)

    def test_duplicate_table_raises(self):
        with self.assertRaises(ValueError):
            rollup.assert_offsets_unique([3, 3], [10, 11])

    def test_nm_maps_five_distinct_pcs(self):
        binpath = os.path.join(HERE, "victim_nm.out")
        r = subprocess.run(
            ["gcc", "-Wall", "-static", "-fno-pie", "-no-pie", "-O2",
             "-I", ATTACK_DIR, os.path.join(ATTACK_DIR, "victim.c"), "-o", binpath],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        ranges = rollup.victim_pc_ranges(binpath)
        self.assertIsNotNone(ranges)
        self.assertEqual(set(ranges.keys()), set(range(rollup.N_PC)))
        los = sorted(lo for lo, _ in ranges.values())
        self.assertEqual(len(set(los)), rollup.N_PC, "PC symbol addresses not distinct")


if __name__ == "__main__":
    unittest.main()
