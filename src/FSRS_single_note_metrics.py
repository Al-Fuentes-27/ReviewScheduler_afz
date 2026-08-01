"""
Here is a plain and simple breakdown of every section and function in the script:

| Location                               | What it does |
| **Imports**                            | Loads standard tools for reading files, parsing data, and doing date math. |
| **`load_config()`**                    | Reads your settings from `config.json` and stops the script if the file is missing. |
| **`resolve_paths()`**                  | Chooses the correct file folders based on whether you are running in "test" or "production" mode. |
| **`load_log()`**                       | Reads your main review history CSV file. |
| **`load_edits()`**                     | Reads your note edit history CSV file (safely returns empty if the file doesn't exist yet). |
| **`group_rows_by_note()`**             | Sorts your review history into separate lists for each individual note. |
| **`group_edits_by_note()`**            | Sorts your edit history into separate lists for each individual note. |
| **`sanitize_filename()`**              | Cleans up note titles (removes bad characters) so they can be safely saved as HTML file names. |
| **`parse_date_flexible()`**            | Reads dates in multiple formats and converts them into a standard format the script can understand. |
| **`compute_note_summary()`**           | Calculates the big-picture stats for a single note (retention, stability, difficulty, lapses, time spent). |
| `compute_note_stability_trajectory()`  | Extracts the "stability" score from every review to draw the stability line chart. |
| `compute_note_difficulty_trajectory()` | Extracts the "difficulty" score from every review to draw the difficulty line chart. |
| `compute_note_grade_distribution()`    | Counts how many times you clicked Again, Hard, Good, or Easy to draw the donut chart. |
| **`compute_note_r_distribution()`**    | Groups your "Retrievability" scores into buckets to draw the histogram bar chart. |
| **`compute_note_review_timeline()`**   | Builds the detailed, row-by-row data for the history table at the bottom of the dashboard. |
| **`compute_note_time_trajectory()`**   | Extracts how many minutes you spent on each review to draw the time-spent bar chart. |
| **`compute_edit_events()`**            | Calculates exactly where note edits happened so they can be drawn as vertical lines on charts and dividers in the table. |
| **`build_note_html()`**                | Generates the entire visual HTML dashboard (styling, layout, and Chart.js graphs) for a single note. |
| **`print_section()`**                  | Prints a clean, formatted divider line in your terminal. |
| **`print_note_summary()`**             | Prints a quick text summary of a note's stats in the terminal while the script is running. |
| **`main()`**                           | The master controller: loads all data, processes every note, saves the HTML files, and automatically opens your most-lapsed note in the browser. |
"""

#!/usr/bin/env python3
import re
import csv
import json
import webbrowser
from pathlib import Path
from collections import defaultdict
from datetime import datetime



# ===== CONFIGURATION =====

