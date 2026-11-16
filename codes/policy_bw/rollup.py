#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'policy_bw' action-distribution steering attack.

Victim runs on core 0, a neighbor on core 1. The neighbor's only lever is its own
DRAM read rate; a heavy neighbor saturates the shared DRAM-bandwidth bucket, which
the victim's Pythia (scooby) reads as its OWN bandwidth level. Under the 'aware'
config that trips scooby's high-bandwidth REWARD table (incorrect -14, none -2),
flipping the contestable victim from gamble (prefetch a nonzero delta) to abstain
(action 0). Under 'blind' the reward table is disabled, so the same contention and
the same bw3 do NOT steer the action -- the isolation control.

What is steered here is WHICH action (the action distribution), not the DEGREE: the
HBW degree curve is pinned EQUAL to the normal curve in both configs, so deg>=4
stays ~constant idle->heavy. The headline metric is the abstain fraction
  f0 = frac(scooby_predict_action_0).

The attacker ships a predefined target action distribution:
  PI_ABSTAIN = {0: 0.84, 1: 0.16}
and success = the victim's measured action distribution converges to it (small L1).

Run files are named <neighbor>_<cfg>.out. Scooby stats are NOT core-tagged: each
.out has two back-to-back scooby_* blocks, each starting 'scooby_st_lookup'. The
FIRST block is core 0 (victim); we use only that one.

Outputs: a per-run table + CSV, an optional plot, then PASS/FAIL success gates.
"""
import argparse
import os
import re
import sys

# --- the attacker's predefined target distribution -------------------------
PI_ABSTAIN = {0: 0.84, 1: 0.16}

# --- regexes ---------------------------------------------------------------
RE_BLOCK_START = re.compile(r"^scooby_st_lookup\b", re.M)
RE_BW   = re.compile(r"^scooby_bw_level_(\d+)\s+(\d+)\s*$", re.M)
RE_DEG  = re.compile(r"^scooby_selected_deg_(\d+)\s+(\d+)\s*$", re.M)
# anchored exactly: must NOT catch scooby_predict_issue_action_ / _hit_action_ / _out_of_bounds_action_
RE_ACT  = re.compile(r"^scooby_predict_action_(-?\d+)\s+(\d+)\s*$", re.M)

RE_IPC  = re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M)

# --- gate thresholds (heuristic; actual numbers are always printed) --------
F0_HIGH         = 0.60   # "collapsed to abstain" (f0_heavy must exceed this)
STEER_GAP       = 0.30   # min idle->heavy swing in f0 to call it steering
L1_TARGET       = 0.30   # max L1 to PI_ABSTAIN to call the target hit
BW3_HIGH        = 0.60   # "high" bandwidth-3 fraction
BLIND_F0_TOL    = 0.20   # max f0 in blind-heavy to call it "did not collapse"
DEG_HELD_TOL    = 0.15   # max |deg>=4 aware-idle - aware-heavy| (degree held)
PEAK_JITTER     = 0.05   # tolerance for "heavy is peak / idle is floor"


def hist_from(text, rx):
    """Parse 'name_<k> <count>' lines into {int k: int count}."""
    return {int(k): int(v) for k, v in rx.findall(text)}


def scalar(text, rx, cast=float):
    m = rx.search(text)
    return cast(m.group(1)) if m else None


def parse_run(path):
    """Return a dict of parsed/derived metrics, or {'missing':reason}."""
    if not os.path.isfile(path):
        return {"missing": "no file"}
    with open(path) as f:
        text = f.read()

    starts = [m.start() for m in RE_BLOCK_START.finditer(text)]
    if not starts:
        return {"missing": "no scooby block (prefetcher off?)"}
    # block 0 = core 0 = victim
    end = starts[1] if len(starts) > 1 else len(text)
    victim = text[starts[0]:end]

    bw  = hist_from(victim, RE_BW)
    deg = hist_from(victim, RE_DEG)
    act = hist_from(victim, RE_ACT)

    sum_bw, sum_act = sum(bw.values()), sum(act.values())
    if sum_bw == 0 or sum_act == 0:
        return {"missing": f"zero counts (bw={sum_bw}, act={sum_act})"}

    bw_frac  = {L: bw.get(L, 0) / sum_bw for L in range(4)}

    # normalized action distribution
    act_norm = {a: c / sum_act for a, c in act.items()}
    f0 = act_norm.get(0, 0.0)
    top_action = max(act_norm, key=act_norm.get)
    l1_target = l1(act_norm, PI_ABSTAIN)

    # degree share >=4 (should stay ~constant: degree lever is pinned off)
    sum_deg = sum(deg.values())
    degge4 = (sum(deg.get(d, 0) for d in deg if d >= 4) / sum_deg) if sum_deg else None

    return {
        "bw_frac": bw_frac, "bw3": bw_frac[3],
        "act_norm": act_norm, "f0": f0, "top_action": top_action,
        "l1_target": l1_target, "degge4": degge4,
        "ipc": scalar(text, RE_IPC, float),
    }


def l1(p, q):
    keys = set(p) | set(q)
    return sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def make_plot(runs, configs, path,
              order=("atk_idle", "atk_light", "atk_medium", "atk_heavy")):
    """ONE clean panel: the victim abstain fraction f0 as a function of attacker
    intensity, one line per config (aware vs blind). This is the whole story in a
    single axes:
      - aware  : f0 climbs idle->heavy toward the predefined target (steering),
      - blind  : f0 stays flat at ~0 despite the SAME bw3 saturation (isolation).
    A dashed line marks the attacker's predefined target f0 (PI_ABSTAIN[0]); each
    aware point is annotated with its bw3 so the "same saturation, opposite
    outcome" contrast is visible without a second subplot."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # matplotlib optional; never fail the rollup over a chart
        print(f"[plot] matplotlib unavailable ({e}); skipping chart")
        return

    labels = [nb.replace("atk_", "") for nb in order]
    x = list(range(len(order)))
    # qualitative, CVD-safe: aware (steering) vs blind (control)
    style = {
        "aware": dict(color="#d1495b", marker="o", label="aware (reward live)"),
        "blind": dict(color="#6c8ebf", marker="s", label="blind (reward inert)"),
    }

    fig, ax = plt.subplots(figsize=(7.5, 4.8))

    # target line first so data draws on top
    ax.axhline(PI_ABSTAIN[0], ls="--", lw=1.2, color="#666", zorder=1,
               label=f"predefined target f0 = {PI_ABSTAIN[0]:.2f}")

    for cfg in configs:
        vals, xs = [], []
        for xi, nb in zip(x, order):
            r = runs.get((nb, cfg), {})
            if r and "missing" not in r:
                xs.append(xi); vals.append(r["f0"])
        if not vals:
            continue
        st = style.get(cfg, dict(label=cfg))
        ax.plot(xs, vals, lw=2.2, markersize=7, zorder=3, **st)

    # annotate each aware point with bw3 (same-saturation context, no 2nd axis)
    for xi, nb in zip(x, order):
        r = runs.get((nb, "aware"), {})
        if r and "missing" not in r:
            ax.annotate(f"bw3={r['bw3']:.2f}", (xi, r["f0"]),
                        textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8, color="#d1495b")

    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_xlabel("attacker intensity (DRAM footprint)")
    ax.set_ylabel("victim abstain fraction  f0 = frac(action 0)")
    ax.set_ylim(-0.03, 1.0)
    ax.set_xlim(-0.2, len(order) - 0.8)
    ax.set_title("policy_bw: victim collapses to abstain only when the reward "
                 "signal is live\n(same bw3 saturation under 'blind' leaves it "
                 "unmoved — isolation)", fontsize=10)
    ax.legend(frameon=False, loc="center left")
    ax.grid(axis="y", ls=":", lw=0.6, alpha=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"chart written to {path}")


