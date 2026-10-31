#!/usr/bin/env python3
"""Nightly performance monitor (a monitor, not a merge gate).

Times every screen's calculate path (src/host/app.calculate: NovaLang facade +
bridge) 20 times after a warm-up and writes median and p90 per screen to
perf-results.json.

CALIBRATED: hosted CI runners differ in speed by up to ~1.8x from run to run
(measured: every screen, including unchanged code, 1.74-1.82x slower on one
runner than on another). So each run also times a fixed NovaLang workload
(CALIBRATION, the same interpreter doing pure integer arithmetic) and records
each screen's median as a multiple of it ("relative"). The gate compares
relative values: if tools/perf_baseline.json exists, any screen whose relative
median is more than 20% above its baseline is reported and the script exits 1,
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
CALIBRATION = """
def calibration_workload() {
    let acc = {total: 0}
    for i = 1 to 20000 {
        acc["total"] = (acc.total + i * 7) % 1000003
    }
    return acc.total
}
"""


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


def calibrate(runs):
    """Median ms of a fixed NovaLang workload on this machine (same interpreter)."""
    nova = app.nova_runtime.load_novalang().Nova()
    nova.exec(CALIBRATION)
    nova.call("calibration_workload")
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        nova.call("calibration_workload")
        timings.append(app.elapsed_ms(start))
    return round(statistics.median(timings), 2)


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--out", default="perf-results.json")
    options = parser.parse_args(argv)

    calibration_ms = calibrate(options.runs)
    screens = {screen: measure(screen, options.runs) for screen in app.SCREEN_KEYS}
    for numbers in screens.values():
        numbers["relative"] = round(numbers["median_ms"] / calibration_ms, 3)
    results = {"python": platform.python_version(), "machine": platform.machine(),
               "calibration_ms": calibration_ms, "screens": screens}
    with open(options.out, "w", encoding="utf-8") as handle:
        json.dump(results, handle, indent=2)
        handle.write("\n")
    print("calibration    median {:>7.1f} ms   (fixed NovaLang workload; screens are compared relative to it)".format(calibration_ms))
    for screen, numbers in results["screens"].items():
        print("{:<14} median {:>7.1f} ms   p90 {:>7.1f} ms   max {:>7.1f} ms   relative {:>6.3f}".format(screen, numbers["median_ms"], numbers["p90_ms"], numbers["max_ms"], numbers["relative"]))

    if not os.path.exists(BASELINE):
        print("no tools/perf_baseline.json yet - recorded only (commit a nightly perf-results.json as the baseline)")
        return 0
    with open(BASELINE, encoding="utf-8") as handle:
        baseline = json.load(handle)["screens"]
    regressions = []
    for screen, numbers in results["screens"].items():
        if screen not in baseline:
            continue
        if "relative" not in baseline[screen]:
            print("baseline has no calibrated 'relative' values - re-baseline from a CI run of this version")
            return 1
        if numbers["relative"] > baseline[screen]["relative"] * REGRESSION:
            regressions.append("{}: {:.3f}x calibration vs baseline {:.3f}x ({} ms now)".format(screen, numbers["relative"], baseline[screen]["relative"], numbers["median_ms"]))
    for line in regressions:
        print("::warning title=Performance regression::" + line)
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
