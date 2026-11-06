#!/usr/bin/env python3
"""
Instagram Content Tracker Builder — generates the workbook that holds the
content plan and post insights for an Instagram account.

The user never types into this file by hand: ideas go in through chat and
execution/instagram_write.py schedules them, logs insights, and answers
"what's today's post". The workbook is the view; the writer is the input.

Tabs:
  Content Plan — one row per idea: planned date, idea, format, pillar, hook,
                 status (Idea/Scheduled → pipeline stages → Posted/Skipped), link.
  Insights     — one row per posted post: reach, views, likes, comments,
                 shares, saves, follows, profile visits, watch time, plus
                 formula-driven engagement / save / share / follow rates.
  Followers    — dated follower counts with change since last entry.
  Dashboard    — averages overall, by format and by pillar (all formulas).
  Settings     — posting days (drives auto-scheduling) and content pillars.

Rows are pre-formatted up to fixed limits (PLAN_LAST_ROW etc.) with formulas
already in place, so the writer only fills raw values into the first blank
row — same approach as expense_tracker.py, and safe to open in Numbers too
(no Excel Tables or dynamic-array formulas).

Usage:
    python3 execution/instagram_tracker.py
    python3 execution/instagram_tracker.py -o outputs/instagram/other.xlsx
"""

import argparse
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "outputs" / "instagram" / "Instagram_Content_Tracker.xlsx"

# Single source of truth for allowed values — instagram_write.py imports these.
FORMATS = ["Reel", "Carousel", "Photo", "Story"]
# Pipeline order (directives/threelittlereaders/00_pipeline.md): each status is the
# last stage *finished*. Briefed = facts + research note in; Hooked = she picked the
# hook; Drafted = copy written; Built = cover/slides made; Approved = QA + her sign-off.
STATUSES = ["Idea", "Scheduled", "Briefed", "Hooked", "Drafted", "Built", "Approved", "Posted", "Skipped"]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

PLAN_LAST_ROW = 401        # rows 2..401
INSIGHTS_LAST_ROW = 401
FOLLOWERS_LAST_ROW = 401
PILLAR_ROWS = range(2, 12)  # Settings!D2:D11

# Column maps (1-indexed) shared with the writer.
# A post has two layers, both labelled from the same pillar list:
#   pillar = what the video shows (e.g. 5yo spelling "articulate" → PROVE)
#   angle  = how the caption frames it (e.g. "5 minutes still counts" → RELATE)
PLAN_COLS = {
    "id": 1, "date": 2, "day": 3, "slot": 4, "idea": 5, "format": 6, "pillar": 7, "angle": 8,
    "hook": 9, "caption": 10, "testing": 11, "variant_of": 12, "follow_reason": 13,
    "status": 14, "posted_date": 15, "link": 16, "verdict": 17, "notes": 18,
}
# Two posting slots a day. Lunch = the daily vlog series; Evening = reach posts.
# Settings column B/C says which weekdays each slot runs on.
SLOTS = ["Lunch", "Evening"]
SLOT_SETTINGS_COL = {"Lunch": 2, "Evening": 3}
EVENING_FROM_HOUR = 16  # UK time; a post published at/after this counts as Evening
DEFAULT_SLOT_DAYS = {"Lunch": set(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]),
                     "Evening": {"Mon", "Wed", "Fri", "Sun"}}
# Settings cells for the posting-frequency test window.
FREQ_START_CELL, FREQ_END_CELL = "B15", "B16"
INSIGHT_COLS = {
    "id": 1, "posted_date": 2, "format": 3, "pillar": 4, "angle": 5, "idea": 6, "captured": 7,
    "days_live": 8, "reach": 9, "views": 10, "non_follower_pct": 11, "likes": 12,
    "comments": 13, "shares": 14, "saves": 15, "follows": 16, "profile_visits": 17,
    "watch_time": 18, "skip_rate": 19, "eng_rate": 20, "save_rate": 21, "share_rate": 22,
    "comment_rate": 23, "visit_rate": 24, "follow_rate": 25, "notes": 26,
    # Share of viewers aged 25–44 (Sally's age band), from the Audience tab.
    # Added 24 Oct 2026: reach alone hid that some posts mostly reached 18–24s.
    "sally_age_pct": 27,
}
VERDICTS = ["Win", "Mixed", "Flop"]
DEFAULT_GOAL = 10000
DEFAULT_GOAL_DATE = "2026-12-31"
# Settings cells for the follower goal (read by the Dashboard and `review`).
GOAL_CELL, GOAL_DATE_CELL = "B12", "B13"
# Headers double as the schema fingerprint: check_schema() compares them so a
# script never writes by column number into a file with a different layout.
PLAN_HEADERS = ["ID", "Planned Date", "Day", "Slot", "Idea", "Format", "Pillar (video)", "Caption angle",
                "Hook / on-screen text", "Caption notes", "Testing (one variable)", "Variant of",
                "Follow reason", "Status", "Posted Date", "Post Link", "Verdict", "Notes"]
