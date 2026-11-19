#!/usr/bin/env python3
"""
rollup.py - result analysis for the 'blend_bw' time-toggled duty-cycle steering attack.

Victim (core 0) has EIGHT load PCs whose predictabilities BRACKET the three duty cutoffs
p*(d) ~ 0.208/0.264/0.310 (two PCs per band): p = 0.185,0.200 | 0.225,0.250 | 0.275,0.295
| 0.325,0.400. A PC abstains at duty d iff p < p*(d), so the sweep should resolve as a +2
staircase (d_lo flips 2 PCs, d_mid 4, d_hi 6). The neighbor (core 1) is the SAME
attacker toggled at THREE duty cycles (atk_d_lo/mid/hi):
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

import numpy as np

# --- victim definition (keep in lockstep with config.h) ---
# policy_target: TWO PCs. PC0 = contestable target (p=0.31), PC1 = anchor (p=0.55).
# The controller places PC0's abstain fraction f0 at a chosen setpoint via a calibrated
# duty; the anchor never flips (p > max reachable p*(d)=0.353).
BLEND_PCS = [(0.31, 4), (0.55, 11)]
BLEND_PMAX = 0.353         # contestable <=> p < this (p < p*(d=1))
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
        "agg": act,                      # full aggregate action histogram (action -> count)
        "per_pc": per_pc,
        "ipc": float(m.group(1)) if m else None,
    }


# ---------------------------------------------------------------------------
# the setpoint controller: fit f0 vs attacker on_lines, invert for targets
# ---------------------------------------------------------------------------
class InvResult(dict):
    """dict {target_f0: on_lines (int)} with a .clamped set of out-of-range targets."""
    clamped = None


def fit_invert(cal_points, targets):
    """Invert the calibrated f0(on_lines) ramp: for each target f0, the on_lines that
    realizes it, by monotone 1-D interpolation. cal_points = [(on_lines, f0), ...].
    Out-of-range targets clamp to the nearest sampled endpoint and are flagged in
    .clamped. The fixed toggle period makes on_lines a 1-parameter duty dial."""
    pts = sorted(cal_points, key=lambda t: t[1])      # ascending f0 for np.interp
    f0s = [float(p[1]) for p in pts]
    ons = [float(p[0]) for p in pts]
    r = InvResult()
    r.clamped = set()
    for tgt in targets:
        if tgt < f0s[0]:
            r[tgt] = int(round(ons[0]))
            r.clamped.add(tgt)
        elif tgt > f0s[-1]:
            r[tgt] = int(round(ons[-1]))
            r.clamped.add(tgt)
        else:
            r[tgt] = int(round(float(np.interp(tgt, f0s, ons))))
    return r


# ---------------------------------------------------------------------------
# gates (spec 2026-11-19-policy-target-design.md section 6)
# ---------------------------------------------------------------------------
def build_target_dist(f0star, signature):
    """The CLEAN named target a setpoint f0* implies: abstain (action 0) with weight
    f0*, the signature action with weight 1-f0*, everything else 0. Deliberately
    full-width-but-sparse so l1_full against it penalizes any realized mass that leaks
    into noise / off-by-one buckets -- that leak is exactly what a 2-bucket collapse
    would hide (spec gate 3 anti-degeneracy)."""
    return {0: f0star, signature: 1.0 - f0star}


def l1_full(agg_counts, target):
    """L1 distance over the UNION of action buckets, both normalized to sum 1. agg_counts
    is the full aggregate action histogram (action -> count); target is a weight dict."""
    tot = sum(agg_counts.values())
    norm = {a: c / tot for a, c in agg_counts.items()} if tot else {}
    keys = set(norm) | set(target)
    return sum(abs(norm.get(a, 0.0) - target.get(a, 0.0)) for a in keys)


def setpoint_gate(realized_by_target, tol):
    """realized_by_target: {target_f0: [f0 per seed]}. Returns {target: (passed, detail)}
    using the CROSS-SEED MEAN (spec gate 2), tolerance tol (or ~2 sigma, set by caller)."""
    out = {}
    for tgt, seeds in realized_by_target.items():
        n = len(seeds)
        mean = sum(seeds) / n if n else float("nan")
        var = sum((x - mean) ** 2 for x in seeds) / n if n else 0.0
        sd = var ** 0.5
        passed = (n > 0) and abs(mean - tgt) <= tol
        out[tgt] = (passed, f"mean={mean:.3f} sd={sd:.3f} |mean-tgt|={abs(mean - tgt):.3f} "
                            f"tol={tol:.3f} n={n}")
    return out


def anchor_gate(f0_by_duty, thresh):
    """True iff the anchor PC stays below `thresh` at EVERY verification duty (spec gate 4
    -- checked at the actual verification duties, not nominal ones)."""
    vals = list(f0_by_duty.values())
    return bool(vals) and all(v < thresh for v in vals)


def isolation_gate(blind_f0_by_duty, thresh):
    """True iff the contestable PC never abstains under blind at any duty (spec gate 5)."""
    vals = list(blind_f0_by_duty.values())
    return bool(vals) and all(v < thresh for v in vals)


def monotone_gate(seq, tol):
    """True iff `seq` is non-decreasing allowing a dip of at most `tol` (spec gate 1)."""
    return all(seq[i + 1] >= seq[i] - tol for i in range(len(seq) - 1))


def degree_gate(vals, tol):
    """True iff deg>=4 spread across duties is below `tol` (spec gate 6: degree held)."""
    return bool(vals) and (max(vals) - min(vals) < tol)


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
    """Return (victims, neighbors, configs). victims is the list of multi-victim seed
    names (empty for the single-victim calibration form)."""
    victims, neighbors, configs = [], [], []
    with open(path) as f:
        for line in f:
            line = line.split("#", 1)[0].split()
            if not line:
                continue
            if line[0] == "victim" and len(line) >= 3:     # multi-victim: victim <name> <src> ...
                victims.append(line[1])
            elif line[0] == "neighbor":
                neighbors.append(line[1])
            elif line[0] == "config":
                configs.append(line[1])
    return victims, neighbors, configs


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




# ---------------------------------------------------------------------------
# policy_target controller + gates driver
# ---------------------------------------------------------------------------
PERIOD = 80                      # fixed toggle period (on + off); duty is the 1-D dial
SETPOINTS = [0.25, 0.50, 0.75]   # the named abstain-fraction targets
CONTESTABLE_J = 0                # PC0 = contestable target
ANCHOR_J = 1                     # PC1 = anchor

# gate thresholds (final values set from the spike / Task 5; printed always)
SETPOINT_TOL = 0.10              # |mean(f0) - f0*| must be <= this (gate 2)
L1_MAX = 0.30                    # full-histogram L1 at the mid setpoint (gate 3)
ANCHOR_F0_MAX = 0.50             # anchor must stay below this at every duty (gate 4)
ISO_F0_MAX = 0.15                # blind contestable f0 must stay below this (gate 5)
DEG_TOL = 0.05                   # deg>=4 spread across duties (gate 6)


def _on_from_name(nb):
    m = re.search(r"on(\d+)", nb)
    return int(m.group(1)) if m else None


def _target_from_name(nb):
    m = re.search(r"ver_f(\d+)", nb)
    return int(m.group(1)) / 100.0 if m else None


def make_plot(cal_pts, inv, path):
    """f0 vs attacker on_lines (the calibrated ramp) with the three setpoints marked."""
    plt = _mpl()
    if not plt or not cal_pts:
        return
    xs = [on for on, _ in sorted(cal_pts)]
    ys = [f0 for _, f0 in sorted(cal_pts)]
    fig, ax = plt.subplots(figsize=(8, 4.6))
    ax.plot(xs, ys, "-o", color="#1f77b4", label="calibrated f0(on_lines)")
    for tgt in sorted(inv):
        on = inv[tgt]
        ax.axhline(tgt, color="#999", lw=0.7, ls=":")
        ax.scatter([on], [tgt], color="#a50026", zorder=5)
        ax.annotate(f"f0*={tgt:g}\non={on}", (on, tgt), textcoords="offset points",
                    xytext=(6, -4), fontsize=8)
    ax.set_xlabel("attacker on_lines (period %d)" % PERIOD)
    ax.set_ylabel("contestable PC0 abstain fraction f0")
    ax.set_title("policy_target: setpoint controller (f0 vs duty)")
    ax.set_ylim(-0.02, 1.02)
    ax.legend(loc="lower right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    print(f"plot written to {path}")


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir", required=True)
    ap.add_argument("--attack", default="policy_target")
    ap.add_argument("--manifest", help="codes/<attack>/matrix")
    ap.add_argument("--victim-bin", help="victim binary for nm PC mapping")
    ap.add_argument("--csv", help="also write the CSV here")
    ap.add_argument("--plot", help="write the f0-vs-duty PNG here")
    ap.add_argument("--emit-matrix", action="store_true",
                    help="print verification neighbor+seed lines for the computed duties")
    ap.add_argument("--tol", type=float, default=SETPOINT_TOL,
                    help="setpoint tolerance (default %.2f; widen to ~2 sigma per the spike)"
                         % SETPOINT_TOL)
    args = ap.parse_args()

    if not args.manifest:
        sys.exit("need --manifest")
    victims, neighbors, configs = read_manifest(args.manifest)

    build_dir = os.environ.get("BUILD_DIR") or os.path.join(here, "..", "..", "build")
    victim_bin = args.victim_bin or os.path.join(build_dir, f"{args.attack}_victim.out")
    ranges = pc_symbols(victim_bin)

    def seed_files(nb, cfg):
        if victims:
            return [os.path.join(args.exp_dir, f"{v}_{nb}_{cfg}.out") for v in victims]
        return [os.path.join(args.exp_dir, f"{nb}_{cfg}.out")]

    def parsed(nb, cfg):
        return [r for r in (parse_run(p) for p in seed_files(nb, cfg)) if "missing" not in r]

    def pcf0(r, j):
        pcmap, _ = map_pcs(r["per_pc"], ranges)
        ip = pcmap.get(j)
        return pc_f0(r["per_pc"].get(ip, {})) if ip is not None else None

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return (sum(xs) / len(xs)) if xs else None

    cal_nbs = sorted([nb for nb in neighbors if _on_from_name(nb) is not None and
                      _target_from_name(nb) is None], key=_on_from_name)
    ver_nbs = sorted([nb for nb in neighbors if _target_from_name(nb) is not None],
                     key=_target_from_name)

    sig_pc0 = BLEND_PCS[CONTESTABLE_J][1]

    print(f"\n=== policy_target rollup (setpoint abstain-fraction controller) ===")
    print(f"victim: contestable PC{CONTESTABLE_J} (p={BLEND_PCS[CONTESTABLE_J][0]}, "
          f"sig={sig_pc0}); anchor PC{ANCHOR_J} (p={BLEND_PCS[ANCHOR_J][0]})")
    print(f"PC mapping via nm: {'ok' if ranges else 'FALLBACK (address order)'} "
          f"({victim_bin})")

    # ---- calibration fit (aware) ------------------------------------------
    cal_pts = []
    for nb in cal_nbs:
        rs = parsed(nb, "aware")
        f0 = mean([pcf0(r, CONTESTABLE_J) for r in rs])
        if f0 is not None:
            cal_pts.append((_on_from_name(nb), f0))
    inv = None
    if cal_pts:
        print("\n--- calibration: contestable f0 vs on_lines (aware) ---")
        for on, f0 in sorted(cal_pts):
            print(f"  on={on:>3} off={PERIOD - on:>3}  f0={f0:.3f}")
        inv = fit_invert(cal_pts, SETPOINTS)
        print("\n--- controller inversion: setpoint -> schedule ---")
        for tgt in SETPOINTS:
            on = inv[tgt]
            flag = "  [CLAMPED: out of calibrated range]" if tgt in inv.clamped else ""
            print(f"  f0*={tgt:.2f}  ->  on={on:>3} off={PERIOD - on:>3}{flag}")
    else:
        print("\n[WARN] no calibration points parsed (no aware cal_* runs yet)")

    # ---- emit verification matrix -----------------------------------------
    if args.emit_matrix and inv is not None:
        print("\n--- verification matrix (append to codes/policy_target/matrix) ---")
        for s in range(3):
            print(f"victim   v_s{s}  victim.c  {s}")
        for tgt in SETPOINTS:
            on = inv[tgt]
            print(f"neighbor ver_f{int(round(tgt * 100)):02d}  attacker.c  {on}  {PERIOD - on}")

    # ---- gates -------------------------------------------------------------
    print("\n--- gates ---")
    gate_rows = []

    # gate 1: monotone (calibration, aware)
    if len(cal_pts) >= 2:
        seq = [f0 for _, f0 in sorted(cal_pts)]
        gate_rows.append(("1 monotone-dial", monotone_gate(seq, MONO_TOL),
                          f"f0 seq {['%.2f' % v for v in seq]} (tol {MONO_TOL})"))

    # gate 6: degree held (calibration, aware)
    deg_vals = []
    for nb in cal_nbs:
        rs = parsed(nb, "aware")
        dv = mean([r.get("degge4") for r in rs])
        if dv is not None:
            deg_vals.append(dv)
    if deg_vals:
        gate_rows.append(("6 degree-held", degree_gate(deg_vals, DEG_TOL),
                          f"deg>=4 spread {max(deg_vals) - min(deg_vals):.3f} (tol {DEG_TOL})"))

    # gates 2-5 need verification runs
    if ver_nbs:
        realized = {}       # {target: [f0 per seed] aware}
        anchor_by_duty = {}
        blind_by_duty = {}
        agg_mid = {}
        for nb in ver_nbs:
            tgt = _target_from_name(nb)
            rs_a = parsed(nb, "aware")
            realized[tgt] = [pcf0(r, CONTESTABLE_J) for r in rs_a
                             if pcf0(r, CONTESTABLE_J) is not None]
            anchor_by_duty[nb] = mean([pcf0(r, ANCHOR_J) for r in rs_a])
            if "blind" in configs:
                rs_b = parsed(nb, "blind")
                blind_by_duty[nb] = mean([pcf0(r, CONTESTABLE_J) for r in rs_b])
            if abs(tgt - 0.50) < 1e-9:
                for r in rs_a:
                    for a, c in r["agg"].items():
                        agg_mid[a] = agg_mid.get(a, 0) + c

        # gate 2: setpoint accuracy
        sp = setpoint_gate(realized, args.tol)
        sp_pass = all(p for p, _ in sp.values()) and len(sp) == len(SETPOINTS)
        detail = "; ".join(f"f0*={t:.2f}:{d}" for t, (p, d) in sorted(sp.items()))
        gate_rows.append(("2 setpoint-accuracy", sp_pass, detail))

        # gate 3: full-histogram L1 at the mid setpoint (anti-degeneracy)
        if agg_mid:
            l1 = l1_full(agg_mid, build_target_dist(0.50, sig_pc0))
            mid_f0 = mean(realized.get(0.50, []))
            two_bucket = 2 * abs((mid_f0 if mid_f0 is not None else 0.50) - 0.50)
            l1_pass = l1 < L1_MAX
            note = ""
            mid_sp = sp.get(0.50, (False, ""))[0]
            if mid_sp and not l1_pass:
                note = "  STRUCTURAL-LIMIT: f0 on target, full-histogram shape NOT controllable"
            gate_rows.append(("3 L1-full-hist", l1_pass,
                              f"L1={l1:.3f} (max {L1_MAX}); 2-bucket collapse={two_bucket:.3f}"
                              f"{note}"))

        # gate 4: anchor holds (at verification duties)
        gate_rows.append(("4 anchor-holds",
                          anchor_gate({k: v for k, v in anchor_by_duty.items() if v is not None},
                                      ANCHOR_F0_MAX),
                          f"anchor f0 by duty { {k: round(v, 2) for k, v in anchor_by_duty.items() if v is not None} }"))

        # gate 5: isolation (blind flat)
        if blind_by_duty:
            gate_rows.append(("5 isolation-blind",
                              isolation_gate({k: v for k, v in blind_by_duty.items() if v is not None},
                                             ISO_F0_MAX),
                              f"blind contestable f0 { {k: round(v, 2) for k, v in blind_by_duty.items() if v is not None} }"))
    else:
        print("  (gates 2-5 pending: no verification ver_f* runs yet -- calibration phase)")

    for name, passed, detail in gate_rows:
        print(f"  [{'PASS' if passed else 'FAIL'}] gate {name}: {detail}")

    # ---- CSV + plot --------------------------------------------------------
    if args.csv:
        cols = ["neighbor", "cfg", "on_lines", "bw3", "f0_pc0", "f0_pc1", "deg_ge4"]
        rows = [",".join(cols)]
        for cfg in configs:
            for nb in cal_nbs + ver_nbs:
                rs = parsed(nb, cfg)
                if not rs:
                    continue
                on = _on_from_name(nb)
                rows.append(",".join([
                    nb, cfg, str(on if on is not None else "NA"),
                    fmt(mean([r["bw3"] for r in rs]), 3),
                    fmt(mean([pcf0(r, CONTESTABLE_J) for r in rs]), 3),
                    fmt(mean([pcf0(r, ANCHOR_J) for r in rs]), 3),
                    fmt(mean([r.get("degge4") for r in rs]), 3)]))
        with open(args.csv, "w") as f:
            f.write("\n".join(rows) + "\n")
        print(f"\nCSV written to {args.csv}")

    if args.plot and inv is not None:
        make_plot(cal_pts, inv, args.plot)


if __name__ == "__main__":
    main()
