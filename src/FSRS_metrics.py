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
        d = date.fromisoformat(r['date'])
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


# ===== HTML GENERATION =====

def build_html(summary, retention_over_time, grade_dist,
               stability_growth, lapse_report, r_dist, difficulty_evo):

    data_js = f"""
    const summaryData       = {json.dumps(summary)};
    const retentionData     = {json.dumps(retention_over_time)};
    const gradeData         = {json.dumps(grade_dist)};
    const stabilityData     = {json.dumps(stability_growth)};
    const lapseData         = {json.dumps(lapse_report)};
    const rDistData         = {json.dumps(r_dist)};
    const difficultyData    = {json.dumps(difficulty_evo)};
    """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FSRS Review Metrics</title>
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
  h1 {{
    font-size: 20px;
    font-weight: 500;
    margin-bottom: 0.25rem;
  }}
  .subtitle {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 2rem;
  }}
  .stat-grid {{
    display: grid;
    grid-template-columns: repeat(5, minmax(0,1fr));
    gap: 12px;
    margin-bottom: 2rem;
  }}
  .stat-card {{
    background: var(--surface);
    border: 0.5px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem;
  }}
  .stat-label {{
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 4px;
  }}
  .stat-value {{
    font-size: 22px;
    font-weight: 500;
  }}
  .chart-grid-2 {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0,1fr));
    gap: 16px;
    margin-bottom: 16px;
  }}
  .chart-grid-3 {{
    display: grid;
    grid-template-columns: repeat(3, minmax(0,1fr));
    gap: 16px;
    margin-bottom: 16px;
  }}
  .chart-card {{
    background: var(--surface);
    border: 0.5px solid var(--border);
    border-radius: var(--radius);
    padding: 1.25rem;
  }}
  .chart-title {{
    font-size: 13px;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .chart-wrap {{
    position: relative;
    width: 100%;
  }}
  .legend {{
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 8px;
    font-size: 12px;
    color: var(--muted);
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 5px;
  }}
  .legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 2px;
    flex-shrink: 0;
  }}
  .target-note {{
    font-size: 11px;
    color: var(--muted);
    margin-top: 6px;
  }}
  .lapse-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 0;
    border-bottom: 0.5px solid var(--border);
    font-size: 13px;
  }}
  .lapse-row:last-child {{ border-bottom: none; }}
  .lapse-bar-wrap {{
    flex: 1;
    background: var(--surface2);
    border-radius: 4px;
    height: 8px;
    overflow: hidden;
  }}
  .lapse-bar {{
    height: 100%;
    background: var(--red);
    border-radius: 4px;
  }}
  .lapse-count {{
    font-size: 12px;
    color: var(--muted);
    min-width: 20px;
    text-align: right;
  }}
  .lapse-name {{
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    max-width: 200px;
  }}
  .status-ok  {{ color: var(--green); }}
  .status-bad {{ color: var(--red);   }}
  .no-data {{
    font-size: 13px;
    color: var(--muted);
    padding: 2rem 0;
    text-align: center;
  }}
</style>
</head>
<body>

<h1>FSRS review metrics</h1>
<div class="subtitle" id="subtitle">Loading…</div>

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
    <div class="stat-label">Avg stability</div>
    <div class="stat-value" id="s-stability">—</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Notes tracked</div>
    <div class="stat-value" id="s-notes">—</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">Total lapses</div>
    <div class="stat-value" id="s-lapses">—</div>
  </div>
</div>

<div class="chart-grid-2">
  <div class="chart-card">
    <div class="chart-title">Retention rate over time</div>
    <div class="legend">
      <span class="legend-item"><span class="legend-dot" style="background:var(--blue)"></span>Retention %</span>
      <span class="legend-item"><span class="legend-dot" style="background:var(--muted);opacity:.5"></span>90% target</span>
    </div>
    <div class="chart-wrap" style="height:200px"><canvas id="c-retention"
      role="img" aria-label="Line chart of weekly retention rate">Weekly retention rate.</canvas></div>
    <div class="target-note">Target: ≥ 88%. Below this → reduce BASE_GROWTH.</div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Grade distribution</div>
    <div class="legend" id="grade-legend"></div>
    <div class="chart-wrap" style="height:200px"><canvas id="c-grade"
      role="img" aria-label="Donut chart of grade distribution">Grade breakdown.</canvas></div>
  </div>