def load_config(config_file: Path) -> dict:
    """Load configuration from config.json. Exit if not found."""
    if not config_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found!\n"
            f"Expected location: {config_file}\n"
            f"Please copy 'config.example.json' to 'config.json' and edit it."
        )
    with open(config_file, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_paths(config: dict) -> dict:
    """Apply test/production mode path switching."""
    mode = config.get("mode", "production")
    resolved = dict(config)
    if mode == "test":
        test = config.get("testing_FSRS_metrics", {})
        if not test:
            raise ValueError(
                "mode is 'test' but 'testing_FSRS_metrics' block is missing from config.json"
            )
        resolved["log_path"]     = test["log_path"]
        resolved["edits_path"]   = test["edits_path"]
        resolved["metrics_path"] = test["metrics_path"]
        print("Running in TEST mode — using test log and metrics paths.")
    else:
        print("Running in PRODUCTION mode.")
    return resolved


# ===== DATA LOADING =====

def load_log(log_path: Path) -> list:
    if not log_path.exists():
        print("No review log found yet. Run the main review script first.")
        return []
    with open(log_path, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("Log file is empty.")
    return rows


def load_edits(edits_path: Path) -> list:
    """Load note edit events from note_edits.csv. Returns [] if file missing."""
    if not edits_path.exists():
        return []
    with open(edits_path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def group_rows_by_note(rows: list) -> dict:
    """Return {note_name: [rows...]} preserving chronological order."""
    groups = defaultdict(list)
    for r in rows:
        groups[r['note']].append(r)
    return dict(groups)


def group_edits_by_note(edit_rows: list) -> dict:
    """Return {note_name: [edit_rows...]} preserving chronological order."""
    groups = defaultdict(list)
    for e in edit_rows:
        groups[e['note']].append(e)
    return dict(groups)


def sanitize_filename(note_name: str) -> str:
    """Convert a note name to a safe filename (no extension)."""
    name = note_name.replace('.md', '')
    safe = re.sub(r'[<>:"/\\|?*\u2014\u2013]', '_', name)
    safe = re.sub(r'[\s_]+', '_', safe).strip('_')
    return safe[:80]


# ===== DATE HELPERS =====

def parse_date_flexible(date_str: str):
    """
    Parse dates in either YYYY-MM-DD or DD/MM/YYYY format.
    The review_log.csv contains both formats across its history.
    Returns a date object, or None if unparseable.
    """
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    return None


# ===== PER-NOTE METRIC COMPUTATIONS =====

def compute_note_summary(rows: list) -> dict:
    """
    Five stat-card values for a single note.
    retention_rate is None when the note has only been reviewed once.
    current_stability and current_difficulty reflect the most recent review.
    """
    non_new = [r for r in rows if r['R_at_review'] != 'new']
    passed  = [r for r in non_new if r['grade'] != 'again']
    retention = round(len(passed) / len(non_new) * 100, 1) if non_new else None

    last         = rows[-1]
    total_lapses = sum(1 for r in rows if r['grade'] == 'again')

    times = [
        float(r['review_time'])
        for r in rows
        if r.get('review_time', '') not in ('', None)
    ]
    avg_time   = round(sum(times) / len(times), 1) if times else None
    total_time = round(sum(times), 1)              if times else None

    return {
        'total_reviews':      len(rows),
        'retention_rate':     retention,
        'current_stability':  round(float(last['new_stability']), 1),
        'current_difficulty': round(float(last['new_difficulty']), 2),
        'total_lapses':       total_lapses,
        'last_reviewed':      last['date'],
        'avg_review_time':    avg_time,
        'total_review_time':  total_time,
    }


def compute_note_stability_trajectory(rows: list) -> list:
    """
    Actual stability value at each review — not an average.
    Each point carries its grade so the chart can color it accordingly:
    again → red   hard → amber   good → green   easy → blue
    """
    return [
        {
            'review_n':  i + 1,
            'stability': round(float(r['new_stability']), 1),
            'grade':     r['grade'],
            'date':      r['date'],
        }
        for i, r in enumerate(rows)
    ]


def compute_note_difficulty_trajectory(rows: list) -> list:
    """
    Actual difficulty value at each review — not an average.
    Difficulty should converge and stabilize. Continued rise signals
    the note needs rewriting, not more reviewing.
    """
    return [
        {
            'review_n':   i + 1,
            'difficulty': round(float(r['new_difficulty']), 2),
            'grade':      r['grade'],
        }
        for i, r in enumerate(rows)
    ]


def compute_note_grade_distribution(rows: list) -> list:
    """Grade counts and percentages for this note only."""
    counts = defaultdict(int)
    for r in rows:
        counts[r['grade']] += 1
    total = sum(counts.values())
    return [
        {
            'grade': g,
            'count': counts.get(g, 0),
            'pct':   round(counts.get(g, 0) / total * 100, 1) if total else 0,
        }
        for g in ['again', 'hard', 'good', 'easy']
    ]


def compute_note_r_distribution(rows: list) -> list:
    """
    Histogram of retrievability at review time for this note.
    First reviews (R_at_review == 'new') are excluded.
    With few reviews the histogram will be sparse — that is expected.
    """
    buckets = ['0.0–0.2', '0.2–0.4', '0.4–0.6', '0.6–0.8', '0.8–1.0']
    counts  = [0, 0, 0, 0, 0]
    for r in rows:
        if r['R_at_review'] == 'new':
            continue
        try:
            val = float(r['R_at_review'])
            idx = min(int(val / 0.2), 4)
            counts[idx] += 1
        except ValueError:
            continue
    return [{'bucket': b, 'count': c} for b, c in zip(buckets, counts)]


def compute_note_review_timeline(rows: list) -> list:
    """
    Full review history — one row per review event.
    This is the most actionable per-note output:
    you can see exactly when each grade occurred, what R was,
    and how stability and difficulty evolved as a result.
    """
    result = []
    for i, r in enumerate(rows):
        t = r.get('review_time', '')
        result.append({
            'review_n':      i + 1,
            'date':          r['date'],
            'grade':         r['grade'],
            'elapsed':       int(r['elapsed']),
            'R_at_review':   r['R_at_review'],
            'stability':     round(float(r['new_stability']), 1),
            'difficulty':    round(float(r['new_difficulty']), 2),
            'review_time': round(float(t), 1) if t and t != '' else None,
        })
    return result


def compute_note_time_trajectory(rows: list) -> list:
    """
    Review time in minutes at each review.
    None for reviews where time was not recorded (older log entries).
    """
    result = []
    for i, r in enumerate(rows):
        t = r.get('review_time', '')
        result.append({
            'review_n': i + 1,
            'time_min': round(float(t), 1) if t and t != '' else None,
            'grade':    r['grade'],
            'date':     r['date'],
        })
    return result


def compute_edit_events(note_rows: list, edit_rows: list) -> list:
    """
    For each edit event belonging to this note, determine its position
    in the review timeline so the dashboard can:
      - draw a vertical annotation line on the charts (x_position)
      - inject an epoch-divider row in the timeline table (before_review_n)

    x_position is a fractional 0-indexed value for Chart.js category scale:
      between R4 (index 3) and R5 (index 4) → x_position = 3.5

    before_review_n is the 1-indexed review number whose table row
    should be preceded by the edit divider.
    """
    if not edit_rows:
        return []

    # Build (parsed_date, 0-based_index, 1-based_review_n) for each review
    review_dates = []
    for i, r in enumerate(note_rows):
        parsed = parse_date_flexible(r['date'])
        review_dates.append((parsed, i, i + 1))

    events = []
    for edit in edit_rows:
        edit_date = parse_date_flexible(edit['date'])
        if edit_date is None:
            continue

        x_position = None
        before_review_n = None

        for parsed, idx, rn in review_dates:
            if parsed is None:
                continue
            
            #
            if edit_date <= parsed:
                # Edit falls before this review
                if idx == 0:
                    x_position = -0.5   # before the very first review
                else:
                    x_position = (idx - 1) + 0.5  # between previous and this
                before_review_n = rn
                break

        if x_position is None:
            # Edit is after all reviews
            x_position = len(review_dates) - 0.5
            before_review_n = len(review_dates) + 1

        events.append({
            'date':            edit['date'],
            'edit_type':       edit['edit_type'],
            'description':     edit.get('description', ''),
            'x_position':      x_position,
            'before_review_n': before_review_n,
        })

    return events


# ===== HTML GENERATION =====

def build_note_html(note_name: str,
                    summary: dict,
                    stability_traj: list,
                    difficulty_traj: list,
                    time_traj: list,
                    grade_dist: list,
                    r_dist: list,
                    timeline: list,
                    edit_events: list) -> str:

    display_name = note_name.replace('.md', '')
    retention_display = (
        f"{summary['retention_rate']}%"
        if summary['retention_rate'] is not None
        else "n/a — only 1 review"
    )

    total_edits = len(edit_events)

    data_js = f"""
    const noteName        = {json.dumps(display_name)};
    const summaryData     = {json.dumps(summary)};
    const stabilityData   = {json.dumps(stability_traj)};
    const difficultyData  = {json.dumps(difficulty_traj)};
    const timeData        = {json.dumps(time_traj)};
    const gradeData       = {json.dumps(grade_dist)};
    const rDistData       = {json.dumps(r_dist)};
    const timelineData    = {json.dumps(timeline)};
    const editEvents      = {json.dumps(edit_events)};
    const totalEdits      = {json.dumps(total_edits)};
    const retentionDisplay = {json.dumps(retention_display)};
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Note metrics — {display_name}</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
<!-- Chart.js Annotation Plugin for Vertical Lines -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/chartjs-plugin-annotation/3.0.1/chartjs-plugin-annotation.min.js"></script>
<style>
:root {{
    --bg:       #f8f8f6;
    --surface:  #ffffff;
    --surface2: #f1f0eb;
    --text:     #1a1a18;
    --muted:    #6b6b67;
    --border:   rgba(0,0,0,0.1);
    --green:    #1D9E75;
    --blue:     #378ADD;
    --amber:    #EF9F27;
    --red:      #E24B4A;
    --purple:   #7F77DD;
    --magenta:  #D946EF;
    --radius:   10px;
}}
@media (prefers-color-scheme: dark) {{
    :root {{
        --bg:      #1a1a18;
        --surface: #242422;
        --surface2:#2e2e2c;
        --text:    #f0efe8;
        --muted:   #9a9a94;
        --border:  rgba(255,255,255,0.1);
        --magenta: #E879F9;
    }}
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 2rem;
    line-height: 1.5;
}}
h1 {{ font-size: 18px; font-weight: 500; margin-bottom: 0.2rem; }}
.subtitle {{ font-size: 12px; color: var(--muted); margin-bottom: 2rem; }}
.stat-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 12px;
    margin-bottom: 1.5rem;
}}
.stat-card {{
    background: var(--surface);
    border: 0.5px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem;
}}
.stat-label {{ font-size: 12px; color: var(--muted); margin-bottom: 4px; }}
.stat-value {{ font-size: 20px; font-weight: 500; }}
.chart-grid-2 {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: 16px;
    margin-bottom: 16px;
}}
.chart-grid-22 {{
    display: grid;
    grid-template-columns: minmax(0,2fr) minmax(0,1fr);
    gap: 16px;
    margin-bottom: 16px;
}}
.chart-card {{
    background: var(--surface);
    border: 0.5px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
}}
.chart-title {{ font-size: 13px; color: var(--muted); margin-bottom: 10px; }}
.chart-wrap {{ position: relative; width: 100%; }}
.target-note {{ font-size: 11px; color: var(--muted); margin-top: 6px; }}
.legend {{
    display: flex; flex-wrap: wrap; gap: 10px;
    margin-bottom: 8px; font-size: 12px; color: var(--muted);
}}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-dot {{
    width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0;
}}
.status-ok  {{ color: var(--green); }}
.status-bad {{ color: var(--red); }}
.no-data {{
    font-size: 13px; color: var(--muted);
    padding: 2rem 0; text-align: center;
}}
/* ── Review timeline table ── */
.timeline-wrap {{ overflow-x: auto; }}
table {{
    width: 100%; border-collapse: collapse;
    font-size: 13px;
}}
th {{
    font-size: 11px; color: var(--muted);
    text-align: left; padding: 6px 14px;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}}
td {{
    padding: 9px 14px;
    border-bottom: 0.5px solid var(--border);
    white-space: nowrap;
}}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: var(--surface2); }}
.badge {{
    display: inline-block;
    padding: 2px 9px; border-radius: 4px;
    font-size: 11px; font-weight: 500;
    color: #fff;
}}
.badge-again  {{ background: #E24B4A; }}
.badge-hard   {{ background: #EF9F27; color: #1a1a18; }}
.badge-good   {{ background: #1D9E75; }}
.badge-easy   {{ background: #378ADD; }}
.lapse-flag   {{ font-size: 11px; color: var(--red); margin-left: 4px; }}
/* ── Edit Divider Row Styles (Magenta/Fuchsia Theme) ── */
.edit-divider-row td {{
    background: rgba(217, 70, 239, 0.08);
    color: #C026D3;
    text-align: center;
    font-size: 12px;
    font-weight: 500;
    padding: 12px 14px;
    border-bottom: 1px dashed var(--magenta);
    letter-spacing: 0.5px;
}}
.edit-divider-row:hover td {{ background: rgba(217, 70, 239, 0.15); }}
.edit-badge {{
    display: inline-block;
    background: var(--magenta);
    color: #1a1a18;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    margin-right: 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}
@media (prefers-color-scheme: dark) {{
    .edit-divider-row td {{
        background: rgba(232, 121, 249, 0.1);
        color: #E879F9;
    }}
    .edit-divider-row:hover td {{ background: rgba(232, 121, 249, 0.15); }}
    .edit-badge {{
        background: #C026D3;
        color: #ffffff;
    }}
}}
/* ── Edit History Section ── */
.edit-history-list {{
    display: flex;
    flex-direction: column;
    gap: 10px;
}}
.edit-entry {{
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 12px;
    background: rgba(217, 70, 239, 0.05);
    border-left: 3px solid var(--magenta);
    border-radius: 6px;
    font-size: 13px;
}}
@media (prefers-color-scheme: dark) {{
    .edit-entry {{ background: rgba(232, 121, 249, 0.07); }}
}}
.edit-entry .edit-badge {{
    display: inline-block;
    background: var(--magenta);
    color: #1a1a18;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 2px;
}}
@media (prefers-color-scheme: dark) {{
    .edit-entry .edit-badge {{ background: #C026D3; color: #ffffff; }}
}}
.edit-entry .edit-date {{
    color: var(--muted);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    flex-shrink: 0;
    margin-top: 2px;
}}
.edit-entry .edit-desc {{
    position: relative;
    color: var(--text);
    cursor: help;
    flex: 1;
}}
.edit-entry .edit-desc:hover {{ text-decoration: underline dotted var(--magenta); }}
.edit-entry .edit-desc::after {{
    content: attr(data-full);
    position: absolute;
    bottom: calc(100% + 8px);
    left: 0;
    min-width: 280px;
    max-width: 520px;
    padding: 10px 12px;
    background: #1a1a18;
    color: #f0efe8;
    font-size: 12px;
    line-height: 1.5;
    white-space: pre-wrap;
    border-radius: 6px;
    border: 1px solid var(--magenta);
    box-shadow: 0 6px 20px rgba(0,0,0,0.25);
    opacity: 0;
    pointer-events: none;
    transform: translateY(4px);
    transition: opacity 0.15s ease, transform 0.15s ease;
    z-index: 100;
}}
.edit-entry .edit-desc:hover::after {{
    opacity: 1;
    transform: translateY(0);
}}
</style>
</head>
<body>

<h1 id="note-title">Loading…</h1>
<div class="subtitle" id="subtitle">Loading…</div>

<!-- ── Stat cards ── -->
<div class="stat-grid">
    <div class="stat-card">
        <div class="stat-label">Total reviews</div>
        <div class="stat-value" id="s-total">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Retention rate</div>
        <div class="stat-value" id="s-retention">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Current stability</div>
        <div class="stat-value" id="s-stability">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Current difficulty</div>
        <div class="stat-value" id="s-difficulty">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Total lapses</div>
        <div class="stat-value" id="s-lapses">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Total Edits</div>
        <div class="stat-value" id="s-edits" style="color: var(--magenta);">—</div>
    </div>
    <div class="stat-card">
        <div class="stat-label">Avg review time</div>
        <div class="stat-value" id="s-time">—</div>
    </div>
</div>

<!-- ── Row 1: stability trajectory (wide) + grade donut ── -->
<div class="chart-grid-22" style="margin-bottom:16px">
    <div class="chart-card">
        <div class="chart-title">Stability trajectory — actual value at each review</div>
        <div class="legend">
            <span class="legend-item">
                <span class="legend-dot" style="background:#E24B4A"></span>again
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background:#EF9F27"></span>hard
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background:#1D9E75"></span>good
            </span>
            <span class="legend-item">
                <span class="legend-dot" style="background:#378ADD"></span>easy
            </span>
        </div>
        <div class="chart-wrap" style="height:210px">
            <canvas id="c-stability"
                    role="img" aria-label="Stability value at each review, colored by grade">
                Stability trajectory.
            </canvas>
        </div>
        <div class="target-note">
            Points colored by grade. Dashed magenta line = note rewrite. A drop after the line = expected reset.
        </div>
    </div>
    <div class="chart-card">
        <div class="chart-title">Grade distribution</div>
        <div class="legend" id="grade-legend"></div>
        <div class="chart-wrap" style="height:180px">
            <canvas id="c-grade"
                    role="img" aria-label="Donut chart of grade distribution for this note">
                Grade breakdown.
            </canvas>
        </div>
    </div>
</div>

<!-- ── Row 2: difficulty trajectory + R distribution ── -->
<div class="chart-grid-2" style="margin-bottom:16px">
    <div class="chart-card">
        <div class="chart-title">Difficulty trajectory — actual value at each review</div>
        <div class="chart-wrap" style="height:190px">
            <canvas id="c-difficulty"
                    role="img" aria-label="Difficulty value at each review">
                Difficulty trajectory.
            </canvas>
        </div>
        <div class="target-note">
            Dashed line = neutral 5.5. Rising past 8 with repeated lapses → rewrite the note.
        </div>
    </div>
    <div class="chart-card">
        <div class="chart-title">Retrievability at review time</div>
        <div class="chart-wrap" style="height:190px">
            <canvas id="c-rdist"
                    role="img" aria-label="Histogram of R values at time of review">
                R distribution.
            </canvas>
        </div>
        <div class="target-note">
            Healthy: reviews clustered in 0.8–1.0. Spread left = reviewing late or irregularly.
        </div>
    </div>
</div>

<!-- ── Time per review chart ── -->
<div class="chart-card" style="margin-bottom:16px">
    <div class="chart-title">Review time per session (minutes)</div>
    <div class="chart-wrap" style="height:160px">
        <canvas id="c-time"
                role="img" aria-label="Bar chart of review time in minutes per review session">
            Review time per session.
        </canvas>
    </div>
    <div class="target-note">
        Bar colored by grade. Missing bars = time not recorded for that session.
    </div>
</div>

<!-- ── Review timeline table ── -->
<div class="chart-card">
    <div class="chart-title">
        Full review history — every review event for this note
    </div>
    <div class="timeline-wrap">
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Date</th>
                    <th>Grade</th>
                    <th>Days since last</th>
                    <th>R at review</th>
                    <th>Stability after</th>
                    <th>Difficulty after</th>
                    <th>Time (min)</th>
                </tr>
            </thead>
            <tbody id="timeline-body"></tbody>
        </table>
    </div>
</div>

<!-- ── Edit History Section ── -->
<div class="chart-card" id="edit-history-card" style="display:none; margin-top:16px">
    <div class="chart-title">Edit history — all content changes to this note</div>
    <div class="edit-history-list" id="edit-history-list"></div>
    <div class="target-note">
        Hover over a description to reveal the full text. Each entry matches a magenta divider in the timeline above.
    </div>
</div>

<script>
{data_js}

const isDark  = matchMedia('(prefers-color-scheme: dark)').matches;
const MAGENTA = isDark ? '#E879F9' : '#D946EF';
const textClr = isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)';
const gridClr = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
const GREEN  = '#1D9E75';
const BLUE   = '#378ADD';
const AMBER  = '#EF9F27';
const RED    = '#E24B4A';
const PURPLE = '#7F77DD';
const gradeColor = {{ again: RED, hard: AMBER, good: GREEN, easy: BLUE }};

const baseScale = {{
    x: {{ ticks: {{ color: textClr, font: {{ size: 11 }} }}, grid: {{ color: gridClr }} }},
    y: {{ ticks: {{ color: textClr, font: {{ size: 11 }} }}, grid: {{ color: gridClr }} }}
}};
const baseOpts = {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: baseScale
}};

// ── Build annotation objects dynamically from edit events ────────────────────
const editAnnotations = {{}};
editEvents.forEach((ev, i) => {{
    editAnnotations['editLine' + i] = {{
        type: 'line',
        xMin: ev.x_position, xMax: ev.x_position,
        borderColor: MAGENTA,
        borderWidth: 2,
        borderDash: [6, 4],
        label: {{
            display: true,
            content: '✏️ ' + ev.edit_type.replace(/_/g, ' '),
            position: 'start',
            backgroundColor: MAGENTA,
            color: isDark ? '#ffffff' : '#1a1a18',
            font: {{ size: 10, weight: 'bold' }},
            padding: 4,
            borderRadius: 4
        }}
    }};
}});
const hasEdits = editEvents.length > 0;
const annotationPlugin = hasEdits
    ? {{ annotation: {{ annotations: editAnnotations }} }}
    : {{}};

// ── Header ───────────────────────────────────────────────────────────────────
document.getElementById('note-title').textContent = noteName;
document.getElementById('subtitle').textContent =
    summaryData.total_reviews + ' reviews  ·  last reviewed ' +
    summaryData.last_reviewed;

// ── Stat cards ───────────────────────────────────────────────────────────────
document.getElementById('s-total').textContent     = summaryData.total_reviews;
document.getElementById('s-stability').textContent = summaryData.current_stability + 'd';
document.getElementById('s-difficulty').textContent = summaryData.current_difficulty;
document.getElementById('s-lapses').textContent    = summaryData.total_lapses;
document.getElementById('s-edits').textContent     = totalEdits;

const timeEl = document.getElementById('s-time');
if (summaryData.avg_review_time !== null && summaryData.avg_review_time !== undefined) {{
    timeEl.textContent = summaryData.avg_review_time + ' min';
}} else {{
    timeEl.textContent = '—';
    timeEl.style.color = 'var(--muted)';
}}

const retEl = document.getElementById('s-retention');
retEl.textContent = retentionDisplay;
if (summaryData.retention_rate !== null) {{
    retEl.className = 'stat-value ' +
        (summaryData.retention_rate >= 88 ? 'status-ok' : 'status-bad');
}}

// ── Stability trajectory ──────────────────────────────────────────────────────
new Chart(document.getElementById('c-stability'), {{
    type: 'line',
    data: {{
        labels: stabilityData.map(d => 'R' + d.review_n + '  ' + d.date),
        datasets: [{{
            label: 'Stability (days)',
            data: stabilityData.map(d => d.stability),
            borderColor: GREEN,
            backgroundColor: 'rgba(29,158,117,0.07)',
            fill: true,
            tension: 0.25,
            pointRadius: 6,
            pointHoverRadius: 8,
            pointBackgroundColor: stabilityData.map(d => gradeColor[d.grade]),
            pointBorderColor: stabilityData.map(d => gradeColor[d.grade]),
        }}]
    }},
    options: {{
        ...baseOpts,
        scales: {{
            x: {{ ticks: {{ color: textClr, font: {{ size: 10 }}, maxRotation: 30 }}, grid: {{ color: gridClr }} }},
            y: {{ ticks: {{ color: textClr, font: {{ size: 11 }}, callback: v => v + 'd' }}, grid: {{ color: gridClr }} }}
        }},
        plugins: {{
            legend: {{ display: false }},
            ...annotationPlugin,
            tooltip: {{
                callbacks: {{
                    label: ctx => {{
                        const d = stabilityData[ctx.dataIndex];
                        return [
                            'Stability: ' + d.stability + 'd',
                            'Grade: ' + d.grade,
                        ];
                    }}
                }}
            }}
        }}
    }}
}});

// ── Grade distribution ────────────────────────────────────────────────────────
const legendEl = document.getElementById('grade-legend');
gradeData.forEach(g => {{
    if (g.count === 0) return;
    legendEl.innerHTML +=
        '<span class="legend-item">' +
        '<span class="legend-dot" style="background:' + gradeColor[g.grade] + '"></span>' +
        g.grade + ' ' + g.pct + '%</span>';
}});

new Chart(document.getElementById('c-grade'), {{
    type: 'doughnut',
    data: {{
        labels: gradeData.map(g => g.grade),
        datasets: [{{
            data: gradeData.map(g => g.count),
            backgroundColor: gradeData.map(g => gradeColor[g.grade]),
            borderWidth: 0,
            hoverOffset: 6
        }}]
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ display: false }} }},
        cutout: '60%'
    }}
}});

// ── Difficulty trajectory ─────────────────────────────────────────────────────
new Chart(document.getElementById('c-difficulty'), {{
    type: 'line',
    data: {{
        labels: difficultyData.map(d => 'R' + d.review_n),
        datasets: [
            {{
                label: 'Difficulty',
                data: difficultyData.map(d => d.difficulty),
                borderColor: PURPLE,
                backgroundColor: 'rgba(127,119,221,0.07)',
                fill: true,
                tension: 0.25,
                pointRadius: 5,
                pointHoverRadius: 7,
                pointBackgroundColor: difficultyData.map(d => gradeColor[d.grade]),
                pointBorderColor: difficultyData.map(d => gradeColor[d.grade]),
            }},
            {{
                label: 'Neutral 5.5',
                data: difficultyData.map(() => 5.5),
                borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.15)',
                borderDash: [5, 4],
                pointRadius: 0,
                fill: false,
            }}
        ]
    }},
    options: {{
        ...baseOpts,
        scales: {{
            x: baseScale.x,
            y: {{
                min: 1, max: 10,
                ticks: {{ color: textClr, font: {{ size: 11 }} }},
                grid: {{ color: gridClr }}
            }}
        }},
        plugins: {{
            ...baseOpts.plugins,
            ...annotationPlugin
        }}
    }}
}});

// ── R distribution ────────────────────────────────────────────────────────────
const rColors = [RED, AMBER, AMBER, GREEN, BLUE];
new Chart(document.getElementById('c-rdist'), {{
    type: 'bar',
    data: {{
        labels: rDistData.map(d => d.bucket),
        datasets: [{{
            label: 'Reviews',
            data: rDistData.map(d => d.count),
            backgroundColor: rColors,
            borderRadius: 4,
        }}]
    }},
    options: {{
        ...baseOpts,
        scales: {{
            x: {{ ticks: {{ color: textClr, font: {{ size: 11 }}, autoSkip: false }}, grid: {{ color: gridClr }} }},
            y: {{
                ticks: {{ color: textClr, font: {{ size: 11 }}, stepSize: 1 }},
                grid: {{ color: gridClr }}
            }}
        }}
    }}
}});

// ── Time per review chart ───────────────────────────────────────────────────────
const hasTimeData = timeData.some(d => d.time_min !== null);
if (hasTimeData) {{
    new Chart(document.getElementById('c-time'), {{
        type: 'bar',
        data: {{
            labels: timeData.map(d => 'R' + d.review_n + ' ' + d.date),
            datasets: [{{
                label: 'Time (min)',
                data: timeData.map(d => d.time_min),
                backgroundColor: timeData.map(d => gradeColor[d.grade]),
                borderRadius: 4,
            }}]
        }},
        options: {{
            ...baseOpts,
            scales: {{
                x: {{ ticks: {{ color: textClr, font: {{ size: 10 }}, maxRotation: 30 }}, grid: {{ color: gridClr }} }},
                y: {{
                    min: 0,
                    ticks: {{ color: textClr, font: {{ size: 11 }}, callback: v => v + ' min' }},
                    grid: {{ color: gridClr }}
                }}
            }},
            plugins: {{
                legend: {{ display: false }},
                ...annotationPlugin,
                tooltip: {{
                    callbacks: {{
                        label: ctx => {{
                            const d = timeData[ctx.dataIndex];
                            return d.time_min !== null
                                ? ['Time: ' + d.time_min + ' min', 'Grade: ' + d.grade]
                                : ['Time: not recorded'];
                        }}
                    }}
                }}
            }}
        }}
    }});
}} else {{
    document.getElementById('c-time').parentElement.innerHTML =
        '<div class="no-data">No review time recorded yet — enter minutes after each grade.</div>';
}}

// ── Review timeline table ─────────────────────────────────────────────────────
const tbody = document.getElementById('timeline-body');
timelineData.forEach(r => {{
    // Inject edit epoch-dividers before the appropriate review row
    editEvents.forEach(ev => {{
        if (ev.before_review_n === r.review_n) {{
            const typeLabel = ev.edit_type.replace(/_/g, ' ').toUpperCase();
            tbody.innerHTML +=
                '<tr class="edit-divider-row">' +
                '<td colspan="8">' +
                '<span class="edit-badge">✏️ ' + typeLabel + '</span>' +
                ev.date +
                '</td></tr>';
        }}
    }});

    const isFirst = r.R_at_review === 'new';
    const isLapse = r.grade === 'again' && !isFirst;
    const rDisplay = isFirst ? '— first review' : r.R_at_review;
    const elapsedDisplay = r.review_n === 1 ? '—' : r.elapsed + 'd';
    const lapseFlag = isLapse ? '<span class="lapse-flag">⚠ lapse</span>' : '';
    const timeDisplay = (r.review_time !== null && r.review_time !== undefined)
        ? r.review_time + ' min'
        : '—';

    tbody.innerHTML +=
        '<tr>' +
        '<td style="color:var(--muted)">' + r.review_n + '</td>' +
        '<td>' + r.date + '</td>' +
        '<td>' +
            '<span class="badge badge-' + r.grade + '">' + r.grade + '</span>' +
            lapseFlag +
        '</td>' +
        '<td>' + elapsedDisplay + '</td>' +
        '<td>' + rDisplay + '</td>' +
        '<td>' + r.stability + 'd</td>' +
        '<td>' + r.difficulty + '</td>' +
        '<td>' + timeDisplay + '</td>' +
        '</tr>';
}});

// ── Edit History Section ─────────────────────────────────────────────────────
if (editEvents.length > 0) {{
    const editHistoryCard = document.getElementById('edit-history-card');
    const editHistoryList = document.getElementById('edit-history-list');
    editHistoryCard.style.display = 'block';
    
    editEvents.forEach(ev => {{
        const typeLabel = ev.edit_type.replace(/_/g, ' ').toUpperCase();
        const maxLen = 160;
        const shortDesc = ev.description && ev.description.length > maxLen
            ? ev.description.slice(0, maxLen).trim() + '…'
            : (ev.description || '');
        const fullDesc = (ev.description || '').replace(/"/g, '&quot;');
        
        editHistoryList.innerHTML +=
            '<div class="edit-entry">' +
                '<span class="edit-badge">✏️ ' + typeLabel + '</span>' +
                '<span class="edit-date">' + ev.date + '</span>' +
                '<span class="edit-desc" data-full="' + fullDesc + '">' + shortDesc + '</span>' +
            '</div>';
    }});
}}
</script>
</body>
</html>"""

    return html


# ===== TERMINAL OUTPUT =====

def print_section(title: str):
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def print_note_summary(note_name: str, summary: dict, out_path: Path,
                       edit_count: int):
    retention = (
        f"{summary['retention_rate']}%"
        if summary['retention_rate'] is not None
        else "n/a"
    )
    retention_flag = ""
    if summary['retention_rate'] is not None and summary['retention_rate'] < 88:
        retention_flag = "  ✗"
    lapse_flag = "  ⚠  rewrite this note" if summary['total_lapses'] >= 3 else ""
    edit_flag  = f"  ✏️ {edit_count} edit(s)" if edit_count > 0 else ""

    print(f"\n{note_name.replace('.md','')}")
    print(f"    Reviews    : {summary['total_reviews']}")
    print(f"    Retention  : {retention}{retention_flag}")
    print(f"    Stability  : {summary['current_stability']}d")
    print(f"    Difficulty : {summary['current_difficulty']}")
    print(f"    Lapses     : {summary['total_lapses']}{lapse_flag}")
    print(f"    Edits      : {edit_count}{edit_flag}")
    if summary['avg_review_time'] is not None:
        print(f"    Avg time   : {summary['avg_review_time']} min  "
              f"(total: {summary['total_review_time']} min)")
    print(f"    Saved to   : {out_path.name}")








# ===== MAIN =====

def main():
    config_path = Path(r"..\data\config.json")
    config      = load_config(config_path)
    config      = resolve_paths(config)

    rows = load_log(Path(config["log_path"]))
    if not rows:
        return
    print(f"Loaded {len(rows)} review events.")

    # Load note edit events (separate CSV, may not exist yet)
    edit_rows = load_edits(Path(config["edits_path"]))
    print(f"Loaded {len(edit_rows)} edit events.")

    # Output directory: sibling folder next to the main metrics HTML
    metrics_dir = Path(config["metrics_path"]).parent / "note_reports"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    print(f"Note reports directory: {metrics_dir.resolve()}")

    note_groups = group_rows_by_note(rows)
    edit_groups = group_edits_by_note(edit_rows)
    print(f"Found {len(note_groups)} unique notes in log.")

    print_section(f"Generating {len(note_groups)} note reports")

    generated = []
    for note_name, note_rows in sorted(note_groups.items()):
        summary         = compute_note_summary(note_rows)
        stability_traj  = compute_note_stability_trajectory(note_rows)
        difficulty_traj = compute_note_difficulty_trajectory(note_rows)
        time_traj       = compute_note_time_trajectory(note_rows)
        grade_dist      = compute_note_grade_distribution(note_rows)
        r_dist          = compute_note_r_distribution(note_rows)
        timeline        = compute_note_review_timeline(note_rows)

        # Compute edit positions for this specific note
        note_edits  = edit_groups.get(note_name, [])
        edit_events = compute_edit_events(note_rows, note_edits)

        html      = build_note_html(
            note_name, summary, stability_traj,
            difficulty_traj, time_traj, grade_dist, r_dist, timeline,
            edit_events
        )

        safe_name = sanitize_filename(note_name)
        out_path  = metrics_dir / f"{safe_name}.html"
        out_path.write_text(html, encoding='utf-8')

        print_note_summary(note_name, summary, out_path, len(edit_events))
        generated.append(out_path)

    print_section("Done")
    print(f"  Generated {len(generated)} note reports.")
    print(f"  Location: {metrics_dir.resolve()}")

    # Open the report for the note with the most lapses
    most_lapsed = max(
        note_groups.items(),
        key=lambda kv: sum(1 for r in kv[1] if r['grade'] == 'again')
    )
    safe      = sanitize_filename(most_lapsed[0])
    highlight = metrics_dir / f"{safe}.html"
    print(f"\nOpening most-lapsed note: {most_lapsed[0].replace('.md','')}")
    webbrowser.open(highlight.resolve().as_uri())





if __name__ == "__main__":
    main()