INSIGHT_HEADERS = ["Post ID", "Posted", "Format", "Pillar (video)", "Caption angle", "Idea", "Captured On",
                   "Days Live", "Reach", "Views", "Non-follower %", "Likes", "Comments", "Shares / Sends",
                   "Saves", "Follows", "Profile Visits", "Avg Watch (s)", "Skip Rate (Reels)",
                   "Engagement Rate", "Save Rate", "Share Rate", "Comment Rate", "Profile Visit Rate",
                   "Follows per 1k reached", "What worked / notes", "Viewers aged 25–44 %"]
assert len(PLAN_HEADERS) == len(PLAN_COLS) and len(INSIGHT_HEADERS) == len(INSIGHT_COLS)


class SchemaError(Exception):
    pass


def check_schema(wb):
    for sheet, expected in (("Content Plan", PLAN_HEADERS), ("Insights", INSIGHT_HEADERS)):
        actual = [wb[sheet].cell(row=1, column=c).value for c in range(1, len(expected) + 1)]
        if actual != expected:
            raise SchemaError(
                f"'{sheet}' columns don't match this version of the scripts. Nothing was written. "
                "Run: python3 execution/instagram_tracker.py --migrate")


# Header renames between schema versions, old → new (used by migrate()).
HEADER_RENAMES = {"Pillar": "Pillar (video)", "Follow Rate": "Follows per 1k reached"}
METRICS = ["reach", "views", "non_follower_pct", "likes", "comments", "shares", "saves",
           "follows", "profile_visits", "watch_time", "skip_rate", "sally_age_pct"]
# Entered as percentages (72 = 72%), stored as fractions.
PERCENT_METRICS = {"non_follower_pct", "skip_rate", "sally_age_pct"}
# Rate columns = numerator metric ÷ reach (× RATE_SCALE). Shared with the writer.
# Follows are shown per 1,000 reached: the main number for the 10k goal,
# and easier to compare than a 0.4% figure.
RATES = {
    "save_rate": "saves", "share_rate": "shares", "comment_rate": "comments",
    "visit_rate": "profile_visits", "follow_rate": "follows",
}
RATE_SCALE = {"follow_rate": 1000}

# Palette
INK = "1F2933"
ACCENT = "C13584"       # Instagram magenta, used sparingly for headers
HEADER_FILL = PatternFill("solid", fgColor=ACCENT)
SUBTLE_FILL = PatternFill("solid", fgColor="F7F3F6")
CALC_FILL = PatternFill("solid", fgColor="F2F4F7")
WHITE_BOLD = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=16, color=INK)
BOLD = Font(bold=True, color=INK)
MUTED = Font(italic=True, color="6B7280", size=9)
THIN = Side(style="thin", color="E5E7EB")
BORDER = Border(bottom=THIN)
WRAP = Alignment(wrap_text=True, vertical="top")

STATUS_COLOURS = {
    "Idea": "EEF2FF", "Scheduled": "FEF3C7", "Briefed": "FFEDD5", "Hooked": "FCE7F3",
    "Drafted": "DBEAFE", "Built": "E0F2FE", "Approved": "CCFBF1",
    "Posted": "DCFCE7", "Skipped": "F3F4F6",
}


def header(ws, labels, widths):
    for i, (label, w) in enumerate(zip(labels, widths), start=1):
        c = ws.cell(row=1, column=i, value=label)
        c.fill = HEADER_FILL
        c.font = WHITE_BOLD
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.row_dimensions[1].height = 30
    ws.freeze_panes = "A2"


