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
OSHORT = [3, 4, 5, 22, 23]
OLONG = [10, 11, 12, 30, 32]
N_PC = 5
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


if __name__ == "__main__":
    # CLI is completed in Task 5 (evaluate_gates + table/CSV/plot).
    ap = argparse.ArgumentParser()
    ap.add_argument("--exp-dir")
    ap.add_argument("--attack")
    ap.add_argument("--manifest")
    ap.add_argument("--csv")
    ap.add_argument("--plot")
    ap.parse_args()
    print("rollup.py: parsing layer ready (gates added in Task 5)", file=sys.stderr)
