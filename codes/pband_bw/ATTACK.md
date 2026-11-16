# Attack Methodology — `pband_bw`: Multi-PC p-Band Steering

Self-contained methodology for the **`pband_bw`** attack on the Pythia (scooby) L2 prefetcher.
`policy_bw` flips *one* contestable PC between gamble and abstain. `pband_bw` extends it to a
victim with **several PCs of differing predictability** and asks: can a blind neighbor drive a
**differentiated** joint policy — some PCs abstain, others keep prefetching — with a single
switch, and know *which* PCs it captures?

---

## 0. The idea in one paragraph

Under the high-bandwidth (HBW) reward table, a PC's fate depends on its **realized**
correctness vs the EV-flip break-even `p ≈ 0.353`: PCs below the edge collapse to abstain, PCs
above it keep prefetching. A victim that mixes low- and high-predictability load PCs therefore
responds to one blind, **binary** bandwidth switch with a *differentiated* joint policy — the
contestable PCs lose their prefetcher, the predictable ones do not. A single contestable blob
collapses globally; a mixed-predictability victim does not. That mix is the attack.

---

## 1. Threat model

Identical to the family: dual-core ChampSim, shared LLC, single shared DRAM channel; victim on
core 0 runs Pythia in a fixed bandwidth-aware config; attacker on core 1 is a static synthetic
trace with **no victim knowledge**, lever = its own DRAM read rate. Only assumed knowledge: the
public fact that Pythia's bandwidth signal is **global**, plus the EV math. Reuses the
`policy_bw` reward lever unchanged — `pband_bw` differs only in the **victim** (six mixed-`p`
PCs) and a read-only per-PC measurement counter.

---

## 2. The shared channel

Every 256 cycles ChampSim buckets the **aggregate** DRAM read-enqueue over all cores into a
level 0–3 and broadcasts the *same* value to every core's Pythia (`src/main.cc:964-978` →
`src/cache.cc:1769` → `Scooby::update_bw`). No per-core accounting. The attack sets
`scooby_high_bw_thresh = 3` so bucket 3 trips the HBW path.

### The lever is binary

The shared bucket saturates (`bw3 ≥ 0.82`) at **< 5 % instantaneous duty**, and `is_high_bw()`
is a hard threshold. There is no graded duty→bandwidth dial — the attacker has an **on/off
switch**. So `pband_bw` uses only two neighbors: `atk_idle` and `atk_heavy`; intermediate
intensities give no gradation. (`blend_bw` later recovers a continuous dial by toggling this
switch *in time*.)

---

## 3. The mechanism: reward shaping, per PC

Same two reward tables as `policy_bw`:

| reward          | normal | high-bandwidth |
|-----------------|:------:|:--------------:|
| correct_timely  |  +20   |  +20 |
| incorrect       |  −8    |  **−14** |
| none (abstain)  |  −4    |  **−2** |

Break-even predictability: normal `p* = 0.143`, HBW `p* = 0.353`. Under the binary HBW switch,
each PC's fate is decided by its realized correctness vs that edge:

- **Contestable PC** (realized `p` below the edge): low confidence → Pythia routes its gambles
  to the featurewise fallback action **+1** (realized-correct ≈ 0) → under the harsher HBW
  `incorrect` penalty, abstain wins → **collapses to action 0**.
- **Predictable PC** (`p` above the edge): high confidence → gambles its **signature**
  confidently (signature fraction ≈ 0.99), realized-correct > 0.353 → HBW still favors
  prefetch → **resists** the switch.

One blind switch therefore produces a *differentiated* joint policy.

### Two assumptions the design had to correct

1. **No intra-band staircase by duty.** Because the lever is binary (§2), there is no dialing
   a p-ordered staircase by attacker duty cycle — the attacker chooses *when* to collapse the
   whole contestable set, not a per-PC subset.
2. **Fallback washout.** Pythia's featurewise engine routes low-confidence predictions to
   action **+1** (`le_featurewise_enable_action_fallback`). Contestable PCs are low-confidence,
   so their gambles land on +1 regardless of signature — per-PC behaviour is **invisible in the
   aggregate** `scooby_predict_action_*` histogram. The fix is a **read-only per-PC action
   counter** in scooby (`scooby_enable_per_pc_stats`): a per-trigger-PC histogram incremented
   exactly where the aggregate `action_dist` is counted, gated by a knob (default off),
   affecting **no** prefetch decision. It is the measurement instrument, not part of the attack.

---

## 4. The victim

