# Small faults, large damage: message loss in `marketplace`

**Scenario:** `marketplace` (built-in)
**Setting changed:** `failures.message_drop`, and nothing else
**Files:** [`scenarios/marketplace_drop_sweep.yaml`](../../../../scenarios/marketplace_drop_sweep.yaml), [`sweep.py`](sweep.py)

---

## What I changed and why

I changed `failures.message_drop` and left every other field in
`marketplace.yaml` alone. Same 100 agents, same 12 layers, same
`catalog_size`, same `rounds`.

I picked that setting because dropped messages are the most ordinary thing
that goes wrong on a real network. And `marketplace` runs on request and
response, so it seemed like the kind of system where losing messages would
actually matter.

## What I expected

That the damage would be proportional. Lose 5% of the messages, lose about 5%
of the trading, because the only thing gone is the messages that got dropped.
I expected a straight line.

I was wrong.

## What happened

Five seeds at each rate, run with `nest run --seed`, counting `send`,
`dropped` and `receive` events straight out of the JSONL traces:

| configured drop | sends (mean ± sd) | observed drop | activity vs. baseline | amplification |
|---:|---:|---:|---:|---:|
| 0% | 1000.0 ± 0.0 | 0.0% | 100.0% | — |
| 5% | 639.0 ± 34.2 | 5.0% | **63.9%** | **7.2×** |
| 10% | 426.2 ± 49.9 | 10.3% | 42.6% | 5.7× |
| 20% | 242.6 ± 28.5 | 20.1% | 24.3% | 3.8× |

*Amplification is just the damage divided by its cause: share of activity
lost ÷ share of messages lost. A proportional system would read 1.0×.*

**Losing 1 message in 20 wiped out 36% of all marketplace activity.**

Two things worth adding:

- **The transport layer isn't the problem.** Averaged across seeds, the
  observed drop rate matches what I configured almost exactly (5.0%, 10.3%,
  20.1%). `in_memory` drops exactly what it's told to drop. The damage
  happens after that.
- **The baseline is completely deterministic** — exactly 1000 sends on all
  five seeds, no variance at all. With no failures injected there's no
  randomness in this scenario, which makes it a clean thing to compare
  against.

### Why one lost message costs so much

Every `send` in these traces has its own correlation ID, and a conversation is
a chain. The buyer's offer has to arrive before the seller can reply, and the
reply has to arrive before anything after it can happen. So dropping one
message doesn't cost you one message — it quietly deletes everything that
would have followed. Across the sweep, each dropped message took roughly
**12 to 18 other sends** down with it.

Nothing raises an error. The buyer just waits.

### The part I didn't expect

The multiplier is **biggest when the fault is smallest**. It's 7.2× at 5%
loss and only 3.8× at 20%. That isn't a measurement artifact — once the
market has mostly collapsed there isn't much activity left to destroy, so the
curve flattens as it approaches total failure.

Which means the small, easy-to-ignore failure rates are the ones that punish
you hardest for their size. 5% packet loss is exactly the sort of number that
gets waved through.

## What surprised me, and how I checked it

The result surprised me, but my own method turned out to be the bigger
problem.

My first pass swept `message_drop` from 0.00 to 0.50 using a **single seed per
rate**. At the high end the observed drop rates came back at 43.9% and 56.2%
against configured 40% and 50%. Higher than they should have been. I nearly
wrote that up as a bug in the failure injector.

Before doing that I checked the sample size. Only around 100 sends survived at
those rates, so the gap was under 1.5 standard deviations — just noise. And
there was a worse problem: changing the failure rate also shifts the
failure-injection RNG stream, so single-seed runs at different rates aren't
really controlled comparisons of each other.

So I rebuilt it as the 4 rates × 5 seeds sweep above. Averaged properly, the
observed rates landed on nominal and the anomaly disappeared. **The
amplification finding survived. The exciting one didn't.**

**A second false alarm:** every event in every trace has `ts: 0.0`, and
`duration` reports `0.0 ticks`. I thought this was a bug, since
`marketplace.yaml` lists `mean_latency` as a metric it can't actually produce.
It's documented behaviour — the repo README's "Determinism & what the clock
does" says `in_memory` delivers at `time = now`, so the clock never advances.
I dropped `mean_latency` from the scenario and used message counts instead,
which the trace can actually support.

## Running it yourself

```bash
python docs/hackathon/submissions/marketplace-drop-amplification/sweep.py
```

That runs 20 simulations into `traces/drop_sweep/` and prints the table above.
Takes about a minute. Every number here comes out of that script.

## What I'd build next

Two things, both of which fall out of the result above.

A **retry-and-acknowledge layer** for comms: agents confirm they received a
message, and resend if no confirmation comes back. That turns a lost message
into a short wait instead of a dead conversation, which is the whole mechanism
behind the 7×.

And a **validator that reports the amplification factor** rather than the raw
loss rate. "5% of messages dropped" is true and almost useless — it makes the
problem sound small when it isn't. "This setup degrades 7× faster than its
loss rate" is a number someone would actually act on, and it would let you
compare coordination layers on how well they hold up instead of just how fast
they are.

## Limits — worth reading before believing any of this

- **One scenario, one task type.** This is `marketplace`'s request/response
  chain. I haven't checked `auction`, `voting` or `consensus`, and the
  mechanism suggests the factor depends a lot on how long a scenario's
  conversation chains are. The 7× shouldn't be generalised.
- **Five seeds isn't many.** Enough to kill the high-rate anomaly and show
  the amplification isn't seed-specific. Not enough for tight confidence
  intervals. That ±50 standard deviation at 10% is real spread.
- **Activity isn't the same as welfare.** I counted messages, not completed
  trades or value exchanged. Sends are a reasonable proxy for "the market is
  working" here, but they're a proxy.
- **Only four rates, none above 20%.** The controlled sweep stops at 20% on
  purpose. The 30–50% numbers come from the noisier single-seed pass and I'm
  not claiming them.
- **Tier 1, single process, zero-latency transport.** No real network, no
  clock skew, no concurrency. Message loss is the only failure mode here.

## Tools and help

- **Claude Code (Claude Opus)** as a coding agent, and it's worth being
  precise about who did what. I ran the built-in `marketplace` scenario and
  wrote my first custom scenarios by hand. The agent wrote `sweep.py`, ran the
  20-run controlled sweep and computed the summary statistics. I set up the
  experiment, reviewed the output, and re-ran the sweep myself to confirm the
  table above reproduces.
- **`nest-core` CLI** — `nest run`, `nest inspect`.
- **Python** `json` and `statistics`, for reading the traces and working out
  per-seed means and standard deviations.
- **NANDA Town quickstart, scenario guide and repo README.** The last of
  those is where I found the `mean_latency` answer.

The most useful thing I did with the agent was adversarial rather than
generative: asking it whether my evidence actually supported my conclusion is
how both the single-seed flaw and the `mean_latency` false alarm got caught
before they ended up in this README.