</div>

<div class="chart-grid-3">
  <div class="chart-card">
    <div class="chart-title">Stability growth by review number</div>
    <div class="chart-wrap" style="height:200px"><canvas id="c-stability"
      role="img" aria-label="Line chart of average stability per review number">Stability growth curve.</canvas></div>
    <div class="target-note">Should roughly triple each review in early stages.</div>
  </div>
  <div class="chart-card">
    <div class="chart-title">Difficulty convergence</div>
    <div class="chart-wrap" style="height:200px"><canvas id="c-difficulty"
      role="img" aria-label="Line chart of average difficulty per review number">Difficulty evolution.</canvas></div>
    <div class="target-note">Should stabilize after 5–8 reviews. Oscillation → reduce DIFFICULTY_DELTA.</div>
  </div>
  <div class="chart-card">
    <div class="chart-title">R at review time</div>
    <div class="chart-wrap" style="height:200px"><canvas id="c-rdist"
      role="img" aria-label="Histogram of retrievability at review time">R distribution.</canvas></div>
    <div class="target-note">Healthy: spike at 0.8–1.0. Spread = irregular reviews.</div>
  </div>
</div>

<div class="chart-card">
  <div class="chart-title">Top notes by lapse count — open and rewrite any note with 3+ lapses</div>
  <div id="lapse-list"></div>
</div>

<script>
{data_js}

const isDark   = matchMedia('(prefers-color-scheme: dark)').matches;
const textClr  = isDark ? 'rgba(255,255,255,0.5)' : 'rgba(0,0,0,0.4)';
const gridClr  = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

const GREEN  = '#1D9E75';
const BLUE   = '#378ADD';
const AMBER  = '#EF9F27';
const RED    = '#E24B4A';
const PURPLE = '#7F77DD';

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


// ── Stat cards ──────────────────────────────────────────────────────────────
document.getElementById('subtitle').textContent =
  'Based on ' + summaryData.total_reviews + ' reviews across ' +
  summaryData.unique_notes + ' notes';

document.getElementById('s-total').textContent     = summaryData.total_reviews;
document.getElementById('s-stability').textContent = summaryData.avg_stability + 'd';
document.getElementById('s-notes').textContent     = summaryData.unique_notes;
document.getElementById('s-lapses').textContent    = summaryData.total_lapses;

const retEl = document.getElementById('s-retention');
retEl.textContent = summaryData.retention_rate + '%';
retEl.className   = 'stat-value ' +
  (summaryData.retention_rate >= 88 ? 'status-ok' : 'status-bad');


// ── Retention over time ──────────────────────────────────────────────────────
if (retentionData.length) {{
  new Chart(document.getElementById('c-retention'), {{
    type: 'line',
    data: {{
      labels: retentionData.map(r => r.week),
      datasets: [
        {{
          label: 'Retention',
          data: retentionData.map(r => r.rate),
          borderColor: BLUE,
          backgroundColor: 'rgba(55,138,221,0.08)',
          fill: true,
          tension: 0.35,
          pointRadius: 4,
          pointBackgroundColor: BLUE,
          borderDash: []
        }},
        {{
          label: 'Target 90%',
          data: retentionData.map(() => 90),
          borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.18)',
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
          min: 70, max: 100,
          ticks: {{ color: textClr, font: {{ size: 11 }}, callback: v => v + '%' }},
          grid: {{ color: gridClr }}
        }}
      }}
    }}
  }});
}} else {{
  document.getElementById('c-retention').parentElement.innerHTML =
    '<div class="no-data">Not enough data yet — needs at least 2 weeks of reviews.</div>';
}}


// ── Grade distribution ───────────────────────────────────────────────────────
const gradeColors = {{ again: RED, hard: AMBER, good: GREEN, easy: BLUE }};
const legendEl    = document.getElementById('grade-legend');
gradeData.forEach(g => {{
  legendEl.innerHTML +=
    '<span class="legend-item">' +
    '<span class="legend-dot" style="background:' + gradeColors[g.grade] + '"></span>' +
    g.grade + ' ' + g.pct + '%</span>';
}});

