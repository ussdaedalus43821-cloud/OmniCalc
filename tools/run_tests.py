#!/usr/bin/env python3
"""Run every tests/**/*.nova file and fail closed.

Each test file must start with a header comment block naming the module under
test and the exact number of checks it runs:

    # module: money
    # expect: 31

A file fails if:
  - either header line is missing, duplicated, or malformed;
  - the named module does not match exactly one src/**/<module>.nova;
  - the interpreter exits non-zero (or times out);
  - its output does not end with exactly one sentinel line `TESTS_OK <n>`;
  - n differs from the `expect` header.

Finding no test files at all is also a failure.

Usage:
    python3 tools/run_tests.py [--bootstrap] [path ...]

--bootstrap runs each file through NovaLang's self-hosted interpreter
(`novalang.py --bootstrap`). It is meant for the nightly CI job, not as a
local gate.
"""

import argparse
import os
import re
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.host.nova_runtime import NOVA_SCRIPT, NovaPinError, assert_pinned  # noqa: E402

TESTS_DIR = os.path.join(REPO_ROOT, "tests")
SRC_DIR = os.path.join(REPO_ROOT, "src")
HEADER_FIELD = re.compile(r"#\s*(module|expect)\s*:\s*(\S+)")
SENTINEL = re.compile(r"^TESTS_OK (\d+)$")
TIMEOUT_SECONDS = 300


def find_files(root, suffix):
    found = []
    for directory, _, names in os.walk(root):
        for name in names:
            if name.endswith(suffix):
                found.append(os.path.join(directory, name))
    return sorted(found)


def read_header(path):
    """The (module, expect) fields from the leading comment block."""
    fields = {"module": [], "expect": []}
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            if not stripped.startswith("#"):
                break
            for key, value in HEADER_FIELD.findall(stripped):
                fields[key].append(value)
    return fields


def check_header(path, modules_by_name):
    """Return (expected_count, problems)."""
    fields = read_header(path)
    problems = []
    expected = None

    if len(fields["module"]) != 1:
        problems.append("needs exactly one `# module: <name>` header line, found {}".format(len(fields["module"])))
    else:
        name = fields["module"][0]
        matches = modules_by_name.get(name, [])
        if len(matches) != 1:
            problems.append("`# module: {}` must match exactly one src/**/{}.nova, found {}".format(name, name, len(matches)))

    if len(fields["expect"]) != 1:
        problems.append("needs exactly one `# expect: <count>` header line, found {}".format(len(fields["expect"])))
    elif not fields["expect"][0].isdigit() or int(fields["expect"][0]) < 1:
        problems.append("`# expect:` must be a positive whole number, got {!r}".format(fields["expect"][0]))
    else:
        expected = int(fields["expect"][0])

    return expected, problems


def check_output(completed, expected):
    problems = []
    if completed.returncode != 0:
        problems.append("interpreter exited with code {}".format(completed.returncode))
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    sentinels = [line for line in lines if SENTINEL.match(line)]
    if len(sentinels) != 1:
        problems.append("expected exactly one `TESTS_OK <n>` line, found {}".format(len(sentinels)))
    elif lines[-1] != sentinels[0]:
        problems.append("`TESTS_OK <n>` must be the last line of output")
    else:
        actual = int(SENTINEL.match(sentinels[0]).group(1))
        if actual != expected:
            problems.append("ran {} checks but the header expects {}".format(actual, expected))
    return problems


def run_file(path, expected, bootstrap):
    command = [sys.executable, NOVA_SCRIPT]
    if bootstrap:
        command.append("--bootstrap")
    command.append(path)
    try:
        completed = subprocess.run(
            command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return ["timed out after {}s".format(TIMEOUT_SECONDS)], None
    return check_output(completed, expected), completed


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bootstrap", action="store_true", help="use the self-hosted interpreter (nightly CI)")
    parser.add_argument("paths", nargs="*", help="test files to run (default: every tests/**/*.nova)")
    options = parser.parse_args(argv)

    try:
        version = assert_pinned()
    except NovaPinError as error:
        print("FAIL pinned runtime: {}".format(error))
        return 1

    tests = [os.path.abspath(p) for p in options.paths] if options.paths else find_files(TESTS_DIR, ".nova")
    if not tests:
        print("FAIL no test files found under tests/")
        return 1

    modules_by_name = {}
    for module_path in find_files(SRC_DIR, ".nova"):
        name = os.path.splitext(os.path.basename(module_path))[0]
        modules_by_name.setdefault(name, []).append(module_path)

    mode = "--bootstrap" if options.bootstrap else "direct"
    print("NovaLang {} ({}), {} test file(s)".format(version, mode, len(tests)))

    failed = 0
    for path in tests:
        label = os.path.relpath(path, REPO_ROOT)
        expected, problems = check_header(path, modules_by_name)
        completed = None
        started = time.monotonic()
        if not problems:
            problems, completed = run_file(path, expected, options.bootstrap)
        elapsed = time.monotonic() - started

        if problems:
            failed += 1
            print("FAIL {} ({:.2f}s)".format(label, elapsed))
            for problem in problems:
                print("     - " + problem)
            if completed is not None:
                for stream in (completed.stdout, completed.stderr):
                    for line in stream.strip().splitlines()[-20:]:
                        print("     | " + line)
        else:
            print("ok   {} ({} checks, {:.2f}s)".format(label, expected, elapsed))

    print("{} passed, {} failed".format(len(tests) - failed, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
