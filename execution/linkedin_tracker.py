#!/usr/bin/env python3
"""
LinkedIn Post Tracker Builder — generates the workbook that logs every
LinkedIn post's performance. Part of the quiet experiment behind the eventual
"I have a confession" post: every post gets logged here from day one, so
there's a real track record to point to when it's revealed.

Not plugged into any pipeline or API — LinkedIn doesn't expose personal-profile
post insights publicly, so this is manual entry from the post's own "View
analytics" screen (same reason Instagram's follows/visits are hand-entered
too). execution/linkedin_write.py is the only way data goes in.

Tabs:
  Posts     — one row per published post: date, track, topic, link, and the
              four numbers LinkedIn's own analytics shows (impressions,
              reactions, comments, reposts), plus a computed engagement rate.
  Dashboard — totals, average engagement rate, best/worst post, by-track
              breakdown.

Usage:
    python3 execution/linkedin_tracker.py
    python3 execution/linkedin_tracker.py -o outputs/linkedin/other.xlsx
"""

import argparse
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "outputs" / "linkedin" / "LinkedIn_Post_Tracker.xlsx"

TRACKS = ["Personal", "Proof-of-build", "Alpha School", "Client", "Other"]

POSTS_LAST_ROW = 300

# Headers double as the schema fingerprint — linkedin_write.py checks these
# before writing so a layout change can't silently land in the wrong column.
POSTS_HEADERS = ["ID", "Posted", "Track", "Topic", "Link", "Impressions",
                 "Reactions", "Comments", "Reposts", "Engagement Rate", "Notes"]
POSTS_COLS = {"id": 1, "posted_date": 2, "track": 3, "topic": 4, "link": 5, "impressions": 6,
              "reactions": 7, "comments": 8, "reposts": 9, "eng_rate": 10, "notes": 11}
METRICS = ["impressions", "reactions", "comments", "reposts"]
assert len(POSTS_HEADERS) == len(POSTS_COLS)

# Palette — LinkedIn blue, used sparingly for headers (this tracker is
# internal, not a deliverable, so it just needs to read cleanly).
INK = "1F2933"
ACCENT = "0A66C2"
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
CALC_FILL = PatternFill("solid", fgColor="F2F4F7")
WHITE_BOLD = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=INK)
BOLD = Font(bold=True, color=INK)
MUTED = Font(italic=True, color="6B7280", size=9)
THIN = Side(style="thin", color="E5E7EB")
WRAP = Alignment(wrap_text=True, vertical="top")


class SchemaError(Exception):
    pass


def check_schema(wb):
    actual = [wb["Posts"].cell(row=1, column=c).value for c in range(1, len(POSTS_HEADERS) + 1)]
    if actual != POSTS_HEADERS:
        raise SchemaError(
            "'Posts' columns don't match this version of the scripts. Nothing was written. "
            "Run: python3 execution/linkedin_tracker.py --migrate")


def header(ws, labels, widths):
    for i, (label, w) in enumerate(zip(labels, widths), start=1):
        c = ws.cell(row=1, column=i, value=label)
        c.fill = HEADER_FILL
        c.font = WHITE_BOLD
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 22
    ws.freeze_panes = "A2"


def list_validation(ws, choices, rng):
    dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(rng)


def eng_rate_formula(r):
    P = lambda key: get_column_letter(POSTS_COLS[key])
    impr = f"{P('impressions')}{r}"
    n = lambda key: f"N({P(key)}{r})"
    return f'=IF(OR({impr}="",{impr}=0),"",({n("reactions")}+{n("comments")}+{n("reposts")})/{impr})'


