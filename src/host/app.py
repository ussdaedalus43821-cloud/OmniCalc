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
import datetime
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.host import nova_runtime  # noqa: E402

BUDGET_MS = 100

# One entry per screen. "fields" are (key, label, default[, options]) in the
# order the facade's calculate() takes them. options may be
#   {"choices": [(value, label), ...]}   a drop-down; the facade gets `value`
#   {"rows": [label, ...]}               an editable list of rows; the facade
#                                        gets a list of lists of strings and
#                                        `default` is the starting rows
# "summary" items are (result key, label, kind); kinds: "money" (an int at
# the result's scale), "count", "percent" ({value, scale}), "text", and
# "decimal" ({value, scale}, e.g. fractional shares), "percent" with no value
# ({}) shown as "-", and
# "phrase" ({before, amount, after}: words around a money amount, so the
# facade decides how a number reads - "saves X" vs "costs X more"; amount
# may be absent, e.g. "no target in this mode"). The
# table and CSV come from the result's columns / column_kinds / rows.
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
            ("mode", "Solve for", "fv", {"choices": [("fv", "Future value"), ("pmt", "Monthly contribution"), ("n", "Time to goal")]}),
            ("initial", "Initial deposit", "10,000.00"),
            ("contribution", "Monthly contribution", "500.00"),
            ("rate", "Annual rate (%)", "7"),
            ("years", "Years", "30"),
            ("target", "Target (goal modes)", "250,000.00"),
        ],
        "summary": [
            ("future_value", "Final balance", "money"),
            ("monthly_contribution", "Monthly contribution", "money"),
            ("time", "Time", "text"),
            ("goal", "Goal", "phrase"),
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
            ("lifetime_result", "Refinancing", "phrase"),
            ("new_payment", "New payment", "money"),
            ("monthly_savings", "Monthly change", "money"),
            ("break_even", "Break-even", "text"),
            ("savings_over_remaining_term", "Net over the shorter term only", "money"),
        ],
    },
    {
        "key": "investments",
        "title": "Investments",
        "facade": os.path.join("src", "app", "investments_screen.nova"),
        "fields": [
            ("positions", "Positions (one row per purchase lot)", [
                ["VTI", "10", "150.00", "195.17", "2023-01-15"],
                ["VTI", "5", "180.00", "195.17", "2023-08-01"],
                ["BND", "2.4", "210.50", "220.10", "2022-06-30"],
            ], {"rows": ["Symbol", "Shares", "Cost / share", "Current price", "Bought (YYYY-MM-DD)"]}),
            ("as_of", "As of (YYYY-MM-DD)", datetime.date.today().isoformat()),
        ],
        "summary": [
            ("total_value", "Value", "money"),
            ("total_cost", "Cost basis", "money"),
            ("total_gain", "Gain", "money"),
            ("total_gain_pct", "Gain %", "percent"),
            ("portfolio_return", "Annualized (XIRR)", "percent"),
        ],
    },
    {
        "key": "debt_payoff",
        "title": "Debt payoff",
        "facade": os.path.join("src", "app", "debt_payoff_screen.nova"),
        "fields": [
            ("debts", "Debts", [["Medical", "1,200.00", "0", "50.00"], ["Card", "6,000.00", "24.99", "150.00"], ["Car", "9,000.00", "7", "250.00"]],
             {"rows": ["Name", "Balance", "APR (%)", "Minimum"]}),
            ("budget", "Monthly budget", "700.00"),
            ("strategy", "Strategy", "avalanche", {"choices": [("avalanche", "Avalanche (highest rate first)"), ("snowball", "Snowball (smallest balance first)")]}),
        ],
        "summary": [
            ("avalanche", "Avalanche", "phrase"),
            ("snowball", "Snowball", "phrase"),
            ("difference", "Difference", "phrase"),
            ("payoff_months", "Debt-free in (months)", "count"),
        ],
    },
]
def load_units_table():
    """The parsed src/math/units.json. File I/O and decoding are the host's job
    (and `json` is undefined inside NovaLang modules); the table's semantics -
    validation, factors, conversions - are all NovaLang's (src/math/units.nova)."""
    with open(os.path.join(REPO_ROOT, "src", "math", "units.json"), encoding="utf-8") as handle:
        return json.load(handle)


SCREENS.append({
    "key": "math",
    "title": "Math",
    "facade": os.path.join("src", "app", "math_screen.nova"),
    "fields": [
        ("expression", "Expression (e.g. 3 + 4 * (2 - 1), sqrt(2), sin(30))", "3 + 4 * (2 - 1)"),
        ("angle", "Angles", "rad", {"choices": [("rad", "Radians"), ("deg", "Degrees")]}),
        ("value", "Convert value", "98.6"),
        ("from_unit", "From unit", "degF"),
        ("to_unit", "To unit", "degC"),
        ("units", "", load_units_table(), {"hidden": True}),
    ],
    "summary": [
        ("result", "Result", "text"),
        ("exact", "Exact", "text"),
        ("converted", "Converted", "text"),
    ],
})
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
        if "value" not in value:
            return "-"
        return format_minor(value["value"], value["scale"], grouping) + "%"
    if kind == "decimal":
        return format_minor(value["value"], value["scale"], grouping)
    if kind == "phrase":
        if "amount" not in value:
            return "".join([value["before"], value["after"]])
        return "".join([value["before"], format_minor(value["amount"], scale, grouping), value["after"]])
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
    return [field[2] for field in SCREENS_BY_KEY[screen_key]["fields"]]


