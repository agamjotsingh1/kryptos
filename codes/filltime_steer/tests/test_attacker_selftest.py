"""Task 2 selftest: the filltime_steer attacker is a graded, blind rate dial.

The attacker's lever is sustained DRAM request rate (-> shared-queue latency -> victim
fill latency). Rate is set by alu_pad: each iteration streams one fresh line (misses LLC
when region >> LLC) then does alu_pad register-only ops. Lower alu_pad -> higher
load:instruction ratio -> more DRAM pressure. We verify:
  - the load:instruction ratio falls monotonically as alu_pad rises (graded dial),
  - alu_pad=0 is pure streaming (ratio ~1),
  - the attacker source references NO victim symbols (blind; no cross-contamination).

Run: python3 -m unittest -v (from codes/filltime_steer/tests/)
"""
import os
import re
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ATTACK_DIR = os.path.dirname(HERE)
ATTACKER_C = os.path.join(ATTACK_DIR, "attacker.c")


def _build():
    binpath = os.path.join(HERE, "attacker_selftest.out")
    r = subprocess.run(
        ["gcc", "-Wall", "-O2", "-DFT_SELFTEST", "-I", ATTACK_DIR, ATTACKER_C, "-o", binpath],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"attacker selftest build failed:\n{r.stderr}"
    return binpath


def _run(binpath, region_log2, alu_pad):
    out = subprocess.run([binpath, str(region_log2), str(alu_pad)],
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"attacker selftest run failed:\n{out.stderr}"
    m = re.search(r"loads (\d+) alu (\d+)", out.stdout)
    assert m, f"no 'loads <n> alu <m>' in output:\n{out.stdout}"
    loads, alu = int(m.group(1)), int(m.group(2))
    return loads, alu


def _ratio(loads, alu):
    return loads / (loads + alu) if (loads + alu) else 0.0


class TestAttackerDial(unittest.TestCase):
    def test_source_has_no_victim_symbols(self):
        with open(ATTACKER_C) as f:
            src = f.read()
        for sym in ("ft_pc", "OSHORT", "OLONG", "VICTIM_PC", "VICTIM_N_PC", "VICTIM_REGION"):
            self.assertNotIn(sym, src, f"attacker references victim symbol '{sym}' (not blind)")

    def test_ratio_monotone_decreasing_in_alu_pad(self):
        b = _build()
        pads = [0, 4, 16, 64]
        ratios = [_ratio(*_run(b, 26, p)) for p in pads]
        for i in range(len(ratios) - 1):
            self.assertGreater(
                ratios[i], ratios[i + 1],
                f"ratio not strictly decreasing at alu_pad {pads[i]}->{pads[i+1]}: {ratios}",
            )

    def test_zero_pad_is_pure_streaming(self):
        b = _build()
        loads, alu = _run(b, 26, 0)
        self.assertGreater(loads, 0, "no loads streamed")
        self.assertEqual(alu, 0, "alu_pad=0 should do no ALU ops")


if __name__ == "__main__":
    unittest.main()
