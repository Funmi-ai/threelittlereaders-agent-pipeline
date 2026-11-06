#!/usr/bin/env python3
"""
Tracker Write — appends rows to a rent-to-rent tracker workbook (built by
expense_tracker.py) without touching its formulas, tables, dropdowns, or
formatting. This is the execution layer for directives/log_transaction.md:
the client describes money moving in plain English, Claude Code maps it to
one of the calls below instead of the client typing into Excel by hand.

Every write is validated against the workbook's own Setup tab (property must
already exist there) and the fixed category/status lists in expense_tracker.py
(imported, not duplicated) — a typo here would otherwise sum to 0 silently in
Monthly Summary rather than error, so it's caught up front instead.

Subcommands:
  property  — add a new property to the Setup tab
  income    — log one row in Income Log
  expense   — log one row in Expense Log
  batch     — log several income/expense/property rows from one JSON payload

Usage:
    python3 execution/tracker_write.py income --property "Mikocheni Villa" \\
        --date 2026-08-01 --category "Tenant Rent" --amount 500 \\
        --description "Room 1 — Aug rent" --method "Bank Transfer" --status Received

    python3 execution/tracker_write.py expense --property "Mikocheni Villa" \\
        --date 2026-08-01 --category "Rent to Landlord" --amount 900 \\
        --description "Aug rent to landlord" --method "Standing Order" --status Paid

    python3 execution/tracker_write.py property --name "Mikocheni Villa" \\
        --address "Mikocheni, Dar es Salaam" --rooms 4 --start-date 2026-08-01 \\
        --landlord-rent 900 --rent-due-day 1 --deposit-paid 900 --target-income 1800

    python3 execution/tracker_write.py batch --json-file /path/to/transactions.json
    python3 execution/tracker_write.py batch --json '[{"type":"income", ...}]'

    # Point at a different workbook (default is the client's live copy):
    python3 execution/tracker_write.py income --file /path/to/other.xlsx ...
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

# Single source of truth for the allowed values — these drive the workbook's
# own dropdowns/conditional formatting, so a script-written row has to match
# them exactly or Monthly Summary's SUMIFS will just silently exclude it.
from expense_tracker import (
    INCOME_CATEGORIES,
    EXPENSE_CATEGORIES,
    PAYMENT_METHODS,
    INCOME_STATUS,
    EXPENSE_STATUS,
)

DEFAULT_TRACKER = Path.home() / "Downloads" / "Property_Business_Rent_to_Rent_Tracker.xlsx"
BACKUP_DIR = Path(__file__).resolve().parent.parent / "outputs" / "trackers" / "backups"
MAX_BACKUPS_PER_FILE = 50

LOG_LAST_ROW = 500     # must match last_income_row/last_expense_row in expense_tracker.py
SETUP_LAST_ROW = 60    # must match last_setup_row in expense_tracker.py


class TrackerError(Exception):
    pass


def check_lock_file(path: Path):
    """Excel drops a ~$<name> lock file next to a workbook that's open for
    editing. If we write while that's present, the client's next Cmd+S in
    Excel will silently overwrite what we just added."""
    lock = path.parent / f"~${path.name}"
    if lock.exists():
        print(
            f"⚠  {lock.name} found next to the tracker — it looks like the file is "
            "currently open in Excel. If it gets saved from Excel after this runs, "
            "these changes will be overwritten. Close the file in Excel (or make sure "
            "not to save from there) before trusting this write.",
            file=sys.stderr,
        )


def backup(path: Path):
    if not path.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(path, BACKUP_DIR / f"{stamp}_{path.name}")
    existing = sorted(BACKUP_DIR.glob(f"*_{path.name}"))
    for old in existing[:-MAX_BACKUPS_PER_FILE]:
        old.unlink()


def parse_date(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        raise TrackerError(f"Date '{s}' must be in YYYY-MM-DD format.")


def parse_amount(v, field="Amount"):
    try:
        n = round(float(v), 2)
    except (TypeError, ValueError):
        raise TrackerError(f"{field} '{v}' isn't a number.")
    if n <= 0:
        raise TrackerError(f"{field} must be greater than 0 (got {v}).")
    return n


def get_properties(wb):
    ws = wb["Setup"]
    names = []
    for r in range(2, SETUP_LAST_ROW + 1):
        v = ws.cell(row=r, column=1).value
        if v and not str(v).strip().upper().startswith("EXAMPLE"):
            names.append(str(v).strip())
    return names


def resolve_property(wb, name):
    props = get_properties(wb)
    for p in props:
        if p.lower() == name.strip().lower():
            return p
    known = ", ".join(props) if props else "(none set up yet)"
    raise TrackerError(
        f"Property '{name}' isn't in the Setup tab. Known properties: {known}. "
        f"Add it first: tracker_write.py property --name \"{name}\" ..."
    )


def validate_choice(value, choices, field):
    for c in choices:
        if c.lower() == value.strip().lower():
            return c
    raise TrackerError(f"{field} '{value}' isn't one of: {', '.join(choices)}")


def first_blank_row(ws, last_row, start=2):
    for r in range(start, last_row + 1):
        if ws.cell(row=r, column=1).value in (None, ""):
            return r
    raise TrackerError(
        f"No blank rows left on '{ws.title}' (checked up to row {last_row}). "
        "Extend the range in expense_tracker.py and regenerate."
    )


# --------------------------------------------------------------------------
# Validate (raise TrackerError, write nothing) — used standalone and by batch
# --------------------------------------------------------------------------
def validate_income(wb, item):
    return {
        "property": resolve_property(wb, item["property"]),
        "category": validate_choice(item["category"], INCOME_CATEGORIES, "Category"),
        "method": validate_choice(item["method"], PAYMENT_METHODS, "Payment method"),
        "status": validate_choice(item.get("status", "Received"), INCOME_STATUS, "Status"),
        "date": parse_date(item["date"]),
        "amount": parse_amount(item["amount"]),
        "description": item.get("description", ""),
        "notes": item.get("notes", ""),
    }


def validate_expense(wb, item):
    return {
        "property": resolve_property(wb, item["property"]),
        "category": validate_choice(item["category"], EXPENSE_CATEGORIES, "Category"),
        "method": validate_choice(item["method"], PAYMENT_METHODS, "Payment method"),
        "status": validate_choice(item.get("status", "Paid"), EXPENSE_STATUS, "Status"),
        "date": parse_date(item["date"]),
        "amount": parse_amount(item["amount"]),
        "description": item.get("description", ""),
        "notes": item.get("notes", ""),
    }


def validate_property(wb, item):
    existing = {p.lower() for p in get_properties(wb)}
    name = item["name"].strip()
    if name.lower() in existing:
        raise TrackerError(f"Property '{name}' already exists in Setup — use income/expense, not property.")
    return {
        "name": name,
        "address": item.get("address", ""),
        "rooms": item.get("rooms"),
        "start_date": parse_date(item["start_date"]) if item.get("start_date") else None,
        "landlord_rent": parse_amount(item["landlord_rent"], "Landlord rent") if item.get("landlord_rent") else None,
        "rent_due_day": item.get("rent_due_day"),
        "deposit_paid": parse_amount(item["deposit_paid"], "Deposit paid") if item.get("deposit_paid") else None,
        "target_income": parse_amount(item["target_income"], "Target income") if item.get("target_income") else None,
        "notes": item.get("notes", ""),
    }


# --------------------------------------------------------------------------
# Write (assumes already validated)
# --------------------------------------------------------------------------
def write_income_row(wb, v):
    ws = wb["Income Log"]
    r = first_blank_row(ws, LOG_LAST_ROW)
    ws.cell(row=r, column=1, value=v["date"])
    ws.cell(row=r, column=2, value=v["property"])
    ws.cell(row=r, column=3, value=v["category"])
    ws.cell(row=r, column=4, value=v["description"])
    ws.cell(row=r, column=5, value=v["amount"])
    ws.cell(row=r, column=6, value=v["method"])
    ws.cell(row=r, column=7, value=v["status"])
    ws.cell(row=r, column=9, value=v["notes"])
    return f"Income Log!A{r} — {v['date']} · {v['property']} · {v['category']} · {v['amount']} · {v['status']}"


def write_expense_row(wb, v):
    ws = wb["Expense Log"]
    r = first_blank_row(ws, LOG_LAST_ROW)
    ws.cell(row=r, column=1, value=v["date"])
    ws.cell(row=r, column=2, value=v["property"])
    ws.cell(row=r, column=3, value=v["category"])
    ws.cell(row=r, column=4, value=v["description"])
    ws.cell(row=r, column=5, value=v["amount"])
    ws.cell(row=r, column=6, value=v["method"])
    ws.cell(row=r, column=7, value=v["status"])
    ws.cell(row=r, column=9, value=v["notes"])
    return f"Expense Log!A{r} — {v['date']} · {v['property']} · {v['category']} · {v['amount']} · {v['status']}"


def write_property_row(wb, v):
    ws = wb["Setup"]
    r = first_blank_row(ws, SETUP_LAST_ROW)
    ws.cell(row=r, column=1, value=v["name"])
    ws.cell(row=r, column=2, value=v["address"])
    ws.cell(row=r, column=3, value=v["rooms"])
    ws.cell(row=r, column=4, value=v["start_date"])
    ws.cell(row=r, column=5, value=v["landlord_rent"])
    ws.cell(row=r, column=6, value=v["rent_due_day"])
    ws.cell(row=r, column=7, value=v["deposit_paid"])
    ws.cell(row=r, column=8, value=v["target_income"])
    ws.cell(row=r, column=9, value=v["notes"])
    return f"Setup!A{r} — {v['name']}"


def item_to_kwargs(item):
    """argparse.Namespace-like dict access used by validate_* (they read item[...] / item.get(...))."""
    return item


def run(args):
    path = Path(args.file).expanduser()
    if not path.exists():
        raise TrackerError(f"Tracker not found at {path}")
    check_lock_file(path)
    wb = load_workbook(path)

    results = []

    if args.command == "income":
        v = validate_income(wb, vars(args))
        results.append(write_income_row(wb, v))
    elif args.command == "expense":
        v = validate_expense(wb, vars(args))
        results.append(write_expense_row(wb, v))
    elif args.command == "property":
        item = dict(vars(args))
        item["name"] = args.name
        v = validate_property(wb, item)
        results.append(write_property_row(wb, v))
    elif args.command == "batch":
        raw = args.json if args.json else Path(args.json_file).read_text()
        try:
            items = json.loads(raw)
        except json.JSONDecodeError as e:
            raise TrackerError(f"Invalid JSON: {e}")
        if not isinstance(items, list):
            raise TrackerError("Batch JSON must be a list of transaction objects.")

        validated = []
        errors = []
        for i, item in enumerate(items):
            t = item.get("type")
            try:
                if t == "income":
                    validated.append(("income", validate_income(wb, item)))
                elif t == "expense":
                    validated.append(("expense", validate_expense(wb, item)))
                elif t == "property":
                    validated.append(("property", validate_property(wb, item)))
                else:
                    raise TrackerError(f"Unknown type '{t}' (must be income/expense/property).")
            except TrackerError as e:
                errors.append(f"  item {i}: {e}")
        if errors:
            raise TrackerError("Batch validation failed, nothing written:\n" + "\n".join(errors))

        for kind, v in validated:
            if kind == "income":
                results.append(write_income_row(wb, v))
            elif kind == "expense":
                results.append(write_expense_row(wb, v))
            else:
                results.append(write_property_row(wb, v))

    backup(path)
    wb.save(path)
    return results


def build_parser():
    # A shared parent so --file works whether it's typed before or after the
    # subcommand (argparse only honors top-level options *before* the
    # subcommand name otherwise).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--file", default=str(DEFAULT_TRACKER), help=f"Path to the tracker (default: {DEFAULT_TRACKER})")

    ap = argparse.ArgumentParser(description="Append rows to a rent-to-rent tracker workbook.", parents=[common])
    sub = ap.add_subparsers(dest="command", required=True)

    inc = sub.add_parser("income", parents=[common], help="Log a row in Income Log")
    inc.add_argument("--property", required=True)
    inc.add_argument("--date", required=True, help="YYYY-MM-DD")
    inc.add_argument("--category", required=True, help=f"One of: {', '.join(INCOME_CATEGORIES)}")
    inc.add_argument("--amount", required=True)
    inc.add_argument("--method", required=True, help=f"One of: {', '.join(PAYMENT_METHODS)}")
    inc.add_argument("--status", default="Received", help=f"One of: {', '.join(INCOME_STATUS)} (default: Received)")
    inc.add_argument("--description", default="")
    inc.add_argument("--notes", default="")

    exp = sub.add_parser("expense", parents=[common], help="Log a row in Expense Log")
    exp.add_argument("--property", required=True)
    exp.add_argument("--date", required=True, help="YYYY-MM-DD")
    exp.add_argument("--category", required=True, help=f"One of: {', '.join(EXPENSE_CATEGORIES)}")
    exp.add_argument("--amount", required=True)
    exp.add_argument("--method", required=True, help=f"One of: {', '.join(PAYMENT_METHODS)}")
    exp.add_argument("--status", default="Paid", help=f"One of: {', '.join(EXPENSE_STATUS)} (default: Paid)")
    exp.add_argument("--description", default="")
    exp.add_argument("--notes", default="")

    prop = sub.add_parser("property", parents=[common], help="Add a new property to Setup")
    prop.add_argument("--name", required=True)
    prop.add_argument("--address", default="")
    prop.add_argument("--rooms", type=int, default=None)
    prop.add_argument("--start-date", dest="start_date", default=None, help="YYYY-MM-DD")
    prop.add_argument("--landlord-rent", dest="landlord_rent", default=None)
    prop.add_argument("--rent-due-day", dest="rent_due_day", type=int, default=None)
    prop.add_argument("--deposit-paid", dest="deposit_paid", default=None)
    prop.add_argument("--target-income", dest="target_income", default=None)
    prop.add_argument("--notes", default="")

    batch = sub.add_parser("batch", parents=[common], help="Log several rows from a JSON list")
    group = batch.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", help="Inline JSON array of transaction objects")
    group.add_argument("--json-file", help="Path to a JSON file containing the array")

    return ap


def main():
    args = build_parser().parse_args()
    try:
        results = run(args)
    except TrackerError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Saved {len(results)} row(s) to {Path(args.file).expanduser()}:")
    for r in results:
        print(f"  + {r}")


if __name__ == "__main__":
    main()