def field_options(field):
    return field[3] if len(field) > 3 else {}


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


def build_rows_field(parent, label, default_rows, headings, on_change, tk, ttk):
    """An editable list of rows (e.g. debts): one Entry per cell, with Add row
    and Remove last row. Returns a reader giving a list of lists of strings.
    Rows are stacked with pack(), so no grid index arithmetic is needed."""
    box = ttk.LabelFrame(parent, text=label, padding=6)
    box.pack(fill="x", padx=10)
    header = ttk.Frame(box)
    header.pack(fill="x")
    for heading in headings:
        ttk.Label(header, text=heading, width=18).pack(side="left", padx=2)
    body = ttk.Frame(box)
    body.pack(fill="x")
    rows = []

    def add_row(values):
        line = ttk.Frame(body)
        line.pack(fill="x", pady=1)
        cells = []
        for value in values:
            variable = tk.StringVar(value=value)
            variable.trace_add("write", on_change)
            ttk.Entry(line, width=20, textvariable=variable).pack(side="left", padx=2)
            cells.append(variable)
        rows.append((line, cells))
        on_change()

    def remove_row():
        if rows:
            line, _ = rows.pop()
            line.destroy()
            on_change()

    for values in default_rows:
        add_row(values)
    controls = ttk.Frame(box)
    controls.pack(fill="x", pady=(4, 0))
    ttk.Button(controls, text="Add row", command=lambda: add_row(["" for _ in headings])).pack(side="left", padx=2)
    ttk.Button(controls, text="Remove last row", command=remove_row).pack(side="left", padx=2)
    return lambda: [[cell.get() for cell in cells] for _, cells in rows]


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

    readers = []
    column = 0
    for field in screen["fields"]:
        key, label, default = field[0], field[1], field[2]
        options = field_options(field)
        if options.get("hidden"):
            # Data the host loaded (e.g. the units table): passed through, no widget.
            readers.append(lambda value=default: value)
            continue
        if "rows" in options:
            readers.append(build_rows_field(frame, label, default, options["rows"], mark_stale, tk, ttk))
            continue
        ttk.Label(form, text=label).grid(row=0, column=column, sticky="w", padx=4)
        if "choices" in options:
            labels_to_values = {text: value for value, text in options["choices"]}
            values_to_labels = {value: text for value, text in options["choices"]}
            variable = tk.StringVar(value=values_to_labels[default])
            ttk.Combobox(form, textvariable=variable, values=list(labels_to_values), state="readonly", width=26).grid(row=1, column=column, padx=4)
            readers.append(lambda variable=variable, mapping=labels_to_values: mapping[variable.get()])
        else:
            variable = tk.StringVar(value=default)
            ttk.Entry(form, width=15, textvariable=variable).grid(row=1, column=column, padx=4)
            readers.append(variable.get)
        variable.trace_add("write", mark_stale)
        column = len(readers)

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
    extra_frame = ttk.Frame(frame, padding=(10, 0))
    extra_frame.pack(fill="x")
    extra_tables = []
    assumptions = ttk.Label(frame, text="", padding=(10, 0, 10, 10), justify="left", wraplength=940)
    assumptions.pack(fill="x")

    def fill(view, columns, kinds, rows, scale):
        if tuple(view["columns"]) != tuple(columns):
            view["columns"] = columns
            for name, kind in zip(columns, kinds):
                view.heading(name, text=name.replace("_", " ").capitalize())
                view.column(name, anchor="w" if kind == "text" else "e", width=110)
        view.delete(*view.get_children())
        for row in rows:
            view.insert("", "end", values=[format_value(value, kind, scale) for value, kind in zip(row, kinds)])

    def on_calculate():
        start = time.perf_counter()
        try:
            result = calculate(screen["key"], *(read() for read in readers))
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
        fill(table, result["columns"], result["column_kinds"], result["rows"], scale)
        for spec in result.get("extra_tables", []):
            if len(extra_tables) < len(result.get("extra_tables", [])):
                box = ttk.LabelFrame(extra_frame, text=spec["title"], padding=4)
                box.pack(fill="x", pady=(4, 0))
                view = ttk.Treeview(box, show="headings", height=6)
                view.pack(fill="x")
                extra_tables.append(view)
        for view, spec in zip(extra_tables, result.get("extra_tables", [])):
            fill(view, spec["columns"], spec["column_kinds"], spec["rows"], scale)
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
