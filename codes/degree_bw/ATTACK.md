# Attack Methodology — `degree_bw`: Prefetch-Degree Steering

Self-contained methodology for the **`degree_bw`** attack on the Pythia (scooby) L2
prefetcher. It is the simplest member of the shared-DRAM-bandwidth attack family: a blind,
open-loop neighbor throttles the victim's prefetch **aggressiveness** (degree) without
touching *what* the victim prefetches.

---

## 0. The idea in one paragraph

Pythia reacts to a DRAM-bandwidth signal that ChampSim computes **globally** (summed over all
cores) with no per-core accounting. When bandwidth is high, Pythia switches to a conservative
**degree curve** — it issues fewer prefetches per trigger. The attacker raises the global
bandwidth bucket purely with its own DRAM traffic, so the victim's Pythia reads a "high
bandwidth" level it never caused and collapses its degree from ~6 down to 1. The attacker
reads nothing about the victim and never confirms the attack.

---

## 1. Threat model

- **Platform:** dual-core ChampSim, shared LLC, a **single shared DRAM channel**
  (`DRAM_CHANNELS = 1` in the 2-core build). Core 0 = victim, core 1 = attacker
  (`-traces victim.xz attacker.xz`).
- **Victim:** runs Pythia (scooby), an RL L2 prefetcher, in a fixed, realistic
  bandwidth-aware config. The attacker cannot change the victim's config, read its memory,
  or read its prefetcher state.
- **Attacker:** a co-located **static synthetic trace** — no shared memory, no IPC, no
  runtime feedback, **no victim knowledge** (not its addresses, hot sets, cache contents, or
  Pythia tables). Its only lever is its own DRAM read rate, dialed by memory **footprint**.
- **Only assumed knowledge:** the *offline, public* architectural fact (Pythia paper + open
  ChampSim source) that Pythia reacts to a DRAM-bandwidth signal that is **global**. The
  attacker exploits a design property, not a secret.

The attacker is open-loop on purpose: that a neighbor who *measures nothing* still steers the
victim makes the result stronger.

---

## 2. The shared channel

Every 256 cycles ChampSim buckets the **aggregate** DRAM read-enqueue count over *all* cores
into a level 0–3 and broadcasts the *same* value to every core's Pythia:

```
src/main.cc:964-978   bucket aggregate rq_enqueue over all cores into level 0..3 each
                      256-cycle epoch (EWMA: epoch = epoch/2 + this_epoch; quartiles vs
                      DRAM_DBUS_MAX_CAS)
src/cache.cc:1769     broadcast the level to the L2 prefetcher
prefetcher/scooby.cc  Scooby::update_bw(level) stores bw_level
                      is_high_bw() == (bw_level >= scooby_high_bw_thresh)
```

There is **no per-core accounting**: the bucket the victim reads reflects the attacker's
traffic as much as its own. That absence of isolation *is* the channel.

The shipped `config/pythia.ini` leaves `scooby_high_bw_thresh` at its default (4), but the
bucket maxes at 3, so the high-bandwidth path ships **dormant**. The attack config enables it
with `scooby_high_bw_thresh = 3` — a realistic bandwidth-aware regime, exactly what the
paper's mechanism is designed for.

---

## 3. The mechanism: the high-bandwidth degree curve

Pythia selects how many lines to prefetch per trigger from a **degree curve**. It keeps two
curves and picks by the bandwidth level:

```
scooby_dyn_degrees_type2     = 1,2,4,6     # normal curve (ramps to 6)
scooby_dyn_degrees_type2_hbw = 1,1,1,1     # high-bw curve, pinned to 1 (the attack)
```

When `is_high_bw()` is true, Pythia uses the HBW curve. The attack pins that curve to **1**,
so the instant the attacker saturates the bucket, the victim — reading that global bucket —
switches from a curve that ramps to 6 down to degree 1. The victim keeps predicting the
**same action** (its learned stride); only *how many* lines it runs ahead changes.

---

## 4. The attacker: a footprint intensity dial

`attacker.c` streams a region whose **size** sets the DRAM rate. ALU padding does *not*
throttle steady-state DRAM (ALU ops are ~free); a smaller region raises LLC residency and
structurally lowers the DRAM rate. One source yields four intensities by argument:

| intensity | region | effect on the shared bucket |
|-----------|--------|-----------------------------|
| `idle`   | tiny (pure ALU / LLC-resident) | bucket ~0 |
| `light`  | 2 MiB  | partially resident |
| `medium` | 3 MiB  | partial residency |
| `heavy`  | 64 MiB | always misses → saturates bucket 3 |
| `benign_cache` | tiny L1/L2-resident (`_common/idle.c`) | shares LLC, ~0 DRAM — a "mere co-location" control |

