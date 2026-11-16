#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'policy_psweep' experiment.

Sweeps the victim predictability p (prob its best action is correct) across and
around the reward EV-flip band (0.143, 0.353) from ATTACK_METHODOLOGY.md §4, and
for each p measures the victim abstain fraction f0 at every attacker intensity
(each intensity = a different shared-DRAM saturation bw3). All runs use the
'aware' config (HBW reward table live, degree pinned => action-selection only).

Theory (§4) prediction, confirmed/examined by this sweep:
  p < 0.143         : abstain wins even under normal reward      -> f0 high always
  0.143 < p < 0.353 : CONTESTABLE -> gamble idle, abstain as bw3 rises
  p > 0.353         : gamble wins even under HBW reward          -> f0 stays ~0

Run files are named <victim>_<neighbor>_<config>.out. Scooby stats are NOT
core-tagged: the FIRST scooby block in each .out is core 0 (the victim).

Outputs: f0 and bw3 tables (p x intensity), a CSV, and a grouped bar chart with
one group per p and one bar per intensity (y = f0), the EV-flip band shaded.
"""
import argparse
import os
import re
import sys

# EV-flip band edges (ATTACK_METHODOLOGY.md §4).
BAND_LO, BAND_HI = 0.143, 0.353

# canonical intensity ordering (idle -> heavy)
INTENSITY_ORDER = ["atk_idle", "atk_light", "atk_medium", "atk_heavy"]

RE_BLOCK_START = re.compile(r"^scooby_st_lookup\b", re.M)
RE_BW  = re.compile(r"^scooby_bw_level_(\d+)\s+(\d+)\s*$", re.M)
RE_ACT = re.compile(r"^scooby_predict_action_(-?\d+)\s+(\d+)\s*$", re.M)
RE_IPC = re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M)


def parse_run(path):
    if not os.path.isfile(path):
        return {"missing": "no file"}
    with open(path) as f:
        text = f.read()
    starts = [m.start() for m in RE_BLOCK_START.finditer(text)]
    if not starts:
        return {"missing": "no scooby block"}
    end = starts[1] if len(starts) > 1 else len(text)
    victim = text[starts[0]:end]

    bw  = {int(k): int(v) for k, v in RE_BW.findall(victim)}
    act = {int(k): int(v) for k, v in RE_ACT.findall(victim)}
    sum_bw, sum_act = sum(bw.values()), sum(act.values())
    if sum_bw == 0 or sum_act == 0:
        return {"missing": f"zero counts (bw={sum_bw}, act={sum_act})"}

    m = RE_IPC.search(text)
    return {
        "bw3": bw.get(3, 0) / sum_bw,
        "f0": act.get(0, 0) / sum_act,
        "top_action": max(act, key=act.get),
        "ipc": float(m.group(1)) if m else None,
    }


def read_manifest(path):
    """Return (victims[(name,p)], neighbors[name], configs[name]). Victim p is the
    per-mille prog-arg (vp250 -> 0.250)."""
    victims, neighbors, configs = [], [], []
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].split()
            if not line:
                continue
            if line[0] == "victim":
                name = line[1]
                permille = int(line[3]) if len(line) > 3 else 250
                victims.append((name, permille / 1000.0))
            elif line[0] == "neighbor":
                neighbors.append(line[1])
            elif line[0] == "config":
                configs.append(line[1])
    return victims, neighbors, configs


def fmt(x, nd=3):
    return "n/a" if x is None else f"{x:.{nd}f}"


def make_plot(victims, neighbors, cfg, runs, path):
    """Grouped bars: one group per p (x), one bar per attacker intensity (y = f0).
    Intensity is ordinal bandwidth, so bars use a sequential (viridis) ramp. The
    EV-flip band (0.143 < p < 0.353) is shaded: inside it, f0 should climb with
    intensity; outside, f0 is pinned (low above the band, high below it)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[plot] matplotlib unavailable ({e}); skipping chart")
        return

    vics = sorted(victims, key=lambda t: t[1])         # by p ascending
    nbs = [nb for nb in INTENSITY_ORDER if nb in neighbors] or list(neighbors)

    cmap = matplotlib.colormaps["viridis"].resampled(len(nbs))
    # mean bw3 per intensity (for the legend) across all victims present
    def mean_bw3(nb):
        vals = [runs[(v[0], nb, cfg)]["bw3"] for v in vics
                if (v[0], nb, cfg) in runs and "missing" not in runs[(v[0], nb, cfg)]]
        return sum(vals) / len(vals) if vals else float("nan")

    ngrp = len(vics)
    nbar = len(nbs)
    width = 0.8 / nbar
    x = list(range(ngrp))

    fig, ax = plt.subplots(figsize=(1.15 * ngrp + 2.5, 5.2))

    # shade the EV-flip band region (groups whose p is inside the band)
    inside = [i for i, (_, p) in enumerate(vics) if BAND_LO < p < BAND_HI]
    if inside:
        ax.axvspan(min(inside) - 0.5, max(inside) + 0.5, color="#ffe9b0",
                   alpha=0.55, zorder=0, label=f"EV-flip band ({BAND_LO}<p<{BAND_HI})")

    for bi, nb in enumerate(nbs):
        vals = []
        for (vname, _p) in vics:
            r = runs.get((vname, nb, cfg), {})
            vals.append(r["f0"] if r and "missing" not in r else 0.0)
        offs = [xi + (bi - (nbar - 1) / 2) * width for xi in x]
        label = f"{nb.replace('atk_','')} (bw3≈{mean_bw3(nb):.2f})"
        ax.bar(offs, vals, width=width, color=cmap(bi), edgecolor="white",
               linewidth=0.6, label=label, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels([f"{p:.3f}" for _, p in vics])
    ax.set_xlabel("victim predictability  p  (prob best action is correct)")
    ax.set_ylabel("victim abstain fraction  f0 = frac(action 0)")
    ax.set_ylim(0, 1.0)
    ax.set_title("policy_psweep: abstain fraction f0 vs victim predictability p, "
                 "per attacker bandwidth (bw3)\nSteering lives inside the EV-flip band",
                 fontsize=10)
    ax.legend(frameon=False, ncol=2, fontsize=8, loc="upper right")
    ax.grid(axis="y", ls=":", lw=0.5, alpha=0.6)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"chart written to {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--attack", default="policy_psweep")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--neighbors", help="comma list to restrict to (e.g. a "
                    "high-bw3 subset like atk_heavy); default = all in manifest")
    ap.add_argument("--csv")
    ap.add_argument("--plot")
    args = ap.parse_args()

    victims, neighbors, configs = read_manifest(args.manifest)
    if args.neighbors:
        want = [s.strip() for s in args.neighbors.split(",") if s.strip()]
        neighbors = [nb for nb in neighbors if nb in want]
    cfg = configs[0] if configs else "aware"
    vics = sorted(victims, key=lambda t: t[1])
    nbs = [nb for nb in INTENSITY_ORDER if nb in neighbors] or list(neighbors)

    runs = {}
    for (vname, _p) in vics:
        for nb in neighbors:
            for c in configs:
                runs[(vname, nb, c)] = parse_run(
                    os.path.join(args.exp_dir, f"{vname}_{nb}_{c}.out"))

    # ---- f0 table (rows = p, cols = intensity) -----------------------------
    print(f"\n=== Attack '{args.attack}' rollup (config='{cfg}') ===")
    print(f"EV-flip band: {BAND_LO} < p < {BAND_HI}\n")
    col = [nb.replace("atk_", "") for nb in nbs]
    print("abstain fraction f0:")
    hdr = f"{'p':>8}{'band':>7}" + "".join(f"{c:>9}" for c in col)
    print(hdr); print("-" * len(hdr))
    missing_any = False
    csv_rows = ["victim,p,intensity,bw3,f0,top_action,core0_ipc"]
    for (vname, p) in vics:
        band = "IN" if BAND_LO < p < BAND_HI else ("below" if p <= BAND_LO else "above")
        cells = []
        for nb in nbs:
            r = runs.get((vname, nb, cfg), {})
            if r and "missing" not in r:
                cells.append(f"{r['f0']:>9.3f}")
            else:
                cells.append(f"{'--':>9}"); missing_any = True
        print(f"{p:>8.3f}{band:>7}" + "".join(cells))
        for nb in nbs:
            r = runs.get((vname, nb, cfg), {})
            if r and "missing" not in r:
                csv_rows.append(f"{vname},{p:.3f},{nb},{r['bw3']:.4f},{r['f0']:.4f},"
                                f"{r['top_action']},{fmt(r['ipc'])}")
            else:
                csv_rows.append(f"{vname},{p:.3f},{nb},NA,NA,NA,NA")

    # ---- bw3 table (confirm the intensity levels) --------------------------
    print("\nbandwidth saturation bw3 (same intensity levels across p):")
    print(hdr); print("-" * len(hdr))
    for (vname, p) in vics:
        band = "IN" if BAND_LO < p < BAND_HI else ("below" if p <= BAND_LO else "above")
        cells = []
        for nb in nbs:
            r = runs.get((vname, nb, cfg), {})
            cells.append(f"{r['bw3']:>9.3f}" if r and "missing" not in r else f"{'--':>9}")
        print(f"{p:>8.3f}{band:>7}" + "".join(cells))

    if args.csv:
        with open(args.csv, "w") as f:
            f.write("\n".join(csv_rows) + "\n")
        print(f"\nCSV written to {args.csv}")

    if args.plot:
        make_plot(victims, neighbors, cfg, runs, args.plot)

    print()
    sys.exit(1 if missing_any else 0)


if __name__ == "__main__":
    main()
