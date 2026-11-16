# Attack Methodology — `policy_bw`: Policy (Action-Distribution) Steering

Self-contained methodology for the **`policy_bw`** attack on the Pythia (scooby) L2
prefetcher. Where `degree_bw` moves *how aggressive* the victim is, `policy_bw` moves *what
the victim decides* — it drives the victim's learned **action distribution** (which prefetch
deltas it selects) toward a target the attacker names in advance, **while the degree curve is
held constant** so the effect is provably action-selection, not degree.

---

## 0. The idea in one paragraph

Pythia modulates its **reward table** by the global DRAM-bandwidth level. The high-bandwidth
table punishes wrong prefetches harder and makes abstaining cheaper. For a victim whose best
action is only *marginally* worth prefetching, that reward shift flips the expected-value
calculation: under the normal table it prefetches, under the high-bandwidth table it abstains.
A blind neighbor raises the global bucket with its own traffic, swaps the victim onto the
harsher table it never earned, and collapses the victim from *gamble* (prefetch a nonzero
delta) to *abstain* (action 0). Degree is pinned equal in both regimes, so the only thing that
can move is the action choice.

---

## 1. Threat model

Identical to `degree_bw` (and the whole family): dual-core ChampSim, shared LLC, single shared
DRAM channel; victim on core 0 runs Pythia in a fixed bandwidth-aware config; attacker on core
1 is a static synthetic trace with **no victim knowledge**, whose only lever is its own DRAM
read rate (set by footprint). The only assumed knowledge is the public architectural fact that
Pythia's bandwidth signal is **global**, plus the EV math below. **The attacker here is
identical to the `degree_bw` attacker** — same channel, same footprint dial. Only the victim
and the config lever differ.

---

## 2. The shared channel

Every 256 cycles ChampSim buckets the **aggregate** DRAM read-enqueue count over all cores
into a level 0–3 and broadcasts the *same* value to every core's Pythia (`src/main.cc:964-978`
→ `src/cache.cc:1769` → `Scooby::update_bw`). No per-core accounting: the bucket the victim
reads reflects the attacker's traffic as much as its own. The attack sets
`scooby_high_bw_thresh = 3` so bucket 3 trips the high-bandwidth (HBW) path.

---

## 3. The mechanism: reward shaping

Pythia keeps two reward tables and swaps by bandwidth level. The HBW table is harsher on wrong
prefetches and gentler on abstaining:

| reward          | normal | high-bandwidth |
|-----------------|:------:|:--------------:|
| correct_timely  |  +20   |  +20 |
| incorrect       |  −8    |  **−14** |
| none (abstain)  |  −4    |  **−2** |

Reward shaping changes which actions accumulate Q-value under SARSA, and therefore which action
the agent settles on. The HBW table discourages gambling (harsher `incorrect`) and makes
abstaining cheap (gentler `none`).

### Why it needs a *contestable* victim — the EV-flip band

Consider an action correct with probability `p` (reward +20) and wrong with `1 − p`.
Prefetching beats abstaining when:

- **normal reward:** `28p − 8 > −4`  ⇒  `p > 0.143`
- **high-bw reward:** `34p − 14 > −2`  ⇒  `p > 0.353`

So for **`p ∈ (0.143, 0.353)`** the *same* workload flips: normal-reward Pythia prefetches
(a nonzero delta wins), HBW-reward Pythia **abstains** (action 0 wins). That band is the whole
attack.

A **trivially predictable** victim (best action `p ≈ 1`, e.g. the `degree_bw` +1 stride) is
**not** steerable this way: its action is always correct, `correct_timely` is unchanged by
regime, and the harsher `incorrect` penalty never bites. The victim must be *contestable*.

---

## 4. The victim

Load addresses advance by a delta drawn **i.i.d. uniform over {1, 3, 4, 5} cache lines** (all
members of `scooby_actions`), wrapped to a 65536-line (~4 MiB) region, one ALU op per load.
With four equiprobable deltas and no predictive structure, any single Pythia action is correct
`p ≈ 0.25` — squarely inside the flip band `(0.143, 0.353)`. This is the victim's *own*
program; constructing it uses no attacker-side victim knowledge (the attacker never sees these
addresses — it only needs the architectural fact that such a victim's action choice is
reward-sensitive).

---

## 5. Config

- `aware.ini` (the attack): `scooby_high_bw_thresh = 3`, `scooby_enable_hbw_reward = true`,
  and the HBW degree curve pinned **equal** to normal (`scooby_dyn_degrees_type2_hbw =
  1,2,4,6`). Pinning the degree curves equal turns the degree lever **off** — any policy
  movement is reward-shaping alone.
- `blind.ini` (isolation control): identical **except** `scooby_enable_hbw_reward = false`.
  The bucket still trips (same `bw3`), but the reward table never swaps.

