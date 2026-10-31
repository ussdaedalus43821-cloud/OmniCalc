#!/usr/bin/env python3
"""OmniCalc desktop host: one Tkinter screen, the amortization calculator.

Bridge contract (CLAUDE.md): this file does NO arithmetic. Every number on
the screen comes from src/app/amortization_screen.nova's calculate(), which
takes the input boxes as typed (strings) and returns integers + scales.
The host formats integer + scale as text, draws it, and writes CSV. The only
functions allowed arithmetic operators are listed in ARITHMETIC_ALLOWED;
tests/host/bridge_test.py enforces this by parsing this file.

Run:
    python3 src/host/app.py                     # needs Tkinter (python3-tk)
    OMNICALC_DEBUG=1 python3 src/host/app.py    # log Calculate timings to stderr
The calculation path (calculate, format_minor, export_csv) imports without
Tkinter or a display, so it can be tested headless.
"""

import argparse
import csv
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.host import nova_runtime  # noqa: E402

SCREEN_FILE = os.path.join(REPO_ROOT, "src", "app", "amortization_screen.nova")
BUDGET_MS = 100
DEFAULT_INPUTS = {"principal": "200,000.00", "rate": "6.5", "months": "360", "extra": "0.00"}

# String formatting, timing, and the smoke-test click delays in parse_args are
# the only places arithmetic operators may appear (tests/host/bridge_test.py
# checks).
ARITHMETIC_ALLOWED = {"format_minor", "elapsed_ms", "parse_args"}


class CalculationError(Exception):
    """An input NovaLang rejected (its message is shown to the person)."""


_engine = {}


def load_engine(fresh=False):
    """The pinned NovaLang engine with the screen facade loaded (cached)."""
    if fresh or "nova" not in _engine:
        nova_runtime.assert_pinned()
        novalang = nova_runtime.load_novalang()
        nova = novalang.Nova()
        nova.load_file(SCREEN_FILE)
        _engine["nova"] = nova
        _engine["error_type"] = novalang.NovaLangError
    return _engine["nova"]


def calculate(principal, rate, months, extra):
    """The four input boxes as typed -> the facade's result (ints, scales, strings)."""
    nova = load_engine()
    try:
        return nova.call("calculate", principal, rate, months, extra)
    except _engine["error_type"] as error:
        raise CalculationError(str(error)) from None


def elapsed_ms(start):
    return (time.perf_counter() - start) * 1000


def format_minor(minor, scale, grouping=True):
    """An integer of 10^-scale units as decimal text: (126414, 2) -> "1,264.14".
    Pure string work: the digits are re-cut around a decimal point."""
    text = str(minor)
    sign = "-" if text.startswith("-") else ""
    digits = text.lstrip("-").rjust(scale + 1, "0")
    whole, fraction = (digits[:-scale], digits[-scale:]) if scale else (digits, "")
    if grouping:
        whole = "{:,}".format(int(whole))
    return sign + whole + ("." + fraction if fraction else "")


def export_csv(result, handle):
    """Write the schedule as CSV: a header row, then one row per period, with
    money as plain decimal text (no grouping) at the result's scale."""
    writer = csv.writer(handle)
    writer.writerow(result["columns"])
    for row in result["rows"]:
        writer.writerow([row[0]] + [format_minor(value, result["scale"], grouping=False) for value in row[1:]])


def parse_args(argv):
    parser = argparse.ArgumentParser(description="OmniCalc amortization calculator")
    parser.add_argument("--calculate", nargs="?", const=1, default=0, type=int, metavar="N",
                        help="press Calculate N times (default 1) after start, 300 ms apart (smoke tests)")
    parser.add_argument("--quit-after", type=int, metavar="MS", help="close the window after MS milliseconds (smoke tests)")
    options = parser.parse_args(argv)
    options.click_delays = [300 * (press + 1) for press in range(options.calculate)]
    return options


