#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'pband_bw' multi-PC p-band steering attack.

Victim (core 0) has six load PCs of differing predictability (p, signature):
  [(0.30,3),(0.33,4),(0.45,5),(0.55,11),(0.75,12),(0.95,22)]
The neighbor (core 1) is a blind BINARY switch: idle or heavy. Heavy saturates the
shared DRAM-bandwidth bucket, which the victim's scooby reads as its own level. Under
'aware' that swaps in the high-bandwidth reward table (incorrect -14, none -2):
contestable PCs (p below the EV-flip edge) collapse to abstain (action 0) while
predictable PCs keep gambling their signature. Under 'blind' the reward table never
swaps, so the same saturation steers nothing -- the isolation control.

Per-PC behaviour is invisible in the aggregate scooby_predict_action_* histogram
(Pythia's featurewise +1 action-fallback washes it out), so it is read from scooby's
read-only per-trigger-PC counter (scooby_enable_per_pc_stats), dumped as
    scooby_per_pc_<hex ip> c0,c1,...,c14,
in scooby_actions order.

Mapping trigger IP -> victim PC j: each victim PC lives in its own noinline function
pband_pc_<j>() in a static, non-PIE binary, so the traced IP is the link-time address.
We `nm` build/<attack>_victim.out and assign each scooby_per_pc_<ip> to the pband_pc_<j>
whose body contains <ip>; within a body the IP with the most triggers is THE region
load (the other loads there are L1-resident bookkeeping). If the binary/symbols are
unavailable we fall back to the 6 hottest trigger IPs, ordered by address (the
functions are emitted in source order).

Run files are <neighbor>_<cfg>.out. Scooby stats are NOT core-tagged: each .out has
two back-to-back scooby_* blocks, each starting 'scooby_st_lookup'; the FIRST is core 0
(victim) and is the only one used.

Results that matter (gates):
  1. Differentiated steering: contestable PCs flip gamble->abstain idle->heavy (aware);
     predictable PCs keep gambling their signature.
  2. Staircase step: min(contestable f0) - max(predictable f0) > 0.4 at aware-heavy.
  3. Named joint target: per-PC verdict vector at aware-heavy == PBAND_TARGET.
  4. Isolation: blind-heavy has the same high bw3, yet no contestable PC abstains.
  5. Degree held: deg>=4 (among issued/gambling prefetches) stable aware idle->heavy.
"""
import argparse
import bisect
import os
import re
import subprocess
import sys

# --- victim definition (keep in lockstep with config.h) --------------------
PBAND_PCS = [(0.30, 3), (0.33, 4), (0.45, 5), (0.55, 11), (0.75, 12), (0.95, 22)]
PBAND_PMAX = 0.40          # EV-flip edge (empirical): p < PMAX => abstains under HBW
PBAND_TARGET = ["abstain" if p < PBAND_PMAX else "gamble" for p, _ in PBAND_PCS]
PC_SYMBOL = "pband_pc_{}"  # victim.c: one noinline function per PC

# scooby_actions order == order scooby dumps per-PC counts in (aware.ini/blind.ini)
ACTIONS = [1, 3, 4, 5, 10, 11, 12, 22, 23, 30, 32, -1, -3, -6, 0]

IDLE, HEAVY = "atk_idle", "atk_heavy"
AWARE, BLIND = "aware", "blind"

# --- gate thresholds (from the reference analyze_pband.py) -----------------
F0_GAMBLE_MAX = 0.10     # a gambling PC's abstain fraction stays below this
F0_ABSTAIN_MIN = 0.50    # a collapsed PC's abstain fraction rises above this
STEP_MARGIN = 0.40       # min(contestable f0) - max(predictable f0) at aware-heavy
SIG_GAMBLE_MIN = 0.50    # a gambling predictable PC keeps its signature above this
F0_BLIND_MAX = 0.20      # under the blind control no contestable PC may abstain
BW3_HIGH = 0.60          # bucket-3 fraction that counts as "heavy contention"
DEG_STABLE_TOL = 0.15    # max |deg>=4| change aware idle->heavy

# --- regexes ---------------------------------------------------------------
RE_BLOCK_START = re.compile(r"^scooby_st_lookup\b", re.M)
RE_BW = re.compile(r"^scooby_bw_level_(\d+)\s+(\d+)\s*$", re.M)
RE_DEG = re.compile(r"^scooby_selected_deg_(\d+)\s+(\d+)\s*$", re.M)
RE_ACT = re.compile(r"^scooby_predict_action_(-?\d+)\s+(\d+)\s*$", re.M)
RE_PERPC = re.compile(r"^scooby_per_pc_([0-9a-fA-F]+)\s+([0-9,]+)\s*$", re.M)
RE_IPC = re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M)


# ---------------------------------------------------------------------------
# parsing
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
        # selected_deg is only counted for ISSUED prefetches => "among gambling"
        "degge4": (sum(c for d, c in deg.items() if d >= 4) / sum_deg) if sum_deg else None,
        "agg_f0": (act.get(0, 0) / sum_act) if sum_act else None,
        "per_pc": per_pc,
        "ipc": float(m.group(1)) if m else None,
    }


def pc_symbols(binary):
    """{j: (start, end)} for pband_pc_<j> from `nm -n`, or None if unavailable."""
    if not binary or not os.path.isfile(binary):
        return None
    try:
        out = subprocess.run(["nm", "-n", binary], capture_output=True, text=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    text_syms = []                       # sorted (addr, name) of code symbols
    for l in out.splitlines():
        f = l.split()
        if len(f) == 3 and f[1] in "tTwW":
            text_syms.append((int(f[0], 16), f[2]))
    addrs = [a for a, _ in text_syms]
    ranges = {}
    for j in range(len(PBAND_PCS)):
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
    """{j: ip} -- the hottest trigger IP inside each pband_pc_<j> body (or fallback)."""
    total = {ip: sum(d.values()) for ip, d in per_pc.items()}
    if ranges:
        out = {}
        for j, (lo, hi) in ranges.items():
            cands = [ip for ip in per_pc if lo <= ip < hi]
            if cands:
                out[j] = max(cands, key=lambda ip: total[ip])
        return out, "nm"
    hot = sorted(sorted(total, key=total.get, reverse=True)[:len(PBAND_PCS)])
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
    return None if f0 is None else ("abstain" if f0 > 0.5 else "gamble")


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
# plot
# ---------------------------------------------------------------------------
def make_plot(runs, pcmap, path):
    """Grouped bars: per-PC abstain f0 for each (neighbor, cfg). The aware-heavy bars
    form the step at the EV-flip edge; blind-heavy stays flat (isolation)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[plot] matplotlib unavailable ({e}); skipping chart")
        return

    series = [((IDLE, AWARE), "aware idle", "#9aa5b1"),
              ((HEAVY, AWARE), "aware heavy (attack)", "#8e6cc0"),
              ((HEAVY, BLIND), "blind heavy (isolation)", "#6c8ebf")]
    n = len(PBAND_PCS)
    w = 0.26
    fig, ax = plt.subplots(figsize=(8, 4.6))
    for s, (key, label, color) in enumerate(series):
        r = runs.get(key, {})
        if not r or "missing" in r:
            continue
        xs, ys = [], []
        for j in range(n):
            ip = pcmap.get(key, {}).get(j)
            f0 = pc_f0(r["per_pc"].get(ip, {})) if ip is not None else None
            if f0 is not None:
                xs.append(j + (s - 1) * w)
                ys.append(f0)
        ax.bar(xs, ys, width=w, color=color,
               label=f"{label}  (d={r['bw3']:.2f})", zorder=3)

    # EV-flip edge between the last contestable and first predictable PC
    n_cont = sum(1 for p, _ in PBAND_PCS if p < PBAND_PMAX)
    ax.axvline(n_cont - 0.5, ls="--", lw=1.1, color="#666", zorder=1)
    ax.text(n_cont - 0.45, 0.93, f"EV-flip edge (p≈{PBAND_PMAX:.2f})",
            fontsize=8, color="#666", va="top")
    ax.axhline(0.5, ls=":", lw=0.8, color="#999", zorder=1)

    ax.set_xticks(range(n))
    ax.set_xticklabels([f"PC{j}\np={p:.2f}\nsig={s}" for j, (p, s) in enumerate(PBAND_PCS)],
                       fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("abstain fraction")
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    ax.grid(axis="y", ls=":", lw=0.6, alpha=0.6)
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"chart written to {path}")


# ---------------------------------------------------------------------------
def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--attack", default="pband_bw")
    ap.add_argument("--manifest", help="codes/<attack>/matrix (neighbors+configs)")
    ap.add_argument("--neighbors", help="comma list (overrides manifest)")
    ap.add_argument("--configs", help="comma list (overrides manifest)")
    ap.add_argument("--victim-bin",
                    help="victim binary for nm PC mapping "
                         "(default: $BUILD_DIR or <repo>/build, <attack>_victim.out)")
    ap.add_argument("--csv", help="also write the CSV here")
    ap.add_argument("--plot", help="write the per-PC abstain PNG here")
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

    # ---- header ------------------------------------------------------------
    print(f"\n=== Attack '{args.attack}' rollup ===")
    print("victim PCs (p, signature): " + ", ".join(f"PC{j}({p},{s})"
                                                  for j, (p, s) in enumerate(PBAND_PCS)))
    print(f"PBAND_TARGET = {PBAND_TARGET}   (contestable: p < {PBAND_PMAX})")
    print(f"PC mapping: {', '.join(sorted(how)) or 'n/a'}  (victim binary: {victim_bin})")
    if ranges is None:
        print("[WARN] could not resolve pband_pc_<j> symbols; using address-order fallback")

    # ---- run summary -------------------------------------------------------
    print("\n--- run summary (victim = core 0) ---")
    hdr = f"{'neighbor':<11}{'cfg':<7}{'bw3':>7}{'degGE4':>8}{'aggF0':>8}{'IPC':>8}"
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
            print(f"{nb:<11}{cfg:<7}{r['bw3']:>7.3f}{fmt(r['degge4'],3):>8}"
                  f"{fmt(r['agg_f0'],3):>8}{fmt(r['ipc'],3):>8}")
    print("(aggF0 = aggregate scooby_predict_action_0 fraction -- washed out by the +1 "
          "fallback; per-PC tables below are the real readout)")

    # ---- per-PC abstain f0 -------------------------------------------------
    pc_hdr = "".join(f"{'p.%02d' % round(p * 100):>7}" for p, _ in PBAND_PCS)

    def per_pc_table(title, fn, nd=2):
        print(f"\n--- {title} ---")
        print(f"{'regime':<20}{pc_hdr}")
        print("-" * (20 + 7 * len(PBAND_PCS)))
        for cfg in configs:
            for nb in neighbors:
                key = (nb, cfg)
                if "missing" in runs[key]:
                    continue
                cells = []
                for j, (_p, sig) in enumerate(PBAND_PCS):
                    d = dist(key, j)
                    v = fn(d, sig) if d else None
                    s = fmt(v, nd) if (v is None or isinstance(v, float)) else str(v)
                    cells.append(f"{s:>7}")
                print(f"{cfg + ' ' + nb.replace('atk_', ''):<20}{''.join(cells)}")

    per_pc_table("per-PC abstain f0 = frac(action 0)", lambda d, s: pc_f0(d))
    per_pc_table("per-PC signature-gamble fraction = frac(action == signature)",
                 lambda d, s: pc_sig_frac(d, s))
    per_pc_table("per-PC top action", lambda d, s: pc_top(d))
    per_pc_table("per-PC verdict (f0 > 0.5 => abstain)",
                 lambda d, s: {"abstain": "ABST", "gamble": "gmbl"}.get(verdict(d)))

    print("\n--- trigger IP per PC (per run) ---")
    for key in sorted(pcmap):
        print(f"{key[1] + ' ' + key[0]:<20}" +
              " ".join(f"PC{j}={pcmap[key].get(j, 0):#x}" for j in range(len(PBAND_PCS))))

    # ---- CSV ---------------------------------------------------------------
    if args.csv:
        cols = ["neighbor", "cfg", "bw0", "bw1", "bw2", "bw3", "deg_ge4", "agg_f0", "core0_ipc"]
        for j, (p, _s) in enumerate(PBAND_PCS):
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
                    fmt(r["degge4"], 4), fmt(r["agg_f0"], 4), fmt(r["ipc"], 4)]
                for j, (_p, sig) in enumerate(PBAND_PCS):
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

    if args.plot:
        make_plot(runs, pcmap, args.plot)

    # ---- success gates -----------------------------------------------------
    print("\n=== Success gates ===")
    gate_fail = False

    def report(n, ok, detail):
        nonlocal gate_fail
        tag = "SKIP" if ok is None else ("PASS" if ok else "FAIL")
        if ok is False:
            gate_fail = True
        print(f"[{tag}] Gate {n}: {detail}")

    def have(*keys):
        return all(k in runs and "missing" not in runs[k] for k in keys)

    def f0(key, j):
        d = dist(key, j)
        return pc_f0(d) if d else None

    cont = [j for j, (p, _s) in enumerate(PBAND_PCS) if p < PBAND_PMAX]
    pred = [j for j, (p, _s) in enumerate(PBAND_PCS) if p >= PBAND_PMAX]
    aw_i, aw_h, bl_h = (IDLE, AWARE), (HEAVY, AWARE), (HEAVY, BLIND)

    # Gate 1: differentiated steering (aware)
    if not have(aw_i, aw_h):
        report(1, None, "differentiated steering: missing aware idle/heavy runs")
    else:
        ok, parts = True, []
        for j, (p, sig) in enumerate(PBAND_PCS):
            fi, fh = f0(aw_i, j), f0(aw_h, j)
            if j in cont:
                good = (fi is not None and fh is not None
                        and fi < F0_GAMBLE_MAX and fh > F0_ABSTAIN_MIN)
                parts.append(f"p{p}:C f0 {fmt(fi)}->{fmt(fh)} {'ok' if good else 'BAD'}")
            else:
                sg = pc_sig_frac(dist(aw_h, j) or {}, sig)
                good = (fh is not None and sg is not None
                        and fh < F0_GAMBLE_MAX and sg > SIG_GAMBLE_MIN)
                parts.append(f"p{p}:P f0={fmt(fh)} sig={fmt(sg)} {'ok' if good else 'BAD'}")
            ok = ok and good
        report(1, ok, "differentiated steering (contestable gamble->abstain, predictable "
                      f"keeps signature)\n         " + "\n         ".join(parts))

    # Gate 2: staircase step at the EV-flip edge
    if not have(aw_h):
        report(2, None, "staircase step: missing aware-heavy run")
    else:
        cf = [f0(aw_h, j) for j in cont]
        pf = [f0(aw_h, j) for j in pred]
        if None in cf or None in pf:
            report(2, False, f"staircase step: unmapped PC(s) cont={cf} pred={pf}")
        else:
            step = min(cf) - max(pf)
            report(2, step > STEP_MARGIN,
                   f"staircase step: min(contestable f0)={min(cf):.2f} - "
                   f"max(predictable f0)={max(pf):.2f} = {step:.2f} (> {STEP_MARGIN})")

    # Gate 3: named joint-target hit
    if not have(aw_h):
        report(3, None, "joint-target hit: missing aware-heavy run")
    else:
        got = [verdict(dist(aw_h, j) or {}) for j in range(len(PBAND_PCS))]
        report(3, got == PBAND_TARGET, f"joint-target hit: {got} == {PBAND_TARGET}")

    # Gate 4: isolation (same saturation, reward-blind => nothing abstains)
    if not have(aw_h, bl_h):
        report(4, None, "isolation: missing aware/blind heavy runs")
    else:
        bw3_aw, bw3_bl = runs[aw_h]["bw3"], runs[bl_h]["bw3"]
        bl_f0 = [f0(bl_h, j) for j in range(len(PBAND_PCS))]
        bl_ok = all(v is not None and v < F0_BLIND_MAX for v in (bl_f0[j] for j in cont))
        report(4, bw3_aw > BW3_HIGH and bw3_bl > BW3_HIGH and bl_ok,
               f"isolation: bw3(heavy) aware={bw3_aw:.2f} blind={bw3_bl:.2f} (> {BW3_HIGH}); "
               f"blind-heavy f0 = [{', '.join(fmt(v) for v in bl_f0)}] "
               f"(contestable < {F0_BLIND_MAX})")

    # Gate 5: degree held aware idle->heavy
    if not have(aw_i, aw_h):
        report(5, None, "degree held: missing aware idle/heavy runs")
    else:
        di, dh = runs[aw_i]["degge4"], runs[aw_h]["degge4"]
        if None in (di, dh):
            report(5, False, f"degree held: no issued prefetches (idle={di}, heavy={dh})")
        else:
            report(5, abs(dh - di) < DEG_STABLE_TOL,
                   f"degree held: deg>=4 (among gambling) idle={di:.2f} heavy={dh:.2f}, "
                   f"|delta|={abs(dh - di):.2f} (< {DEG_STABLE_TOL})")

    print()
    sys.exit(1 if (missing_any or gate_fail) else 0)


if __name__ == "__main__":
    main()