new Chart(document.getElementById('c-grade'), {{
  type: 'doughnut',
  data: {{
    labels: gradeData.map(g => g.grade),
    datasets: [{{
      data: gradeData.map(g => g.count),
      backgroundColor: gradeData.map(g => gradeColors[g.grade]),
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


// ── Stability growth ─────────────────────────────────────────────────────────
new Chart(document.getElementById('c-stability'), {{
  type: 'line',
  data: {{
    labels: stabilityData.map(d => 'Review ' + d.review_n),
    datasets: [{{
      label: 'Avg stability (days)',
      data: stabilityData.map(d => d.avg_stability),
      borderColor: GREEN,
      backgroundColor: 'rgba(29,158,117,0.08)',
      fill: true,
      tension: 0.3,
      pointRadius: 4,
      pointBackgroundColor: GREEN,
    }}]
  }},
  options: {{
    ...baseOpts,
    scales: {{
      x: baseScale.x,
      y: {{
        ticks: {{ color: textClr, font: {{ size: 11 }}, callback: v => v + 'd' }},
        grid: {{ color: gridClr }}
      }}
    }}
  }}
}});


// ── Difficulty evolution ─────────────────────────────────────────────────────
if (difficultyData.length) {{
  new Chart(document.getElementById('c-difficulty'), {{
    type: 'line',
    data: {{
      labels: difficultyData.map(d => 'Review ' + d.review_n),
      datasets: [{{
        label: 'Avg difficulty',
        data: difficultyData.map(d => d.avg_difficulty),
        borderColor: PURPLE,
        backgroundColor: 'rgba(127,119,221,0.08)',
        fill: true,
        tension: 0.3,
        pointRadius: 4,
        pointBackgroundColor: PURPLE,
      }},
      {{
        label: 'Neutral 5.5',
        data: difficultyData.map(() => 5.5),
        borderColor: isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.18)',
        borderDash: [5, 4],
        pointRadius: 0,
        fill: false,
      }}]
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
      }}
    }}
  }});
}} else {{
  document.getElementById('c-difficulty').parentElement.innerHTML =
    '<div class="no-data">No difficulty data yet.</div>';
}}


// ── R distribution ───────────────────────────────────────────────────────────
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
      y: {{ ticks: {{ color: textClr, font: {{ size: 11 }} }}, grid: {{ color: gridClr }} }}
    }}
  }}
}});


// ── Lapse report ─────────────────────────────────────────────────────────────
const lapseEl  = document.getElementById('lapse-list');
const maxLapse = lapseData.length ? lapseData[0].lapses : 1;

if (lapseData.length === 0) {{
  lapseEl.innerHTML = '<div class="no-data">No lapses recorded yet.</div>';
}} else {{
  lapseData.forEach(d => {{
    const barPct = Math.round(d.lapses / maxLapse * 100);
    const warn   = d.lapses >= 3 ? ' style="color:var(--red)"' : '';
    lapseEl.innerHTML +=
      '<div class="lapse-row">' +
      '<span class="lapse-name"' + warn + ' title="' + d.note + '">' + d.note + '</span>' +
      '<div class="lapse-bar-wrap"><div class="lapse-bar" style="width:' + barPct + '%"></div></div>' +
      '<span class="lapse-count">' + d.lapses + '</span>' +
      '</div>';
  }});
}}

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

    print(f"Loaded {len(rows)} review events.")
    print("Computing metrics...")

    summary          = compute_summary_stats(rows)
    retention_time   = compute_retention_over_time(rows)
    grade_dist       = compute_grade_distribution(rows)
    stability_growth = compute_stability_growth(rows)
    lapse_report     = compute_lapse_report(rows)
    r_dist           = compute_r_distribution(rows)
    difficulty_evo   = compute_difficulty_evolution(rows)

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

    # ── HTML dashboard ─────────────────────────────────────────────────────────
    print_section("Generating dashboard")
    html = build_html(
        summary, retention_time, grade_dist,
        stability_growth, lapse_report, r_dist, difficulty_evo
    )


    out_path = Path(config["metrics_path"])
    out_path.write_text(html, encoding='utf-8')
    print(f"  Dashboard written to : {out_path.resolve()}")
    print("  Opening in browser...")
    webbrowser.open(out_path.resolve().as_uri())


if __name__ == "__main__":
    main()