def run_app(argv):
    options = parse_args(argv)
    import tkinter as tk
    from tkinter import filedialog, ttk

    debug = os.environ.get("OMNICALC_DEBUG") == "1"
    root = tk.Tk()
    root.title("OmniCalc — Amortization")
    root.geometry("900x640")

    state = {"result": None}
    inputs = {}
    form = ttk.Frame(root, padding=10)
    form.pack(fill="x")
    fields = [("principal", "Principal"), ("rate", "Annual rate (%)"), ("months", "Months"), ("extra", "Extra principal / month")]
    for column, (key, label) in enumerate(fields):
        ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=4)
        entry = ttk.Entry(form, width=18)
        entry.insert(0, DEFAULT_INPUTS[key])
        entry.grid(row=1, column=column, padx=4)
        inputs[key] = entry

    summary = ttk.Frame(root, padding=(10, 0))
    summary.pack(fill="x")
    labels = {}
    for column, key in enumerate(["payment", "total_interest", "total_paid", "payoff", "implied", "timing"]):
        labels[key] = ttk.Label(summary, text="")
        labels[key].grid(row=0, column=column, sticky="w", padx=6)
    error_label = ttk.Label(root, text="", foreground="#b00020", padding=(10, 4))
    error_label.pack(fill="x")

    table_frame = ttk.Frame(root, padding=10)
    table_frame.pack(fill="both", expand=True)
    columns = ["period", "payment", "interest", "principal", "balance", "extra", "adjustment"]
    table = ttk.Treeview(table_frame, columns=columns, show="headings")
    for name in columns:
        table.heading(name, text=name.capitalize())
        table.column(name, anchor="e", width=110)
    scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")

    assumptions = ttk.Label(root, text="", padding=(10, 0, 10, 10), justify="left", wraplength=860)
    assumptions.pack(fill="x")

    def on_calculate():
        start = time.perf_counter()
        try:
            result = calculate(*(inputs[key].get() for key, _ in fields))
        except CalculationError as error:
            error_label.config(text=str(error))
            return
        calc_ms = elapsed_ms(start)
        error_label.config(text="")
        state["result"] = result
        scale, currency = result["scale"], result["currency"]
        labels["payment"].config(text="Payment: " + format_minor(result["payment"], scale) + " " + currency)
        labels["total_interest"].config(text="Total interest: " + format_minor(result["total_interest"], scale))
        labels["total_paid"].config(text="Total paid: " + format_minor(result["total_paid"], scale))
        labels["payoff"].config(text="Payoff: month " + str(result["payoff_period"]))
        implied = result["implied_rate"]
        labels["implied"].config(text="IRR-implied rate: " + format_minor(implied["value"], implied["scale"]) + "%")
        table.delete(*table.get_children())
        for row in result["rows"]:
            table.insert("", "end", values=[row[0]] + [format_minor(value, scale) for value in row[1:]])
        assumptions.config(text="Assumptions: " + " ".join(result["assumptions"]))
        total_ms = elapsed_ms(start)
        labels["timing"].config(text="{:.0f} ms".format(total_ms) if debug else "")
        if debug:
            print("calculate: {:.1f} ms in NovaLang, {:.1f} ms with drawing (budget {} ms)".format(calc_ms, total_ms, BUDGET_MS), file=sys.stderr)

    def on_export():
        if state["result"] is None:
            error_label.config(text="Calculate first, then export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                export_csv(state["result"], handle)

    buttons = ttk.Frame(form)
    buttons.grid(row=1, column=len(fields), padx=8)
    ttk.Button(buttons, text="Calculate", command=on_calculate).pack(side="left", padx=2)
    ttk.Button(buttons, text="Export CSV", command=on_export).pack(side="left", padx=2)
    root.bind("<Return>", lambda event: on_calculate())

    for delay in options.click_delays:
        root.after(delay, on_calculate)
    if options.quit_after:
        root.after(options.quit_after, root.destroy)
    root.mainloop()


def warm_up():
    """One throwaway calculation at startup. The first call in a fresh process
    is ~50% slower (measured: 72-108 ms cold vs ~55-65 ms warm), which would
    put the first Calculate press over the 100 ms budget."""
    calculate(DEFAULT_INPUTS["principal"], DEFAULT_INPUTS["rate"], DEFAULT_INPUTS["months"], DEFAULT_INPUTS["extra"])


def main(argv):
    try:
        load_engine()
    except nova_runtime.NovaPinError as error:
        print("OmniCalc cannot start: {}".format(error), file=sys.stderr)
        return 1
    warm_up()
    run_app(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
