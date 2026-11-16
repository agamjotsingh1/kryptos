# Design — `fallback_bw`: sub-threshold action-fallback steering of Pythia

**Status:** design, awaiting approval. Research-only, inside ChampSim, same threat
model as the four attacks in `DOSSIER.md`. Core 0 = victim, core 1 = attacker,
single shared DRAM channel, open-loop attacker with no victim knowledge.

---

## 1. Intent and the why

The four existing attacks (`degree_bw`, `policy_bw`, `pband_bw`, `blend_bw`) all
exploit the **same** two Pythia mechanisms — the HBW **degree curve** and the HBW
**reward table** — both reached through the `is_high_bw()` gate, which requires the
shared bandwidth bucket to **saturate** (`bw_level >= scooby_high_bw_thresh`, set to
3 in every attack). All four must first **enable a dormant path**: the shipped
`high_bw_thresh = 4 > max bucket 3`, so `is_high_bw()` never fires on defaults.

`fallback_bw` attacks a **third, distinct** bandwidth-gated mechanism that the four
miss: the featurewise engine's **action fallback**
(`src/learning_engine_featurewise.cc:401`, `do_fallback`). This surface is
qualitatively different and strictly widens the demonstrated attack family:

- **New mechanism.** Action *selection* default, not degree and not reward.
- **New regime.** Fires at `bw_level >= 1` (any non-idle neighbor, **sub-saturation**),
  via a **separate knob** `le_featurewise_bw_acc_check_level = 1` that is
  **independent of `scooby_high_bw_thresh`**. Smaller attacker footprint than the
  whole saturation-based family.
- **New property — live on shipped defaults.** Because the branch uses its own knob
  (not `high_bw_thresh`), it is active in the **default** `config/pythia.ini`. The
  "we enabled a dormant path" caveat the four attacks carry **does not apply**.
- **New capability.** The reward family only moves the gamble↔abstain *threshold*.
  Fallback **pins the victim to a specific concrete action (+1 next-line, action
  index 0)** when ON, and releases it to the learned policy when OFF. First attack
  in the family that forces/releases a *chosen offset*.

Why now: the user judged four attacks insufficient coverage of Pythia's steerable
surfaces and asked to broaden the family. This is the next attack in that program.

## 2. The mechanism (verified in source)

```
src/learning_engine_featurewise.cc:401  bool do_fallback(State *state)
  if(!enable_dyn_action_fallback) return enable_action_fallback;   // static (true)
  if(state->is_high_bw) return false;                               // branch 1: DORMANT
  else if(state->bw_level >= bw_acc_check_level(1)                  // branch 2: LIVE
          && state->acc_level <= acc_thresh(2)) return false;
  return true;                                                      // fallback ON
```

In `getMaxAction` (`:186`), `!fallback` sets `init_index = 1` so index 0 **is** in the
max search; when `fallback == true`, index 0 is **excluded** from the search and
`selected_action` stays defaulted to 0. Index 0 is `scooby_actions[0] = +1` (next
line). So:

- **fallback ON** → victim emits **+1 next-line** on any state whose other learned
  actions have `Q <= 0` (common for a contestable victim).
- **fallback OFF** → full Q consulted (index 0 included, abstain index 14 included)
  → victim runs its **learned policy**.

Inputs to branch 2, both verified:
- `bw_level` — the shared DRAM bucket (`src/main.cc:964-978`), **global aggregate over
  all cores**, threshold `>= 1` (any non-idle traffic; sub-saturation). Because it is
  aggregate, the **victim's own DRAM misses also raise it** — see §4a, the key victim
  constraint.
- `acc_level` — victim's **own** per-core L2 prefetch accuracy, `pf_useful/pf_filled`
  quantized into `CACHE_ACC_LEVELS = 10` buckets (`src/cache.cc:1878-1890`), broadcast
  every `measure_cache_acc_epoch = 1024` cycles. `acc_thresh = 2` ⇒ fires when victim
  accuracy `<= ~29%`. A **contestable** victim sits here naturally; no attacker
  influence on `acc_level` is required for A (that conjunction is candidate B, out of
  scope).