def list_validation(ws, choices, rng):
    dv = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(rng)


def build_plan(wb):
    ws = wb.active
    ws.title = "Content Plan"
    header(ws, PLAN_HEADERS,
           [9, 13, 7, 9, 44, 11, 14, 14, 40, 36, 30, 10, 28, 12, 13, 30, 10, 30])
    last = PLAN_LAST_ROW
    P = lambda key: get_column_letter(PLAN_COLS[key])
    for r in range(2, last + 1):
        ws.cell(row=r, column=PLAN_COLS["date"]).number_format = "ddd d mmm yyyy"
        ws.cell(row=r, column=PLAN_COLS["posted_date"]).number_format = "d mmm yyyy"
        day = ws.cell(row=r, column=PLAN_COLS["day"], value=f'=IF({P("date")}{r}="","",TEXT({P("date")}{r},"ddd"))')
        day.fill = CALC_FILL
        for col in (PLAN_COLS["idea"], PLAN_COLS["hook"], PLAN_COLS["caption"], PLAN_COLS["testing"],
                    PLAN_COLS["follow_reason"], PLAN_COLS["notes"]):
            ws.cell(row=r, column=col).alignment = WRAP
    list_validation(ws, FORMATS, f"{P('format')}2:{P('format')}{last}")
    list_validation(ws, STATUSES, f"{P('status')}2:{P('status')}{last}")
    list_validation(ws, SLOTS, f"{P('slot')}2:{P('slot')}{last}")
    list_validation(ws, VERDICTS, f"{P('verdict')}2:{P('verdict')}{last}")
    v = P("verdict")
    for verdict, (fill, font) in {"Win": ("BBF7D0", "166534"), "Flop": ("FECACA", "991B1B")}.items():
        ws.conditional_formatting.add(
            f"{v}2:{v}{last}",
            CellIsRule(operator="equal", formula=[f'"{verdict}"'], fill=PatternFill("solid", fgColor=fill),
                       font=Font(bold=True, color=font)),
        )
    pillar_dv = DataValidation(type="list", formula1="=Settings!$D$2:$D$11", allow_blank=True)
    ws.add_data_validation(pillar_dv)
    pillar_dv.add(f"{P('pillar')}2:{P('angle')}{last}")
    end = get_column_letter(len(PLAN_COLS))
    for status, colour in STATUS_COLOURS.items():
        ws.conditional_formatting.add(
            f"A2:{end}{last}",
            FormulaRule(formula=[f'${P("status")}2="{status}"'], fill=PatternFill("solid", fgColor=colour)),
        )


def insight_formulas(r):
    """Formula cells for one Insights row. A rate stays blank when its
    metric is blank — the API doesn't supply follows/visits for reels, and a
    0% there would drag every Dashboard average down."""
    L = lambda key: get_column_letter(INSIGHT_COLS[key])
    reach = f"{L('reach')}{r}"
    no_reach = f'OR($A{r}="",{reach}="",{reach}=0)'
    n = lambda key: f"N({L(key)}{r})"
    calcs = {
        "days_live": f'=IF(OR({L("posted_date")}{r}="",{L("captured")}{r}=""),"",'
                     f'{L("captured")}{r}-{L("posted_date")}{r})',
        # Instagram's own definition: interactions / accounts reached.
        "eng_rate": f'=IF({no_reach},"",({n("likes")}+{n("comments")}+{n("shares")}+{n("saves")})/{reach})',
    }
    for rate, metric in RATES.items():
        scale = f"*{RATE_SCALE[rate]}" if rate in RATE_SCALE else ""
        calcs[rate] = f'=IF(OR({no_reach},{L(metric)}{r}=""),"",{L(metric)}{r}/{reach}{scale})'
    return calcs


def refresh_formulas(path: Path):
    """Rewrite Insights formula cells in an existing tracker in place, so a
    formula fix reaches the live file without a rebuild (which would lose data)."""
    from openpyxl import load_workbook
    wb = load_workbook(path)
    ws = wb["Insights"]
    for r in range(2, INSIGHTS_LAST_ROW + 1):
        for key, formula in insight_formulas(r).items():
            ws.cell(row=r, column=INSIGHT_COLS[key]).value = formula
    wb.save(path)


