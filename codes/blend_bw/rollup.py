#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'blend_bw' time-toggled duty-cycle steering attack.

Victim (core 0) has FIVE load PCs of differing predictability
(p, signature) = [(0.21,3),(0.33,5),(0.45,11),(0.65,12),(0.90,22)] -- only the first TWO
(p=0.21, p=0.33) are contestable, placed at the band extremes for max separation. The
neighbor (core 1) is the SAME attacker toggled at FOUR duty cycles (atk_d_lo/mid/mhi/hi):
each ON phase saturates the shared DRAM bucket, each OFF phase lets its EWMA decay, so
the victim's scooby spends a fraction d of its SARSA updates under the high-bandwidth
reward table. d (the "blend fraction") is read off the victim's own bw-level histogram
as bw3 -- that MEASURED bw3 is the x-axis of this analysis, not the nominal on:off ratio.

The bet (blend_bw_methodology): raising d makes the EV-flip break-even
    p*(d) = (4 + 8d) / (28 + 6d)
climb continuously from 0.143 (d=0) to 0.353 (d=1). Each PC flips gamble->abstain when
p*(d) crosses its own predictability p, i.e. at d_crit(p) = (28p-4)/(8-6p). Since d_crit
increases with p, raising the duty flips PCs ONE AT A TIME in predictability order:
    PC0 (p=0.21, d_crit~0.28) flips before PC1 (p=0.33, d_crit~0.87);
    the anchors (p>=0.45) have d_crit>1 and never flip.
Under 'blind' the reward table never swaps, so the same bw3 (same d) steers nothing --
the isolation control.

Per-PC behaviour is invisible in the aggregate scooby_predict_action_* histogram (the
featurewise +1 action-fallback washes it out), so it is read from scooby's read-only
per-trigger-PC counter (scooby_enable_per_pc_stats), dumped as
    scooby_per_pc_<hex ip> c0,c1,...,c14,
in scooby_actions order. Trigger IP -> PC j is resolved by `nm` on the static non-PIE
build/blend_bw_victim.out (one noinline blend_pc_<j> per PC); fallback = 6 hottest IPs.

Run files are <neighbor>_<cfg>.out. scooby stats are NOT core-tagged: each .out has two
back-to-back scooby_* blocks; the FIRST is core 0 (victim) and is the only one used.

Results that matter (gates), ordered as blend_bw_methodology 5:
  A. Dial: each contestable PC's abstain f0 rises monotonically with the duty (bw3).
  B. Stable intermediate (make-or-break): bw3 is genuinely graded across the three
     duties (not all saturated) AND a contestable PC sits at an intermediate f0 at the
     mid duty -- strictly between its low and high extremes, not snapped to 0/1.
  C. Ordered staircase: PC0 (p=0.30) flips at a lower duty than PC1 (p=0.33).
  D. Anchors hold: PCs with p>=0.45 keep gambling their signature at every duty.
  E. Isolation: blind has the same bw3 at each duty, yet no contestable PC abstains.
  F. Degree held: deg>=4 (among gambling prefetches) stable across the aware duties.
