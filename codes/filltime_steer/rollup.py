#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'filltime_steer' fill-timing distance-steering attack.

The DRAM-bandwidth path is OFF (scooby_high_bw_thresh=4). The attacker raises shared-memory
fill latency with its own blind streaming; the victim's Pythia sees that only through the
base reward's timely(+20) vs untimely(+12) classification. Because prefetch lead-time scales
with offset (O* = L/T_line), the attacker's intensity moves which offset distance Pythia
learns: contestable PCs (small O_short) flip short->long, anchors (large O_short) hold.

Readouts (victim = core 0 = FIRST of the two scooby blocks per .out):
  - scooby_reward_<action> none,incorrect,untimely,timely,oob,tracker   (per-offset reward.dist)
  - scooby_per_pc_<ip> c0..c14  in scooby_actions order                 (per-PC action histogram)
  - scooby_reward_<type>_high_bw                                        (gate E: must be 0)

Task 4 defines parsing + mapping + metrics. Task 5 adds evaluate_gates + the CLI.
"""
import argparse
import bisect
import os
import re
import subprocess
import sys

# --- victim definition (keep in lockstep with config.h) --------------------
OSHORT = [5, 4, 11, 3]
OLONG = [10, 12, 22, 30]
N_PC = 4
PC_SYMBOL = "ft_pc_{}"      # victim.c: one noinline function per PC

# scooby_actions order == order scooby dumps per-PC counts in (aware.ini/flat.ini)
ACTIONS = [1, 3, 4, 5, 10, 11, 12, 22, 23, 30, 32, -1, -3, -6, 0]

# RewardType enum order (scooby_helper.h) == columns of `scooby_reward_<action>`
REWARD_COLS = ["none", "incorrect", "untimely", "timely", "oob", "tracker"]

# --- regexes ---------------------------------------------------------------
RE_BLOCK_START = re.compile(r"^scooby_st_lookup\b", re.M)
RE_RWTOTAL = {
    "reward_no_pref": re.compile(r"^scooby_reward_no_pref\s+(\d+)\s*$", re.M),
    "reward_incorrect": re.compile(r"^scooby_reward_incorrect\s+(\d+)\s*$", re.M),
    "reward_untimely": re.compile(r"^scooby_reward_correct_untimely\s+(\d+)\s*$", re.M),
    "reward_timely": re.compile(r"^scooby_reward_correct_timely\s+(\d+)\s*$", re.M),
}
RE_DIST = re.compile(r"^scooby_reward_(-?\d+)\s+([\d,]+)\s*$", re.M)
RE_ACT = re.compile(r"^scooby_predict_action_(-?\d+)\s+(\d+)\s*$", re.M)
RE_PERPC = re.compile(r"^scooby_per_pc_([0-9a-fA-F]+)\s+([0-9,]+)\s*$", re.M)
RE_DEG = re.compile(r"^scooby_selected_deg_(\d+)\s+(\d+)\s*$", re.M)
RE_HIGHBW = re.compile(r"^scooby_reward_\w+_high_bw\s+(\d+)\s*$", re.M)
RE_IPC = re.compile(r"^Core_0_IPC\s+([0-9.]+)", re.M)


def parse_out(path):
    """Parsed metrics for the VICTIM scooby block of one .out, or {'missing': why}."""
    if not os.path.isfile(path):
        return {"missing": "no file"}
    with open(path) as f:
        text = f.read()

    starts = [m.start() for m in RE_BLOCK_START.finditer(text)]
    if not starts:
        return {"missing": "no scooby block (prefetcher off?)"}
    end = starts[1] if len(starts) > 1 else len(text)
    victim = text[starts[0]:end]

    out = {}
    for key, rx in RE_RWTOTAL.items():
        m = rx.search(victim)
        out[key] = int(m.group(1)) if m else 0

    dist = {}
    for off, vals in RE_DIST.findall(victim):
        cols = [int(x) for x in vals.split(",") if x != ""]
        if len(cols) >= 4:
            dist[int(off)] = {REWARD_COLS[i]: (cols[i] if i < len(cols) else 0)
                              for i in range(len(REWARD_COLS))}
    out["reward_dist"] = dist

    out["predict_action"] = {int(o): int(n) for o, n in RE_ACT.findall(victim)}

    per_pc = {}
    for ip, vals in RE_PERPC.findall(victim):
        counts = [int(x) for x in vals.rstrip(",").split(",") if x != ""]
        per_pc[int(ip, 16)] = dict(zip(ACTIONS, counts))
    out["per_pc"] = per_pc

    out["deg_dist"] = {int(d): int(n) for d, n in RE_DEG.findall(victim)}

    hb = [int(x) for x in RE_HIGHBW.findall(victim)]
    out["reward_high_bw_total"] = sum(hb)
    out["is_high_bw_fired"] = sum(hb) > 0

    m = RE_IPC.search(text)
    out["Core_0_IPC"] = float(m.group(1)) if m else None
    return out


# --- metrics ---------------------------------------------------------------
def offset_timely_fraction(parsed, offset):
    d = parsed.get("reward_dist", {}).get(offset)
    if not d:
        return None
    denom = d["timely"] + d["untimely"] + d["incorrect"]
    return d["timely"] / denom if denom else None


def offset_incorrect_fraction(parsed, offset):
    d = parsed.get("reward_dist", {}).get(offset)
    if not d:
        return None
    denom = d["timely"] + d["untimely"] + d["incorrect"]
    return d["incorrect"] / denom if denom else None


def offset_samples(parsed, offset):
    """Prefetch-outcome samples for this offset (timely+untimely+incorrect). A fraction
    computed over a handful of exploration samples is noise, so gates ignore offsets below
    MIN_OFFSET_SAMPLES -- otherwise a long offset Pythia picked ~100x reports a spurious
    incorrect-fraction near 1.0."""
    d = parsed.get("reward_dist", {}).get(offset)
    if not d:
        return 0
    return d["timely"] + d["untimely"] + d["incorrect"]


def per_pc_long_fraction(parsed, mapping):
    """{pc_index: O_long selections / (O_short+O_long selections)} for mapped trigger ips."""
    out = {}
    for j, ip in mapping.items():
        dist = parsed.get("per_pc", {}).get(ip)
        if not dist:
            out[j] = None
            continue
        s, l = dist.get(OSHORT[j], 0), dist.get(OLONG[j], 0)
        out[j] = (l / (s + l)) if (s + l) else None
    return out


# --- PC mapping ------------------------------------------------------------
def assert_offsets_unique(oshort, olong):
    allo = list(oshort) + list(olong)
    if len(set(allo)) != len(allo):
        raise ValueError(f"victim offsets not globally unique: {allo}")


def victim_pc_ranges(binary):
    """{j: (start, end)} for ft_pc_<j> from `nm -n`, or None if unavailable."""
    if not binary or not os.path.isfile(binary):
        return None
    try:
        out = subprocess.run(["nm", "-n", binary], capture_output=True, text=True,
                             check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    text_syms = [(int(f[0], 16), f[2]) for f in (l.split() for l in out.splitlines())
                 if len(f) == 3 and f[1] in "tTwW"]
    addrs = [a for a, _ in text_syms]
    ranges = {}
    for j in range(N_PC):
        hit = [a for a, n in text_syms if n == PC_SYMBOL.format(j)]
        if not hit:
            return None
        start = hit[0]
        k = bisect.bisect_right(addrs, start)
        ranges[j] = (start, addrs[k] if k < len(addrs) else start + 0x1000)
    return ranges


def map_pc_offsets(parsed, binary):
    """{pc_index: hottest trigger ip inside ft_pc_<j>}; raises if the table is not unique."""
    assert_offsets_unique(OSHORT, OLONG)
    ranges = victim_pc_ranges(binary)
    per_pc = parsed.get("per_pc", {})
    total = {ip: sum(d.values()) for ip, d in per_pc.items()}
    if ranges:
        out = {}
        for j, (lo, hi) in ranges.items():
            cands = [ip for ip in per_pc if lo <= ip < hi]
            if cands:
                out[j] = max(cands, key=lambda ip: total[ip])
        return out
    hot = sorted(sorted(total, key=total.get, reverse=True)[:N_PC])
    return dict(enumerate(hot))


# --- gates ------------------------------------------------------------------
CONTEST = [0, 1, 2]
ANCHOR = [3]
INTENS = ["idle", "atk_lo", "atk_mid", "atk_hi"]   # rising intensity (excludes benign)

RISE_MIN = 0.25          # A: contestable long-fraction rise idle->atk_hi
MONO_TOL = 0.08          # A: tolerated dip in the non-decreasing sweep
LONG_FLIP = 0.50         # a PC has flipped to long when long-fraction crosses this
SHORT_TIMELY_FALL = 0.20 # B: O_short timely-fraction must fall at least this
LONG_TIMELY_HOLD = 0.60  # B: O_long timely-fraction stays at/above this at atk_hi
ANCHOR_DELTA_MAX = 0.15  # C: an anchor's long-fraction barely moves
INCORRECT_MAX = 0.10     # D': contestable-offset incorrect-fraction stays ~0
MIN_OFFSET_SAMPLES = 200 # D'/B: ignore offsets with too few prefetch-outcome samples
FLAT_DELTA_MAX = 0.15    # D: flat atk_hi vs flat idle, contestable long-fraction
BENIGN_DELTA_MAX = 0.15  # F: benign vs idle, contestable long-fraction


def _lf(runs, pcmap, neighbor, config):
    key = (neighbor, config)
    if key not in runs or key not in pcmap:
        return {}
    return per_pc_long_fraction(runs[key], pcmap[key])


def _first_cross(seq, thr):
    for i, v in enumerate(seq):
        if v is not None and v >= thr:
            return i
    return len(seq)


def evaluate_gates(runs, pcmap):
    """{gate: (passed, detail)} for gates A-F + D' (spec 6). Operates on parsed runs
    keyed by (neighbor, config) and their per-PC ip maps."""
    g = {}
    aw = {nb: _lf(runs, pcmap, nb, "aware") for nb in INTENS}

    # A. distance steer: contestable long-fraction rises monotonically idle->atk_hi
    okA, dA = True, []
    for j in CONTEST:
        seq = [aw[nb].get(j) for nb in INTENS]
        if any(v is None for v in seq):
            okA = False; dA.append(f"PC{j}:missing"); continue
        mono = all(seq[i + 1] >= seq[i] - MONO_TOL for i in range(len(seq) - 1))
        rise = seq[-1] - seq[0]
        if not (mono and rise >= RISE_MIN):
            okA = False
        dA.append(f"PC{j}:{seq[0]:.2f}->{seq[-1]:.2f}{'' if mono else ' (dip)'}")
    g["A"] = (okA, "distance steer " + ", ".join(dA))

    # B. crossover: O_short timely falls while O_long timely holds (aware idle vs atk_hi)
    okB, dB = True, []
    for j in CONTEST:
        s_lo = offset_timely_fraction(runs.get(("idle", "aware"), {}), OSHORT[j])
        s_hi = offset_timely_fraction(runs.get(("atk_hi", "aware"), {}), OSHORT[j])
        l_hi = offset_timely_fraction(runs.get(("atk_hi", "aware"), {}), OLONG[j])
        if None in (s_lo, s_hi, l_hi):
            okB = False; dB.append(f"PC{j}:missing"); continue
        if not ((s_lo - s_hi) >= SHORT_TIMELY_FALL and l_hi >= LONG_TIMELY_HOLD):
            okB = False
        dB.append(f"PC{j}:short {s_lo:.2f}->{s_hi:.2f}, long@hi {l_hi:.2f}")
    g["B"] = (okB, "crossover " + ", ".join(dB))

    # C. selectivity: contestable cross LONG_FLIP in O_short order; anchors barely move
    cross_idx = [_first_cross([aw[nb].get(j) for nb in INTENS], LONG_FLIP) for j in CONTEST]
    ordered = all(cross_idx[i] <= cross_idx[i + 1] for i in range(len(cross_idx) - 1))
    anchors_ok, dC = True, []
    for j in ANCHOR:
        lo, hi = aw["idle"].get(j), aw["atk_hi"].get(j)
        if None in (lo, hi) or abs(hi - lo) > ANCHOR_DELTA_MAX:
            anchors_ok = False
        dC.append(f"PC{j}:{(lo if lo is not None else float('nan')):.2f}->"
                  f"{(hi if hi is not None else float('nan')):.2f}")
    g["C"] = (ordered and anchors_ok,
              f"selectivity cross-order {cross_idx} ordered={ordered}; anchors " + ", ".join(dC))

    # D. isolation: under flat, contestable long-fraction unmoved idle->atk_hi
    fl_idle = _lf(runs, pcmap, "idle", "flat")
    fl_hi = _lf(runs, pcmap, "atk_hi", "flat")
    okD, dD = True, []
    for j in CONTEST:
        lo, hi = fl_idle.get(j), fl_hi.get(j)
        if None in (lo, hi) or abs(hi - lo) > FLAT_DELTA_MAX:
            okD = False
        dD.append(f"PC{j}:{(lo if lo is not None else float('nan')):.2f}->"
                  f"{(hi if hi is not None else float('nan')):.2f}")
    g["D"] = (okD, "isolation(flat) " + ", ".join(dD))

    # D'. no -8 contamination: contestable-offset incorrect-fraction ~0 at every intensity
    okDp, worst = True, 0.0
    for nb in INTENS:
        r = runs.get((nb, "aware"), {})
        for j in CONTEST:
            for off in (OSHORT[j], OLONG[j]):
                if offset_samples(r, off) < MIN_OFFSET_SAMPLES:
                    continue   # too few samples -> fraction is noise (spec: exploration)
                fr = offset_incorrect_fraction(r, off)
                if fr is not None:
                    worst = max(worst, fr)
                    if fr > INCORRECT_MAX:
                        okDp = False
    g["D'"] = (okDp, f"max contestable incorrect-fraction {worst:.3f} (<= {INCORRECT_MAX}, "
                     f">= {MIN_OFFSET_SAMPLES} samples)")

    # E. bandwidth-orthogonal: is_high_bw never fires, no high-bw reward in any run
    okE, bad = True, []
    for key, r in runs.items():
        if r.get("is_high_bw_fired") or r.get("reward_high_bw_total", 0) > 0:
            okE = False; bad.append("_".join(key))
    g["E"] = (okE, "bandwidth path off" if okE else f"HIGH-BW FIRED in {bad}")

    # F. benign ~ idle: mere LLC-resident co-location does nothing
    bn = _lf(runs, pcmap, "benign", "aware")
    okF, dF = True, []
    for j in CONTEST:
        a, b = aw["idle"].get(j), bn.get(j)
        if None in (a, b) or abs(a - b) > BENIGN_DELTA_MAX:
            okF = False
        dF.append(f"PC{j}:{(b if b is not None else float('nan')):.2f}")
    g["F"] = (okF, "benign~idle " + ", ".join(dF))
    return g


# --- CLI --------------------------------------------------------------------
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


def _fmt(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--attack", default="filltime_steer")
    ap.add_argument("--manifest")
    ap.add_argument("--csv")
    ap.add_argument("--plot")
    args = ap.parse_args()

    if args.manifest and os.path.isfile(args.manifest):
        neighbors, configs = read_manifest(args.manifest)
    else:
        neighbors, configs = INTENS + ["benign"], ["aware", "flat"]

    binary = os.path.join(os.environ.get("BUILD_DIR", "build"), f"{args.attack}_victim.out")
    runs, pcmap = {}, {}
    for nb in neighbors:
        for cfg in configs:
            parsed = parse_out(os.path.join(args.exp_dir, f"{nb}_{cfg}.out"))
            runs[(nb, cfg)] = parsed
            pcmap[(nb, cfg)] = {} if "missing" in parsed else map_pc_offsets(parsed, binary)

    print(f"=== filltime_steer rollup ({args.exp_dir}) ===\n")
    print("per-PC long-offset fraction (aware):")
    print("  PC  " + "  ".join(f"{nb:>8}" for nb in neighbors if (nb, "aware") in runs))
    for j in range(N_PC):
        role = "C" if j in CONTEST else "A"
        cells = []
        for nb in neighbors:
            if (nb, "aware") not in runs:
                continue
            lf = per_pc_long_fraction(runs[(nb, "aware")], pcmap.get((nb, "aware"), {})).get(j)
            cells.append(f"{_fmt(lf):>8}")
        print(f"  {j}{role} O{OSHORT[j]}/{OLONG[j]}  " + "  ".join(cells))

    g = evaluate_gates(runs, pcmap)
    print("\ngates:")
    npass = 0
    for name in ("A", "B", "C", "D", "D'", "E", "F"):
        ok, detail = g[name]
        npass += ok
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    print(f"\n{npass}/7 gates pass")

    if args.csv:
        with open(args.csv, "w") as f:
            f.write("neighbor,config," + ",".join(f"pc{j}_longfrac" for j in range(N_PC)) + "\n")
            for nb in neighbors:
                for cfg in configs:
                    key = (nb, cfg)
                    if key not in runs or "missing" in runs[key]:
                        continue
                    lf = per_pc_long_fraction(runs[key], pcmap.get(key, {}))
                    f.write(f"{nb},{cfg}," + ",".join(_fmt(lf.get(j)) for j in range(N_PC)) + "\n")
        print(f"csv written to {args.csv}")

    if args.plot:
        _make_plot(runs, pcmap, neighbors, args.plot)


def _make_plot(runs, pcmap, neighbors, path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"[plot] matplotlib unavailable ({e}); skipping chart")
        return
    aware_nbs = [nb for nb in INTENS if (nb, "aware") in runs and "missing" not in runs[(nb, "aware")]]
    if not aware_nbs:
        print("[plot] no aware runs; skipping")
        return
    fig, ax = plt.subplots(figsize=(9, 4.8))
    k = len(aware_nbs)
    w = 0.8 / k
    for s, nb in enumerate(aware_nbs):
        lf = per_pc_long_fraction(runs[(nb, "aware")], pcmap.get((nb, "aware"), {}))
        xs = [j + (s - (k - 1) / 2.0) * w for j in range(N_PC)]
        ys = [lf.get(j) or 0 for j in range(N_PC)]
        ax.bar(xs, ys, width=w, zorder=3, label=nb.replace("atk_", ""))
    ax.axhline(LONG_FLIP, ls=":", lw=0.9, color="#333")
    ax.set_xticks(range(N_PC))
    ax.set_xticklabels([f"PC{j}\nO{OSHORT[j]}/{OLONG[j]}\n{'contest' if j in CONTEST else 'anchor'}"
                        for j in range(N_PC)], fontsize=8)
    ax.set_ylim(0, 1.0)
    ax.set_ylabel("per-PC long-offset fraction")
    ax.set_title("filltime_steer: rising attacker fill-latency steers contestable PCs "
                 "short->long\n(bandwidth path OFF; anchors hold)", fontsize=9.5)
    ax.legend(frameon=False, fontsize=8, title="intensity")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"chart written to {path}")


if __name__ == "__main__":
    main()