6 load PCs, `(p, signature)` = `[(0.30,3),(0.33,4),(0.45,5),(0.55,11),(0.75,12),(0.95,22)]`.
Each PC advances its own disjoint region by its signature with probability `p`, else by a
**non-action** noise delta `{7,8,9,13,14}` (so Pythia can only ever be correct on the
signature, and the fingerprint is clean). Signatures avoid +1 (the fallback attractor); ~12 ALU
ops/load keep the victim's self-bandwidth low, so the attacker-idle baseline is clean
(`bw3 ≈ 0`). Contestable = `p < 0.4` (PCs at 0.30, 0.33); anchors = the rest.

---

## 5. Config

- `aware.ini` (the attack): `scooby_high_bw_thresh = 3`, `scooby_enable_hbw_reward = true`, HBW
  degree curve pinned **equal** to normal (`scooby_dyn_degrees_type2_hbw = 1,2,4,6` → degree
  lever off), `scooby_enable_per_pc_stats = true`.
- `blind.ini` (isolation control): identical **except** `scooby_enable_hbw_reward = false`.

Readout: scooby's **per-PC** per-trigger action counter (the aggregate histogram is washed out
by the +1 fallback). `rollup.py` maps each trigger IP to a `pband_pc_<j>` load site via `nm` on
the static, non-PIE `build/pband_bw_victim.out`. Headline metric is per-PC `f0 = frac(action
0)`.

### The predefined target

`PBAND_TARGET` is a **per-PC verdict vector** — the joint policy the switch reaches at
aware-heavy: `[abstain, abstain, gamble, gamble, gamble, gamble]` (contestable PCs abstain,
predictable prefetch).

---

## 6. Results (victim = core 0; per-PC abstain fraction `f0`)

| regime | bw3 | p=0.30 | p=0.33 | p=0.45 | p=0.55 | p=0.75 | p=0.95 |
|--------|:---:|:------:|:------:|:------:|:------:|:------:|:------:|
| aware idle  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| **aware heavy** | 0.875 | **0.68** | **0.74** | 0.00 | 0.00 | 0.00 | 0.00 |
| blind idle  | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |
| blind heavy | 0.867 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

Per-PC signature-gamble fraction confirms the mirror: at aware-heavy the contestable PCs drop
from signature ≈ 0.95/0.99 to ≈ 0.19/0.20 (they stop gambling their signature), while the four
predictable PCs hold signature ≈ 0.99–1.00. `abstain(p)` at aware-heavy is a clean **step** at
the EV-flip edge — a staircase in *p-space*.

### Isolation control (decisive)

Blind-heavy has the *same* `bw3 = 0.867` yet **no PC abstains** (`f0 = 0` for all six). The
collapse is the reward *signal*, not the contention the heavy attacker also produces.

---

## 7. Success gates (`rollup.py`) — all PASS

1. **[PASS] Differentiated steering:** contestable PCs flip gamble → abstain idle → heavy;
   predictable PCs keep gambling their signature.
2. **[PASS] Staircase step:** `min(contestable f0) − max(predictable f0) = 0.68 − 0.00 = 0.68 >
   0.4` at aware-heavy.
3. **[PASS] Named joint-target hit:** per-PC verdict vector `== PBAND_TARGET`
   (`[abstain, abstain, gamble, gamble, gamble, gamble]`).
4. **[PASS] Isolation:** blind-heavy same `bw3` (0.87) yet no contestable PC abstains.
5. **[PASS] Degree held:** `deg≥4` (among gambling prefetches) stable idle → heavy (|Δ| = 0.06
   < 0.15).

**Status: 5 / 5 gates PASS.**

---

## 8. What is steered — and the honest scope

The attacker selects a **subset** of the victim's PCs to deprive of prefetching — richer than
`policy_bw`'s single-PC flip. **Scope limit:** the lever is binary and the reward threshold
single, so this is **one step, not a multi-step dial**; the attacker cannot place an arbitrary
per-PC subset — it chooses *when* to collapse the whole contestable set, and from public
knowledge of the band knows *which* PCs that captures. Widening the lever into a continuous
ramp is `blend_bw`'s job.

---

## 9. Root cause and mitigation

Root cause (shared with the family): **Pythia consumes a system-wide bandwidth signal with no
per-core isolation**, so a blind neighbor can select which of the victim's PCs lose their
prefetcher — a differentiated, per-PC denial driven by one switch.

**Mitigation:** derive Pythia's bandwidth level from **per-core** DRAM accounting rather than
the single global counter (`src/main.cc:964-978`).

---

## 10. How to run

```bash
source scripts/set_env.sh
./scripts/launch.sh pband_bw
```

Outputs land in `experiments/pband_bw/`: `<neighbor>_<cfg>.out` (2 neighbors × `aware`/`blind`
= 4 runs), `rollup.txt` (with the per-PC tables), `rollup.csv`, and the per-PC chart
`degree_dist.png`. `rollup.py` also reads `build/pband_bw_victim.out` via `nm` to map trigger
PCs to load sites.
