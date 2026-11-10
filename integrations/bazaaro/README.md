# Bazaaro × Nanda Town

Bazaaro is a marketplace where AI orchestrators find and hire specialist agents. This folder plugs Bazaaro into Nanda Town as the town's **registry** (its phone book of agents): Town's agents register in Bazaaro and find each other through it.

## Files

- `bazaaro_registry.py`: connector that sends Town's register and search requests to Bazaaro's API [TBD: Leyre]
- `bazaaro_eviction.yaml`: failure test, a forged agent card (below)
- [TBD: Leyre's main end-to-end scenario]

## Versions

- Nanda Town commit: `6f9a7c0`
- Python: 3.15.2 (Town's CI tests 3.11 and 3.12)
- Bazaaro version: [TBD: Ryan]

## Setup

```
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
export BAZAARO_API_KEY=<test key>
```

The API key is never stored in this repo.

## Failure test: forged agent card

**What it tests:** a rival seller publishes a fake card under the honest seller's name. Bazaaro should refuse it, keep the honest listing, and the honest seller should still get paid. This is the main risk once outside developers can register agents.

**Run it:**

```
nandatown run integrations/bazaaro/bazaaro_eviction.yaml
```

**Expected result (written before running):** Town's three checks pass:
1. `forgery_detected`: the fake card is recorded as refused
2. `listing_intact`: the buyer still reaches the honest seller after the fake
3. `honest_trade_completed`: the honest seller is paid

**Baselines (Town's own registries, same agents and seed):**

| Registry | Result | Run |
|---|---|---|
| `index.owned.v1` (checks ownership) | Passed | `sim-0c090f49ca7b` |
| `index.v1` (no ownership check) | Failed at `listing_intact` | `sim-d39f057fbe2d` |

Detecting a fake is not enough: the no-ownership registry flagged the fake card but still let it replace the honest listing.

**Observed result with Bazaaro:** [TBD]

**Limitations:** [TBD]. Uses Town's reference agents, not independently built agents.