def build_posts(wb):
    ws = wb.active
    ws.title = "Posts"
    header(ws, POSTS_HEADERS, [8, 12, 14, 42, 32, 11, 10, 10, 9, 13, 36])
    last = POSTS_LAST_ROW
    P = lambda key: get_column_letter(POSTS_COLS[key])
    for r in range(2, last + 1):
        ws.cell(row=r, column=POSTS_COLS["posted_date"]).number_format = "d mmm yyyy"
        ws.cell(row=r, column=POSTS_COLS["topic"]).alignment = WRAP
        ws.cell(row=r, column=POSTS_COLS["notes"]).alignment = WRAP
        c = ws.cell(row=r, column=POSTS_COLS["eng_rate"], value=eng_rate_formula(r))
        c.fill = CALC_FILL
        c.number_format = "0.0%"
    list_validation(ws, TRACKS, f"{P('track')}2:{P('track')}{last}")
    er = P("eng_rate")
    ws.conditional_formatting.add(
        f"{er}2:{er}{last}",
        CellIsRule(operator="greaterThanOrEqual", formula=["0.02"],
                   fill=PatternFill("solid", fgColor="DCFCE7"), font=Font(bold=True, color="166534")),
    )


def build_dashboard(wb):
    ws = wb.create_sheet("Dashboard")
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 42
    ws["A1"] = "LinkedIn Post Tracker"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Quiet experiment — see directives/linkedin_experiment.md"
    ws["A2"].font = MUTED

    last = POSTS_LAST_ROW
    idc, dt, trk, tpc, imp, rxn, cmt, rpt, er = (get_column_letter(POSTS_COLS[k]) for k in
        ("id", "posted_date", "track", "topic", "impressions", "reactions", "comments", "reposts", "eng_rate"))
    rng = lambda col: f"Posts!{col}2:{col}{last}"

    rows = [
        ("Posts logged", f'=COUNTIF({rng(idc)},"<>")'),
        ("Average engagement rate", f'=IFERROR(AVERAGE({rng(er)}),"")'),
        ("Total impressions", f'=SUM({rng(imp)})'),
        ("Total reactions", f'=SUM({rng(rxn)})'),
        ("Total comments", f'=SUM({rng(cmt)})'),
        ("Total reposts", f'=SUM({rng(rpt)})'),
    ]
    r = 4
    for label, formula in rows:
        ws.cell(row=r, column=1, value=label).font = BOLD
        c = ws.cell(row=r, column=2, value=formula)
        c.fill = CALC_FILL
        if "rate" in label.lower():
            c.number_format = "0.0%"
        elif "Total" in label:
            c.number_format = "#,##0"
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="Best post (by engagement rate)").font = BOLD
    best_row = f'MATCH(MAX({rng(er)}),{rng(er)},0)+1'
    ws.cell(row=r, column=2,
            value=f'=IFERROR(INDEX({rng(tpc)},{best_row})&" ("&TEXT(MAX({rng(er)}),"0.0%")&")","")')
    ws.cell(row=r, column=2).fill = CALC_FILL
    r += 1
    ws.cell(row=r, column=1, value="Weakest post (by engagement rate)").font = BOLD
    # MIN, like MAX, ignores the "" text a blank-impressions row's formula
    # returns — no need for an array/CSE formula to exclude blanks.
    worst_row = f'MATCH(MIN({rng(er)}),{rng(er)},0)+1'
    ws.cell(row=r, column=2,
            value=f'=IFERROR(INDEX({rng(tpc)},{worst_row})&" ("&TEXT(MIN({rng(er)}),"0.0%")&")","")')
    ws.cell(row=r, column=2).fill = CALC_FILL
    r += 2

    ws.cell(row=r, column=1, value="By track").font = BOLD
    r += 1
    for track in TRACKS:
        ws.cell(row=r, column=1, value=track)
        c = ws.cell(row=r, column=2, value=f'=COUNTIF({rng(trk)},"{track}")')
        c.fill = CALC_FILL
        c.number_format = "#,##0"
        r += 1


def build(path: Path):
    wb = Workbook()
    build_posts(wb)
    build_dashboard(wb)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main():
    ap = argparse.ArgumentParser(description="Build the LinkedIn Post Tracker workbook.")
    ap.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()
    out = Path(args.output)
    if out.exists():
        print(f"{out} already exists — not overwriting. Delete it first, or pass -o for a new path.")
        return
    build(out)
    print(f"Built {out}")


if __name__ == "__main__":
    main()