def migrate(path: Path):
    """Move an existing tracker onto the current schema: build a fresh
    workbook, then copy every non-formula value across by header name
    (HEADER_RENAMES covers renamed headers). Formulas come from the fresh
    build, so column moves can't leave stale references behind. The old file
    is kept as <name>.pre-migrate.xlsx."""
    import shutil
    from openpyxl import load_workbook
    old = load_workbook(path)
    tmp = path.with_suffix(".migrating.xlsx")
    build(tmp)
    new = load_workbook(tmp)
    copied = {}
    for name in ("Content Plan", "Insights", "Followers"):
        o, n = old[name], new[name]
        new_cols = {n.cell(row=1, column=c).value: c for c in range(1, n.max_column + 1)}
        mapping = {}
        for c in range(1, o.max_column + 1):
            h = o.cell(row=1, column=c).value
            h = HEADER_RENAMES.get(h, h)
            if h in new_cols:
                mapping[c] = new_cols[h]
        rows = 0
        for r in range(2, o.max_row + 1):
            row_has_data = False
            for oc, nc in mapping.items():
                v = o.cell(row=r, column=oc).value
                if v is None or (isinstance(v, str) and v.startswith("=")):
                    continue
                n.cell(row=r, column=nc).value = v
                row_has_data = True
            rows += row_has_data
        copied[name] = rows
    # Settings: posting days and pillars.
    for r in range(2, 9):
        new["Settings"].cell(row=r, column=2).value = old["Settings"].cell(row=r, column=2).value
        if old["Settings"]["C1"].value == "Evening post?":
            new["Settings"].cell(row=r, column=3).value = old["Settings"].cell(row=r, column=3).value
    if old["Settings"]["A15"].value == "Frequency test start":
        for cell in (FREQ_START_CELL, FREQ_END_CELL):
            new["Settings"][cell].value = old["Settings"][cell].value
    for r in PILLAR_ROWS:
        new["Settings"].cell(row=r, column=4).value = old["Settings"].cell(row=r, column=4).value
    for cell in (GOAL_CELL, GOAL_DATE_CELL):
        if old["Settings"]["A12"].value == "Follower goal" and old["Settings"][cell].value is not None:
            new["Settings"][cell].value = old["Settings"][cell].value
    new.save(tmp)
    shutil.copy2(path, path.with_suffix(".pre-migrate.xlsx"))
    tmp.replace(path)
    return copied


def build_insights(wb):
    ws = wb.create_sheet("Insights")
    header(ws, INSIGHT_HEADERS,
           [9, 12, 10, 12, 12, 36, 12, 8, 9, 9, 11, 8, 10, 9, 8, 9, 9, 10, 10, 11, 9, 9, 10, 11, 9, 40, 11])
    last = INSIGHTS_LAST_ROW
    L = lambda key: get_column_letter(INSIGHT_COLS[key])
    for r in range(2, last + 1):
        for col in (INSIGHT_COLS["posted_date"], INSIGHT_COLS["captured"]):
            ws.cell(row=r, column=col).number_format = "d mmm yy"
        for key in PERCENT_METRICS:
            ws.cell(row=r, column=INSIGHT_COLS[key]).number_format = "0%"
        ws.cell(row=r, column=INSIGHT_COLS["idea"]).alignment = WRAP
        ws.cell(row=r, column=INSIGHT_COLS["notes"]).alignment = WRAP
        for key, formula in insight_formulas(r).items():
            c = ws.cell(row=r, column=INSIGHT_COLS[key], value=formula)
            c.fill = CALC_FILL
            if key in RATE_SCALE:
                c.number_format = "0.0"
            elif key != "days_live":
                c.number_format = "0.0%"
    # Highlight standout posts: engagement rate at or above 5%.
    er = L("eng_rate")
    ws.conditional_formatting.add(
        f"{er}2:{er}{last}",
        CellIsRule(operator="greaterThanOrEqual", formula=["0.05"],
                   fill=PatternFill("solid", fgColor="DCFCE7"), font=Font(bold=True, color="166534")),
    )


