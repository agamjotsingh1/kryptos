#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'demo' attack.

Reads the ChampSim .out files that launch.sh produced in the experiment dir and
reports, per prefetcher config, how much the attacker slows the victim down.

For each exp config (nopref, pythia) it compares the victim's IPC when
co-located with the attacker vs when co-located with the idle baseline:

    slowdown = victim_IPC(idle) / victim_IPC(attack)      (higher = worse)
    impact % = (1 - victim_IPC(attack)/victim_IPC(idle)) * 100

File naming (set by launch.sh / create_jobfile.pl):
    <attack>_attack_<exp>.out   victim(core0) + attacker(core1)
    <attack>_idle_<exp>.out     victim(core0) + idle(core1)

Core_0 = victim, Core_1 = co-runner.
"""
import argparse
import os
import re
import sys

IPC_RE = {
    0: re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M),
    1: re.compile(r"^Core_1_IPC\s+([0-9.]+)", re.M),
}


def read_ipc(path, core):
    if not os.path.isfile(path):
        return None
    with open(path) as f:
        text = f.read()
    m = IPC_RE[core].search(text)
    return float(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True, help="experiments/<attack> dir")
    ap.add_argument("--attack", required=True, help="attack name")
    ap.add_argument("--configs", default="nopref,pythia",
                    help="comma-separated exp config names")
    args = ap.parse_args()

    configs = [c.strip() for c in args.configs.split(",") if c.strip()]

    rows = []
    for cfg in configs:
        attack_out = os.path.join(args.exp_dir, f"{args.attack}_attack_{cfg}.out")
        idle_out = os.path.join(args.exp_dir, f"{args.attack}_idle_{cfg}.out")

        v_attack = read_ipc(attack_out, 0)
        v_idle = read_ipc(idle_out, 0)
        a_ipc = read_ipc(attack_out, 1)

        if v_attack is None or v_idle is None:
            rows.append((cfg, v_idle, v_attack, a_ipc, None, None))
            continue

        slowdown = v_idle / v_attack if v_attack else float("inf")
        impact = (1.0 - (v_attack / v_idle)) * 100.0 if v_idle else float("nan")
        rows.append((cfg, v_idle, v_attack, a_ipc, slowdown, impact))

    print(f"\n=== Attack '{args.attack}' rollup ===")
    print(f"{'config':<10} {'vIPC idle':>10} {'vIPC attack':>12} "
          f"{'aIPC':>8} {'slowdown':>9} {'impact%':>9}")
    print("-" * 62)
    missing = False
    for cfg, v_idle, v_attack, a_ipc, slowdown, impact in rows:
        if slowdown is None:
            missing = True
            vi = "n/a" if v_idle is None else f"{v_idle:.4f}"
            va = "n/a" if v_attack is None else f"{v_attack:.4f}"
            ai = "n/a" if a_ipc is None else f"{a_ipc:.4f}"
            print(f"{cfg:<10} {vi:>10} {va:>12} {ai:>8} {'MISSING':>9} {'-':>9}")
        else:
            print(f"{cfg:<10} {v_idle:>10.4f} {v_attack:>12.4f} "
                  f"{a_ipc:>8.4f} {slowdown:>9.3f} {impact:>8.2f}%")
    print()

    # Does Pythia make the attack worse than no-prefetch?
    by = {cfg: si for cfg, _, _, _, si, _ in rows}  # cfg -> slowdown
    if "nopref" in by and "pythia" in by and \
       by["nopref"] is not None and by["pythia"] is not None:
        delta = by["pythia"] - by["nopref"]
        verdict = "amplifies" if delta > 0 else "mitigates"
        print(f"Pythia {verdict} the attack: "
              f"slowdown {by['nopref']:.3f} (nopref) -> "
              f"{by['pythia']:.3f} (pythia), delta {delta:+.3f}\n")

    sys.exit(1 if missing else 0)


if __name__ == "__main__":
    main()