A clean A-F proves a continuous cross-core dial on a learned policy. If bw3 cannot be
graded (B fails on separation), the window is empty and blend_bw collapses to pband_bw's
binary switch -- a reportable negative that hardens the "the lever is binary" claim.
"""
import argparse
import bisect
import os
import re
import subprocess
import sys

# --- victim definition (keep in lockstep with config.h) ---
# TWO contestable PCs at the band extremes (0.21, 0.33) for max p-separation; the rest
# anchors. (First attempt used three clustered at 0.21/0.24/0.27 -> flipped as a block.)
BLEND_PCS = [(0.21, 3), (0.33, 5), (0.45, 11), (0.65, 12), (0.90, 22)]
BLEND_PMAX = 0.40          # contestable (blend-reachable) <=> p < this (p < p*(1)=0.353)
PC_SYMBOL = "blend_pc_{}"  # victim.c: one noinline function per PC

# scooby_actions order == order scooby dumps per-PC counts in (aware.ini/blind.ini)
ACTIONS = [1, 3, 4, 5, 10, 11, 12, 22, 23, 30, 32, -1, -3, -6, 0]

AWARE, BLIND = "aware", "blind"

# --- gate thresholds -------------------------------------------------------
F0_ABSTAIN = 0.50        # f0 above this => the PC is abstaining
RISE_MIN = 0.25          # contestable f0 must rise this much low-duty -> high-duty
MONO_TOL = 0.08          # tolerated dip when checking non-decreasing f0 vs duty
BW3_LO_MAX = 0.80        # lowest duty must NOT already be saturated (else no dial)
BW3_SEP = 0.12           # min bw3 gap between consecutive duties (genuinely graded)
MID_MARGIN = 0.10        # stable-intermediate: f0_mid inside (f0_lo+m, f0_hi-m)
F0_PRED_MAX = 0.10       # an anchor PC's abstain fraction stays below this
SIG_PRED_MIN = 0.50      # an anchor PC keeps its signature above this
F0_BLIND_MAX = 0.20      # under blind, no contestable PC may abstain, any duty
BW3_MATCH_TOL = 0.15     # |bw3 aware - bw3 blind| at the same neighbor
DEG_STABLE_TOL = 0.15    # max spread of deg>=4 across the aware duties

# --- regexes ---------------------------------------------------------------
RE_BLOCK_START = re.compile(r"^scooby_st_lookup\b", re.M)
RE_BW = re.compile(r"^scooby_bw_level_(\d+)\s+(\d+)\s*$", re.M)
RE_DEG = re.compile(r"^scooby_selected_deg_(\d+)\s+(\d+)\s*$", re.M)
RE_ACT = re.compile(r"^scooby_predict_action_(-?\d+)\s+(\d+)\s*$", re.M)
RE_PERPC = re.compile(r"^scooby_per_pc_([0-9a-fA-F]+)\s+([0-9,]+)\s*$", re.M)
RE_IPC = re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M)


# ---------------------------------------------------------------------------
# the blend model (blend_bw_methodology 3)
# ---------------------------------------------------------------------------
def pstar(d):
    """EV-flip break-even predictability at blend fraction d."""
    return (4.0 + 8.0 * d) / (28.0 + 6.0 * d)


def dcrit(p):
    """Blend fraction at which a PC of predictability p flips (NaN-ish if out of [0,1])."""
    denom = 8.0 - 6.0 * p
    return (28.0 * p - 4.0) / denom if denom != 0 else float("inf")


# ---------------------------------------------------------------------------
# parsing  (identical approach to pband_bw/rollup.py)
# ---------------------------------------------------------------------------
def parse_run(path):
    """Return parsed metrics for the victim block of one .out, or {'missing':why}."""
    if not os.path.isfile(path):
        return {"missing": "no file"}
    with open(path) as f:
        text = f.read()

    starts = [m.start() for m in RE_BLOCK_START.finditer(text)]
    if not starts:
        return {"missing": "no scooby block (prefetcher off?)"}
    end = starts[1] if len(starts) > 1 else len(text)
    victim = text[starts[0]:end]

    bw = {int(k): int(v) for k, v in RE_BW.findall(victim)}
    deg = {int(k): int(v) for k, v in RE_DEG.findall(victim)}
    act = {int(k): int(v) for k, v in RE_ACT.findall(victim)}
    per_pc = {}
    for ip, vals in RE_PERPC.findall(victim):
        counts = [int(x) for x in vals.rstrip(",").split(",") if x != ""]
        per_pc[int(ip, 16)] = dict(zip(ACTIONS, counts))

    sum_bw = sum(bw.values())
    if sum_bw == 0:
        return {"missing": "zero bw-level counts"}
    if not per_pc:
        return {"missing": "no scooby_per_pc_* lines (scooby_enable_per_pc_stats off, "
                           "or binary built without the per-PC counter)"}

    sum_deg = sum(deg.values())
    sum_act = sum(act.values())
    m = RE_IPC.search(text)
    return {
        "bw_frac": {L: bw.get(L, 0) / sum_bw for L in range(4)},
        "bw3": bw.get(3, 0) / sum_bw,
        "degge4": (sum(c for d, c in deg.items() if d >= 4) / sum_deg) if sum_deg else None,
        "agg_f0": (act.get(0, 0) / sum_act) if sum_act else None,
        "per_pc": per_pc,
        "ipc": float(m.group(1)) if m else None,
    }


def pc_symbols(binary):
    """{j: (start, end)} for blend_pc_<j> from `nm -n`, or None if unavailable."""
    if not binary or not os.path.isfile(binary):
        return None
    try:
        out = subprocess.run(["nm", "-n", binary], capture_output=True, text=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    text_syms = []
    for l in out.splitlines():
        f = l.split()
        if len(f) == 3 and f[1] in "tTwW":
            text_syms.append((int(f[0], 16), f[2]))
    addrs = [a for a, _ in text_syms]
    ranges = {}
    for j in range(len(BLEND_PCS)):
        name = PC_SYMBOL.format(j)
        hit = [a for a, n in text_syms if n == name]
        if not hit:
            return None
        start = hit[0]
        k = bisect.bisect_right(addrs, start)
        end = addrs[k] if k < len(addrs) else start + 0x1000
        ranges[j] = (start, end)
    return ranges


def map_pcs(per_pc, ranges):
    """{j: ip} -- hottest trigger IP inside each blend_pc_<j> body (or fallback)."""
    total = {ip: sum(d.values()) for ip, d in per_pc.items()}
    if ranges:
        out = {}
        for j, (lo, hi) in ranges.items():
            cands = [ip for ip in per_pc if lo <= ip < hi]
            if cands:
                out[j] = max(cands, key=lambda ip: total[ip])
        return out, "nm"
    hot = sorted(sorted(total, key=total.get, reverse=True)[:len(BLEND_PCS)])
    return dict(enumerate(hot)), "fallback(top-6 by count, address order)"


def pc_f0(dist):
    t = sum(dist.values())
    return dist.get(0, 0) / t if t else None


def pc_sig_frac(dist, sig):
    t = sum(dist.values())
    return dist.get(sig, 0) / t if t else None


def pc_top(dist):
    return max(dist, key=dist.get) if dist and sum(dist.values()) else None


def verdict(dist):
    f0 = pc_f0(dist)
    return None if f0 is None else ("abstain" if f0 > F0_ABSTAIN else "gamble")


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


def fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------
DUTY_COLORS = ["#fdae61", "#f46d43", "#a50026"]   # light -> dark as duty rises


def _mpl():
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        return plt
    except Exception as e:
        print(f"[plot] matplotlib unavailable ({e}); skipping chart")
        return None


def make_plot(runs, pcmap, aware_ordered, path):
    """THE requested chart: per PC, one bar PER DUTY CYCLE (aware), ordered by measured
    bw3 (= the blend fraction d). As the duty rises the contestable PCs' bars cross the
    abstain line while the anchors stay flat -- the abstain cutoff sweeps up the p-axis."""
    plt = _mpl()
    if plt is None:
        return
    n = len(BLEND_PCS)
    k = len(aware_ordered)
    if k == 0:
        print("[plot] no aware runs; skipping main chart")
        return
    w = 0.8 / k
    fig, ax = plt.subplots(figsize=(9, 4.8))

    for s, key in enumerate(aware_ordered):
        r = runs[key]
        color = DUTY_COLORS[min(s, len(DUTY_COLORS) - 1)] if k <= len(DUTY_COLORS) \
            else plt.cm.YlOrRd((s + 1) / (k + 1))
        xs, ys = [], []
        for j in range(n):
            ip = pcmap.get(key, {}).get(j)
            f0 = pc_f0(r["per_pc"].get(ip, {})) if ip is not None else None
            if f0 is not None:
                xs.append(j + (s - (k - 1) / 2.0) * w)
                ys.append(f0)
        ax.bar(xs, ys, width=w, color=color, zorder=3,
               label=f"{key[0].replace('atk_', '')}:  d≈{r['bw3']:.2f}")
        # predicted flip edge at this duty: shade PCs the model says should abstain
        ps = pstar(r["bw3"])
        n_pred = sum(1 for p, _ in BLEND_PCS if p < ps)
        ax.axvline(n_pred - 0.5, ls="--", lw=1.0, color=color, alpha=0.7, zorder=1)

    ax.axhline(F0_ABSTAIN, ls=":", lw=0.9, color="#333", zorder=2)
    ax.text(n - 0.5, F0_ABSTAIN + 0.01, "abstain", fontsize=8, color="#333",
            ha="right", va="bottom")

    ax.set_xticks(range(n))
    ax.set_xticklabels([f"PC{j}\np={p:.2f}\nsig={s}" for j, (p, s) in enumerate(BLEND_PCS)],
                       fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("per-PC abstain fraction  f0 = frac(action 0)")
    ax.set_title("blend_bw: raising the attacker's DUTY CYCLE sweeps the abstain cutoff "
                 "up the p-order\n(dashed line per duty = EV-flip edge p*(d) predicted "
                 "from that run's measured d)", fontsize=9.5)
    ax.legend(frameon=False, fontsize=8, loc="upper right", title="duty (aware)")
    ax.grid(axis="y", ls=":", lw=0.6, alpha=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"chart written to {path}")


def make_isolation_plot(runs, pcmap, aware_key, blind_key, path):
    """Companion: aware vs blind at the HIGHEST duty. Same bw3, yet only aware abstains."""
    plt = _mpl()
    if plt is None:
        return
    if aware_key is None or blind_key is None:
        return
    if "missing" in runs.get(aware_key, {"missing": 1}) or \
       "missing" in runs.get(blind_key, {"missing": 1}):
        return
    n = len(BLEND_PCS)
    w = 0.38
    fig, ax = plt.subplots(figsize=(8, 4.4))
    for s, (key, color) in enumerate(((aware_key, "#a50026"), (blind_key, "#6c8ebf"))):
        r = runs[key]
        xs, ys = [], []
        for j in range(n):
            ip = pcmap.get(key, {}).get(j)
            f0 = pc_f0(r["per_pc"].get(ip, {})) if ip is not None else None
            if f0 is not None:
                xs.append(j + (s - 0.5) * w)
                ys.append(f0)
        lab = f"{key[1]} {key[0].replace('atk_', '')}  (d≈{r['bw3']:.2f})"
        ax.bar(xs, ys, width=w, color=color, zorder=3, label=lab)
    ax.axhline(F0_ABSTAIN, ls=":", lw=0.9, color="#333", zorder=2)
    ax.set_xticks(range(n))
    ax.set_xticklabels([f"PC{j}\np={p:.2f}" for j, (p, _s) in enumerate(BLEND_PCS)], fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("per-PC abstain fraction  f0")
    ax.set_title("blend_bw isolation: same measured d, reward-blind victim never abstains",
                 fontsize=10)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.grid(axis="y", ls=":", lw=0.6, alpha=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"isolation chart written to {path}")


# ---------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--attack", default="blend_bw")
    ap.add_argument("--manifest", help="codes/<attack>/matrix (neighbors+configs)")
    ap.add_argument("--neighbors", help="comma list (overrides manifest)")
    ap.add_argument("--configs", help="comma list (overrides manifest)")
    ap.add_argument("--victim-bin",
                    help="victim binary for nm PC mapping "
                         "(default: $BUILD_DIR or <repo>/build, <attack>_victim.out)")
    ap.add_argument("--csv", help="also write the CSV here")
    ap.add_argument("--plot", help="write the per-PC duty-sweep PNG here "
                                   "(an _isolation.png companion is written alongside)")
    args = ap.parse_args()

    if args.neighbors and args.configs:
        neighbors = [s.strip() for s in args.neighbors.split(",") if s.strip()]
        configs = [s.strip() for s in args.configs.split(",") if s.strip()]
    elif args.manifest:
        neighbors, configs = read_manifest(args.manifest)
    else:
        sys.exit("need --manifest or --neighbors/--configs")

    build_dir = os.environ.get("BUILD_DIR") or os.path.join(here, "..", "..", "build")
    victim_bin = args.victim_bin or os.path.join(build_dir, f"{args.attack}_victim.out")
    ranges = pc_symbols(victim_bin)

    runs, pcmap, how = {}, {}, set()
    for cfg in configs:
        for nb in neighbors:
            r = parse_run(os.path.join(args.exp_dir, f"{nb}_{cfg}.out"))
            runs[(nb, cfg)] = r
            if "missing" not in r:
                pcmap[(nb, cfg)], h = map_pcs(r["per_pc"], ranges)
                how.add(h)

    def dist(key, j):
        r = runs.get(key, {})
        if not r or "missing" in r:
            return None
        ip = pcmap[key].get(j)
        return None if ip is None else r["per_pc"].get(ip, {})

    def f0(key, j):
        d = dist(key, j)
        return pc_f0(d) if d else None

    # Order the aware duties by MEASURED bw3 (the real blend fraction d), low -> high.
    aware_ordered = sorted(
        [(nb, AWARE) for nb in neighbors if "missing" not in runs[(nb, AWARE)]],
        key=lambda k: runs[k]["bw3"]) if AWARE in configs else []

    cont = [j for j, (p, _s) in enumerate(BLEND_PCS) if p < BLEND_PMAX]
    pred = [j for j, (p, _s) in enumerate(BLEND_PCS) if p >= BLEND_PMAX]

    # ---- header ------------------------------------------------------------
    print(f"\n=== Attack '{args.attack}' rollup (time-toggled duty-cycle steering) ===")
    print("victim PCs (p, signature): " + ", ".join(f"PC{j}({p},{s})"
                                                  for j, (p, s) in enumerate(BLEND_PCS)))
    print(f"contestable (p < {BLEND_PMAX}): {['PC%d' % j for j in cont]}; "
          f"anchors: {['PC%d' % j for j in pred]}")
    print("blend model: p*(d) = (4+8d)/(28+6d)  in [0.143, 0.353];  flip duties d_crit(p): "
          + ", ".join("p%.2f=%.2f" % (BLEND_PCS[j][0], dcrit(BLEND_PCS[j][0])) for j in cont))
    print(f"PC mapping: {', '.join(sorted(how)) or 'n/a'}  (victim binary: {victim_bin})")
    if ranges is None:
        print("[WARN] could not resolve blend_pc_<j> symbols; using address-order fallback")

    # ---- run summary -------------------------------------------------------
    print("\n--- run summary (victim = core 0) ---")
    hdr = f"{'neighbor':<11}{'cfg':<7}{'bw3=d':>8}{'degGE4':>8}{'aggF0':>8}{'IPC':>8}"
    print(hdr)
    print("-" * len(hdr))
    missing_any = False
    for cfg in configs:
        for nb in neighbors:
            r = runs[(nb, cfg)]
            if "missing" in r:
                missing_any = True
                print(f"{nb:<11}{cfg:<7}  MISSING: {r['missing']}")
                continue
            print(f"{nb:<11}{cfg:<7}{r['bw3']:>8.3f}{fmt(r['degge4'],3):>8}"
                  f"{fmt(r['agg_f0'],3):>8}{fmt(r['ipc'],3):>8}")
    print("(aggF0 = aggregate action-0 fraction; washed out by the +1 fallback -- the "
          "per-PC tables below are the real readout)")

    # ---- predicted vs observed abstain cutoff, per aware duty ---------------
    if aware_ordered:
        print("\n--- abstain cutoff vs duty (aware; the headline 'dial') ---")
        ch = f"{'duty':<9}{'d=bw3':>8}{'p*(d)':>8}  predicted-abstain        observed-abstain"
        print(ch)
        print("-" * (len(ch) + 6))
        for key in aware_ordered:
            d = runs[key]["bw3"]
            ps = pstar(d)
            predset = [f"PC{j}" for j, (p, _s) in enumerate(BLEND_PCS) if p < ps]
            obsset = [f"PC{j}" for j in range(len(BLEND_PCS))
                      if (verdict(dist(key, j) or {}) == "abstain")]
            print(f"{key[0].replace('atk_',''):<9}{d:>8.3f}{ps:>8.3f}  "
                  f"{','.join(predset) or '(none)':<24} {','.join(obsset) or '(none)'}")

    # ---- per-PC tables -----------------------------------------------------
    pc_hdr = "".join(f"{'p.%02d' % round(p * 100):>7}" for p, _ in BLEND_PCS)

    # order rows: aware low->high duty, then blind low->high duty
    def ordered_keys(cfg):
        ks = [(nb, cfg) for nb in neighbors if "missing" not in runs[(nb, cfg)]]
        return sorted(ks, key=lambda k: runs[k]["bw3"])

    row_keys = []
    for cfg in configs:
        row_keys += ordered_keys(cfg)

    def per_pc_table(title, fn, nd=2):
        print(f"\n--- {title} ---")
        print(f"{'regime':<20}{pc_hdr}")
        print("-" * (20 + 7 * len(BLEND_PCS)))
        for key in row_keys:
            cells = []
            for j, (_p, sig) in enumerate(BLEND_PCS):
                d = dist(key, j)
                v = fn(d, sig) if d else None
                s = fmt(v, nd) if (v is None or isinstance(v, float)) else str(v)
                cells.append(f"{s:>7}")
            label = f"{key[1]} {key[0].replace('atk_', '')} d={runs[key]['bw3']:.2f}"
            print(f"{label:<20}{''.join(cells)}")

    per_pc_table("per-PC abstain f0 = frac(action 0)", lambda d, s: pc_f0(d))
    per_pc_table("per-PC signature-gamble fraction = frac(action == signature)",
                 lambda d, s: pc_sig_frac(d, s))
    per_pc_table("per-PC top action", lambda d, s: pc_top(d))
    per_pc_table("per-PC verdict (f0 > 0.5 => abstain)",
                 lambda d, s: {"abstain": "ABST", "gamble": "gmbl"}.get(verdict(d)))

    # ---- CSV ---------------------------------------------------------------
    if args.csv:
        cols = ["neighbor", "cfg", "bw0", "bw1", "bw2", "bw3_d", "pstar_d",
                "deg_ge4", "agg_f0", "core0_ipc"]
        for j, (p, _s) in enumerate(BLEND_PCS):
            cols += [f"pc{j}_p{p}_ip", f"pc{j}_p{p}_f0", f"pc{j}_p{p}_sig",
                     f"pc{j}_p{p}_top", f"pc{j}_p{p}_verdict"]
        rows = [",".join(cols)]
        for cfg in configs:
            for nb in neighbors:
                key = (nb, cfg)
                r = runs[key]
                if "missing" in r:
                    rows.append(",".join([nb, cfg] + ["NA"] * (len(cols) - 2)))
                    continue
                bw = r["bw_frac"]
                row = [nb, cfg] + [f"{bw[L]:.4f}" for L in range(4)] + [
                    fmt(pstar(r["bw3"]), 4), fmt(r["degge4"], 4),
                    fmt(r["agg_f0"], 4), fmt(r["ipc"], 4)]
                for j, (_p, sig) in enumerate(BLEND_PCS):
                    d = dist(key, j) or {}
                    ip = pcmap[key].get(j)
                    row += [f"{ip:#x}" if ip is not None else "NA",
                            fmt(pc_f0(d), 4), fmt(pc_sig_frac(d, sig), 4),
                            str(pc_top(d)) if pc_top(d) is not None else "NA",
                            verdict(d) or "NA"]
                rows.append(",".join(row))
        with open(args.csv, "w") as f:
            f.write("\n".join(rows) + "\n")
        print(f"\nCSV written to {args.csv}")

    # ---- plots -------------------------------------------------------------
    if args.plot:
        make_plot(runs, pcmap, aware_ordered, args.plot)
        aware_hi = aware_ordered[-1] if aware_ordered else None
        blind_hi = (aware_hi[0], BLIND) if (aware_hi and BLIND in configs
                                            and "missing" not in runs.get((aware_hi[0], BLIND),
                                                                          {"missing": 1})) else None
        iso_path = re.sub(r"\.png$", "", args.plot) + "_isolation.png"
        make_isolation_plot(runs, pcmap, aware_hi, blind_hi, iso_path)

    # ---- success gates -----------------------------------------------------
    print("\n=== Success gates ===")
    gate_fail = False

    def report(n, ok, detail):
        nonlocal gate_fail
        tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        if ok is False:
            gate_fail = True
        print(f"[{tag}] Gate {n}: {detail}")

    if len(aware_ordered) < 2:
        report("A-F", None, "need >=2 aware duties present to assess the dial; "
                            f"have {[k[0] for k in aware_ordered]}")
        print()
        sys.exit(1 if (missing_any or gate_fail) else 0)

    lo, hi = aware_ordered[0], aware_ordered[-1]
    mid = aware_ordered[len(aware_ordered) // 2]
    bw_lo, bw_hi = runs[lo]["bw3"], runs[hi]["bw3"]

    # Gate A: dial -- contestable f0 rises monotonically with duty
    parts, okA = [], True
    for j in cont:
        series = [f0(k, j) for k in aware_ordered]
        if any(v is None for v in series):
            okA = False
            parts.append(f"PC{j}: unmapped")
            continue
        mono = all(series[i + 1] >= series[i] - MONO_TOL for i in range(len(series) - 1))
        rise = series[-1] - series[0]
        good = mono and rise > RISE_MIN
        okA = okA and good
        parts.append(f"PC{j}: f0 " + "->".join(f"{v:.2f}" for v in series) +
                     f" (rise {rise:+.2f}) {'ok' if good else 'BAD'}")
    report("A", okA, "dial (contestable f0 rises monotonically with duty)\n         " +
           "\n         ".join(parts))

    # Gate B: stable intermediate (make-or-break)
    seps = [runs[aware_ordered[i + 1]]["bw3"] - runs[aware_ordered[i]]["bw3"]
            for i in range(len(aware_ordered) - 1)]
    graded = bw_lo < BW3_LO_MAX and all(s > BW3_SEP for s in seps)
    if not graded:
        report("B", False,
               f"NO graded duty: bw3 = {[round(runs[k]['bw3'],2) for k in aware_ordered]} "
               f"(low={bw_lo:.2f} must be < {BW3_LO_MAX}; consecutive gaps {[round(s,2) for s in seps]} "
               f"must exceed {BW3_SEP}). The toggle window is EMPTY -- blend_bw collapses to "
               f"the pband_bw binary switch. This is the reportable negative (binary lever "
               f"confirmed); CALIBRATE the attacker ratios/period and re-run.")
    else:
        inter = []
        for j in cont:
            series = [f0(k, j) for k in aware_ordered]
            if any(v is None for v in series):
                continue
            f_mid = f0(mid, j)
            lo_e, hi_e = series[0], series[-1]
            if hi_e - lo_e > 2 * MID_MARGIN and (lo_e + MID_MARGIN) < f_mid < (hi_e - MID_MARGIN):
                inter.append(f"PC{j}: f0_mid={f_mid:.2f} in ({lo_e+MID_MARGIN:.2f},"
                             f"{hi_e-MID_MARGIN:.2f})")
        report("B", len(inter) > 0,
               "stable intermediate: bw3 graded " +
               f"{[round(runs[k]['bw3'],2) for k in aware_ordered]}; "
               + ("; ".join(inter) if inter
                  else "but NO contestable PC sits strictly between its low/high f0 "
                       "(snapped to 0/1 -> thrashing, not a blend)"))

    # Gate C: ordered staircase -- PC0 (p=0.30) flips at a lower duty than PC1 (p=0.33)
    def first_flip_duty(j):
        for k in aware_ordered:
            v = f0(k, j)
            if v is not None and v > F0_ABSTAIN:
                return runs[k]["bw3"]
        return None
    if len(cont) >= 2:
        d0, d1 = first_flip_duty(cont[0]), first_flip_duty(cont[1])
        if d0 is None and d1 is None:
            report("C", None, "ordered staircase: neither contestable PC abstained at any "
                              "tested duty (raise the top duty / widen the sweep)")
        else:
            d0e = d0 if d0 is not None else float("inf")
            d1e = d1 if d1 is not None else float("inf")
            report("C", d0e <= d1e,
                   f"ordered staircase: PC{cont[0]}(p={BLEND_PCS[cont[0]][0]}) first abstains "
                   f"at d={fmt(d0)}, PC{cont[1]}(p={BLEND_PCS[cont[1]][0]}) at d={fmt(d1)} "
                   f"(expect PC{cont[0]} <= PC{cont[1]})")
    else:
        report("C", None, "ordered staircase: fewer than 2 contestable PCs")

    # Gate D: anchors hold at every aware duty
    okD, badD = True, []
    for j in pred:
        for k in aware_ordered:
            fv = f0(k, j)
            sg = pc_sig_frac(dist(k, j) or {}, BLEND_PCS[j][1])
            good = (fv is not None and sg is not None and fv < F0_PRED_MAX and sg > SIG_PRED_MIN)
            if not good:
                okD = False
                badD.append(f"PC{j}@d={runs[k]['bw3']:.2f}: f0={fmt(fv)} sig={fmt(sg)}")
    report("D", okD, "anchors hold (p>=0.45 keep gambling signature at every duty)" +
           ("" if okD else ":\n         " + "\n         ".join(badD)))

    # Gate E: isolation -- blind matches bw3 but never abstains
    blind_present = [(nb, BLIND) for nb in neighbors
                     if BLIND in configs and "missing" not in runs[(nb, BLIND)]]
    if not blind_present:
        report("E", None, "isolation: no blind runs present")
    else:
        okE, partsE = True, []
        for nb in neighbors:
            ak, bk = (nb, AWARE), (nb, BLIND)
            if "missing" in runs.get(ak, {"missing": 1}) or "missing" in runs.get(bk, {"missing": 1}):
                continue
            match = abs(runs[ak]["bw3"] - runs[bk]["bw3"]) < BW3_MATCH_TOL
            cf = [f0(bk, j) for j in cont]
            noflip = all(v is not None and v < F0_BLIND_MAX for v in cf)
            good = match and noflip
            okE = okE and good
            partsE.append(f"{nb.replace('atk_','')}: bw3 aware={runs[ak]['bw3']:.2f} "
                          f"blind={runs[bk]['bw3']:.2f} ({'match' if match else 'MISMATCH'}); "
                          f"blind contestable f0={[fmt(v) for v in cf]} "
                          f"{'ok' if noflip else 'BAD'}")
        report("E", okE, "isolation (blind: same d, no contestable abstain)\n         " +
               "\n         ".join(partsE))

    # Gate F: degree held across the aware duties
    degs = [runs[k]["degge4"] for k in aware_ordered]
    if any(v is None for v in degs):
        report("F", False, f"degree held: no issued prefetches at some duty (deg={degs})")
    else:
        spread = max(degs) - min(degs)
        report("F", spread < DEG_STABLE_TOL,
               f"degree held: deg>=4 across duties = {[round(v,2) for v in degs]}, "
               f"spread={spread:.2f} (< {DEG_STABLE_TOL})")

    print()
    sys.exit(1 if (missing_any or gate_fail) else 0)


if __name__ == "__main__":
    main()