def build_followers(wb):
    ws = wb.create_sheet("Followers")
    header(ws, ["Date", "Followers", "Change", "Notes"], [14, 12, 10, 40])
    for r in range(2, FOLLOWERS_LAST_ROW + 1):
        ws.cell(row=r, column=1).number_format = "d mmm yyyy"
        if r == 2:
            continue
        c = ws.cell(row=r, column=3, value=f'=IF(OR(B{r}="",B{r - 1}=""),"",B{r}-B{r - 1})')
        c.fill = CALC_FILL
        c.number_format = '+0;-0;0'


def build_settings(wb):
    ws = wb.create_sheet("Settings")
    ws["A1"], ws["B1"], ws["C1"] = "Weekday", "Lunchtime post?", "Evening post?"
    ws["D1"] = "Content pillars (edit freely)"
    for cell in ("A1", "B1", "C1", "D1"):
        ws[cell].fill = HEADER_FILL
        ws[cell].font = WHITE_BOLD
    for i, day in enumerate(WEEKDAYS, start=2):
        ws.cell(row=i, column=1, value=day).font = BOLD
        for slot, col in SLOT_SETTINGS_COL.items():
            ws.cell(row=i, column=col, value="Yes" if day in DEFAULT_SLOT_DAYS[slot] else "No")
    list_validation(ws, ["Yes", "No"], "B2:C8")
    ws["A10"] = "New ideas get the next free 'Yes' day automatically."
    ws["A10"].font = MUTED
    from datetime import date as _date
    ws["A12"], ws[GOAL_CELL] = "Follower goal", DEFAULT_GOAL
    ws["A13"], ws[GOAL_DATE_CELL] = "Goal date", _date.fromisoformat(DEFAULT_GOAL_DATE)
    ws["A12"].font = ws["A13"].font = BOLD
    ws[GOAL_CELL].number_format = "#,##0"
    ws[GOAL_DATE_CELL].number_format = "d mmm yyyy"
    ws["A15"], ws["A16"] = "Frequency test start", "Frequency test end"
    ws["A15"].font = ws["A16"].font = BOLD
    ws[FREQ_START_CELL].number_format = ws[FREQ_END_CELL].number_format = "d mmm yyyy"
    ws.column_dimensions["A"].width = 12
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 30