def read_manifest(path):
    neighbors, configs = [], []
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].split()
            if not line:
                continue
            if line[0] == "neighbor":
                neighbors.append(line[1])
            elif line[0] == "config":
                configs.append(line[1])
    return neighbors, configs


def fmt(x, nd=4):
    return "n/a" if x is None else f"{x:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--attack", default="policy_bw")
    ap.add_argument("--manifest", help="codes/<attack>/matrix (neighbors+configs)")
    ap.add_argument("--neighbors", help="comma list (overrides manifest)")
    ap.add_argument("--configs", help="comma list (overrides manifest)")
    ap.add_argument("--idle-ref", default="atk_idle",
                    help="neighbor used as the ~0-DRAM reference")
    ap.add_argument("--csv", help="also write the CSV here")
    ap.add_argument("--plot", help="write an abstain-fraction PNG here")
    args = ap.parse_args()

    if args.neighbors and args.configs:
        neighbors = [s.strip() for s in args.neighbors.split(",") if s.strip()]
        configs = [s.strip() for s in args.configs.split(",") if s.strip()]
    elif args.manifest:
        neighbors, configs = read_manifest(args.manifest)
    else:
        sys.exit("need --manifest or --neighbors/--configs")

    # parse every available run
    runs = {}   # (neighbor, cfg) -> metrics
    for cfg in configs:
        for nb in neighbors:
            runs[(nb, cfg)] = parse_run(
                os.path.join(args.exp_dir, f"{nb}_{cfg}.out"))

    # ---- per-run table -----------------------------------------------------
    print(f"\n=== Attack '{args.attack}' rollup ===")
    print(f"target distribution PI_ABSTAIN = {PI_ABSTAIN}")
    hdr = (f"{'neighbor':<14}{'cfg':<8}{'bw3':>7}{'f0':>8}"
           f"{'top_act':>8}{'L1targ':>8}{'degGE4':>8}{'IPC':>8}")
    print(hdr)
    print("-" * len(hdr))

    csv_rows = [("neighbor,cfg,bw0,bw1,bw2,bw3,f0,top_action,l1_to_target,"
                 "degge4,core0_ipc")]
    missing_any = False

    for cfg in configs:
        for nb in neighbors:
            r = runs[(nb, cfg)]
            if "missing" in r:
                missing_any = True
                print(f"{nb:<14}{cfg:<8}  MISSING: {r['missing']}")
                csv_rows.append(f"{nb},{cfg}," + ",".join(["NA"] * 9))
                continue

            print(f"{nb:<14}{cfg:<8}{r['bw3']:>7.3f}{r['f0']:>8.3f}"
                  f"{r['top_action']:>8d}{r['l1_target']:>8.3f}"
                  f"{fmt(r['degge4'],3):>8}{fmt(r['ipc'],3):>8}")

            bw = r["bw_frac"]
            csv_rows.append(
                f"{nb},{cfg},"
                f"{bw[0]:.4f},{bw[1]:.4f},{bw[2]:.4f},{bw[3]:.4f},"
                f"{r['f0']:.4f},{r['top_action']},{r['l1_target']:.4f},"
                f"{fmt(r['degge4'])},{fmt(r['ipc'])}")

    print("\n(bw*/f0/degGE4 are FRACTIONS of their histograms; "
          "L1targ = L1 distance of the action dist to PI_ABSTAIN)")

    if args.csv:
        with open(args.csv, "w") as f:
            f.write("\n".join(csv_rows) + "\n")
        print(f"CSV written to {args.csv}")

    if args.plot:
        make_plot(runs, configs, args.plot)

    # ---- success gates -----------------------------------------------------
    print("\n=== Success gates ===")

    def g(nb, cfg, key):
        r = runs.get((nb, cfg), {})
        return None if "missing" in r or not r else r.get(key)

    gate_fail = False

    def report(n, ok, detail):
        nonlocal gate_fail
        if ok is None:
            tag = "SKIP"
        elif ok:
            tag = "PASS"
        else:
            tag = "FAIL"; gate_fail = True
        print(f"[{tag}] Gate {n}: {detail}")

    chain = ["atk_idle", "atk_light", "atk_medium", "atk_heavy"]

    # Gate 1: steering (aware) -- f0 rises idle->heavy, heavy peak, idle floor
    f0s = [g(nb, "aware", "f0") for nb in chain]
    if any(v is None for v in f0s):
        report(1, None, f"steering (aware): missing {chain} -> {f0s}")
    else:
        f0_idle, f0_heavy = f0s[0], f0s[-1]
        peak_floor = (f0_heavy >= max(f0s) - PEAK_JITTER
                      and f0_idle <= min(f0s) + PEAK_JITTER)
        ok = (peak_floor and f0_heavy > F0_HIGH
              and (f0_heavy - f0_idle) > STEER_GAP)
        report(1, ok, "steering (aware) f0 idle<...<heavy = "
               + ", ".join(f"{nb.split('_')[-1]}={v:.3f}" for nb, v in zip(chain, f0s))
               + f"  (f0_heavy>{F0_HIGH}, gap>{STEER_GAP})")

    # Gate 2: target hit -- L1(aware-heavy action dist, PI_ABSTAIN) < 0.30
    l1_h = g("atk_heavy", "aware", "l1_target")
    if l1_h is None:
        report(2, None, "target hit (aware-heavy): missing run")
    else:
        report(2, l1_h < L1_TARGET,
               f"target hit: L1(aware-heavy, PI_ABSTAIN)={l1_h:.3f} (< {L1_TARGET})")

    # Gate 3: isolation -- same high bw3 in aware & blind, f0 collapses ONLY aware
    bw3_aw = g("atk_heavy", "aware", "bw3")
    bw3_bl = g("atk_heavy", "blind", "bw3")
    f0_aw  = g("atk_heavy", "aware", "f0")
    f0_bl  = g("atk_heavy", "blind", "f0")
    if None in (bw3_aw, bw3_bl, f0_aw, f0_bl):
        report(3, None, "isolation: missing aware/blind heavy runs")
    else:
        ok = (bw3_aw > BW3_HIGH and bw3_bl > BW3_HIGH
              and f0_aw > F0_HIGH and f0_bl < BLIND_F0_TOL)
        report(3, ok, f"isolation: bw3(heavy) aware={bw3_aw:.3f} blind={bw3_bl:.3f} "
               f"both high; f0 aware={f0_aw:.3f} (collapsed) vs blind={f0_bl:.3f} (held)")

    # Gate 4: degree held -- |deg>=4 aware-idle - aware-heavy| < 0.15
    d4_i, d4_h = g("atk_idle", "aware", "degge4"), g("atk_heavy", "aware", "degge4")
    if None in (d4_i, d4_h):
        report(4, None, "degree held (aware): missing idle/heavy runs")
    else:
        report(4, abs(d4_h - d4_i) < DEG_HELD_TOL,
               f"degree held (aware): degGE4 idle={d4_i:.3f} heavy={d4_h:.3f}, "
               f"|delta|={abs(d4_h - d4_i):.3f} (< {DEG_HELD_TOL})")

    print()
    sys.exit(1 if (missing_any or gate_fail) else 0)


if __name__ == "__main__":
    main()
