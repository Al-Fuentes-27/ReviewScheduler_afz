#!/usr/bin/env python3
import csv
import json
import webbrowser
from pathlib import Path
from collections import defaultdict




# ===== CONFIGURATION =====

def load_config(CONFIG_FILE):
    """Load configuration from config.json. Exit if not found."""
    if not CONFIG_FILE.exists():
        raise FileNotFoundError(
            f"Configuration file not found!\n"
            f"Expected location: {CONFIG_FILE}\n"
            f"Please copy 'config.example.json' to 'config.json' and edit it with your local paths."
        )
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

# ===== DATE PARSING =====

def parse_date(date_str: str):
    """
    Parse a date string that may be in one of two formats:
      YYYY-MM-DD  (ISO format — written by current script versions)
      DD/MM/YYYY  (written by older script versions)
    Raises ValueError with a clear message if neither format matches.
    """
    from datetime import date
    date_str = date_str.strip()
    if '-' in date_str:
        # YYYY-MM-DD
        return date.fromisoformat(date_str)
    elif '/' in date_str:
        # DD/MM/YYYY
        day, month, year = date_str.split('/')
        return date(int(year), int(month), int(day))
    else:
        raise ValueError(
            f"Unrecognised date format: '{date_str}'. "
            f"Expected YYYY-MM-DD or DD/MM/YYYY."
        )

# ===== DATA LOADING =====

