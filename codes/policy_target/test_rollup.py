#!/usr/bin/env python3
"""Standalone tests for policy_target/rollup.py.

No pytest in this environment (no pip), so this file is BOTH a plain runnable
script (`python3 test_rollup.py` -> nonzero exit on failure) and
pytest-discoverable (test_* functions). TDD gate for Tasks 2 and 3.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rollup  # noqa: E402
from rollup import parse_run, pc_f0  # noqa: E402

# A minimal victim scooby block: block marker, bw histogram, aggregate action
# histogram (abstain=84, signature action 4 =16), one per-PC line whose counts
# put 50 on action 4 and 50 on action 0 (abstain) -> f0 = 0.5.
SYNTH_OUT = """\
scooby_st_lookup 1
scooby_bw_level_0 100
scooby_bw_level_1 50
scooby_bw_level_2 30
scooby_bw_level_3 20
scooby_selected_deg_1 10
scooby_selected_deg_4 90
scooby_predict_action_0 84
scooby_predict_action_4 16
scooby_per_pc_402fd0 0,0,50,0,0,0,0,0,0,0,0,0,0,0,50,
Core_0_IPC 1.23
"""


def test_parse_run_reads_agg_and_perpc(tmp_path):
    out = os.path.join(tmp_path, "cal_on40_aware.out")
    with open(out, "w") as f:
        f.write(SYNTH_OUT)
    r = parse_run(out)
    assert "missing" not in r, r
    assert r["agg"][0] == 84 and r["agg"][4] == 16
    assert abs(pc_f0(next(iter(r["per_pc"].values()))) - 0.5) < 1e-9


def test_fit_invert_monotone_interpolation():
    from rollup import fit_invert
    pts = [(8, 0.12), (24, 0.30), (40, 0.52), (56, 0.70), (72, 0.84)]  # f0 rises with on
    got = fit_invert(pts, [0.25, 0.50, 0.75])
    assert 16 < got[0.25] < 32 and 32 < got[0.50] < 48 and 56 < got[0.75] < 72
    assert got[0.25] < got[0.50] < got[0.75]                           # order preserved


# --- minimal runner (stands in for pytest) ---------------------------------
def _run():
    import tempfile
    import traceback
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    passed = failed = 0
    for name, fn in tests:
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as td:
                    fn(td)
            else:
                fn()
            print("PASS", name)
            passed += 1
        except Exception:
            print("FAIL", name)
            traceback.print_exc()
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run())