Default knobs confirmed in `src/knobs.cc`: `bw_acc_check_level = 1`, `acc_thresh = 2`,
`enable_dyn_action_fallback = true`, `enable_action_fallback = true`,
`measure_cache_acc = true`, `high_bw_thresh = 4`.

## 3. Goals / non-goals / anti-goals

**Goals**
- Demonstrate a neighbor's **sub-saturation** DRAM traffic flips the victim between
  the fixed **+1 next-line fallback** and its **learned policy**, through `do_fallback`
  branch 2, with the HBW **reward and degree levers held dead**.
- Show the flip is the **fallback signal**, not raw contention: an isolation control
  with `enable_dyn_action_fallback = false` sees the **same** bandwidth and does **not**
  flip.
- Show the effect is **live on default knobs** (no `high_bw_thresh = 3` edit; branch 1
  stays dormant at the default 4 — the flip comes only from branch 2).

**Non-goals**
- No reward-table steering (gamble↔abstain EV flip) — that is `policy_bw`. Here
  `enable_hbw_reward = false`.
- No per-PC differentiation (`pband_bw`) or duty-cycle dial (`blend_bw`). Aggregate
  action distribution is the readout.
- No attacker influence on `acc_level` via LLC pollution — that conjunction is
  candidate **B** (`acc_fallback_and`), explicitly deferred.

**Anti-goals (failure even if it "runs")**
- A flip that also appears under `enable_dyn_action_fallback = false` ⇒ it was raw
  contention / another mechanism, not fallback. Isolation **must** separate them.
- A victim whose `acc_level > 2` ⇒ branch 2 never fires ⇒ nothing to steer. Victim
  design must keep `acc_level <= 2` (verified from the acc histogram, gate).
- Needing `high_bw_thresh = 3` to see the effect ⇒ collapses into the existing family;
  must demonstrate on default thresh 4.

## 4a. The decisive victim constraint — a clean idle baseline (builder-check Q1)

`bw_level` is the **global** bucket, so the victim's *own* DRAM traffic raises it. This
is not hypothetical: in the real `experiments/policy_bw/atk_idle_aware.out` (victim =
single PC striding a **4 MiB** region, idle neighbor) the victim-solo bucket is already
`bw 173199 / 44765 / 32172 / 11374` ⇒ **P(bw_level ≥ 1) ≈ 0.34**, and
`dyn_fallback_saved_bw_acc = 1,050,768` — branch 2 **already fires ~1/3 of epochs with
no neighbor at all**. If `fallback_bw` reused that victim, the idle baseline would
*not* be fallback-ON/high-`f1`; the idle→busy contrast would be compressed or absent.
A wrong guess here is the difference between "works" and "no contrast to measure."

**Fix (verified geometry, 2-core build): make the victim LLC-resident.** `L2C = 512×8×64
= 256 KiB`; shared `LLC = NUM_CPUS·2048 × 16 × 64 = 4 MiB` (`inc/cache.h:65,74`).
policy_bw's 4 MiB region **equals** the whole LLC, so it spills to DRAM — that is the
pollution above. Size the `fallback_bw` victim region to **~1 MiB**: strictly larger
than L2 (256 KiB) so **every access still L2-misses** → Pythia triggers on every
access, prefetch volume stays high, accuracy stays low (`acc_level ≤ 2`), but well
inside the 4 MiB LLC so, when **solo**, demand/prefetch fills land in LLC and enqueue
**no DRAM reads** → victim-solo `bw_level ≈ 0`. A streaming neighbor (64 MiB) then both
adds its own DRAM traffic and evicts the victim from LLC; either way the shared bucket
rises to `≥ 1` — so the attacker is the one that moves it off the floor.

The acc side is already safe: the same real run shows victim `acc` histogram
`31013 / 22581 / 10352 / 1432` ⇒ **P(acc_level ≤ 2) ≈ 0.98**, so a contestable
random-delta victim sits in branch 2's accuracy regime robustly (builder-check Q2 is
mild; one delta-set iteration is budgeted if the spike shows drift).

## 4. Constraints

