# Small faults, large damage: message-loss amplification in `marketplace`

**Scenario:** `marketplace` (built-in)
**Setting changed:** `failures.message_drop` — one setting, nothing else
**Files:** [`scenarios/marketplace_drop_sweep.yaml`](../../../../scenarios/marketplace_drop_sweep.yaml), [`sweep.py`](sweep.py)

---

## The choice

I changed `failures.message_drop` and left every other field in
`marketplace.yaml` untouched — same 100 agents, same 12 layers, same
`catalog_size` and `rounds`.

I picked it for two reasons. It models the most ordinary real-world failure
there is — an unreliable network — and `marketplace` is a request/response
protocol, so it is exactly the shape of system where I would expect message
loss to matter. I wanted to know how much reliability this stack actually
needs before it stops functioning.

## The hypothesis (written before running)

**Degradation would be proportional.** A 5% drop rate would cost roughly 5%
of marketplace activity, because the only thing lost is the dropped messages
themselves. I expected a straight line.

That was wrong.

## What happened

Five seeds per rate, `nest run` with `--seed` overrides, counting `send`,
`dropped`, and `receive` events directly from the JSONL traces:

| configured drop | sends (mean ± sd) | observed drop | activity vs. baseline | amplification |
|---:|---:|---:|---:|---:|
| 0% | 1000.0 ± 0.0 | 0.0% | 100.0% | — |
| 5% | 639.0 ± 34.2 | 5.0% | **63.9%** | **7.2×** |
| 10% | 426.2 ± 49.9 | 10.3% | 42.6% | 5.7× |
| 20% | 242.6 ± 28.5 | 20.1% | 24.3% | 3.8× |

*Amplification = share of activity destroyed ÷ share of messages lost. A
proportional system would read 1.0×.*

**Losing 1 message in 20 removed 36% of all marketplace activity.**

Two supporting details:

- **The transport layer is innocent.** Averaged across seeds, the observed
  per-message drop rate matches the configured rate almost exactly (5.0%,
  10.3%, 20.1%). `in_memory` drops precisely what it is told to drop. The
  amplification happens *downstream* of the drop.
- **Baseline is perfectly deterministic** — exactly 1000 sends on all five
  seeds, zero variance. With no failures injected this scenario has no
  stochasticity at all, which makes it a clean control.

### Why it amplifies

Every `send` in these traces carries its own correlation ID, and a
conversation is a chain: a buyer's offer must arrive for the seller to reply,
and the reply must arrive for anything after it to happen. Dropping one
message does not cost one message — it silently deletes the entire remainder
of that exchange. Measured across the sweep, each dropped message eliminated
roughly **12–18 sends that never occurred**.

Nothing reports an error. The buyer simply waits.

### The counterintuitive part

The amplification factor is **largest when the fault is smallest** — 7.2× at
5% loss, falling to 3.8× at 20%. That is not a measurement artifact: once the
market has already collapsed there is little activity left to destroy, so the
damage curve flattens as it approaches total failure.

The practical reading: the small, easy-to-shrug-at fault rates are the ones
that punish hardest relative to their size. A 5% packet loss is the kind of
number that gets waved through in review.

## What surprised me, and how I investigated it

**The result surprised me, but my own method was the bigger problem.**

My first pass swept `message_drop` from 0.00 to 0.50 with a **single seed per
rate**. At the high end the observed drop rates came back at 43.9% and 56.2%
against configured 40% and 50% — above nominal. I nearly wrote that up as a
finding about the failure injector over-dropping.

Before doing that I checked the sample size. Only ~100 sends survived at
those rates, so the deviation was under 1.5 standard deviations — ordinary
sampling noise, not an effect. Worse, changing the failure rate also
perturbs the failure-injection RNG stream, so single-seed runs at different
rates are not clean controlled comparisons of each other.

So I rebuilt it as the 4 rates × 5 seeds sweep above. Averaged properly, the
observed rates converged on nominal and the anomaly disappeared entirely.
**The amplification finding survived; the exciting one did not.**

**Second false alarm:** every event in every trace carries `ts: 0.0`, and
`duration` reports `0.0 ticks`. I initially took this for a bug, since
`marketplace.yaml` lists `mean_latency` as a metric it cannot produce. It is
documented behavior — the README's "Determinism & what the clock does"
states that `in_memory` delivers at `time = now`, so the clock never
advances. I dropped `mean_latency` from the scenario's metrics and used
message counts instead, which the trace can actually support.

## Reproducing

```bash
python docs/hackathon/submissions/marketplace-drop-amplification/sweep.py
```

Runs 20 simulations into `traces/drop_sweep/` and prints the table above.
Takes about a minute. Every number in this README comes from that script.

## Limits — read before believing this

- **One scenario, one task type.** This is `marketplace`'s request/response
  chain. I have not checked whether `auction`, `voting`, or `consensus`
  amplify similarly, and the mechanism suggests the factor depends heavily on
  how long a scenario's conversation chains are. Do not generalize the 7×.
- **Five seeds is few.** Enough to kill the high-rate anomaly and show the
  amplification is not seed-specific, not enough for tight confidence
  intervals. The ±50 standard deviation at 10% is real spread.
- **Activity is not welfare.** I measured message volume, not completed
  trades or value exchanged. Sends are a proxy for "the market is working,"
  and a reasonable one here, but they are not the same thing.
- **Only four rates, all ≤ 20%.** The controlled sweep deliberately stops at
  20%; the 30–50% points come from the noisier single-seed pass and are not
  claimed here.
- **Tier 1, single process, zero-latency transport.** No real network, no
  clock skew, no concurrency. Message loss is the only failure mode modelled.

## Tools and help

- **Claude Code (Claude Opus)** — used heavily, and worth being precise about
  the division of labour. I ran the built-in `marketplace` scenario and wrote
  my first custom scenarios by hand. The agent then wrote `sweep.py`, ran the
  20-run controlled sweep, and computed the summary statistics. I directed the
  experiment, reviewed the output, and re-ran the sweep myself to confirm the
  table above reproduces.
- **`nest-core` CLI** — `nest run`, `nest inspect`.
- **Python** `json` and `statistics` for parsing JSONL traces and computing
  per-seed means and standard deviations.
- **NANDA Town Quickstart, scenario guide, and repo README** — the last of
  these is what settled the `mean_latency` question.

The most valuable use of the agent was adversarial rather than generative:
asking it to check whether my evidence actually supported my conclusion is
how both the single-seed flaw and the `mean_latency` false alarm were caught
before they reached this README.