def build_dashboard(wb):
    ws = wb.create_sheet("Dashboard", 0)
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Instagram Dashboard"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = "Everything here is calculated from the Insights and Followers tabs."
    ws["A2"].font = MUTED

    I = f"Insights!$%s$2:$%s${INSIGHTS_LAST_ROW}"
    col = lambda key: get_column_letter(INSIGHT_COLS[key])
    rng = lambda key: I % (col(key), col(key))
    F = f"Followers!$B$2:$B${FOLLOWERS_LAST_ROW}"

    now = f'IFERROR(INDEX({F},COUNT({F})),0)'
    goal, goal_date = f"Settings!${GOAL_CELL[0]}${GOAL_CELL[1:]}", f"Settings!${GOAL_DATE_CELL[0]}${GOAL_DATE_CELL[1:]}"
    kpis = [
        ("Followers now", f'=IFERROR(INDEX({F},COUNT({F})),"")', "#,##0"),
        ("Follower goal", f"={goal}", "#,##0"),
        ("Progress to goal", f'=IFERROR({now}/{goal},"")', "0%"),
        ("Follows needed per day", f'=IFERROR(MAX(0,({goal}-{now})/MAX(1,{goal_date}-TODAY())),"")', "#,##0"),
        ("Avg follows per 1k reached", f'=IFERROR(AVERAGE({rng("follow_rate")}),"")', "0.0"),
        ("Posts tracked", f'=COUNTA({rng("id")})', "0"),
        ("Avg reach", f'=IFERROR(AVERAGE({rng("reach")}),"")', "#,##0"),
        ("Avg engagement rate", f'=IFERROR(AVERAGE({rng("eng_rate")}),"")', "0.0%"),
        ("Avg save rate", f'=IFERROR(AVERAGE({rng("save_rate")}),"")', "0.0%"),
        ("Avg share rate", f'=IFERROR(AVERAGE({rng("share_rate")}),"")', "0.0%"),
        ("Follows from posts", f'=SUM({rng("follows")})', "#,##0"),
        ("Best post (engagement)",
         f'=IFERROR(INDEX({rng("id")},MATCH(MAX({rng("eng_rate")}),{rng("eng_rate")},0)),"")', "@"),
    ]
    for i, (label, formula, fmt) in enumerate(kpis):
        r = 4 + i
        ws.cell(row=r, column=1, value=label).font = BOLD
        c = ws.cell(row=r, column=2, value=formula)
        c.number_format = fmt
        c.fill = SUBTLE_FILL
        c.alignment = Alignment(horizontal="right")

    # Each rate answers a different question: non-follower % = reach beyond
    # existing followers, follow rate = conversion, visit rate = curiosity,
    # save rate = practical value, comment rate = conversation, skip rate =
    # whether the opening holds (lower is better).
    columns = [
        ("Avg reach", "reach", "#,##0"),
        ("Non-follower %", "non_follower_pct", "0%"),
        ("Engagement", "eng_rate", "0.0%"),
        ("Save rate", "save_rate", "0.0%"),
        ("Share rate", "share_rate", "0.0%"),
        ("Comment rate", "comment_rate", "0.0%"),
        ("Profile visit rate", "visit_rate", "0.0%"),
        ("Follows per 1k", "follow_rate", "0.0"),
        ("Skip rate", "skip_rate", "0%"),
    ]

    def breakdown(start_row, title, key_range, keys):
        ws.cell(row=start_row, column=1, value=title).font = Font(bold=True, size=12, color=INK)
        labels = ["Posts"] + [c[0] for c in columns] + ["Total follows"]
        for j, label in enumerate(labels, start=2):
            c = ws.cell(row=start_row + 1, column=j, value=label)
            c.fill = HEADER_FILL
            c.font = WHITE_BOLD
            c.alignment = Alignment(wrap_text=True, vertical="center")
        for i, key in enumerate(keys):
            r = start_row + 2 + i
            k = f"$A{r}"
            ws.cell(row=r, column=1, value=key).font = BOLD
            guard = lambda expr: f'=IF(OR({k}="",B{r}=0),"",IFERROR({expr},""))'
            cells = [(f'=IF({k}="","",COUNTIF({key_range},{k}))', "0")]
            cells += [(guard(f'AVERAGEIF({key_range},{k},{rng(metric)})'), fmt) for _, metric, fmt in columns]
            cells.append((guard(f'SUMIF({key_range},{k},{rng("follows")})'), "#,##0"))
            for j, (formula, fmt) in enumerate(cells, start=2):
                c = ws.cell(row=r, column=j, value=formula)
                c.number_format = fmt
                c.border = BORDER

    top = 4 + len(kpis) + 1
    breakdown(top, "By format", rng("format"), FORMATS)
    # Pillar names live in Settings so they can be renamed without a rebuild.
    pillar_names = [f"=IF(Settings!D{r}=\"\",\"\",Settings!D{r})" for r in PILLAR_ROWS]
    top += 3 + len(FORMATS)
    breakdown(top, "By pillar (what the video shows)", rng("pillar"), pillar_names)
    breakdown(top + 3 + len(PILLAR_ROWS), "By caption angle", rng("angle"), pillar_names)

    ws.column_dimensions["A"].width = 24
    for j in range(2, 3 + len(columns) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 12


def build(output: Path):
    wb = Workbook()
    build_plan(wb)
    build_insights(wb)
    build_followers(wb)
    build_settings(wb)
    build_dashboard(wb)
    output.parent.mkdir(parents=True, exist_ok=True)
    wb.save(output)
    return output


def main():
    ap = argparse.ArgumentParser(description="Build the Instagram content tracker workbook.")
    ap.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT))
    ap.add_argument("--refresh-formulas", action="store_true",
                    help="Rewrite Insights formulas in the existing file (keeps all data)")
    ap.add_argument("--migrate", action="store_true",
                    help="Move the existing file onto the current column layout (keeps all data)")
    args = ap.parse_args()
    out = Path(args.output).expanduser()
    if args.migrate:
        copied = migrate(out)
        print(f"Migrated {out} — rows carried over: {copied}")
        return
    if args.refresh_formulas:
        refresh_formulas(out)
        print(f"Refreshed Insights formulas in {out}")
        return
    if out.exists():
        raise SystemExit(f"{out} already exists — refusing to overwrite a live tracker. Pass -o for a new path.")
    print(f"Built {build(out)}")


if __name__ == "__main__":
    main()