- ChampSim 2-core build, `DRAM_CHANNELS = 1`, same harness as the four attacks.
- Reuse the established attack scaffold: `codes/fallback_bw/{config.h, victim.c,
  attacker.c, aware.ini, blind.ini, matrix, rollup.py, ATTACK.md}`, run via
  `./scripts/launch.sh fallback_bw`, results in `experiments/fallback_bw/`.
- Stats available with no simulator change: `scooby_predict_action_<v>` (per-action
  counts), `scooby_cache_acc_level_<n>` (acc histogram), `scooby_bw_level_<n>` (bucket),
  `learning_engine_featurewise.action.fallback` and `.dyn_fallback_saved_bw_acc`
  (direct branch-2 firing counter), `Core_0_IPC`. First `scooby_*` block = core 0.
- No new knobs, no C++ edits expected. If verification shows a readout gap (e.g. the
  per-action count conflates forced-+1 with learned-+1), fall back to the per-PC
  counter already added for `pband_bw` (`scooby_enable_per_pc_stats`) — read-only, no
  decision change. Decided by the verification spike (§6), marked as a builder call.

## 5. Approaches considered

**(A1) Observe the +1-action fraction, chosen.** Victim = contestable i.i.d.-uniform
deltas drawn from a 4-set that **excludes 1**, e.g. `{3,4,5,10}` (all members of
`scooby_actions`). Best single action correct `p ~= 0.25` ⇒ accuracy ~25% ⇒
`acc_level ~= 2 <= thresh` (branch 2 eligible), and under the **normal** reward table
`p = 0.25 > 0.143` so the learned policy **gambles on {3,4,5,10}** — never +1. So +1
appears **only** via fallback.
- idle neighbor (`bw_level ~0`): branch 2 false ⇒ fallback ON ⇒ **+1 fraction high**.
- light/medium neighbor (`bw_level >= 1`, sub-saturation): branch 2 true ⇒ fallback
  OFF ⇒ learned policy ⇒ **+1 fraction collapses**, mass moves to {3,4,5,10}/abstain.
- Headline metric `f1 = frac(scooby_predict_action_1)`, corroborated by the direct
  `dyn_fallback_saved_bw_acc` counter.
- **Why chosen:** cleanest separation — +1 is diagnostic of fallback because the victim
  never learns it; metric already emitted; direction is a clean idle→busy step.

**(A2) Observe the raw fallback counters only.** Gate purely on
`action.fallback` / `dyn_fallback_saved_bw_acc` idle vs busy. Rejected as the
*primary* readout: counts the mechanism firing, not its effect on emitted prefetches;
weaker as a "steering" claim. Kept as **corroborating** evidence.

**(A3) Reuse the `policy_bw` victim `{1,3,4,5}`.** Rejected: +1 **is** a learned
action there, so forced-fallback +1 and learned +1 are indistinguishable in the
aggregate histogram — muddies the headline metric. Excluding 1 from the delta set is
the key design move.

Attacker: **reuse `policy_bw`/`degree_bw` attacker verbatim** (footprint dial
idle/light/medium/heavy). The only lever is DRAM read rate; `fallback_bw` just reads a
different victim consequence. Add nothing. (A `feather` sub-light intensity may be
added to sharpen the "sub-saturation" claim — builder call, §6.)

## 6. The how, as decided

**Victim** (`victim.c`): single load PC, `line += delta` wrapped to a **~1 MiB**
LLC-resident region (§4a: > L2 so it L2-misses, < LLC so solo-DRAM ≈ 0), one ALU op per
load — structurally like `policy_bw/victim.c` except (i) region shrunk from 4 MiB to
~1 MiB, (ii) `DELTAS = {3,4,5,10}` (excludes 1; all in `scooby_actions`).
Decorrelated-LCG stream, seedable via argv[1], same portability note as `policy_bw`.
Exact region size (0.5–2 MiB) is fixed in the spike by the victim-solo bw floor.

**Attacker** (`attacker.c`) + `config.h`: copied from `policy_bw` unchanged (footprint
dial). `config.h` victim section updated for the new delta set and documented.

