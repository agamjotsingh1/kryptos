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
  `correct_untimely` 12→20, collapsing the crossover) — the isolation control.
- **Gates A–F + D′** in `rollup.py`, with offline unit tests (25, all green).

**Isolation is structural, via `scooby_high_bw_thresh = 4 > max bucket level 3`** (the bucket
maxes at 3, so `is_high_bw()` can never fire; asserted by `test_configs.test_bandwidth_path_off`).
Note gate E's `*_high_bw == 0` check is only *necessary*, not sufficient: with
`enable_hbw_reward=false` those columns are structurally 0 whatever the bucket does
(`scooby.cc:722`). The committed evidence shows the bucket *did* reach L3 under attack
(`bucket L3` 0.00→0.92), so the isolation is "Pythia ignores a bucket it does see," not "the
bucket was never raised."

## 3. Result

`experiments/filltime_steer/rollup.txt` / `rollup.csv` (victim = core 0, `TRACE=15M/WARMUP=3M/SIM=12M`):

| aware run | idle | atk_lo | atk_mid | **atk_hi** |
|-----------|:----:|:------:|:-------:|:----------:|
| contestable long-fraction | 0.00 | 0.00 | 0.00 | **0.00** |
| victim **timely-fraction** | 0.40 | 0.40 | 0.40 | **0.39** |
| victim IPC | 1.39 | 1.37 | 1.35 | **1.25** |
| bucket L3 fraction | 0.00 | 0.00 | 0.37 | **0.92** |

**Gates: 5/7 PASS.** The attacker **contends hard** (IPC 1.39→1.25, bucket 0→0.92), yet the
victim's timely-fraction is **invariant** (0.40→0.39) and no offset ever flips (long-fraction
0.00 throughout). FAIL — **A** (distance steer) and **B** (crossover): the two steering gates,
failed by reality. A confirmatory **degree=1 probe** (uncommitted config: set
`scooby_enable_dyn_degree=false`; reproduce via §6) shows the same invariance from the opposite
extreme — short offset ~100% timely, `atk_hi` only 0.98.

*Honest reading of the passes:* **D′** (no −8 contamination, 0.009) is a real, non-vacuous pass —
but it only proves `O_short` (= the literal stride) is demand-reused, which is near-trivial; the
`O_long` offsets are selected so rarely (<~100×, OOB-heavy) that the dual-touch claim is
effectively untested for them. **C, D, F** pass only because *nothing moves* (0.00→0.00
everywhere) — they are vacuous here, not evidence of a working selector/isolation. **E** is the
necessary-not-sufficient check above. So the load-bearing facts are the two measured FAILs plus
the timely-fraction/IPC/bucket evidence, not a "5/7" score.

## 4. Why — the leading explanation (scale-invariance), and a confound

**Measured:** the victim's timely-fraction is invariant to contention (0.40→0.39 while IPC falls
1.39→1.25 and the bucket saturates). That is the hard result.

**Inferred mechanism (not directly measured):** a prefetch of offset `O` is timely iff
`L < O · T_line`, i.e. iff `O > O* = L / T_line`. The attacker hoped to move `O*` by raising `L`.
But the victim is memory-bound — every demand misses to the *same* shared memory the prefetch
fills from — so its per-line time `T_line` scales with `L` too, and `O* = L / T_line` stays
≈ constant. Raising `L` lengthens the victim's lead-time in lock-step; the *ratio* timeliness
depends on does not move. This matches the observed invariance, and is the "pure slowdown is
scale-invariant" concern noted at design time. **Caveat:** `T_line` and `L` are not separately
logged, so this is the consistent explanation, not a measured one.

**A second, not-excluded cause of "long-fraction = 0":** exploration is near-off
(`scooby_epsilon ≈ 0.0018`), so `O_long` is tried only ~tens–hundreds of times and never
accrues a timely record — Pythia stays on `O_short` partly because it never meaningfully samples
the alternative, independent of any latency argument. The experiment does not disentangle this
from scale-invariance. Both point the same way (no steering); the *timely-fraction* invariance
(§3) is the claim that does not depend on either.

Either way the conclusion is channel-specific: it does **not** apply to the bandwidth-reward
channel the four dossier attacks use (that channel reads an *absolute* bucket, not a *ratio*),
which is why those steer and this does not.

## 5. Honest scope / what this proves

- The fill-timing reward classification **is** a real, bandwidth-independent surface (isolation is
  structural via `high_bw_thresh=4`; `incorrect ≈ 0.009`). The dossier's bandwidth mitigation
  would not touch it.
- But the neighbor **does not steer it**: timely-fraction is invariant to contention. The best
  explanation is ratio scale-invariance (§4), with low-exploration under-sampling of `O_long` as
  a not-excluded co-cause; a single-neighbor contention budget (~10% IPC) is not obviously the
  limit, the limit looks structural.
- **Caveats this experiment does not resolve:** (a) the idle baseline is *not* the clean
  "`O_short` timely at idle" the design wanted — at dyn-degree `O_short` is predominantly
  *untimely* at idle (offset 3/4/5 timely-fraction 0.20/0.27/0.34), and the degree=1 probe
  (`O_short` ~1.0 timely) is a *different* regime; (b) the anchor PC3 never flips, but because
  `O_long` is under-explored/OOB, **not** because `O_short` is timely (offset 3 is in fact the
  *least* timely); (c) there is an undisclosed-by-design **out-of-bounds** tail — prefetches
  crossing Pythia's 64-line page get `−12` (e.g. offset 11 ≈ 17% OOB), so the channel is a
  *three*-outcome signal (timely/untimely/OOB), not the pure two-outcome one the pitch implies.
  OOB is also contention-invariant, so it does not rescue steering.
- **Boundary on the thesis:** Pythia's *bandwidth-indexed* reward is weaponizable; its
  *timeliness* reward, on this evidence, is not. The channel carrying an absolute system signal
  is the attackable one; the channel carrying a latency *ratio* is self-cancelling. A useful
  sharpening of why the dossier's four attacks work.

## 6. Reproduce

```bash
source scripts/set_env.sh
TRACE_INSTR=15000000 WARMUP=3000000 SIM=12000000 ./scripts/launch.sh filltime_steer
# degree=1 confirmatory probe: set scooby_enable_dyn_degree=false in aware.ini/flat.ini, rerun.
```

Offline harness tests (no simulator): `python3 -m unittest discover -s codes/filltime_steer/tests`.
