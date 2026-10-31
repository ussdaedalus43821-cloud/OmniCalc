#!/usr/bin/env python3
"""OmniCalc desktop host: three calculator screens in one Tkinter window.

Bridge contract (CLAUDE.md): this file does NO arithmetic. Every number on
screen comes from a NovaLang screen facade (src/app/*_screen.nova), whose
calculate() takes the input boxes as typed (strings) and returns integers,
scales and strings. The host formats integer + scale as text, draws it, and
writes CSV. The only functions allowed arithmetic operators are listed in
ARITHMETIC_ALLOWED; tests/host/bridge_test.py enforces this by parsing this
file.

Navigation (CLAUDE.md "Screens and navigation"): one window, one ttk.Notebook
tab per screen. Each tab keeps its own inputs and results while you switch,
and only recalculates when you press Calculate (or Enter); editing an input
marks the results as stale until then.

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

BUDGET_MS = 100

# One entry per screen. "fields" are (key, label, default text) in the order
# the facade's calculate() takes them. "summary" items are (result key,
# label, kind); kinds: "money" (int at the result's scale), "count",
# "percent" ({value, scale}), "text". The table and CSV come from the
# result's columns / column_kinds / rows.
SCREENS = [
    {
        "key": "amortization",
        "title": "Amortization",
        "facade": os.path.join("src", "app", "amortization_screen.nova"),
        "fields": [
            ("principal", "Principal", "200,000.00"),
            ("rate", "Annual rate (%)", "6.5"),
            ("months", "Months", "360"),
            ("extra", "Extra principal / month", "0.00"),
        ],
        "summary": [
            ("payment", "Payment", "money"),
            ("total_interest", "Total interest", "money"),
            ("total_paid", "Total paid", "money"),
            ("payoff_period", "Payoff month", "count"),
            ("implied_rate", "IRR-implied rate", "percent"),
        ],
    },
    {
        "key": "savings",
        "title": "Savings",
        "facade": os.path.join("src", "app", "savings_screen.nova"),
        "fields": [
            ("initial", "Initial deposit", "10,000.00"),
            ("contribution", "Monthly contribution", "500.00"),
            ("rate", "Annual rate (%)", "7"),
            ("years", "Years", "30"),
        ],
        "summary": [
            ("future_value", "Future value", "money"),
            ("total_contributed", "Total contributed", "money"),
            ("total_interest", "Total interest", "money"),
        ],
    },
    {
        "key": "refinance",
        "title": "Refinance",
        "facade": os.path.join("src", "app", "refinance_screen.nova"),
        "fields": [
            ("principal", "Current principal", "200,000.00"),
            ("current_rate", "Current rate (%)", "6.5"),
            ("remaining", "Months remaining", "360"),
            ("payment", "Current payment", "1,264.14"),
            ("new_rate", "New rate (%)", "5.0"),
            ("new_term", "New term (months)", "360"),
            ("closing", "Closing costs", "6,000.00"),
        ],
        "summary": [
            ("new_payment", "New payment", "money"),
            ("monthly_savings", "Monthly savings", "money"),
            ("break_even", "Break-even", "text"),
            ("total_savings", "Savings (shorter term)", "money"),
            ("lifetime_savings", "Lifetime savings", "money"),
        ],
    },
]
SCREENS_BY_KEY = {screen["key"]: screen for screen in SCREENS}
SCREEN_KEYS = [screen["key"] for screen in SCREENS]

# String formatting, timing, and the smoke-test click delays in parse_args are
# the only places arithmetic operators may appear (tests/host/bridge_test.py
# checks).
ARITHMETIC_ALLOWED = {"format_minor", "elapsed_ms", "parse_args"}


class CalculationError(Exception):
    """An input NovaLang rejected (its message is shown to the person)."""


_engines = {}


def load_engine(screen_key, fresh=False):
    """The pinned NovaLang engine with this screen's facade loaded (cached).
    One engine per screen: every facade exports calculate()."""
    if fresh or screen_key not in _engines:
        nova_runtime.assert_pinned()
        novalang = nova_runtime.load_novalang()
        nova = novalang.Nova()
        nova.load_file(os.path.join(REPO_ROOT, SCREENS_BY_KEY[screen_key]["facade"]))
        _engines[screen_key] = (nova, novalang.NovaLangError)
    return _engines[screen_key][0]


def calculate(screen_key, *inputs):
    """A screen's input boxes as typed -> its facade's result (ints, scales, strings)."""
    nova = load_engine(screen_key)
    try:
        return nova.call("calculate", *inputs)
    except _engines[screen_key][1] as error:
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


def format_value(value, kind, scale, grouping=True):
    """One result value as text, by kind (see SCREENS)."""
    if kind == "money":
        return format_minor(value, scale, grouping)
    if kind == "percent":
        return format_minor(value["value"], value["scale"], grouping) + "%"
    return str(value)


def export_csv(result, handle):
    """Write a result's table as CSV: a header row, then its rows, money as
    plain decimal text (no grouping) at the result's scale."""
    writer = csv.writer(handle)
    writer.writerow(result["columns"])
    kinds = result["column_kinds"]
    for row in result["rows"]:
        writer.writerow([format_value(value, kind, result["scale"], grouping=False) for value, kind in zip(row, kinds)])


def default_inputs(screen_key):
    return [default for _, _, default in SCREENS_BY_KEY[screen_key]["fields"]]


def warm_up():
    """One throwaway calculation per screen at startup. The first call in a
    fresh process is ~50% slower (measured in M4: 72-108 ms cold vs ~55-65 ms
    warm), which would put the first Calculate press over budget."""
    for key in SCREEN_KEYS:
        calculate(key, *default_inputs(key))


