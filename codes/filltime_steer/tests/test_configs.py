"""Task 3: filltime_steer scooby configs enforce the attack's invariants.

Global constraints (spec 4): the DRAM-bandwidth path is OFF in every config
(scooby_high_bw_thresh = 4 so is_high_bw() never fires; HBW reward off), per-PC stats
on, and flat.ini differs from aware.ini in EXACTLY ONE knob -- correct_untimely raised
12 -> 20 -- so it collapses the timely/untimely crossover while holding contention
byte-for-byte identical (the decisive isolation control, gate D).

Run: python3 -m unittest -v (from codes/filltime_steer/tests/)
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ATTACK_DIR = os.path.dirname(HERE)
sys.path.insert(0, ATTACK_DIR)


def _config_macro_list(name):
    with open(os.path.join(ATTACK_DIR, "config.h")) as f:
        txt = f.read()
    m = re.search(r"#define\s+%s\s*\{([^}]*)\}" % re.escape(name), txt)
    assert m, f"macro {name} not found in config.h"
    return [int(x) for x in m.group(1).replace(" ", "").split(",") if x != ""]


def parse_ini(name):
    d = {}
    with open(os.path.join(ATTACK_DIR, name)) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            d[k.strip()] = v.strip()
    return d


class TestConfigs(unittest.TestCase):
    def test_bandwidth_path_off(self):
        for ini in ("aware.ini", "flat.ini"):
            k = parse_ini(ini)
            self.assertEqual(k.get("scooby_high_bw_thresh"), "4", f"{ini}: bucket maxes at 3, 4 disables HBW")
            self.assertEqual(k.get("scooby_enable_hbw_reward"), "false", f"{ini}: HBW reward must be off")
            self.assertEqual(k.get("scooby_enable_per_pc_stats"), "true", f"{ini}: per-PC readout required")

    def test_base_reward_values(self):
        a = parse_ini("aware.ini")
        self.assertEqual(a.get("scooby_reward_correct_timely"), "20")
        self.assertEqual(a.get("scooby_reward_correct_untimely"), "12")
        self.assertEqual(a.get("scooby_reward_incorrect"), "-8")
        self.assertEqual(a.get("scooby_reward_none"), "-4")

    def test_flat_differs_only_in_untimely(self):
        a, f = parse_ini("aware.ini"), parse_ini("flat.ini")
        self.assertEqual(a.get("scooby_reward_correct_untimely"), "12")
        self.assertEqual(f.get("scooby_reward_correct_untimely"), "20")
        diff = {key for key in set(a) | set(f) if a.get(key) != f.get(key)}
        self.assertEqual(diff, {"scooby_reward_correct_untimely"},
                         f"flat.ini must differ from aware.ini in exactly one knob; diff={diff}")

    def test_matrix_wires_configs_and_neighbors(self):
        with open(os.path.join(ATTACK_DIR, "matrix")) as f:
            lines = [ln.split("#", 1)[0].split() for ln in f if ln.split("#", 1)[0].split()]
        kinds = [ln[0] for ln in lines]
        self.assertEqual(kinds.count("victim"), 1, "exactly one victim")
        self.assertIn("neighbor", kinds)
        configs = {ln[1] for ln in lines if ln[0] == "config"}
        self.assertEqual(configs, {"aware", "flat"}, f"configs must be aware+flat; got {configs}")
        # every neighbor source resolves (attack dir or codes/)
        for ln in lines:
            if ln[0] == "neighbor":
                src = ln[2]
                p1 = os.path.join(ATTACK_DIR, src)
                p2 = os.path.join(os.path.dirname(ATTACK_DIR), src)
                self.assertTrue(os.path.isfile(p1) or os.path.isfile(p2),
                                f"neighbor source not found: {src}")


class TestOffsetTableConsistency(unittest.TestCase):
    """The offset table lives in config.h (labels), rollup.py (analysis) and the victim
    selftest. config.h's VICTIM_PC_OSHORT/OLONG are analysis-side labels not used by
    victim.c (which marches by STRIDE); this guards against silent drift that would
    misattribute per-PC reward.dist."""

    def test_config_offsets_match_rollup(self):
        import rollup
        self.assertEqual(_config_macro_list("VICTIM_PC_OSHORT"), rollup.OSHORT)
        self.assertEqual(_config_macro_list("VICTIM_PC_OLONG"), rollup.OLONG)

    def test_offsets_are_stride_multiples(self):
        stride = _config_macro_list("VICTIM_PC_STRIDE")
        osh = _config_macro_list("VICTIM_PC_OSHORT")
        olo = _config_macro_list("VICTIM_PC_OLONG")
        for j, s in enumerate(stride):
            self.assertEqual(osh[j] % s, 0, f"PC{j} O_short {osh[j]} not a multiple of stride {s}")
            self.assertEqual(olo[j] % s, 0, f"PC{j} O_long {olo[j]} not a multiple of stride {s}")


if __name__ == "__main__":
    unittest.main()