def load_log(LOG_PATH):
    if not LOG_PATH.exists():
        print("No review log found yet. Run the main review script first.")
        return []
    with open(LOG_PATH, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("Log file is empty.")
    return rows


def load_edits(EDITS_PATH):
    """Load note_edits.csv. Returns empty list if file missing or empty."""
    if not EDITS_PATH.exists():
        return []
    with open(EDITS_PATH, newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    return rows

# ===== METRIC COMPUTATIONS =====

def compute_retention_over_time(rows):
    """
    Weekly retention rate over time.
    Returns list of {week, rate, total} dicts.
    Groups reviews by ISO week and computes pass rate per week.
    Excludes first-time reviews (R_at_review == 'new').
    """
    from datetime import date
    weekly = defaultdict(lambda: {'passed': 0, 'total': 0})
    for r in rows:
        if r['R_at_review'] == 'new':
            continue
        d = parse_date(r['date'])
        week_label = f"{d.isocalendar().year}-W{d.isocalendar().week:02d}"
        weekly[week_label]['total'] += 1
        if r['grade'] != 'again':
            weekly[week_label]['passed'] += 1
    result = []
    for week in sorted(weekly):
        total = weekly[week]['total']
        passed = weekly[week]['passed']
        result.append({
            'week': week,
            'rate': round(passed / total * 100, 1) if total else 0,
            'total': total
        })
    return result


def compute_grade_distribution(rows):
    """Count of each grade across all reviews."""
    counts = defaultdict(int)
    for r in rows:
        counts[r['grade']] += 1
    total = sum(counts.values())
    return [
        {'grade': g, 'count': counts.get(g, 0),
         'pct': round(counts.get(g, 0) / total * 100, 1) if total else 0}
        for g in ['again', 'hard', 'good', 'easy']
    ]


def compute_stability_growth(rows):
    """
    Average stability at each review number across all notes.
    Review number = how many times that specific note has been reviewed so far.
    """
    review_n       = defaultdict(int)
    stability_sums = defaultdict(float)
    stability_cnt  = defaultdict(int)
    for r in rows:
        note = r['note']
        review_n[note] += 1
        n = review_n[note]
        stability_sums[n] += float(r['new_stability'])
        stability_cnt[n]  += 1
    return [
        {'review_n': n,
         'avg_stability': round(stability_sums[n] / stability_cnt[n], 1),
         'note_count': stability_cnt[n]}
        for n in sorted(stability_sums)
    ]


def compute_lapse_report(rows):
    """Notes with the most lapses, top 10 descending."""
    lapses = defaultdict(int)
    for r in rows:
        if r['grade'] == 'again':
            lapses[r['note']] += 1
    sorted_lapses = sorted(lapses.items(), key=lambda x: x[1], reverse=True)
    return [{'note': note, 'lapses': count} for note, count in sorted_lapses[:10]]


def compute_r_distribution(rows):
    """
    Histogram of R_at_review values across all non-new reviews.
    Bucketed into 5 equal bins from 0 to 1.
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


def compute_difficulty_evolution(rows):
    """
    Average difficulty per note across review sequence.
    Shows whether difficulty scores are converging.
    """
    review_n   = defaultdict(int)
    diff_sums  = defaultdict(float)
    diff_cnt   = defaultdict(int)
    for r in rows:
        note = r['note']
        review_n[note] += 1
        n = review_n[note]
        try:
            diff_sums[n] += float(r['new_difficulty'])
            diff_cnt[n]  += 1
        except (ValueError, KeyError):
            continue
    return [
        {'review_n': n,
         'avg_difficulty': round(diff_sums[n] / diff_cnt[n], 2)}
        for n in sorted(diff_sums)
    ]


def compute_summary_stats(rows):
    """Top-level summary numbers for the stat cards."""
    non_new = [r for r in rows if r['R_at_review'] != 'new']
    passed  = [r for r in non_new if r['grade'] != 'again']
    retention = round(len(passed) / len(non_new) * 100, 1) if non_new else 0

    stabilities = []
    for r in rows:
        try:
            stabilities.append(float(r['new_stability']))
        except (ValueError, KeyError):
            continue
    avg_stab = round(sum(stabilities) / len(stabilities), 1) if stabilities else 0

    unique_notes = len(set(r['note'] for r in rows))
    total_lapses = sum(1 for r in rows if r['grade'] == 'again')

    return {
        'total_reviews':  len(rows),
        'retention_rate': retention,
        'avg_stability':  avg_stab,
        'unique_notes':   unique_notes,
        'total_lapses':   total_lapses,
    }


# ===== NEW: TIME & EDIT METRIC COMPUTATIONS =====

def compute_time_metrics(rows):
    """
    Compute review-time statistics from the review_time column.
    Only rows with a non-empty review_time are included.
    Returns dict with total_time, avg_time, per_note averages, and raw timed events.
    """
    timed = []
    for r in rows:
        rt = r.get('review_time', '').strip()
        if rt:
            try:
                timed.append({
                    'date': r['date'],
                    'note': r['note'],
                    'grade': r['grade'],
                    'time': float(rt),
                    'stability': float(r['new_stability']),
                    'difficulty': float(r['new_difficulty']),
                })
            except (ValueError, KeyError):
                continue

    if not timed:
        return {'total_time': 0, 'avg_time': 0, 'count': 0,
                'per_note': [], 'events': []}

    total_time = sum(e['time'] for e in timed)
    avg_time = total_time / len(timed)

    # Per-note averages
    note_sums = defaultdict(float)
    note_cnts = defaultdict(int)
    for e in timed:
        note_sums[e['note']] += e['time']
        note_cnts[e['note']] += 1
    per_note = []
    for note in sorted(note_sums, key=lambda n: note_sums[n] / note_cnts[n], reverse=True):
        per_note.append({
            'note': note,
            'avg_time': round(note_sums[note] / note_cnts[note], 2),
            'total_time': round(note_sums[note], 1),
            'count': note_cnts[note],
        })

    return {
        'total_time': round(total_time, 1),
        'avg_time': round(avg_time, 2),
        'count': len(timed),
        'per_note': per_note,
        'events': timed,
    }


def compute_edit_metrics(edits, rows):
    """
    Compute edit-related metrics by joining note_edits.csv with review_log.csv.
    Returns dict with edit timeline, pre/post comparisons, and effectiveness scores.
    """
    if not edits:
        return {'edits': [], 'pre_post': [], 'effectiveness': [], 'edit_count': 0}

    # Build a lookup of reviews per note sorted by date
    reviews_by_note = defaultdict(list)
    for r in rows:
        try:
            d = parse_date(r['date'])
            rt = r.get('review_time', '').strip()
            reviews_by_note[r['note']].append({
                'date': d,
                'grade': r['grade'],
                'r_at_review': r['R_at_review'],
                'stability': float(r['new_stability']),
                'time': float(rt) if rt else None,
            })
        except (ValueError, KeyError):
            continue
    for note in reviews_by_note:
        reviews_by_note[note].sort(key=lambda x: x['date'])

    edit_results = []
    pre_post_results = []
    effectiveness_results = []

    for edit in edits:
        edit_date = parse_date(edit['date'])
        note = edit['note']
        edit_type = edit.get('edit_type', 'unknown')
        description = edit.get('description', '')

        edit_results.append({
            'date': edit['date'],
            'note': note,
            'edit_type': edit_type,
            'description': description,
        })

        # Find pre/post reviews (up to 3 before, all after)
        note_reviews = reviews_by_note.get(note, [])
        pre_reviews = [rv for rv in note_reviews if rv['date'] < edit_date]
        post_reviews = [rv for rv in note_reviews if rv['date'] >= edit_date]

        # Take last 3 pre-edit reviews
        pre_window = pre_reviews[-3:] if len(pre_reviews) >= 3 else pre_reviews
        # Take first 3 post-edit reviews
        post_window = post_reviews[:3] if len(post_reviews) >= 3 else post_reviews

        pre_times = [rv['time'] for rv in pre_window if rv['time'] is not None]
        post_times = [rv['time'] for rv in post_window if rv['time'] is not None]
        pre_lapses = sum(1 for rv in pre_window if rv['grade'] == 'again')
        post_lapses = sum(1 for rv in post_window if rv['grade'] == 'again')
        pre_stabs = [rv['stability'] for rv in pre_window]
        post_stabs = [rv['stability'] for rv in post_window]
        pre_rs = []
        post_rs = []
        for rv in pre_window:
            try:
                pre_rs.append(float(rv['r_at_review']))
            except (ValueError, TypeError):
                continue
        for rv in post_window:
            try:
                post_rs.append(float(rv['r_at_review']))
            except (ValueError, TypeError):
                continue

        pre_avg_time = round(sum(pre_times) / len(pre_times), 2) if pre_times else None
        post_avg_time = round(sum(post_times) / len(post_times), 2) if post_times else None
        time_delta = round(post_avg_time - pre_avg_time, 2) if (pre_avg_time and post_avg_time) else None

        pre_post_results.append({
            'note': note,
            'edit_date': edit['date'],
            'pre_reviews': len(pre_window),
            'post_reviews': len(post_window),
            'pre_avg_time': pre_avg_time,
            'post_avg_time': post_avg_time,
            'time_delta': time_delta,
            'pre_lapses': pre_lapses,
            'post_lapses': post_lapses,
            'pre_avg_stability': round(sum(pre_stabs) / len(pre_stabs), 1) if pre_stabs else None,
            'post_avg_stability': round(sum(post_stabs) / len(post_stabs), 1) if post_stabs else None,
            'pre_avg_r': round(sum(pre_rs) / len(pre_rs), 3) if pre_rs else None,
            'post_avg_r': round(sum(post_rs) / len(post_rs), 3) if post_rs else None,
            'pre_grades': [rv['grade'] for rv in pre_window],
            'post_grades': [rv['grade'] for rv in post_window],
        })

        effectiveness_results.append({
            'note': note,
            'time_delta': time_delta,
            'lapse_delta': post_lapses - pre_lapses,
            'stability_delta': round(
                (sum(post_stabs) / len(post_stabs)) - (sum(pre_stabs) / len(pre_stabs)), 1
            ) if pre_stabs and post_stabs else None,
            'verdict': (
                'effective' if (time_delta is not None and time_delta < 0 and post_lapses <= pre_lapses)
                else 'inconclusive' if len(post_window) < 2
                else 'needs_attention'
            ),
        })

    return {
        'edits': edit_results,
        'pre_post': pre_post_results,
        'effectiveness': effectiveness_results,
        'edit_count': len(edits),
    }


def compute_heatmap_data(rows):
    """
    Compute average review time per note per ISO week for the heatmap.
    Returns dict with week labels and per-note time arrays.
    """
    timed = []
    for r in rows:
        rt = r.get('review_time', '').strip()
        if rt:
            try:
                d = parse_date(r['date'])
                week_label = f"W{d.isocalendar().week:02d}"
                timed.append({'note': r['note'], 'week': week_label, 'time': float(rt)})
            except (ValueError, KeyError):
                continue

    if not timed:
        return {'weeks': [], 'notes': []}

    # Collect all weeks and notes
    all_weeks = sorted(set(e['week'] for e in timed))
    all_notes = sorted(set(e['note'] for e in timed),
                       key=lambda n: -sum(e['time'] for e in timed if e['note'] == n))

    # Build grid
    notes_data = []
    for note in all_notes:
        times = []
        for week in all_weeks:
            vals = [e['time'] for e in timed if e['note'] == note and e['week'] == week]
            times.append(round(sum(vals) / len(vals), 1) if vals else None)
        # Short label for display
        short = note.split('—')[0].strip() if '—' in note else note[:12]
        notes_data.append({'name': note, 'short': short, 'times': times})

    return {'weeks': all_weeks, 'notes': notes_data}


def compute_divergence_data(rows):
    """
    Compute latest difficulty and average review time per note.
    Used for the C4 divergence scatter plot.
    """
    timed = []
    for r in rows:
        rt = r.get('review_time', '').strip()
        if rt:
            try:
                timed.append({
                    'note': r['note'],
                    'time': float(rt),
                    'difficulty': float(r['new_difficulty']),
                })
            except (ValueError, KeyError):
                continue

    if not timed:
        return []

    note_times = defaultdict(list)
    note_diffs = defaultdict(list)
    for e in timed:
        note_times[e['note']].append(e['time'])
        note_diffs[e['note']].append(e['difficulty'])

    result = []
    for note in note_times:
        result.append({
            'note': note,
            'avg_time': round(sum(note_times[note]) / len(note_times[note]), 2),
            'difficulty': note_diffs[note][-1],  # latest difficulty
        })
    return result


def compute_pipeline_data(rows, edits):
    """
    Build the Lapse → Edit → Recovery pipeline for each note that had lapses.
    Returns list of pipeline entries.
    """
    # Find all lapse events per note
    lapses_by_note = defaultdict(list)
    for r in rows:
        if r['grade'] == 'again':
            lapses_by_note[r['note']].append(r)

    # Find edit dates per note
    edit_dates = {}
    for e in edits:
        edit_dates[e['note']] = parse_date(e['date'])

    # Find latest review per note after any edit
    reviews_by_note = defaultdict(list)
    for r in rows:
        try:
            d = parse_date(r['date'])
            rt = r.get('review_time', '').strip()
            reviews_by_note[r['note']].append({
                'date': d,
                'grade': r['grade'],
                'r': r['R_at_review'],
                'stability': r['new_stability'],
                'time': float(rt) if rt else None,
            })
        except (ValueError, KeyError):
            continue
    for note in reviews_by_note:
        reviews_by_note[note].sort(key=lambda x: x['date'])

    pipeline = []
    for note, lapse_list in sorted(lapses_by_note.items(),
                                    key=lambda x: len(x[1]), reverse=True):
        last_lapse = lapse_list[-1]
        lapse_date = parse_date(last_lapse['date'])
        has_edit = note in edit_dates
        edit_date = edit_dates.get(note)

        # Find recovery: first review after edit (or after last lapse if no edit)
        ref_date = edit_date if has_edit else lapse_date
        post_reviews = [rv for rv in reviews_by_note.get(note, []) if rv['date'] > ref_date]
        recovery = post_reviews[-1] if post_reviews else None

        status = 'unaddressed'
        if has_edit and recovery and recovery['grade'] != 'again':
            status = 'recovered'
        elif not has_edit and recovery and recovery['grade'] != 'again':
            status = 'self_recovered'
        elif has_edit and recovery and recovery['grade'] == 'again':
            status = 'failed_fix'

        pipeline.append({
            'note': note,
            'lapse_count': len(lapse_list),
            'lapse_date': last_lapse['date'],
            'lapse_grade': last_lapse['grade'],
            'lapse_r': last_lapse['R_at_review'],
            'lapse_time': last_lapse.get('review_time', ''),
            'has_edit': has_edit,
            'edit_date': str(edit_date) if edit_date else None,
            'edit_type': next((e.get('edit_type', '') for e in edits if e['note'] == note), None),
            'recovery': recovery,
            'status': status,
        })

    return pipeline[:8]  # top 8 by lapse count


# ===== HTML GENERATION =====

def build_html(summary, retention_over_time, grade_dist,
               stability_growth, lapse_report, r_dist, difficulty_evo,
               time_metrics, edit_metrics, heatmap_data, divergence_data,
               pipeline_data):
    """Build the full dashboard HTML with all sections (A, B, C, D)."""

    # Prepare timed events as JS array
    events_js = json.dumps(time_metrics['events'], default=str)
    per_note_js = json.dumps(time_metrics['per_note'])
    edits_js = json.dumps(edit_metrics['edits'], default=str)
    pre_post_js = json.dumps(edit_metrics['pre_post'], default=str)
    effectiveness_js = json.dumps(edit_metrics['effectiveness'], default=str)
    heatmap_js = json.dumps(heatmap_data, default=str)
    divergence_js = json.dumps(divergence_data, default=str)
    pipeline_js = json.dumps(pipeline_data, default=str)
    lapse_js = json.dumps(lapse_report)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FSRS Full Review Metrics Dashboard</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>
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
  --cyan:     #2AA1B5;
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
h1 {{ font-size: 20px; font-weight: 500; margin-bottom: 0.25rem; }}
.subtitle {{ font-size: 13px; color: var(--muted); margin-bottom: 1.5rem; }}
h2 {{
  font-size: 15px; font-weight: 500;
  margin: 2rem 0 0.75rem;
  padding-bottom: 6px;
  border-bottom: 0.5px solid var(--border);
}}
.section-desc {{ font-size: 12px; color: var(--muted); margin-bottom: 1rem; max-width: 720px; }}
.tab-bar {{
  display: flex; gap: 4px;
  margin-bottom: 1.5rem;
  border-bottom: 1px solid var(--border);
}}
.tab-btn {{
  padding: 8px 18px; font-size: 13px; font-weight: 500;
  border: none; background: none; color: var(--muted);
  cursor: pointer; border-bottom: 2px solid transparent;
  transition: all 0.15s;
}}
.tab-btn:hover {{ color: var(--text); }}
.tab-btn.active {{ color: var(--text); border-bottom-color: var(--blue); }}
.tab-panel {{ display: none; }}
.tab-panel.active {{ display: block; }}
.stat-grid-primary {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0,1fr)) 140px;
  gap: 12px; margin-bottom: 12px; align-items: stretch;
}}
.stat-grid-secondary {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0,1fr));
  gap: 12px; margin-bottom: 2rem;
}}
.stat-card {{
  background: var(--surface);
  border: 0.5px solid var(--border);
  border-radius: var(--radius);
  padding: 1rem; position: relative; overflow: hidden;
  display: flex; flex-direction: column;
}}
.stat-card::after {{
  content: ''; position: absolute;
  top: 0; left: 0; right: 0; height: 3px;
  border-radius: var(--radius) var(--radius) 0 0;
}}
.stat-card.accent-time::after      {{ background: var(--cyan); }}
.stat-card.accent-avg::after       {{ background: var(--blue); }}
.stat-card.accent-edits::after     {{ background: var(--purple); }}
.stat-card.accent-month::after     {{ background: var(--amber); }}
.stat-card.accent-saved::after     {{ background: var(--green); }}
.stat-card.accent-grade::after     {{ background: linear-gradient(90deg, var(--red), var(--amber), var(--green), var(--blue)); }}
.stat-card.accent-total::after     {{ background: var(--muted); }}
.stat-card.accent-retention::after {{ background: var(--green); }}
.stat-card.accent-stability::after {{ background: var(--blue); }}
.stat-card.accent-notes::after     {{ background: var(--purple); }}
.stat-card.accent-lapses::after    {{ background: var(--red); }}
.stat-label {{ font-size: 11px; color: var(--muted); margin-bottom: 4px; font-weight: 500; }}
.stat-value {{ font-size: 24px; font-weight: 600; letter-spacing: -0.02em; }}
.stat-value.positive {{ color: var(--green); }}
.stat-value.negative {{ color: var(--red); }}
.stat-sub {{ font-size: 11px; color: var(--muted); margin-top: 2px; }}
.stat-delta {{
  display: inline-flex; align-items: center; gap: 3px;
  font-size: 11px; font-weight: 500;
  padding: 1px 6px; border-radius: 4px; margin-top: 4px;
}}
.stat-delta.up   {{ background: rgba(29,158,117,0.1); color: var(--green); }}
.stat-delta.down {{ background: rgba(226,75,74,0.1);  color: var(--red); }}
.stat-delta.flat {{ background: var(--surface2);      color: var(--muted); }}
.section-label {{
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--muted);
  margin-bottom: 8px; margin-top: 1.5rem;
}}
.section-label:first-of-type {{ margin-top: 0; }}
.grade-donut-wrap {{
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; min-height: 90px;
}}
.grade-donut-canvas {{ width: 80px !important; height: 80px !important; }}
.grade-legend-mini {{
  display: flex; flex-wrap: wrap; gap: 4px 8px;
  margin-top: 6px; font-size: 9px; color: var(--muted); justify-content: center;
}}
.grade-legend-mini span {{ display: flex; align-items: center; gap: 3px; }}
.grade-legend-mini .dot {{ width: 7px; height: 7px; border-radius: 2px; flex-shrink: 0; }}
.chart-grid-2 {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 16px; margin-bottom: 16px; }}
.chart-full {{ margin-bottom: 16px; }}
.chart-card {{
  background: var(--surface);
  border: 0.5px solid var(--border);
  border-radius: var(--radius); padding: 1.25rem;
}}
.chart-title {{ font-size: 13px; color: var(--muted); margin-bottom: 12px; }}
.chart-wrap {{ position: relative; width: 100%; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 8px; font-size: 12px; color: var(--muted); }}
.legend-item {{ display: flex; align-items: center; gap: 5px; }}
.legend-dot {{ width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
.target-note {{ font-size: 11px; color: var(--muted); margin-top: 6px; }}
.timeline {{ position: relative; padding-left: 28px; margin-bottom: 1.5rem; }}
.timeline::before {{ content:''; position:absolute; left:8px; top:0; bottom:0; width:2px; background:var(--border); }}
.timeline-item {{
  position: relative; margin-bottom: 1.5rem;
  background: var(--surface); border: 0.5px solid var(--border);
  border-radius: var(--radius); padding: 1rem 1.25rem;
}}
.timeline-item::before {{
  content:''; position:absolute; left:-24px; top:1.25rem;
  width:10px; height:10px; border-radius:50%;
  background:var(--red); border:2px solid var(--surface);
}}
.timeline-date {{ font-size:11px; color:var(--muted); margin-bottom:4px; }}
.timeline-note {{ font-size:14px; font-weight:500; margin-bottom:6px; }}
.timeline-desc {{ font-size:13px; color:var(--muted); line-height:1.5; }}
.badge {{ display:inline-block; font-size:11px; font-weight:500; padding:2px 8px; border-radius:4px; }}
.badge-rewrite {{ background:rgba(226,75,74,0.12); color:var(--red); }}
.comparison-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr)); gap:16px; margin-bottom:1.5rem; }}
.compare-card {{ background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); padding:1.25rem; }}
.compare-card-title {{ font-size:14px; font-weight:500; margin-bottom:12px; }}
.compare-body {{ display:grid; grid-template-columns:1fr 40px 1fr; gap:8px; align-items:start; }}
.compare-col {{ background:var(--surface2); border-radius:8px; padding:12px; }}
.compare-col-label {{ font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; color:var(--muted); margin-bottom:8px; }}
.compare-arrow {{ display:flex; align-items:center; justify-content:center; font-size:18px; color:var(--muted); padding-top:2rem; }}
.metric-row {{ display:flex; justify-content:space-between; align-items:center; padding:4px 0; font-size:12px; }}
.metric-row .label {{ color:var(--muted); }}
.metric-row .value {{ font-weight:500; }}
.metric-row .value.positive {{ color:var(--green); }}
.metric-row .value.negative {{ color:var(--red); }}
.compare-footer {{ margin-top:10px; padding-top:8px; border-top:0.5px solid var(--border); font-size:11px; color:var(--muted); }}
.section-card {{ background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); padding:1.25rem; margin-bottom:16px; }}
.lapse-table {{ width:100%; border-collapse:collapse; font-size:13px; }}
.lapse-table th {{ text-align:left; font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; color:var(--muted); padding:8px 12px; border-bottom:1px solid var(--border); }}
.lapse-table td {{ padding:10px 12px; border-bottom:0.5px solid var(--border); vertical-align:middle; }}
.lapse-table tr:last-child td {{ border-bottom:none; }}
.edit-badge {{ display:inline-flex; align-items:center; gap:4px; font-size:11px; padding:2px 8px; border-radius:10px; background:rgba(226,75,74,0.1); color:var(--red); font-weight:500; }}
.edit-badge-none {{ background:var(--surface2); color:var(--muted); }}
.status-pill {{ font-size:11px; padding:2px 8px; border-radius:10px; font-weight:500; }}
.status-fixed {{ background:rgba(29,158,117,0.12); color:var(--green); }}
.status-struggling {{ background:rgba(226,75,74,0.12); color:var(--red); }}
.status-pending {{ background:rgba(239,159,39,0.12); color:var(--amber); }}
.lapse-bar-wrap {{ width:100%; background:var(--surface2); border-radius:4px; height:8px; overflow:hidden; }}
.lapse-bar {{ height:100%; border-radius:4px; background:var(--red); }}
.eff-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; margin-bottom:1.5rem; }}
.eff-card {{ background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); padding:1.25rem; }}
.eff-card-title {{ font-size:13px; font-weight:500; margin-bottom:10px; }}
.eff-metric {{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }}
.eff-metric-label {{ font-size:12px; color:var(--muted); min-width:110px; }}
.eff-bar-track {{ flex:1; height:10px; background:var(--surface2); border-radius:5px; position:relative; }}
.eff-bar-fill {{ height:100%; border-radius:5px; position:absolute; left:50%; }}
.eff-bar-fill.positive {{ background:var(--green); transform:translateX(0); }}
.eff-bar-fill.negative {{ background:var(--red); right:50%; left:auto; }}
.eff-bar-center {{ position:absolute; left:50%; top:-2px; bottom:-2px; width:1px; background:var(--muted); }}
.eff-value {{ font-size:12px; font-weight:500; min-width:50px; text-align:right; }}
.eff-value.positive {{ color:var(--green); }}
.eff-value.negative {{ color:var(--red); }}
.eff-value.neutral {{ color:var(--muted); }}
.eff-verdict {{ margin-top:12px; padding-top:8px; border-top:0.5px solid var(--border); font-size:12px; color:var(--muted); }}
.eff-verdict strong {{ color:var(--text); font-weight:500; }}
.pipeline-container {{ display:flex; flex-direction:column; gap:16px; margin-bottom:1.5rem; }}
.pipeline-header {{ display:flex; gap:0; margin-bottom:8px; }}
.pipeline-header-col {{ flex:1; text-align:center; font-size:11px; font-weight:600; color:var(--muted); text-transform:uppercase; letter-spacing:0.03em; }}
.pipeline-row {{ display:flex; align-items:stretch; background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); overflow:hidden; }}
.pipeline-col {{ flex:1; padding:14px 16px; display:flex; flex-direction:column; justify-content:center; }}
.pipeline-col:not(:last-child) {{ border-right:0.5px solid var(--border); }}
.pipeline-arrow {{ display:flex; align-items:center; padding:0 6px; color:var(--muted); font-size:16px; flex-shrink:0; }}
.pipeline-note-name {{ font-weight:500; font-size:13px; margin-bottom:4px; }}
.pipeline-date {{ font-size:11px; color:var(--muted); }}
.pipeline-metric {{ font-size:11px; margin-top:2px; }}
.pipeline-metric .val {{ font-weight:500; }}
.pipeline-metric .val.bad {{ color:var(--red); }}
.pipeline-metric .val.good {{ color:var(--green); }}
.pipeline-metric .val.neutral {{ color:var(--amber); }}
.pipeline-edit-type {{ display:inline-block; font-size:10px; font-weight:600; padding:1px 6px; border-radius:4px; background:rgba(226,75,74,0.1); color:var(--red); margin-bottom:4px; }}
.pipeline-no-edit {{ font-size:11px; color:var(--muted); font-style:italic; }}
.pipeline-status {{ font-size:11px; font-weight:500; padding:2px 8px; border-radius:10px; display:inline-block; margin-top:4px; }}
.status-recovered {{ background:rgba(29,158,117,0.12); color:var(--green); }}
.status-unaddressed {{ background:rgba(226,75,74,0.12); color:var(--red); }}
.time-saved-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-bottom:1.5rem; }}
.ts-card {{ background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); padding:1.25rem; }}
.ts-card-title {{ font-size:13px; font-weight:500; margin-bottom:12px; }}
.ts-big-number {{ font-size:32px; font-weight:600; margin-bottom:4px; }}
.ts-big-number.positive {{ color:var(--green); }}
.ts-big-number.negative {{ color:var(--red); }}
.ts-big-number.neutral {{ color:var(--muted); }}
.ts-sub {{ font-size:12px; color:var(--muted); margin-bottom:12px; }}
.ts-detail {{ display:flex; justify-content:space-between; font-size:12px; padding:4px 0; border-top:0.5px solid var(--border); }}
.ts-detail .label {{ color:var(--muted); }}
.ts-detail .value {{ font-weight:500; }}
.ts-verdict {{ margin-top:10px; padding:8px 12px; border-radius:6px; font-size:12px; line-height:1.4; }}
.ts-verdict.good {{ background:rgba(29,158,117,0.08); color:var(--green); }}
.ts-verdict.bad {{ background:rgba(226,75,74,0.08); color:var(--red); }}
.ts-verdict.meh {{ background:rgba(239,159,39,0.08); color:var(--amber); }}
.heatmap-wrapper {{ background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); padding:1.25rem; overflow-x:auto; margin-bottom:1.5rem; }}
.heatmap-title {{ font-size:13px; color:var(--muted); margin-bottom:12px; }}
.heatmap-cell {{ width:36px; height:28px; border-radius:3px; display:flex; align-items:center; justify-content:center; font-size:9px; font-weight:500; color:white; cursor:default; transition:transform 0.1s; }}
.heatmap-cell:hover {{ transform:scale(1.15); z-index:2; }}
.heatmap-cell.empty {{ background:var(--surface2); color:var(--muted); }}
.heatmap-label-row {{ display:flex; align-items:center; font-size:11px; color:var(--muted); white-space:nowrap; padding-right:8px; min-width:90px; }}
.heatmap-label-col {{ font-size:10px; color:var(--muted); text-align:center; writing-mode:vertical-lr; transform:rotate(180deg); height:40px; display:flex; align-items:center; justify-content:center; }}
.heatmap-legend {{ display:flex; align-items:center; gap:4px; margin-top:12px; font-size:11px; color:var(--muted); }}
.heatmap-legend-bar {{ width:120px; height:10px; border-radius:5px; background:linear-gradient(to right,#1D9E75,#EF9F27,#E24B4A); }}
.divergence-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-bottom:1.5rem; }}
.alert-list {{ margin-top:12px; }}
.alert-item {{ display:flex; align-items:flex-start; gap:8px; padding:8px 12px; border-radius:6px; margin-bottom:6px; font-size:12px; line-height:1.4; }}
.alert-item.warn {{ background:rgba(226,75,74,0.06); border:0.5px solid rgba(226,75,74,0.15); }}
.alert-item.info {{ background:rgba(55,138,221,0.06); border:0.5px solid rgba(55,138,221,0.15); }}
.alert-item.ok {{ background:rgba(29,158,117,0.06); border:0.5px solid rgba(29,158,117,0.15); }}
.alert-icon {{ flex-shrink:0; font-size:14px; }}
.alert-text strong {{ font-weight:500; }}
.detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:16px; margin-bottom:1.5rem; }}
.detail-card {{ background:var(--surface); border:0.5px solid var(--border); border-radius:var(--radius); padding:1.25rem; }}
.detail-card-title {{ font-size:13px; font-weight:500; margin-bottom:12px; }}
.detail-row {{ display:flex; justify-content:space-between; align-items:center; padding:6px 0; border-bottom:0.5px solid var(--border); font-size:12px; }}
.detail-row:last-child {{ border-bottom:none; }}
.detail-row .label {{ color:var(--muted); }}
.detail-row .value {{ font-weight:500; }}
.detail-row .value.green {{ color:var(--green); }}
.detail-row .value.red {{ color:var(--red); }}
.detail-row .value.amber {{ color:var(--amber); }}
.insight-box {{ background:var(--surface2); border-radius:8px; padding:12px 16px; font-size:12px; color:var(--muted); margin-top:12px; line-height:1.5; }}
.insight-box strong {{ color:var(--text); }}
.footer-note {{ margin-top:2rem; padding:12px 16px; background:var(--surface2); border-radius:8px; font-size:12px; color:var(--muted); line-height:1.5; }}
.footer-note strong {{ color:var(--text); font-weight:500; }}
.no-data {{ font-size:13px; color:var(--muted); padding:2rem 0; text-align:center; }}
@media (max-width: 1100px) {{
  .stat-grid-primary {{ grid-template-columns: repeat(3,1fr); }}
  .chart-grid-2, .divergence-grid {{ grid-template-columns: 1fr; }}
}}
@media (max-width: 700px) {{
  .stat-grid-primary {{ grid-template-columns: repeat(2,1fr); }}
  .stat-grid-secondary {{ grid-template-columns: repeat(2,1fr); }}
  .pipeline-row {{ flex-direction:column; }}
  .pipeline-col:not(:last-child) {{ border-right:none; border-bottom:0.5px solid var(--border); }}
}}
</style>
</head>
<body>
<h1>FSRS full review metrics dashboard</h1>
<div class="subtitle" id="subtitle">Loading…</div>

<!-- D. SUMMARY STAT CARDS -->
<div class="section-label">Time &amp; Edit Metrics (new)</div>
<div class="stat-grid-primary">
  <div class="stat-card accent-time">
    <div class="stat-label">Total review time</div>
    <div class="stat-value" id="s-total-time">—</div>
    <div class="stat-sub" id="s-total-time-sub"></div>
  </div>
  <div class="stat-card accent-avg">
    <div class="stat-label">Avg time / card</div>
    <div class="stat-value" id="s-avg-time">—</div>
    <div class="stat-sub">Target: &lt; 12 min</div>
  </div>
  <div class="stat-card accent-edits">
    <div class="stat-label">Notes edited</div>
    <div class="stat-value" id="s-notes-edited">—</div>
    <div class="stat-sub" id="s-notes-edited-sub"></div>
  </div>
  <div class="stat-card accent-month">
    <div class="stat-label">Total edits</div>
    <div class="stat-value" id="s-edit-count">—</div>
    <div class="stat-sub" id="s-edit-count-sub"></div>
  </div>
  <div class="stat-card accent-saved">
    <div class="stat-label">Time saved post-edit</div>
    <div class="stat-value" id="s-time-saved">—</div>
    <div class="stat-sub" id="s-time-saved-sub"></div>
  </div>
  <div class="stat-card accent-grade">
    <div class="stat-label">Grade distribution</div>
    <div class="grade-donut-wrap">
      <canvas id="c-grade-donut" class="grade-donut-canvas"></canvas>
      <div class="grade-legend-mini" id="grade-legend-mini"></div>
    </div>
  </div>
</div>

<div class="section-label">Core FSRS Metrics (existing)</div>
<div class="stat-grid-secondary">
  <div class="stat-card accent-total">
    <div class="stat-label">Total reviews</div>
    <div class="stat-value" id="s-total">—</div>
  </div>
  <div class="stat-card accent-retention">
    <div class="stat-label">Retention rate</div>
    <div class="stat-value" id="s-retention">—</div>
  </div>
  <div class="stat-card accent-stability">
    <div class="stat-label">Avg stability</div>
    <div class="stat-value" id="s-stability">—</div>
  </div>
  <div class="stat-card accent-notes">
    <div class="stat-label">Notes tracked</div>
    <div class="stat-value" id="s-notes">—</div>
  </div>
  <div class="stat-card accent-lapses">
    <div class="stat-label">Total lapses</div>
    <div class="stat-value" id="s-lapses" style="color:var(--red)">—</div>
  </div>
</div>

<!-- TAB NAVIGATION -->
<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('tabA')">A · Review Time</button>
  <button class="tab-btn" onclick="switchTab('tabB')">B · Note Edits</button>
  <button class="tab-btn" onclick="switchTab('tabC')">C · Cross-Cutting</button>
  <button class="tab-btn" onclick="switchTab('tabD')">D · Detail Breakdown</button>
</div>

<!-- TAB A -->
<div class="tab-panel active" id="tabA">
  <h2>A1 · Average review time per note</h2>
  <div class="chart-grid-2">
    <div class="chart-card">
      <div class="chart-title">Horizontal bar — sorted by average time (minutes)</div>
      <div class="chart-wrap" style="height:260px"><canvas id="c-a1"></canvas></div>
      <div class="target-note">Notes above 16 min are rewrite candidates. Below 8 min = well-structured.</div>
    </div>
    <div class="chart-card">
      <div class="chart-title">A2 · Review time by grade</div>
      <div class="legend">
        <span class="legend-item"><span class="legend-dot" style="background:var(--red)"></span>again</span>
        <span class="legend-item"><span class="legend-dot" style="background:var(--amber)"></span>hard</span>
        <span class="legend-item"><span class="legend-dot" style="background:var(--green)"></span>good</span>
        <span class="legend-item"><span class="legend-dot" style="background:var(--blue)"></span>easy</span>
      </div>
      <div class="chart-wrap" style="height:230px"><canvas id="c-a2"></canvas></div>
    </div>
  </div>
  <h2>A3–A4 · Trends &amp; Daily Load</h2>
  <div class="chart-grid-2">
    <div class="chart-card">
      <div class="chart-title">A3 · Average review time trend (weekly)</div>
      <div class="chart-wrap" style="height:200px"><canvas id="c-a3"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">A4 · Daily review load (stacked by note)</div>
      <div class="chart-wrap" style="height:200px"><canvas id="c-a4"></canvas></div>
    </div>
  </div>
  <h2>A5 · Efficiency ratio</h2>
  <div class="chart-full">
    <div class="chart-card">
      <div class="chart-title">Time spent per stability-day gained (min / day)</div>
      <div class="chart-wrap" style="height:240px"><canvas id="c-a5"></canvas></div>
    </div>
  </div>
</div>

<!-- TAB B -->
<div class="tab-panel" id="tabB">
  <h2>B1 · Edit timeline</h2>
  <div class="timeline" id="edit-timeline"></div>
  <h2>B2 · Pre / Post edit performance</h2>
  <div class="comparison-grid" id="pre-post-grid"></div>
  <h2>B3 · Lapse report with edit status</h2>
  <div class="section-card">
    <table class="lapse-table">
      <thead><tr><th>Note</th><th style="width:120px">Lapses</th><th style="width:50px"></th><th style="width:70px">Edits</th><th style="width:110px">Status</th></tr></thead>
      <tbody id="lapse-tbody"></tbody>
    </table>
    <div class="insight-box"><strong>Guide:</strong> 3+ lapses &amp; 0 edits → rewrite candidate.</div>
  </div>
  <h2>B4 · Edit effectiveness score</h2>
  <div class="eff-grid" id="eff-grid"></div>
</div>

<!-- TAB C -->
<div class="tab-panel" id="tabC">
  <h2>C1 · Lapse → Edit → Recovery pipeline</h2>
  <div class="pipeline-header">
    <div class="pipeline-header-col">① Lapse Event</div>
    <div class="pipeline-header-col">② Edit Applied</div>
    <div class="pipeline-header-col">③ Recovery Outcome</div>
  </div>
  <div class="pipeline-container" id="pipeline-container"></div>
  <h2>C2 · Time saved after rewrite</h2>
  <div class="time-saved-grid" id="time-saved-grid"></div>
  <h2>C3 · Review time heatmap (note × week)</h2>
  <div class="heatmap-wrapper">
    <div class="heatmap-title">Average review time (min) per note per ISO week</div>
    <div id="heatmap-container"></div>
    <div class="heatmap-legend"><span>Fast</span><div class="heatmap-legend-bar"></div><span>Slow</span></div>
  </div>
  <h2>C4 · Difficulty vs. time divergence</h2>
  <div class="divergence-grid">
    <div class="chart-card">
      <div class="chart-title">Difficulty (y) vs. Avg Review Time (x)</div>
      <div class="chart-wrap" style="height:280px"><canvas id="c-c4"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">Divergence alerts</div>
      <div class="alert-list" id="alert-list"></div>
    </div>
  </div>
</div>

<!-- TAB D -->
<div class="tab-panel" id="tabD">
  <div class="detail-grid" id="detail-grid"></div>
  <div class="footer-note" id="footer-note"></div>
</div>

<script>
// ── Injected data ────────────────────────────────────────────────────────────
const summaryData     = {json.dumps(summary)};
const retentionData   = {json.dumps(retention_over_time)};
const gradeData       = {json.dumps(grade_dist)};
const stabilityData   = {json.dumps(stability_growth)};
const lapseData       = {lapse_js};
const rDistData       = {json.dumps(r_dist)};
const difficultyData  = {json.dumps(difficulty_evo)};
const timeMetrics     = {{ total: {time_metrics['total_time']}, avg: {time_metrics['avg_time']}, count: {time_metrics['count']}, perNote: {per_note_js}, events: {events_js} }};
const editMetrics     = {{ edits: {edits_js}, prePost: {pre_post_js}, effectiveness: {effectiveness_js}, count: {edit_metrics['edit_count']} }};
const heatmapData     = {heatmap_js};
const divergenceData  = {divergence_js};
const pipelineData    = {pipeline_js};

// ── Tab switching ────────────────────────────────────────────────────────────
function switchTab(id) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}}

// ── Chart.js globals ─────────────────────────────────────────────────────────
const isDark  = matchMedia('(prefers-color-scheme: dark)').matches;
const textClr = isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)';
const gridClr = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';
const GREEN='#1D9E75', BLUE='#378ADD', AMBER='#EF9F27', RED='#E24B4A', PURPLE='#7F77DD', CYAN='#2AA1B5';
const gradeColors = {{again:RED, hard:AMBER, good:GREEN, easy:BLUE}};
const noteColors = {{}};
const colorPalette = ['#6366f1','#f59e0b','#ef4444','#10b981','#3b82f6','#8b5cf6','#ec4899','#14b8a6','#f97316','#06b6d4'];
const allNoteNames = [...new Set(timeMetrics.events.map(e=>e.note))];
allNoteNames.forEach((n,i) => noteColors[n] = colorPalette[i % colorPalette.length]);
const baseScale = {{x:{{ticks:{{color:textClr,font:{{size:11}}}},grid:{{color:gridClr}}}},y:{{ticks:{{color:textClr,font:{{size:11}}}},grid:{{color:gridClr}}}}}};
const baseOpts = {{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}}}}}};
function shortNote(n) {{ return n.length > 30 ? n.substring(0,28)+'…' : n; }}

// ── Stat cards ───────────────────────────────────────────────────────────────
document.getElementById('subtitle').textContent =
  timeMetrics.count + ' timed reviews · ' + summaryData.total_reviews + ' total reviews · ' +
  editMetrics.count + ' edits · ' + summaryData.unique_notes + ' notes';
const totalHrs = (timeMetrics.total / 60).toFixed(1);
document.getElementById('s-total-time').innerHTML = totalHrs + '<span style="font-size:14px;font-weight:400;color:var(--muted)"> hrs</span>';
document.getElementById('s-total-time-sub').textContent = timeMetrics.total + ' min cumulative · ' + timeMetrics.count + ' timed events';
document.getElementById('s-avg-time').innerHTML = timeMetrics.avg.toFixed(1) + '<span style="font-size:14px;font-weight:400;color:var(--muted)"> min</span>';
document.getElementById('s-notes-edited').innerHTML = new Set(editMetrics.edits.map(e=>e.note)).size + '<span style="font-size:14px;font-weight:400;color:var(--muted)"> / ' + summaryData.unique_notes + '</span>';
document.getElementById('s-notes-edited-sub').textContent = Math.round(new Set(editMetrics.edits.map(e=>e.note)).size / summaryData.unique_notes * 100) + '% of corpus restructured';
document.getElementById('s-edit-count').textContent = editMetrics.count;
document.getElementById('s-edit-count-sub').textContent = editMetrics.edits.length ? 'Last: ' + editMetrics.edits[editMetrics.edits.length-1].date : 'none yet';
const timeDeltas = editMetrics.prePost.filter(p=>p.time_delta!==null).map(p=>p.time_delta);
const netDelta = timeDeltas.length ? (timeDeltas.reduce((a,b)=>a+b,0)/timeDeltas.length).toFixed(1) : '—';
const savedEl = document.getElementById('s-time-saved');
savedEl.innerHTML = (netDelta <= 0 ? '' : '+') + netDelta + '<span style="font-size:14px;font-weight:400;color:var(--muted)"> min</span>';
savedEl.className = 'stat-value ' + (netDelta <= 0 ? 'positive' : 'negative');
document.getElementById('s-time-saved-sub').textContent = 'net avg across edits';
document.getElementById('s-total').textContent = summaryData.total_reviews;
document.getElementById('s-stability').textContent = summaryData.avg_stability + 'd';
document.getElementById('s-notes').textContent = summaryData.unique_notes;
document.getElementById('s-lapses').textContent = summaryData.total_lapses;
const retEl = document.getElementById('s-retention');
retEl.textContent = summaryData.retention_rate + '%';
retEl.style.color = summaryData.retention_rate >= 88 ? 'var(--green)' : 'var(--red)';

// ── Grade donut ──────────────────────────────────────────────────────────────
const legendMini = document.getElementById('grade-legend-mini');
gradeData.forEach(g => {{
  legendMini.innerHTML += '<span><span class="dot" style="background:'+gradeColors[g.grade]+'"></span>'+g.pct+'%</span>';
}});
new Chart(document.getElementById('c-grade-donut'), {{
  type:'doughnut',
  data:{{ labels:gradeData.map(g=>g.grade), datasets:[{{ data:gradeData.map(g=>g.count), backgroundColor:gradeData.map(g=>gradeColors[g.grade]), borderWidth:0, hoverOffset:4 }}] }},
  options:{{ responsive:false, maintainAspectRatio:false, cutout:'58%', plugins:{{ legend:{{display:false}}, tooltip:{{callbacks:{{label:ctx=>ctx.label+': '+ctx.raw}}}} }} }}
}});

// ── A1: Horizontal bar ───────────────────────────────────────────────────────
const sortedPN = [...timeMetrics.perNote].sort((a,b)=>b.avg_time-a.avg_time);
new Chart(document.getElementById('c-a1'), {{
  type:'bar',
  data:{{ labels:sortedPN.map(p=>shortNote(p.note)), datasets:[{{ data:sortedPN.map(p=>p.avg_time), backgroundColor:sortedPN.map(p=>noteColors[p.note]||'#888'), borderRadius:4, barThickness:22 }}] }},
  options:{{...baseOpts, indexAxis:'y', scales:{{x:{{...baseScale.x,title:{{display:true,text:'minutes',color:textClr,font:{{size:11}}}}}},y:{{...baseScale.y,ticks:{{color:textClr,font:{{size:10}}}}}}}}, plugins:{{tooltip:{{callbacks:{{label:ctx=>ctx.raw.toFixed(1)+' min avg'}}}}}}}}
}});

// ── A2: Scatter time vs grade ────────────────────────────────────────────────
const gradeIndex={{again:0,hard:1,good:2,easy:3}};
const a2Data={{again:[],hard:[],good:[],easy:[]}};
timeMetrics.events.forEach(r=>a2Data[r.grade].push({{x:r.time,y:gradeIndex[r.grade]+(Math.random()-0.5)*0.3}}));
new Chart(document.getElementById('c-a2'), {{
  type:'scatter',
  data:{{datasets:Object.entries(a2Data).map(([g,pts])=>({{label:g,data:pts,backgroundColor:gradeColors[g],pointRadius:5,pointHoverRadius:7}}))}},
  options:{{...baseOpts,scales:{{x:{{...baseScale.x,title:{{display:true,text:'review time (min)',color:textClr,font:{{size:11}}}},min:0}},y:{{...baseScale.y,min:-0.5,max:3.5,ticks:{{color:textClr,font:{{size:11}},stepSize:1,callback:v=>['again','hard','good','easy'][v]||''}},grid:{{color:gridClr}}}}}},plugins:{{tooltip:{{callbacks:{{label:ctx=>ctx.dataset.label+': '+ctx.raw.x.toFixed(1)+' min'}}}}}}}}
}});

// ── A3: Weekly trend ─────────────────────────────────────────────────────────
function isoWeek(dateObj) {{
  const d = new Date(Date.UTC(dateObj.getFullYear(), dateObj.getMonth(), dateObj.getDate()));
  const dayNum = d.getUTCDay() || 7;
  d.setUTCDate(d.getUTCDate() + 4 - dayNum);
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1));
  const weekNo = Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
  return d.getUTCFullYear() + '-W' + String(weekNo).padStart(2, '0');
}}
const weeklyTime={{}};
timeMetrics.events.forEach(r=>{{
  const d=new Date(r.date.includes('-')?r.date:r.date.split('/').reverse().join('-'));
  const w=isoWeek(d);
  if(!weeklyTime[w])weeklyTime[w]={{sum:0,cnt:0}};
  weeklyTime[w].sum+=r.time; weeklyTime[w].cnt++;
}});
const a3Weeks=Object.keys(weeklyTime).sort();
const a3Avgs=a3Weeks.map(w=>+(weeklyTime[w].sum/weeklyTime[w].cnt).toFixed(2));
new Chart(document.getElementById('c-a3'), {{
  type:'line',
  data:{{labels:a3Weeks,datasets:[{{label:'Avg time',data:a3Avgs,borderColor:CYAN,backgroundColor:'rgba(42,161,181,0.08)',fill:true,tension:0.35,pointRadius:4,pointBackgroundColor:CYAN}}]}},
  options:{{...baseOpts,
    scales:{{
      x:{{...baseScale.x,ticks:{{color:textClr,font:{{size:10}},maxRotation:45}}}},
      y:{{...baseScale.y,title:{{display:true,text:'minutes',color:textClr,font:{{size:11}}}},min:0}}
    }},
    plugins:{{
      legend:{{display:false}},
      tooltip:{{callbacks:{{label:ctx=>ctx.raw.toFixed(1)+' min avg'}}}}
    }}
  }}
}});

// ── A4: Daily stacked ────────────────────────────────────────────────────────
const dailyByNote={{}};
timeMetrics.events.forEach(r=>{{
  const d=r.date;
  if(!dailyByNote[d])dailyByNote[d]={{}};
  if(!dailyByNote[d][r.note])dailyByNote[d][r.note]=0;
  dailyByNote[d][r.note]+=r.time;
}});
const a4Days=Object.keys(dailyByNote).sort();
const a4Notes=allNoteNames;
const a4Datasets=a4Notes.map(note=>({{label:shortNote(note),data:a4Days.map(d=>(dailyByNote[d]&&dailyByNote[d][note])?+dailyByNote[d][note].toFixed(1):0),backgroundColor:noteColors[note]||'#888',borderRadius:2}}));
new Chart(document.getElementById('c-a4'), {{
  type:'bar',
  data:{{labels:a4Days,datasets:a4Datasets}},
  options:{{...baseOpts,scales:{{x:{{stacked:true,...baseScale.x,ticks:{{color:textClr,font:{{size:9}},maxRotation:60}}}},y:{{stacked:true,...baseScale.y,title:{{display:true,text:'minutes',color:textClr,font:{{size:11}}}}}}}},plugins:{{legend:{{display:false}},tooltip:{{mode:'index',intersect:false}}}}}}
}});

// ── A5: Efficiency scatter ───────────────────────────────────────────────────
const a5Data={{}};
timeMetrics.events.forEach(r=>{{
  if(!a5Data[r.note])a5Data[r.note]=[];
  a5Data[r.note].push({{x:r.stability,y:+(r.time/r.stability).toFixed(3)}});
}});
new Chart(document.getElementById('c-a5'), {{
  type:'scatter',
  data:{{datasets:Object.entries(a5Data).map(([note,pts])=>({{label:shortNote(note),data:pts,backgroundColor:noteColors[note]||'#888',pointRadius:5,pointHoverRadius:7}}))}},
  options:{{...baseOpts,scales:{{x:{{...baseScale.x,title:{{display:true,text:'new stability (days)',color:textClr,font:{{size:11}}}},min:0}},y:{{...baseScale.y,title:{{display:true,text:'min per stability-day',color:textClr,font:{{size:11}}}},min:0}}}},plugins:{{legend:{{display:true,position:'bottom',labels:{{color:textClr,font:{{size:10}},boxWidth:12,padding:10}}}},tooltip:{{callbacks:{{label:ctx=>ctx.dataset.label+': '+ctx.raw.y.toFixed(2)+' min/day'}}}}}}}}
}});

// ── B1: Edit timeline ────────────────────────────────────────────────────────
const timelineEl = document.getElementById('edit-timeline');
if (editMetrics.edits.length === 0) {{
  timelineEl.innerHTML = '<div class="no-data">No edits recorded yet.</div>';
}} else {{
  editMetrics.edits.forEach(e => {{
    timelineEl.innerHTML += '<div class="timeline-item">' +
      '<div class="timeline-date">' + e.date + '</div>' +
      '<div class="timeline-note">' + shortNote(e.note) + ' <span class="badge badge-rewrite">' + e.edit_type + '</span></div>' +
      '<div class="timeline-desc">' + (e.description||'').substring(0,300) + '</div></div>';
  }});
}}

// ── B2: Pre/Post comparison ──────────────────────────────────────────────────
const ppGrid = document.getElementById('pre-post-grid');
editMetrics.prePost.forEach(pp => {{
  const timeDeltaStr = pp.time_delta !== null ? (pp.time_delta <= 0 ? '' : '+') + pp.time_delta.toFixed(1) + ' min' : '—';
  const timeCls = pp.time_delta !== null ? (pp.time_delta <= 0 ? 'positive' : 'negative') : '';
  ppGrid.innerHTML += '<div class="compare-card"><div class="compare-card-title">' + shortNote(pp.note) + '</div>' +
    '<div class="compare-body"><div class="compare-col"><div class="compare-col-label">Before (' + pp.pre_reviews + ' reviews)</div>' +
    '<div class="metric-row"><span class="label">Avg time</span><span class="value">' + (pp.pre_avg_time||'—') + ' min</span></div>' +
    '<div class="metric-row"><span class="label">Lapses</span><span class="value">' + pp.pre_lapses + '</span></div>' +
    '<div class="metric-row"><span class="label">Avg stability</span><span class="value">' + (pp.pre_avg_stability||'—') + 'd</span></div></div>' +
    '<div class="compare-arrow">→</div>' +
    '<div class="compare-col"><div class="compare-col-label">After (' + pp.post_reviews + ' reviews)</div>' +
    '<div class="metric-row"><span class="label">Avg time</span><span class="value ' + timeCls + '">' + (pp.post_avg_time||'—') + ' min</span></div>' +
    '<div class="metric-row"><span class="label">Lapses</span><span class="value">' + pp.post_lapses + '</span></div>' +
    '<div class="metric-row"><span class="label">Avg stability</span><span class="value">' + (pp.post_avg_stability||'—') + 'd</span></div></div></div>' +
    '<div class="compare-footer">Δ time: ' + timeDeltaStr + '</div></div>';
}});
if (!editMetrics.prePost.length) ppGrid.innerHTML = '<div class="no-data">No edit data to compare.</div>';

// ── B3: Lapse table ──────────────────────────────────────────────────────────
const tbody = document.getElementById('lapse-tbody');
const maxLapse = lapseData.length ? lapseData[0].lapses : 1;
lapseData.forEach(d => {{
  const editInfo = editMetrics.edits.find(e => e.note === d.note);
  const barPct = Math.round(d.lapses / maxLapse * 100);
  const warn = d.lapses >= 3 && !editInfo;
  const editBadge = editInfo ? '<span class="edit-badge">✎ 1</span>' : '<span class="edit-badge edit-badge-none">—</span>';
  let statusPill;
  if (editInfo) statusPill = '<span class="status-pill status-fixed">✓ edited</span>';
  else if (warn) statusPill = '<span class="status-pill status-struggling">⚠ rewrite needed</span>';
  else statusPill = '<span class="status-pill status-pending">— pending</span>';
  const nameStyle = warn ? ' style="color:var(--red);font-weight:500"' : '';
  tbody.innerHTML += '<tr><td' + nameStyle + '>' + shortNote(d.note) + '</td>' +
    '<td><div class="lapse-bar-wrap"><div class="lapse-bar" style="width:' + barPct + '%"></div></div></td>' +
    '<td style="font-size:12px;color:var(--muted);text-align:right">' + d.lapses + '</td>' +
    '<td>' + editBadge + '</td><td>' + statusPill + '</td></tr>';
}});

// ── B4: Effectiveness ────────────────────────────────────────────────────────
const effGrid = document.getElementById('eff-grid');
editMetrics.effectiveness.forEach(eff => {{
  const tCls = eff.time_delta !== null ? (eff.time_delta <= 0 ? 'positive' : 'negative') : 'neutral';
  const tStr = eff.time_delta !== null ? (eff.time_delta <= 0 ? '' : '+') + eff.time_delta.toFixed(1) + ' min' : '—';
  const lCls = eff.lapse_delta <= 0 ? 'positive' : 'negative';
  effGrid.innerHTML += '<div class="eff-card"><div class="eff-card-title">' + shortNote(eff.note) + '</div>' +
    '<div class="eff-metric"><span class="eff-metric-label">Δ Review time</span><div class="eff-bar-track"><div class="eff-bar-center"></div><div class="eff-bar-fill ' + (eff.time_delta<=0?'positive':'negative') + '" style="width:' + Math.min(Math.abs(eff.time_delta||0)*8,40) + '%"></div></div><span class="eff-value ' + tCls + '">' + tStr + '</span></div>' +
    '<div class="eff-metric"><span class="eff-metric-label">Δ Lapse count</span><div class="eff-bar-track"><div class="eff-bar-center"></div><div class="eff-bar-fill ' + lCls + '" style="width:' + Math.min(Math.abs(eff.lapse_delta)*15,40) + '%"></div></div><span class="eff-value ' + lCls + '">' + (eff.lapse_delta<=0?'':'') + eff.lapse_delta + '</span></div>' +
    '<div class="eff-verdict"><strong>Verdict: ' + eff.verdict + '.</strong></div></div>';
}});
if (!editMetrics.effectiveness.length) effGrid.innerHTML = '<div class="no-data">No edits to evaluate.</div>';

// ── C1: Pipeline ─────────────────────────────────────────────────────────────
const pipeEl = document.getElementById('pipeline-container');
pipelineData.forEach(p => {{
  const statusCls = p.status === 'recovered' || p.status === 'self_recovered' ? 'status-recovered' : 'status-unaddressed';
  const statusTxt = p.status === 'recovered' ? '✓ Recovered' : p.status === 'self_recovered' ? '✓ Self-recovered' : p.status === 'failed_fix' ? '✗ Failed fix' : '⚠ Unaddressed';
  const rec = p.recovery;
  pipeEl.innerHTML += '<div class="pipeline-row">' +
    '<div class="pipeline-col"><div class="pipeline-note-name">' + shortNote(p.note) + '</div>' +
    '<div class="pipeline-date">' + p.lapse_date + ' · ' + p.lapse_count + ' lapse(s)</div>' +
    '<div class="pipeline-metric">R=<span class="val bad">' + p.lapse_r + '</span></div></div>' +
    '<div class="pipeline-arrow">→</div>' +
    '<div class="pipeline-col">' + (p.has_edit ? '<span class="pipeline-edit-type">' + (p.edit_type||'edit') + '</span><div class="pipeline-date">' + (p.edit_date||'') + '</div>' : '<span class="pipeline-no-edit">No edit applied</span>') + '</div>' +
    '<div class="pipeline-arrow">→</div>' +
    '<div class="pipeline-col">' + (rec ? '<div class="pipeline-date">' + rec.grade + '</div><div class="pipeline-metric">R=<span class="val good">' + rec.r + '</span> · stab=<span class="val">' + rec.stability + 'd</span></div>' : '<div class="pipeline-date">No post-data</div>') +
    '<span class="pipeline-status ' + statusCls + '">' + statusTxt + '</span></div></div>';
}});

// ── C2: Time saved ───────────────────────────────────────────────────────────
const tsGrid = document.getElementById('time-saved-grid');
editMetrics.prePost.forEach(pp => {{
  const delta = pp.time_delta;
  const cls = delta !== null ? (delta <= 0 ? 'positive' : 'negative') : 'neutral';
  const str = delta !== null ? (delta <= 0 ? '' : '+') + delta.toFixed(1) + ' min' : '—';
  tsGrid.innerHTML += '<div class="ts-card"><div class="ts-card-title">' + shortNote(pp.note) + '</div>' +
    '<div class="ts-big-number ' + cls + '">' + str + '</div>' +
    '<div class="ts-sub">' + (pp.pre_avg_time||'?') + ' → ' + (pp.post_avg_time||'?') + ' min</div>' +
    '<div class="ts-detail"><span class="label">Pre-edit (' + pp.pre_reviews + ' rev)</span><span class="value">' + (pp.pre_avg_time||'—') + ' min</span></div>' +
    '<div class="ts-detail"><span class="label">Post-edit (' + pp.post_reviews + ' rev)</span><span class="value">' + (pp.post_avg_time||'—') + ' min</span></div>' +
    '<div class="ts-detail"><span class="label">Lapse delta</span><span class="value">' + pp.pre_lapses + ' → ' + pp.post_lapses + '</span></div></div>';
}});
if (!editMetrics.prePost.length) tsGrid.innerHTML = '<div class="no-data">No edit data.</div>';

// ── C3: Heatmap ──────────────────────────────────────────────────────────────
function timeToColor(t) {{ if(t===null)return''; if(t<8)return'#1D9E75'; if(t<12)return'#7bc8a4'; if(t<16)return'#EF9F27'; if(t<20)return'#e06040'; return'#E24B4A'; }}
const hmEl = document.getElementById('heatmap-container');
if (heatmapData.weeks && heatmapData.weeks.length) {{
  let hhtml = '<div style="display:grid;grid-template-columns:90px repeat(' + heatmapData.weeks.length + ',36px);gap:2px;align-items:center;">';
  hhtml += '<div></div>';
  heatmapData.weeks.forEach(w => {{ hhtml += '<div class="heatmap-label-col">' + w + '</div>'; }});
  heatmapData.notes.forEach(note => {{
    hhtml += '<div class="heatmap-label-row">' + note.short.substring(0,12) + '</div>';
    note.times.forEach((t,i) => {{
      if (t===null) hhtml += '<div class="heatmap-cell empty">—</div>';
      else hhtml += '<div class="heatmap-cell" style="background:'+timeToColor(t)+'" title="'+note.short+' '+heatmapData.weeks[i]+': '+t+' min">'+Math.round(t)+'</div>';
    }});
  }});
  hhtml += '</div>';
  hmEl.innerHTML = hhtml;
}} else {{
  hmEl.innerHTML = '<div class="no-data">No timed data for heatmap.</div>';
}}

// ── C4: Divergence scatter ───────────────────────────────────────────────────
if (divergenceData.length) {{
  new Chart(document.getElementById('c-c4'), {{
    type:'scatter',
    data:{{datasets:[
      {{label:'Notes',data:divergenceData.map(p=>({{x:p.avg_time,y:p.difficulty}})),backgroundColor:divergenceData.map((p,i)=>colorPalette[i%colorPalette.length]),pointRadius:8,pointHoverRadius:11}},
      {{label:'Time threshold',data:[{{x:12,y:7}},{{x:12,y:10.5}}],type:'line',borderColor:'rgba(239,159,39,0.4)',borderDash:[4,4],borderWidth:1.5,pointRadius:0,fill:false}},
      {{label:'Diff threshold',data:[{{x:3,y:9.5}},{{x:25,y:9.5}}],type:'line',borderColor:'rgba(226,75,74,0.4)',borderDash:[4,4],borderWidth:1.5,pointRadius:0,fill:false}}
    ]}},
    options:{{responsive:true,maintainAspectRatio:false,plugins:{{legend:{{display:false}},tooltip:{{callbacks:{{label:ctx=>{{if(ctx.datasetIndex===0){{const p=divergenceData[ctx.dataIndex];return shortNote(p.note)+': '+p.avg_time.toFixed(1)+' min, diff='+p.difficulty;}}return'';}}}}}}}},scales:{{x:{{min:3,max:25,title:{{display:true,text:'Avg review time (min)',color:textClr,font:{{size:11}}}},ticks:{{color:textClr,font:{{size:10}}}},grid:{{color:gridClr}}}},y:{{min:7,max:10.5,title:{{display:true,text:'FSRS Difficulty',color:textClr,font:{{size:11}}}},ticks:{{color:textClr,font:{{size:10}}}},grid:{{color:gridClr}}}}}}}},
    plugins:[{{afterDraw:function(chart){{const ctx=chart.ctx;const meta=chart.getDatasetMeta(0);ctx.save();ctx.font='10px -apple-system,sans-serif';ctx.fillStyle=isDark?'rgba(255,255,255,0.7)':'rgba(0,0,0,0.6)';meta.data.forEach((point,i)=>{{ctx.fillText(shortNote(divergenceData[i].note).substring(0,10),point.x+10,point.y+3);}});ctx.restore();}}}}]
  }});
}}

// ── C4: Alerts ───────────────────────────────────────────────────────────────
const alertEl = document.getElementById('alert-list');
divergenceData.forEach(p => {{
  if (p.avg_time > 16 && p.difficulty >= 9.5) {{
    alertEl.innerHTML += '<div class="alert-item warn"><span class="alert-icon">⚠️</span><span class="alert-text"><strong>' + shortNote(p.note) + '</strong> — Diff ' + p.difficulty + ' + Time ' + p.avg_time.toFixed(1) + ' min. Hard AND slow. <strong>Action:</strong> Rewrite.</span></div>';
  }} else if (p.avg_time < 8) {{
    alertEl.innerHTML += '<div class="alert-item info"><span class="alert-icon">💡</span><span class="alert-text"><strong>' + shortNote(p.note) + '</strong> — Diff ' + p.difficulty + ' + Time ' + p.avg_time.toFixed(1) + ' min. Very efficient structure.</span></div>';
  }}
}});
if (!alertEl.innerHTML) alertEl.innerHTML = '<div class="alert-item ok"><span class="alert-icon">✓</span><span class="alert-text">No divergence alerts. All notes within normal range.</span></div>';

// ── D: Detail breakdown ──────────────────────────────────────────────────────
const detailGrid = document.getElementById('detail-grid');
let dhtml = '<div class="detail-card"><div class="detail-card-title">⏱ Time breakdown by note</div>';
sortedPN.forEach(p => {{
  const cls = p.avg_time > 16 ? 'red' : p.avg_time < 8 ? 'green' : '';
  dhtml += '<div class="detail-row"><span class="label">' + shortNote(p.note) + ' (' + p.count + ' rev)</span><span class="value ' + cls + '">' + p.total_time + ' min · avg ' + p.avg_time + '</span></div>';
}});
dhtml += '</div>';
dhtml += '<div class="detail-card"><div class="detail-card-title">📊 Time distribution</div>';
const times = timeMetrics.events.map(e=>e.time).sort((a,b)=>a-b);
const median = times.length ? times[Math.floor(times.length/2)] : 0;
const fastest = times.length ? times[0] : 0;
const slowest = times.length ? times[times.length-1] : 0;
dhtml += '<div class="detail-row"><span class="label">Fastest review</span><span class="value green">' + fastest.toFixed(1) + ' min</span></div>';
dhtml += '<div class="detail-row"><span class="label">Slowest review</span><span class="value red">' + slowest.toFixed(1) + ' min</span></div>';
dhtml += '<div class="detail-row"><span class="label">Median</span><span class="value">' + median.toFixed(1) + ' min</span></div>';
dhtml += '<div class="detail-row"><span class="label">Reviews &lt; 10 min</span><span class="value green">' + times.filter(t=>t<10).length + ' / ' + times.length + '</span></div>';
dhtml += '<div class="detail-row"><span class="label">Reviews &gt; 20 min</span><span class="value red">' + times.filter(t=>t>20).length + ' / ' + times.length + '</span></div>';
dhtml += '</div>';
detailGrid.innerHTML = dhtml;
document.getElementById('footer-note').innerHTML = '<strong>Action triggers:</strong> Avg time &gt; 12 min → simplify note structure. Notes with 3+ lapses and 0 edits → schedule rewrite. Time saved trending negative → strategy working.';
</script>
</body>
</html>"""
    return html

# ===== MAIN =====

def print_section(title):
    """Print a clearly delimited section header."""
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def main():
    # Load the config once when the script starts
    config_path = Path(r"..\data\config.json")
    config = load_config(config_path)

    rows = load_log(Path(config["log_path"]))
    if not rows:
        return

    edits = load_edits(Path(config["edits_path"]))

    print(f"Loaded {len(rows)} review events.")
    print(f"Loaded {len(edits)} note edits.")
    print("Computing metrics...")

    summary          = compute_summary_stats(rows)
    retention_time   = compute_retention_over_time(rows)
    grade_dist       = compute_grade_distribution(rows)
    stability_growth = compute_stability_growth(rows)
    lapse_report     = compute_lapse_report(rows)
    r_dist           = compute_r_distribution(rows)
    difficulty_evo   = compute_difficulty_evolution(rows)

    # New: time & edit metrics
    time_metrics     = compute_time_metrics(rows)
    edit_metrics     = compute_edit_metrics(edits, rows)
    heatmap_data     = compute_heatmap_data(rows)
    divergence_data  = compute_divergence_data(rows)
    pipeline_data    = compute_pipeline_data(rows, edits)

    # ── Summary ────────────────────────────────────────────────────────────────
    print_section("Summary")
    retention_status = (
        "✓ on target"
        if summary['retention_rate'] >= 88
        else "✗ below target — consider reducing BASE_GROWTH"
    )
    print(f"  Total reviews  : {summary['total_reviews']}")
    print(f"  Retention rate : {summary['retention_rate']}%  {retention_status}")
    print(f"  Avg stability  : {summary['avg_stability']}d")
    print(f"  Unique notes   : {summary['unique_notes']}")
    print(f"  Total lapses   : {summary['total_lapses']}")

    # ── Grade distribution ─────────────────────────────────────────────────────
    print_section("Grade distribution")
    for entry in grade_dist:
        print(f"  {entry['grade']:6s}: {entry['count']:4d} reviews  ({entry['pct']:5.1f}%)")

    # ── Stability by review number ─────────────────────────────────────────────
    print_section("Average stability by review number")
    for entry in stability_growth:
        print(f"  Review {entry['review_n']:2d}: "
              f"avg stability = {entry['avg_stability']:6.1f} days  "
              f"({entry['note_count']} notes)")

    # ── Difficulty convergence ─────────────────────────────────────────────────
    print_section("Average difficulty by review number")
    for entry in difficulty_evo:
        bar_len  = int(entry['avg_difficulty'])
        bar      = '█' * bar_len + '░' * (10 - bar_len)
        print(f"  Review {entry['review_n']:2d}: "
              f"avg difficulty = {entry['avg_difficulty']:4.2f}  [{bar}]")

    # ── R at review time ───────────────────────────────────────────────────────
    print_section("Retrievability at review time (R distribution)")
    max_r = max((e['count'] for e in r_dist), default=1)
    for entry in r_dist:
        bar_len = int(entry['count'] / max(max_r, 1) * 20)
        bar     = '█' * bar_len
        print(f"  {entry['bucket']} : {bar:<20s}  {entry['count']:3d} reviews")
    print("  (Healthy: most reviews should fall in the 0.8–1.0 bucket)")

    # ── Lapse report ───────────────────────────────────────────────────────────
    print_section("Notes with most lapses")
    if not lapse_report:
        print("  No lapses recorded yet.")
    else:
        for entry in lapse_report:
            warning = "  ⚠  rewrite this note" if entry['lapses'] >= 3 else ""
            print(f"  {entry['lapses']:2d} lapses — {entry['note']}{warning}")

    # ── Time metrics ───────────────────────────────────────────────────────────
    print_section("Review time metrics")
    print(f"  Total review time : {time_metrics['total_time']} min ({time_metrics['total_time']/60:.1f} hrs)")
    print(f"  Avg time / card   : {time_metrics['avg_time']} min")
    print(f"  Timed events      : {time_metrics['count']}")
    if time_metrics['per_note']:
        print(f"  Slowest note      : {time_metrics['per_note'][0]['note'][:40]} ({time_metrics['per_note'][0]['avg_time']} min)")
        print(f"  Fastest note      : {time_metrics['per_note'][-1]['note'][:40]} ({time_metrics['per_note'][-1]['avg_time']} min)")

    # ── Edit metrics ───────────────────────────────────────────────────────────
    print_section("Note edit metrics")
    print(f"  Total edits       : {edit_metrics['edit_count']}")
    for eff in edit_metrics['effectiveness']:
        print(f"  {eff['note'][:40]:40s} → verdict: {eff['verdict']}")

    # ── HTML dashboard ─────────────────────────────────────────────────────────
    print_section("Generating dashboard")
    html = build_html(
        summary, retention_time, grade_dist,
        stability_growth, lapse_report, r_dist, difficulty_evo,
        time_metrics, edit_metrics, heatmap_data, divergence_data,
        pipeline_data
    )

    out_path = Path(config["metrics_path"])
    out_path.write_text(html, encoding='utf-8')
    print(f"  Dashboard written to : {out_path.resolve()}")
    print("  Opening in browser...")
    webbrowser.open(out_path.resolve().as_uri())




if __name__ == "__main__":
    main()
    
    