#!/usr/bin/env python3
"""Nightly performance monitor (a monitor, not a merge gate).

Times every screen's calculate path (src/host/app.calculate: NovaLang facade +
bridge) 20 times after a warm-up and writes median and p90 per screen to
perf-results.json. If tools/perf_baseline.json exists, any screen whose median
is more than 20% slower than its baseline is reported and the script exits 1,
which fails the nightly job (the alert). Without a baseline it only records.

Baselines must come from the same kind of machine they are compared on: set
one by downloading perf-results.json from a nightly run and committing it as
tools/perf_baseline.json.

    python3 tools/perf.py [--runs 20] [--out perf-results.json]
"""

import argparse
import json
import os
import platform
import statistics
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.host import app  # noqa: E402

BASELINE = os.path.join(REPO_ROOT, "tools", "perf_baseline.json")
REGRESSION = 1.20


def measure(screen, runs):
    inputs = app.default_inputs(screen)
    app.calculate(screen, *inputs)
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        app.calculate(screen, *inputs)
        timings.append(app.elapsed_ms(start))
    timings.sort()
    return {"median_ms": round(statistics.median(timings), 2),
            "p90_ms": round(timings[int(0.9 * (len(timings) - 1))], 2),
            "max_ms": round(timings[-1], 2), "runs": runs}


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--out", default="perf-results.json")
    options = parser.parse_args(argv)

    results = {"python": platform.python_version(), "machine": platform.machine(),
               "screens": {screen: measure(screen, options.runs) for screen in app.SCREEN_KEYS}}
    with open(options.out, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
        handle.write("\n")
    for screen, numbers in results["screens"].items():
        print("{:<14} median {:>7.1f} ms   p90 {:>7.1f} ms   max {:>7.1f} ms".format(screen, numbers["median_ms"], numbers["p90_ms"], numbers["max_ms"]))

    if not os.path.exists(BASELINE):
        print("no tools/perf_baseline.json yet - recorded only (commit a nightly perf-results.json as the baseline)")
        return 0
    with open(BASELINE, encoding="utf-8") as handle:
        baseline = json.load(handle)["screens"]
    regressions = []
    for screen, numbers in results["screens"].items():
        if screen in baseline and numbers["median_ms"] > baseline[screen]["median_ms"] * REGRESSION:
            regressions.append("{}: median {} ms vs baseline {} ms".format(screen, numbers["median_ms"], baseline[screen]["median_ms"]))
    for line in regressions:
        print("::warning title=Performance regression::" + line)
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