Readout: scooby's aggregate action-distribution histogram, parsed by `rollup.py`. Headline
metric is the **abstain fraction** `f0 = frac(action 0)`.

### The predefined target

```
rollup.py  PI_ABSTAIN = {0: 0.84, 1: 0.16}   # collapse the victim to abstain (action 0)
```

Success = the victim's measured action distribution converges to this target (small L1) and is
far from the no-attack baseline.

---

## 6. Results (victim = core 0)

| neighbor (aware) | bw3 | abstain f0 | top action | L1 to target | deg≥4 | IPC |
|------------------|:---:|:----------:|:----------:|:------------:|:-----:|:---:|
| `atk_idle`     | 0.043 | 0.000 | 5 (gamble)  | 1.679 | 0.689 | 0.630 |
| `atk_light`    | 0.692 | 0.396 | 5 (gamble)  | 1.193 | 0.688 | 0.500 |
| `atk_medium`   | 0.742 | 0.788 | 0 (abstain) | 0.420 | 0.689 | 0.415 |
| **`atk_heavy`**| 0.924 | **0.814** | 0 (abstain) | **0.371** | 0.691 | 0.399 |

The attacker dials the victim from gamble to **abstain** (`f0` 0.00 → 0.81), and `deg≥4` stays
≈ 0.69 throughout — the move is action-selection, **not** degree.

### Isolation control (decisive)

A **reward-blind** victim (`scooby_enable_hbw_reward = false`) under the *same* heavy attacker:

| neighbor (blind) | bw3 | abstain f0 | top action |
|------------------|:---:|:----------:|:----------:|
| `atk_idle`     | 0.042 | 0.000 | 5 |
| `atk_heavy`    | 0.934 | **0.000** | 5 |

Same bucket-3 saturation (`bw3 = 0.934`), yet the blind victim **never abstains** — it only
keeps gambling. The abstain collapse happens only when the reward signal is live ⇒ the
steering is the **signal**, not contention.

---

## 7. Success gates (`rollup.py`)

1. **[PASS] Steering:** `f0` rises idle → heavy; `f0_heavy > 0.6` and `f0_heavy − f0_idle >
   0.3`. (Observed: 0.00 → 0.81.)
2. **[FAIL] Target hit:** `L1(aware-heavy, PI_ABSTAIN) < 0.3`. Observed **L1 = 0.371** —
   narrowly over threshold. The victim collapsed to abstain (`f0 = 0.81`, top action 0) but
   did not land tightly enough on the exact `{0: 0.84, 1: 0.16}` shape.
3. **[PASS] Isolation:** same high `bw3` in aware and blind, but `f0` collapses only in aware
   (0.81 vs 0.00).
4. **[PASS] Degree held:** `|deg≥4 aware-idle − aware-heavy| = 0.002 < 0.15`.

**Status: 3 / 4 gates PASS.** The core claim — reward-signal-driven, degree-isolated collapse
to abstain — holds on all three decisive gates; only the *exact-target-shape* gate is narrowly
missed (`L1 = 0.371` vs the 0.3 bar). The steering direction, magnitude, and isolation are all
confirmed.

---

## 8. What is steered — and the honest scope

The attacker drives the victim's **decision** from π_gamble (prefetch nonzero deltas) to
π_abstain (action 0, no prefetch), with the degree lever held off.

**Reachable-target limit (honest scope):** the lever is one scalar (the global bucket) and the
HBW branch is a **binary** threshold, so the reachable target set is ~1-dimensional: the
action distribution interpolates between π_gamble (idle) and π_abstain (saturated) by **duty
cycle** (fraction of epochs above threshold). In practice even a *light* attacker nearly
saturates the bucket, so the dial is more switch-like than smooth — which is exactly why the
exact-shape target (gate 2) is hard to hit precisely. The attacker's target must lie on this
reachable curve; this is **not** an arbitrary-target attack. (`pband_bw` extends this to a
*differentiated* multi-PC target; `blend_bw` recovers a continuous duty dial by toggling the
switch in time.)

---

## 9. Root cause and mitigation

Root cause (shared with the family): **Pythia consumes a system-wide bandwidth signal with no
per-core isolation**, so a neighbor's traffic enters the victim's reward loop and redirects
what the RL agent learns to do.

**Mitigation:** derive Pythia's bandwidth level from **per-core** DRAM accounting rather than
the single global counter (`src/main.cc:964-978`), so one core's traffic cannot swap another
core's reward table.

---

## 10. How to run

```bash
source scripts/set_env.sh
./scripts/launch.sh policy_bw
```

Outputs land in `experiments/policy_bw/`: `<neighbor>_<cfg>.out` (4 intensities ×
`aware`/`blind`), `rollup.txt`, `rollup.csv`, and the action-distribution chart
`degree_dist.png`.