**`aware.ini`** (the attack): start from `policy_bw/aware.ini`, then
- `scooby_enable_hbw_reward = false`  (reward lever **dead**)
- `scooby_high_bw_thresh = 4`         (default; branch 1 **dormant** — proves default-config)
- `scooby_dyn_degrees_type2_hbw = 1,2,4,6` (equal to normal; degree held — moot with
  thresh 4 but kept explicit)
- `le_featurewise_enable_dyn_action_fallback = true`  (the attack surface, **live**)
- `le_featurewise_bw_acc_check_level = 1`, `le_featurewise_acc_thresh = 2` (defaults, explicit)

**`blind.ini`** (isolation): identical to `aware.ini` **except**
`le_featurewise_enable_dyn_action_fallback = false` ⇒ `do_fallback` returns the static
`enable_action_fallback = true` ⇒ fallback **always ON** regardless of `bw_level` ⇒ +1
fraction stays high under a busy neighbor. Same contention, same `bw3`, no flip.

**`matrix`**: victim + {atk_idle, atk_light, atk_medium, atk_heavy} × {aware, blind}.
(Optionally add `atk_feather`.)

**`rollup.py`**: adapt `policy_bw/rollup.py`. Headline `f1 = frac(action==+1)`.
Gates (final thresholds set from the verification run; numbers always printed):
1. **steering**: `f1` drops idle→busy by a decisive margin (e.g. `>= 0.30`).
2. **sub-saturation**: the drop is already present at **light/medium** (`bw3` not
   saturated), proving `bw_level >= 1` suffices — not `>= 3`.
3. **mechanism evidence**: `dyn_fallback_saved_bw_acc` ~0 at idle, large under busy;
   `action.fallback` moves oppositely.
4. **isolation (decisive)**: blind-busy sees the same `bw3` yet `f1` unmoved.
5. **victim-in-regime**: victim `acc_level <= 2` (acc histogram) — branch 2 eligible.
6. **reward/degree held**: `enable_hbw_reward = false`, `high_bw_thresh = 4`; abstain
   fraction and `deg>=4` ~constant idle→busy ⇒ movement is fallback alone, not reward
   or degree.

**`ATTACK.md`**: per-attack deep dive in the house style; `DOSSIER.md` updated with a
`fallback_bw` row and a short section once results land.

**Verification spike (first step of the plan, before gate-tuning).** A short
`./scripts/launch.sh fallback_bw` run to confirm, from the `.out`:
- **(0, GATING) victim-solo bw floor** — in the **idle** run, victim (core 0)
  `scooby_bw_level_<n>` must show `P(bw_level ≥ 1)` small (target ≲ 0.05) and
  `dyn_fallback_saved_bw_acc` near 0. This is the §4a acceptance test; if it fails,
  shrink the region / add ALU throttle until the solo floor is clean **before** looking
  at `f1`. Without this, no clean idle baseline exists.
- (a) victim `acc_level <= 2` (acc histogram);
- (b) idle `f1` meaningfully high (fallback-ON forcing +1);
- (c) `f1` collapses under **light** AND stays collapsed under heavy (sub-saturation);
- (d) `dyn_fallback_saved_bw_acc` ~0 idle → large busy;
- (e) blind does not flip.

Remedies: (0) fails → shrink region / add ALU-per-load. (a) fails → widen deltas / tune
ALU to push accuracy `<= 29%`. Aggregate `f1` ambiguous → per-PC counter (A2/pband
fallback) — expected unnecessary here since the victim excludes delta 1, so +1 is never
a learned action (`Q(+1) = EV = −8`, never the max under fallback-OFF). These are the
anticipated builder calls.

## 7. Left to the builder

- Final numeric gate thresholds (from the verification run; the shape is fixed above).
- Whether to add `atk_feather` and/or per-PC readout (decide from the spike).
- Exact `TRACE_INSTR/WARMUP/SIM` (reuse the family default unless the spike shows
  under-settling; `blend_bw` needed 50M, this is simpler so the default is expected).
- `rollup.py` parsing details and plot, following `policy_bw/rollup.py`.
