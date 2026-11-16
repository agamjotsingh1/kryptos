# `filltime_steer` — fill-timing prefetch-distance steering (NEGATIVE result)

**Status:** ✅ harness + isolation verified; ❌ **steering does not occur** — a clean,
well-characterized **negative**. The fill-timing channel is real and provably independent of
the DRAM-bandwidth channel, but it is **not weaponizable** by a co-located neighbor, for a
structural reason (§4). Spec: `docs/superpowers/specs/2026-11-16-filltime-steer-design.md`.

This is the fifth attack studied against Pythia and the first to target a channel **other** than
the global DRAM-bandwidth bucket. The four attacks in `DOSSIER.md` steer Pythia through its
bandwidth-indexed reward/degree tables and all require the HBW path **on**
(`scooby_high_bw_thresh = 3`). `filltime_steer` turns that path **off**
(`scooby_high_bw_thresh = 4`) and asks whether the *base* reward's timely/untimely
classification is a second, independent steering channel. Answer: the channel exists and is
isolated, but a neighbor cannot move it.

---

## 1. The idea

Pythia's base reward scores a demand-reused prefetch `+20` if it filled before its demand
(**timely**) and `+12` if after (**untimely**) — purely a *timing* classification
(`prefetcher/scooby.cc:655`). Fill timing is set by memory latency `L`, which a co-located
neighbor raises through shared-LLC/DRAM-queue contention **without touching the bandwidth
bucket**. Because a prefetch of offset `O` is demanded after the victim advances `O` lines, the
hypothesis was: raising `L` moves the timely↔untimely crossover `O* = L / T_line`
(`T_line` = victim time per line), so a victim with two viable offsets (`O_short`, `O_long`)
could be steered short→long by the neighbor's blind intensity.

## 2. What was built (and verified)

- **Dual-touch victim** (`victim.c`): a single-load constant-stride march per PC. Every access is
  a Pythia trigger from which offsets `{S, 2S, 3S, …}` are all future demands, so `O_short` and
  `O_long` (two action-multiples of `S`) are **both always correct** — whichever Pythia picks is
  demand-reused, so contention can only make it *late*, never *wrong*. Confirmed: global
  `incorrect` ≈ **0.009** (gate D′). Four PCs: contestable 0–2 (`S=5,4,11`), anchor 3 (`S=3`,
  high ALU).
- **Blind attacker** (`attacker.c`): own disjoint 64 MiB region, streaming rate dial via
  `alu_pad`. No victim knowledge, open-loop.
- **Configs:** `aware.ini` (bandwidth path off, `high_bw_thresh=4`), `flat.ini` (= aware but
  `correct_untimely` 12→20, collapsing the crossover) — the decisive isolation control.
- **Gates A–F + D′** in `rollup.py`, with offline unit tests (24, all green).

## 3. Result

`experiments/filltime_steer/rollup.txt` (victim = core 0, `TRACE=15M/WARMUP=3M/SIM=12M`):

| regime | idle | atk_lo | atk_mid | **atk_hi** | victim IPC | bucket |
|--------|:----:|:------:|:-------:|:----------:|:----------:|:------:|
| per-PC long-fraction (contestable) | 0.00 | 0.00 | 0.00 | **0.00** | — | — |
| victim **timely-fraction** (dyn-degree) | 0.40 | 0.40 | 0.40 | **0.39** | 1.39 → 1.25 | 0 → sat |
| victim **timely-fraction** (degree=1 probe) | 1.00 | 1.00 | 1.00 | **0.98** | 1.39 → 1.29 | 0 → sat |

**Gates: 5/7.** PASS — C (selectivity, trivially: nothing moves), D (isolation), **D′** (no −8
contamination, 0.009), **E** (bandwidth path off: all `*_high_bw` = 0, `is_high_bw` never fires),
F (benign ≈ idle). **FAIL — A** (distance steer: long-fraction 0.00 at every intensity),
**B** (crossover: contestable timely-fraction does not fall with intensity).

The attacker **does** contend (victim IPC 1.39→1.25, bucket 0→saturated), yet the victim's
timely-fraction is **invariant** to it. No offset ever flips. Shown across *both* Pythia degree
regimes (default dyn-degree and pinned degree=1), so the negative is robust, not a tuning miss.

## 4. Why — the structural reason (scale-invariance)

A prefetch of offset `O` is timely iff `L < O · T_line`, i.e. iff `O > O* = L / T_line`. The
crossover `O*` is what the attacker hoped to move by raising `L`. But **`T_line` scales with `L`
too**: the victim is memory-bound — every demand misses to the *same* shared memory the
prefetch fills from — so `T_line ≈ L`. Then `O* = L / T_line ≈ constant`, independent of
contention. Raising `L` lengthens the victim's per-line time in lock-step with the fill latency;
their ratio, which is what timeliness depends on, does not move. The neighbor cannot shift the
crossover, so it cannot flip any offset.

This is the "pure slowdown is scale-invariant" concern noted at design time, now confirmed
quantitatively. It is specific to the fill-timing channel and does **not** apply to the
bandwidth-reward channel the four dossier attacks use (that channel reads an *absolute*
bucket, not a *ratio*), which is why those steer and this does not.

## 5. Honest scope / what this proves

- The fill-timing reward classification **is** a real, bandwidth-independent surface (gate E, D′
  isolate it cleanly). The dossier's bandwidth mitigation would not touch it.
- But it is **not steerable** by a co-located neighbor, because the lever (`L`) scales the
  victim's own lead-time with it. A single-neighbor contention budget (~10% IPC) is not the
  limit; the limit is structural (ratio-invariance), so more contention would not help.
- **Boundary on the thesis:** Pythia's *bandwidth-indexed* reward is weaponizable; its
  *timeliness* reward is not. The channel that carries an absolute system signal is the
  attackable one; the channel that carries a latency *ratio* is self-cancelling. A useful
  sharpening of why the dossier's four attacks work.

## 6. Reproduce

```bash
source scripts/set_env.sh
TRACE_INSTR=15000000 WARMUP=3000000 SIM=12000000 ./scripts/launch.sh filltime_steer
# degree=1 confirmatory probe: set scooby_enable_dyn_degree=false in aware.ini/flat.ini, rerun.
```

Offline harness tests (no simulator): `python3 -m unittest discover -s codes/filltime_steer/tests`.
