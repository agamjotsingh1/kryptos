#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'degree_bw' bandwidth-steering attack.

Victim runs on core 0, a neighbor on core 1. The neighbor's only lever is its
own DRAM read rate; a heavy neighbor saturates the shared DRAM-bandwidth bucket,
which the victim's Pythia (scooby) reads as its OWN bandwidth level. Under the
'bwaware' config that trips scooby's high-bandwidth path and collapses the
victim's prefetch DEGREE to 1. Under 'bwblind' the HBW path never trips, so the
same contention does NOT steer the degree -- the isolation control.

What is steered here is prefetch DEGREE (how many lines), not WHICH action: the
victim keeps predicting +1 stride, so the action-distribution stays ~flat
(policy_dist_vs_idle ~ 0).

Run files are named <neighbor>_<cfg>.out (written by launch.sh/create_jobfile.pl).
Scooby stats are NOT core-tagged: each .out has two back-to-back scooby_* blocks,
each starting with a 'scooby_st_lookup' line. The FIRST block is core 0 (victim);
we use only that one.

Outputs: a per-run table + CSV (fractions), then PASS/FAIL success gates.
"""
import argparse
import os
import re
import sys

# --- regexes ---------------------------------------------------------------
RE_BLOCK_START = re.compile(r"^scooby_st_lookup\b", re.M)
RE_BW   = re.compile(r"^scooby_bw_level_(\d+)\s+(\d+)\s*$", re.M)
RE_DEG  = re.compile(r"^scooby_selected_deg_(\d+)\s+(\d+)\s*$", re.M)
# anchored exactly: must NOT catch scooby_predict_issue_action_ / _hit_action_ / _out_of_bounds_action_
RE_ACT  = re.compile(r"^scooby_predict_action_(-?\d+)\s+(\d+)\s*$", re.M)

RE_IPC      = re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M)
RE_PF_USE   = re.compile(r"^Core_0_L2C_prefetch_useful\s+(\d+)", re.M)
RE_PF_USELS = re.compile(r"^Core_0_L2C_prefetch_useless\s+(\d+)", re.M)
RE_MISS     = re.compile(r"^Core_0_L2C_total_miss\s+(\d+)", re.M)

# --- gate thresholds (heuristic; actual numbers are always printed) --------
BW3_HIGH      = 0.60   # "high" bandwidth-3 fraction
DEG1_HIGH     = 0.60   # "collapsed to degree 1"
DEGGE4_HIGH   = 0.60   # "still aggressive"
COLLAPSE_GAP  = 0.30   # min idle->heavy swing to call it a collapse
UNMOVED_TOL   = 0.20   # max |heavy-idle| swing to call it "unmoved"
BENIGN_TOL    = 0.10   # max benign-vs-idle difference


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

    sum_bw, sum_deg = sum(bw.values()), sum(deg.values())
    if sum_bw == 0 or sum_deg == 0:
        return {"missing": f"zero counts (bw={sum_bw}, deg={sum_deg})"}

    useful = scalar(text, RE_PF_USE, int)
    useless = scalar(text, RE_PF_USELS, int)
    miss = scalar(text, RE_MISS, int)
    ipc = scalar(text, RE_IPC, float)

    bw_frac  = {L: bw.get(L, 0) / sum_bw for L in range(4)}
    deg_frac = {D: deg.get(D, 0) / sum_deg for D in range(1, 7)}
    degge4 = sum(deg.get(d, 0) for d in deg if d >= 4) / sum_deg

    acc = (useful / (useful + useless)) if (useful is not None and useless is not None
                                            and (useful + useless) > 0) else None
    cov = (useful / (useful + miss)) if (useful is not None and miss is not None
                                         and (useful + miss) > 0) else None

    # normalized action distribution (for policy_dist_vs_idle)
    sum_act = sum(act.values())
    act_norm = {a: c / sum_act for a, c in act.items()} if sum_act else {}

    return {
        "bw_frac": bw_frac, "deg_frac": deg_frac, "deg1": deg_frac[1],
        "degge4": degge4, "bw3": bw_frac[3],
        "accuracy": acc, "coverage": cov, "ipc": ipc,
        "act_norm": act_norm,
    }


def l1(p, q):
    keys = set(p) | set(q)
    return sum(abs(p.get(k, 0.0) - q.get(k, 0.0)) for k in keys)


def make_plot(runs, configs, path, order=("atk_idle", "atk_light", "atk_medium", "atk_heavy")):
    """100% stacked bar of the victim's selected-degree distribution, one panel
    per config, one bar per attacker intensity. benign_cache is excluded (it is
    the negative control, == idle). Degree is ordinal, so colors are a sequential
    perceptual ramp (viridis: CVD-safe, monotonic light->dark)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:  # matplotlib optional; never fail the rollup over a chart
        print(f"[plot] matplotlib unavailable ({e}); skipping chart")
        return

    degs = [1, 2, 3, 4, 5, 6]
    cmap = matplotlib.colormaps["viridis"].resampled(len(degs))
    colors = [cmap(i) for i in range(len(degs))]

    cfgs = list(configs)
    fig, axes = plt.subplots(1, len(cfgs), figsize=(4.2 * len(cfgs), 5),
                             sharey=True, squeeze=False)
    axes = axes[0]

    for ax, cfg in zip(axes, cfgs):
        present = []
        for nb in order:
            r = runs.get((nb, cfg), {})
            if r and "missing" not in r:
                present.append((nb.replace("atk_", ""), r))
        if not present:
            ax.set_title(f"{cfg}\n(no data)")
            continue

        x = range(len(present))
        bottom = [0.0] * len(present)
        for di, d in enumerate(degs):
            vals = [r["deg_frac"][d] * 100 for _, r in present]
            ax.bar(x, vals, bottom=bottom, width=0.72, color=colors[di],
                   edgecolor="white", linewidth=1.0, label=f"deg{d}")
            for xi, (v, b) in enumerate(zip(vals, bottom)):
                if v >= 5:                       # selective direct labels only
                    ax.text(xi, b + v / 2, f"{v:.0f}", ha="center", va="center",
                            fontsize=8, color="white" if di < 3 else "black")
            bottom = [b + v for b, v in zip(bottom, vals)]

        ax.set_xticks(list(x))
        ax.set_xticklabels([lbl for lbl, _ in present])
        ax.set_title(cfg)
        ax.set_xlabel("attacker intensity")
        ax.set_ylim(0, 100)
        ax.margins(x=0.08)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)

    axes[0].set_ylabel("victim selected-degree share (%)")
    handles, lbls = axes[0].get_legend_handles_labels()
    # legend in degree order, highest degree on top to mirror the stack
    fig.legend(handles[::-1], lbls[::-1], title="degree", loc="center right",
               frameon=False)
    fig.suptitle("degree_bw: victim prefetch-degree distribution (100% stacked)")
    fig.tight_layout(rect=[0, 0, 0.88, 0.95])
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
    ap.add_argument("--attack", default="degree_bw")
    ap.add_argument("--manifest", help="codes/<attack>/matrix (neighbors+configs)")
    ap.add_argument("--neighbors", help="comma list (overrides manifest)")
    ap.add_argument("--configs", help="comma list (overrides manifest)")
    ap.add_argument("--idle-ref", default="atk_idle",
                    help="neighbor used as the ~0-DRAM reference")
    ap.add_argument("--csv", help="also write the CSV here")
    ap.add_argument("--plot", help="write a 100%% stacked degree-distribution PNG here")
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
    hdr = (f"{'neighbor':<14}{'cfg':<9}{'bw3':>7}"
           f"{'deg1':>7}{'deg2':>7}{'deg4':>7}{'deg6':>7}"
           f"{'acc':>7}{'cov':>7}{'IPC':>8}{'pdist':>7}")
    print(hdr)
    print("-" * len(hdr))

    csv_rows = [("neighbor,cfg,bw0,bw1,bw2,bw3,deg1,deg2,deg3,deg4,deg5,deg6,"
                 "pref_accuracy,coverage,core0_ipc,policy_dist_vs_idle")]
    missing_any = False

    for cfg in configs:
        for nb in neighbors:
            r = runs[(nb, cfg)]
            if "missing" in r:
                missing_any = True
                print(f"{nb:<14}{cfg:<9}  MISSING: {r['missing']}")
                csv_rows.append(f"{nb},{cfg}," + ",".join(["NA"] * 14))
                continue

            ref = runs.get((args.idle_ref, cfg), {})
            pdist = (l1(r["act_norm"], ref["act_norm"])
                     if ref and "act_norm" in ref else None)

            dg = r["deg_frac"]
            print(f"{nb:<14}{cfg:<9}{r['bw3']:>7.3f}"
                  f"{dg[1]:>7.3f}{dg[2]:>7.3f}{dg[4]:>7.3f}{dg[6]:>7.3f}"
                  f"{fmt(r['accuracy'],3):>7}"
                  f"{fmt(r['coverage'],3):>7}{fmt(r['ipc'],3):>8}"
                  f"{fmt(pdist,3):>7}")

            bw, dg = r["bw_frac"], r["deg_frac"]
            csv_rows.append(
                f"{nb},{cfg},"
                f"{bw[0]:.4f},{bw[1]:.4f},{bw[2]:.4f},{bw[3]:.4f},"
                f"{dg[1]:.4f},{dg[2]:.4f},{dg[3]:.4f},{dg[4]:.4f},{dg[5]:.4f},{dg[6]:.4f},"
                f"{fmt(r['accuracy'])},{fmt(r['coverage'])},{fmt(r['ipc'])},{fmt(pdist)}")

    print("\n(bw*/deg* are FRACTIONS of their histograms; pdist = L1 action-dist "
          f"vs ({args.idle_ref}, same cfg))")

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

    # Gate 1: monotone steering of bw3 (bwaware) idle<light<medium<heavy
    chain = ["atk_idle", "atk_light", "atk_medium", "atk_heavy"]
    vals = [g(nb, "bwaware", "bw3") for nb in chain]
    if any(v is None for v in vals):
        report(1, None, f"monotone bw3 (bwaware): missing {chain} -> {vals}")
    else:
        mono = all(b > a for a, b in zip(vals, vals[1:]))
        report(1, mono, "monotone bw3 (bwaware) idle<light<medium<heavy = "
               + ", ".join(f"{nb.split('_')[-1]}={v:.3f}" for nb, v in zip(chain, vals)))

    # Gate 2: degree collapse (bwaware) idle->heavy
    d1_i, d1_h = g("atk_idle", "bwaware", "deg1"), g("atk_heavy", "bwaware", "deg1")
    g4_i, g4_h = g("atk_idle", "bwaware", "degge4"), g("atk_heavy", "bwaware", "degge4")
    if None in (d1_i, d1_h, g4_i, g4_h):
        report(2, None, "degree collapse (bwaware): missing idle/heavy runs")
    else:
        ok = (d1_h > DEG1_HIGH and (d1_h - d1_i) > COLLAPSE_GAP
              and g4_i > DEGGE4_HIGH and (g4_i - g4_h) > COLLAPSE_GAP)
        report(2, ok, f"degree collapse (bwaware): deg1 {d1_i:.3f}->{d1_h:.3f}, "
               f"degGE4 {g4_i:.3f}->{g4_h:.3f}")

    # Gate 3: isolation (bwblind) same bw3, degree UNMOVED
    bw3_blind_h = g("atk_heavy", "bwblind", "bw3")
    g4_blind_i = g("atk_idle", "bwblind", "degge4")
    g4_blind_h = g("atk_heavy", "bwblind", "degge4")
    if None in (bw3_blind_h, g4_blind_i, g4_blind_h):
        report(3, None, "isolation (bwblind): missing heavy/idle runs")
    else:
        ok = (bw3_blind_h > BW3_HIGH
              and abs(g4_blind_h - g4_blind_i) < UNMOVED_TOL
              and g4_blind_h > DEGGE4_HIGH)
        report(3, ok, f"isolation (bwblind): bw3(heavy)={bw3_blind_h:.3f} high, "
               f"degGE4 idle={g4_blind_i:.3f} heavy={g4_blind_h:.3f} (unmoved)")

    # Gate 4: benign co-location ~= idle (bwaware) on bw3 and degree
    bw3_b, bw3_ref = g("benign_cache", "bwaware", "bw3"), g("atk_idle", "bwaware", "bw3")
    g4_b, g4_ref = g("benign_cache", "bwaware", "degge4"), g("atk_idle", "bwaware", "degge4")
    if None in (bw3_b, bw3_ref, g4_b, g4_ref):
        report(4, None, "benign co-location (bwaware): missing benign/idle runs")
    else:
        ok = abs(bw3_b - bw3_ref) < BENIGN_TOL and abs(g4_b - g4_ref) < BENIGN_TOL
        report(4, ok, f"benign ~= idle (bwaware): bw3 {bw3_ref:.3f} vs {bw3_b:.3f}, "
               f"degGE4 {g4_ref:.3f} vs {g4_b:.3f}")

    print()
    sys.exit(1 if (missing_any or gate_fail) else 0)


if __name__ == "__main__":
    main()
