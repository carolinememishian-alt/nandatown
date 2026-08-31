# SPDX-License-Identifier: Apache-2.0
"""Sweep `failures.message_drop` across rates and seeds, and report amplification.

Reproduces every number in this directory's README.md.

Usage::

    python docs/hackathon/submissions/marketplace-drop-amplification/sweep.py

Writes traces to ./traces/drop_sweep/ and prints a summary table.
"""

from __future__ import annotations

import collections
import json
import statistics as st
import subprocess
import sys
import tempfile
from pathlib import Path

RATES = (0.00, 0.05, 0.10, 0.20)
SEEDS = (1, 2, 3, 4, 5)

REPO = Path(__file__).resolve().parents[4]
BASE_SCENARIO = REPO / "scenarios" / "marketplace_drop_sweep.yaml"
TRACE_DIR = REPO / "traces" / "drop_sweep"


def scenario_at_rate(rate: float, tmpdir: Path) -> Path:
    """Copy the base scenario with `message_drop` rewritten to `rate`."""
    out = tmpdir / f"drop_{rate:.2f}.yaml"
    lines = BASE_SCENARIO.read_text().splitlines(keepends=True)
    rewritten = [
        f"  message_drop: {rate:.2f}\n"
        if line.startswith("  message_drop:")
        else line
        for line in lines
    ]
    out.write_text("".join(rewritten))
    return out


def run(scenario: Path, seed: int, trace: Path) -> None:
    subprocess.run(
        ["nest", "run", str(scenario), "--seed", str(seed), "-o", str(trace)],
        check=True,
        capture_output=True,
    )


def count_kinds(trace: Path) -> collections.Counter[str]:
    with trace.open() as fh:
        return collections.Counter(json.loads(line)["kind"] for line in fh)


def main() -> int:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[float, list[tuple[int, int]]] = collections.defaultdict(list)

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        for rate in RATES:
            scenario = scenario_at_rate(rate, tmpdir)
            for seed in SEEDS:
                trace = TRACE_DIR / f"r{rate:.2f}_s{seed}.jsonl"
                run(scenario, seed, trace)
                kinds = count_kinds(trace)
                results[rate].append((kinds["send"], kinds["dropped"]))
                print(f"  ran rate={rate:.2f} seed={seed}", file=sys.stderr)

    baseline = st.mean(s for s, _ in results[0.00])

    print(f"\n{len(SEEDS)} seeds per rate, baseline = {baseline:.0f} sends\n")
    header = f"{'drop':>6} {'sends (mean+-sd)':>20} {'observed':>9} {'activity':>9} {'amplification':>14}"
    print(header)
    print("-" * len(header))
    for rate in RATES:
        sends = [s for s, _ in results[rate]]
        drops = [d for _, d in results[rate]]
        sd = st.stdev(sends) if len(sends) > 1 else 0.0
        observed = sum(drops) / sum(sends) * 100 if sum(sends) else 0.0
        activity = st.mean(sends) / baseline * 100
        # Amplification: share of activity destroyed, per unit of message loss.
        amp = (100 - activity) / (rate * 100) if rate else 0.0
        amp_str = f"{amp:.1f}x" if rate else "-"
        print(
            f"{rate * 100:5.0f}% {st.mean(sends):12.1f} +- {sd:4.1f} "
            f"{observed:8.1f}% {activity:8.1f}% {amp_str:>14}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