def parse_args(argv):
    parser = argparse.ArgumentParser(description="OmniCalc calculators")
    parser.add_argument("--calculate", nargs="?", const=1, default=0, type=int, metavar="N",
                        help="press Calculate on every tab N times (default 1) after start, 300 ms apart (smoke tests)")
    parser.add_argument("--tab", choices=SCREEN_KEYS, help="open on this tab")
    parser.add_argument("--quit-after", type=int, metavar="MS", help="close the window after MS milliseconds (smoke tests)")
    options = parser.parse_args(argv)
    options.click_delays = [300 * (press + 1) for press in range(options.calculate)]
    return options


def build_tab(notebook, screen, debug, tk, ttk, filedialog):
    """One screen's tab: inputs, Calculate / Export CSV, summary, table,
    assumptions. Returns (frame, Calculate handler)."""
    frame = ttk.Frame(notebook)
    notebook.add(frame, text=screen["title"])
    state = {"result": None}

    form = ttk.Frame(frame, padding=10)
    form.pack(fill="x")
    status = ttk.Label(frame, text="", foreground="#8a6d00", padding=(10, 0))

    def mark_stale(*_):
        if state["result"] is not None:
            status.config(text="Inputs changed - press Calculate to refresh the results.")

    variables = []
    for column, (key, label, default) in enumerate(screen["fields"]):
        variable = tk.StringVar(value=default)
        variable.trace_add("write", mark_stale)
        ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=4)
        ttk.Entry(form, width=15, textvariable=variable).grid(row=1, column=column, padx=4)
        variables.append(variable)

    buttons = ttk.Frame(frame, padding=(10, 0))
    buttons.pack(fill="x")
    summary = ttk.Frame(frame, padding=(10, 6))
    summary.pack(fill="x")
    status.pack(fill="x")
    error_label = ttk.Label(frame, text="", foreground="#b00020", padding=(10, 2))
    error_label.pack(fill="x")
    labels = []
    for column, (key, label, kind) in enumerate(screen["summary"]):
        value_label = ttk.Label(summary, text=label + ": -")
        value_label.grid(row=0, column=column, sticky="w", padx=6)
        labels.append(value_label)
    timing_label = ttk.Label(summary, text="")
    timing_label.grid(row=1, column=0, sticky="w", padx=6)

    table_frame = ttk.Frame(frame, padding=10)
    table_frame.pack(fill="both", expand=True)
    table = ttk.Treeview(table_frame, show="headings")
    scroll = ttk.Scrollbar(table_frame, orient="vertical", command=table.yview)
    table.configure(yscrollcommand=scroll.set)
    table.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    assumptions = ttk.Label(frame, text="", padding=(10, 0, 10, 10), justify="left", wraplength=940)
    assumptions.pack(fill="x")

    def on_calculate():
        start = time.perf_counter()
        try:
            result = calculate(screen["key"], *(variable.get() for variable in variables))
        except CalculationError as error:
            error_label.config(text=str(error))
            return
        calc_ms = elapsed_ms(start)
        error_label.config(text="")
        status.config(text="")
        state["result"] = result
        scale = result["scale"]
        for value_label, (key, label, kind) in zip(labels, screen["summary"]):
            value_label.config(text=label + ": " + format_value(result[key], kind, scale))
        if tuple(table["columns"]) != tuple(result["columns"]):
            table["columns"] = result["columns"]
            for name, kind in zip(result["columns"], result["column_kinds"]):
                table.heading(name, text=name.replace("_", " ").capitalize())
                table.column(name, anchor="w" if kind == "text" else "e", width=125)
        table.delete(*table.get_children())
        for row in result["rows"]:
            table.insert("", "end", values=[format_value(value, kind, scale) for value, kind in zip(row, result["column_kinds"])])
        assumptions.config(text="Assumptions: " + " ".join(result["assumptions"]))
        total_ms = elapsed_ms(start)
        timing_label.config(text="{:.0f} ms".format(total_ms) if debug else "")
        if debug:
            print("{}: {:.1f} ms in NovaLang, {:.1f} ms with drawing (budget {} ms)".format(screen["key"], calc_ms, total_ms, BUDGET_MS), file=sys.stderr)

    def on_export():
        if state["result"] is None:
            error_label.config(text="Calculate first, then export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".csv", initialfile=screen["key"] + ".csv", filetypes=[("CSV", "*.csv")])
        if path:
            with open(path, "w", newline="", encoding="utf-8") as handle:
                export_csv(state["result"], handle)

    ttk.Button(buttons, text="Calculate", command=on_calculate).pack(side="left", padx=2)
    ttk.Button(buttons, text="Export CSV", command=on_export).pack(side="left", padx=2)
    return frame, on_calculate


def run_app(argv):
    options = parse_args(argv)
    import tkinter as tk
    from tkinter import filedialog, ttk

    debug = os.environ.get("OMNICALC_DEBUG") == "1"
    root = tk.Tk()
    root.title("OmniCalc")
    root.geometry("1000x680")
    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)
    handlers = {}
    for screen in SCREENS:
        frame, handler = build_tab(notebook, screen, debug, tk, ttk, filedialog)
        handlers[str(frame)] = handler
    root.bind("<Return>", lambda event: handlers[notebook.select()]())
    if options.tab:
        notebook.select(SCREEN_KEYS.index(options.tab))
    for delay in options.click_delays:
        for handler in handlers.values():
            root.after(delay, handler)
    if options.quit_after:
        root.after(options.quit_after, root.destroy)
    root.mainloop()


def main(argv):
    try:
        for key in SCREEN_KEYS:
            load_engine(key)
    except nova_runtime.NovaPinError as error:
        print("OmniCalc cannot start: {}".format(error), file=sys.stderr)
        return 1
    warm_up()
    run_app(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