---

## 5. The victim

A constant **+1-line-stride** stream over a ~2 MiB region. Pythia trivially learns the delta
(action = +1) and ramps its degree. The working set caches after warm-up, so the victim's own
steady-state DRAM traffic is ~0 — the bucket it observes under attack is almost entirely the
attacker's. Because the victim's action is always correct, the *reward* lever (see
`policy_bw`) never bites here; only the degree curve moves. That isolation is the point of
using a trivially predictable victim.

---

## 6. Config

- `bwaware.ini` (the attack): `scooby_high_bw_thresh = 3`, `scooby_dyn_degrees_type2_hbw =
  1,1,1,1`. The HBW path is live and its degree curve is pinned to 1.
- `bwblind.ini` (isolation control): identical **except** `scooby_high_bw_thresh = 4`. The
  bucket still saturates (same `bw3`), but `is_high_bw()` never trips, so the degree curve
  never swaps.

Readout: scooby's per-core selected-degree histogram, parsed by `rollup.py`. Headline metric
is the **degree-1 fraction** (and its mirror, `deg≥4`).

---

## 7. Results (victim = core 0)

| neighbor (bwaware) | bw3 | deg1 | deg≥4 | victim IPC |
|--------------------|:---:|:----:|:-----:|:----------:|
| `atk_idle`     | 0.000 | 0.049 | 0.920 | 1.425 |
| `atk_light`    | 0.216 | 0.197 | 0.776 | 1.346 |
| `atk_medium`   | 0.603 | 0.544 | 0.440 | 1.361 |
| **`atk_heavy`**| **0.915** | **0.848** | **0.147** | 1.338 |
| `benign_cache` | 0.000 | 0.049 | 0.920 | 1.425 |

As intensity rises, `bw3` rises monotonically and the degree curve collapses: `deg1` goes
0.05 → 0.85, `deg≥4` goes 0.92 → 0.15. The victim keeps predicting the same +1 stride; only
its degree changes.

### Isolation control (decisive)

A **bandwidth-blind** victim (`scooby_high_bw_thresh = 4`) under the *same* heavy attacker:

| neighbor (bwblind) | bw3 | deg1 | deg≥4 |
|--------------------|:---:|:----:|:-----:|
| `atk_idle`     | 0.000 | 0.049 | 0.920 |
| `atk_heavy`    | 0.905 | 0.049 | 0.920 |

Same bucket-3 saturation (`bw3 = 0.905`), yet the degree policy does **not** move (`deg≥4`
stays 0.92). Identical contention, opposite outcome ⇒ the steering is the *signal*, not raw
slowdown. `benign_cache` ≈ `idle` confirms mere co-location does nothing.

---

## 8. Success gates (`rollup.py`) — all PASS

1. **Monotone bw3 (aware):** idle < light < medium < heavy.
2. **Degree collapse (aware):** `deg1` 0.05 → 0.85, `deg≥4` 0.92 → 0.15 under heavy.
3. **Isolation (blind):** same high `bw3` under heavy, yet `deg≥4` unmoved (0.92 → 0.92).
4. **Benign ≈ idle (aware):** `benign_cache` matches `idle` on `bw3` and `deg≥4`.

---

## 9. What is steered — and the honest scope

The attacker throttles *how aggressive* the victim's prefetcher is (degree 6 → 1) while
leaving *what it decides* alone. This is a denial-of-aggressiveness, not a redirection of the
policy — `policy_bw` and `pband_bw` take the next step and move *which action* the victim
selects. The lever is the footprint intensity ramp; in practice even a light attacker already
moves the bucket, and heavy saturates it.

---

## 10. Root cause and mitigation

Root cause (shared with the whole family): **Pythia consumes a system-wide bandwidth signal
with no per-core isolation**, so a neighbor's traffic enters the victim's decision loop and
flips its degree regime.

**Mitigation:** derive Pythia's bandwidth level from **per-core** DRAM accounting rather than
the single global counter (`src/main.cc:964-978`), so one core's traffic cannot move another
core's degree curve.

---

## 11. How to run

```bash
source scripts/set_env.sh
./scripts/launch.sh degree_bw
```

Outputs land in `experiments/degree_bw/`: `<neighbor>_<cfg>.out` (5 neighbors ×
`bwaware`/`bwblind`), `rollup.txt`, `rollup.csv`, and the 100%-stacked degree chart
`degree_dist.png`.
