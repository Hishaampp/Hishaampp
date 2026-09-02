#!/usr/bin/env python3
"""
Generates stats.svg, streak.svg, langs.svg, year.svg for a GitHub profile
README, entirely from the standard library (urllib only — nothing to break
in CI). Reads two pre-subsetted, OFL-licensed JetBrains Mono woff2 files
from fonts/ and inlines them as base64 into every SVG, so the page makes
zero third-party requests at view time.

Determinism:
  - the contribution window is pinned to whole UTC days (today-364d 00:00:00Z
    to today 23:59:59Z), so two runs minutes apart bucket days identically.
  - repositories are filtered to privacy: PUBLIC, so the workflow's
    GITHUB_TOKEN and a personal token agree on language totals.

Run with:
  GITHUB_TOKEN=... GH_LOGIN=yourusername python3 scripts/generate_stats.py
"""
import base64
import datetime as dt
import json
import os
import sys
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(ROOT, "fonts")

TOKEN = os.environ["GITHUB_TOKEN"]
LOGIN = os.environ["GH_LOGIN"]

# ---------------------------------------------------------------- palette --
INK = "#1a1a1a"          # single fill colour — no per-character rainbow
DIM = "#767676"
LINE = "#d8d8d8"
ACCENT = "#1a1a1a"
BG = "#ffffff"

RAMP = " .`:-=+*cs#%@"    # same 13-level ramp as the portrait

# ------------------------------------------------------------------ fonts --
def _load_font_b64(name):
    path = os.path.join(FONTS_DIR, name)
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def font_face_css():
    reg = _load_font_b64("jbm-regular.woff2")
    bold = _load_font_b64("jbm-bold.woff2")
    return f"""
    @font-face {{
      font-family: 'JBM';
      src: url(data:font/woff2;base64,{reg}) format('woff2');
      font-weight: 400;
    }}
    @font-face {{
      font-family: 'JBM';
      src: url(data:font/woff2;base64,{bold}) format('woff2');
      font-weight: 700;
    }}
    text {{ font-family: 'JBM', ui-monospace, monospace; fill: {INK}; }}
    """.strip()


# --------------------------------------------------------------- GraphQL --
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount weekday }
        }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
      nodes {
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def gh_graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{LOGIN}-profile-stats",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.stderr.write(f"GraphQL HTTP {e.code}: {e.read().decode()}\n")
        raise
    if "errors" in data:
        sys.stderr.write(json.dumps(data["errors"], indent=2) + "\n")
        raise RuntimeError("GraphQL query returned errors")
    return data["data"]


def fetch():
    # Pin the window to whole UTC days so two runs minutes apart don't
    # bucket days into different weeks.
    today = dt.datetime.now(dt.timezone.utc).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    start = (today - dt.timedelta(days=364)).replace(hour=0, minute=0, second=0)
    variables = {
        "login": LOGIN,
        "from": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to": today.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return gh_graphql(QUERY, variables), start, today


# ------------------------------------------------------------- analytics --
def flatten_days(calendar):
    days = []
    for week in calendar["weeks"]:
        for d in week["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort()
    return days


def compute_streaks(days):
    """Returns (current_streak, current_range, longest_streak, longest_range)."""
    best_len, best_range = 0, None
    run_len, run_start = 0, None
    for date_str, count in days:
        if count > 0:
            if run_len == 0:
                run_start = date_str
            run_len += 1
            if run_len > best_len:
                best_len = run_len
                best_range = (run_start, date_str)
        else:
            run_len = 0

    # current streak: walk back from the most recent day with data
    current_len, current_range = 0, None
    for date_str, count in reversed(days):
        if count > 0:
            if current_len == 0:
                current_range_end = date_str
            current_len += 1
            current_range_start = date_str
        else:
            if current_len > 0:
                break
            # allow "today has no contributions yet" to not break the streak
            continue
    if current_len:
        current_range = (current_range_start, current_range_end)

    return current_len, current_range, best_len, best_range


def weekly_totals(days):
    weeks, bucket, count = [], [], 0
    for i, (_, c) in enumerate(days):
        bucket.append(c)
        if len(bucket) == 7:
            weeks.append(sum(bucket))
            bucket = []
    if bucket:
        weeks.append(sum(bucket))
    return weeks


def active_days(days):
    return sum(1 for _, c in days if c > 0)


def best_week(weeks):
    return max(weeks) if weeks else 0


def top_languages(repo_nodes, limit=6):
    totals = {}
    colors = {}
    for repo in repo_nodes:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or DIM
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    total = sum(totals.values()) or 1
    return [(name, size, size / total, colors[name]) for name, size in ranked]


def ramp_char(count, max_count):
    if max_count <= 0 or count <= 0:
        return RAMP[0]
    level = min(len(RAMP) - 1, int((count / max_count) * (len(RAMP) - 1)) + 1)
    return RAMP[level]


# ------------------------------------------------------------------- svg --
def svg_header(width, height):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-size="12">\n'
        f"<style>{font_face_css()}</style>\n"
        f'<rect width="{width}" height="{height}" fill="{BG}"/>\n'
    )


def svg_footer():
    return "</svg>\n"


def label(x, y, text, size=11, weight=400, fill=INK, anchor="start"):
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'fill="{fill}" text-anchor="{anchor}">{esc(text)}</text>\n'
    )


def esc(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_stats_svg(total, weeks, days_active, best_week_total):
    """Dense three-metric header (total / active days / best week) over a
    full-width weekly sparkline — continuity is defensible at the weekly
    aggregate, even though the underlying daily counts are sparse."""
    W, H = 480, 180
    out = [svg_header(W, H)]

    out.append(label(20, 34, "contributions · last 12 months", size=11, fill=DIM))
    out.append(label(20, 78, f"{total:,}", size=38, weight=700))

    # secondary metrics, right-aligned column
    out.append(label(W - 20, 30, f"{days_active:,}", size=20, weight=700, anchor="end"))
    out.append(label(W - 20, 45, "active days", size=10, fill=DIM, anchor="end"))
    out.append(label(W - 20, 68, f"{best_week_total:,}", size=20, weight=700, anchor="end"))
    out.append(label(W - 20, 83, "best week", size=10, fill=DIM, anchor="end"))

    # full-width weekly sparkline, filled area for a denser feel
    if weeks:
        chart_x, chart_y, chart_w, chart_h = 20, 105, W - 40, 55
        mx = max(weeks) or 1
        n = len(weeks)
        pts = []
        for i, v in enumerate(weeks):
            x = chart_x + (i / max(1, n - 1)) * chart_w
            y = chart_y + chart_h - (v / mx) * chart_h
            pts.append((x, y))
        poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        area = (
            f"{chart_x:.1f},{chart_y+chart_h:.1f} " + poly +
            f" {chart_x+chart_w:.1f},{chart_y+chart_h:.1f}"
        )
        out.append(f'<polygon points="{area}" fill="{ACCENT}" opacity="0.06"/>\n')
        out.append(
            f'<polyline points="{poly}" fill="none" stroke="{ACCENT}" '
            f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>\n'
        )
        # dot on the final point, like a live cursor
        lx, ly = pts[-1]
        out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="2.5" fill="{ACCENT}"/>\n')
        out.append(
            f'<line x1="{chart_x}" y1="{chart_y+chart_h}" x2="{chart_x+chart_w}" '
            f'y2="{chart_y+chart_h}" stroke="{LINE}" stroke-width="1"/>\n'
        )
    out.append(svg_footer())
    return "".join(out)


def build_streak_svg(current_len, current_range, longest_len, longest_range):
    W, H = 480, 120
    out = [svg_header(W, H)]

    def fmt_range(r):
        if not r:
            return "—"
        a = dt.date.fromisoformat(r[0]).strftime("%b %-d")
        b = dt.date.fromisoformat(r[1]).strftime("%b %-d")
        return f"{a} – {b}" if a != b else a

    col_w = W / 2
    out.append(label(20, 34, "current streak", size=11, fill=DIM))
    out.append(label(20, 68, f"{current_len} day{'s' if current_len != 1 else ''}", size=26, weight=700))
    out.append(label(20, 90, fmt_range(current_range), size=11, fill=DIM))

    out.append(f'<line x1="{col_w}" y1="20" x2="{col_w}" y2="{H-20}" stroke="{LINE}"/>\n')

    out.append(label(20 + col_w, 34, "longest streak", size=11, fill=DIM))
    out.append(label(20 + col_w, 68, f"{longest_len} day{'s' if longest_len != 1 else ''}", size=26, weight=700))
    out.append(label(20 + col_w, 90, fmt_range(longest_range), size=11, fill=DIM))

    out.append(svg_footer())
    return "".join(out)


def build_langs_svg(langs):
    W, H = 480, 30 + 26 * max(1, len(langs))
    out = [svg_header(W, H)]
    out.append(label(20, 24, "top languages · by bytes", size=11, fill=DIM))
    bar_x, bar_w = 140, 260
    y = 46
    for name, size, frac, color in langs:
        out.append(label(20, y + 4, name, size=11))
        out.append(
            f'<rect x="{bar_x}" y="{y-9}" width="{bar_w}" height="10" fill="{LINE}"/>\n'
        )
        out.append(
            f'<rect x="{bar_x}" y="{y-9}" width="{max(2, bar_w*frac):.1f}" height="10" fill="{color}"/>\n'
        )
        out.append(label(bar_x + bar_w + 10, y + 4, f"{frac*100:.1f}%", size=10, fill=DIM))
        y += 26
    out.append(svg_footer())
    return "".join(out)


def build_year_svg(days):
    """One character per day, using the portrait's own 13-level ramp,
    laid out as 7 rows (weekdays) x ~52 columns, columns not lines —
    daily contributions are sparse and discrete."""
    cell = 12
    cols = (len(days) + 6) // 7
    W = 40 + cols * cell
    H = 40 + 7 * cell
    max_count = max((c for _, c in days), default=0)
    out = [svg_header(W, H)]
    out.append(label(20, 20, "the year · one character per day", size=11, fill=DIM))

    # Align first day to its weekday row (0=Mon .. 6=Sun, ISO)
    x0, y0 = 20, 34
    for i, (date_str, count) in enumerate(days):
        weekday = dt.date.fromisoformat(date_str).weekday()  # 0=Mon
        col = i // 7
        row = weekday
        ch = ramp_char(count, max_count)
        cx = x0 + col * cell
        cy = y0 + row * cell + 9
        out.append(
            f'<text x="{cx}" y="{cy}" font-size="11" fill="{INK}">{esc(ch)}</text>\n'
        )
    out.append(svg_footer())
    return "".join(out)


# ------------------------------------------------------------------ main --
def main():
    data, start, end = fetch()
    user = data["user"]
    calendar = user["contributionsCollection"]["contributionCalendar"]
    total = calendar["totalContributions"]
    days = flatten_days(calendar)
    weeks = weekly_totals(days)
    cur_len, cur_range, long_len, long_range = compute_streaks(days)
    langs = top_languages(user["repositories"]["nodes"])
    days_active = active_days(days)
    best_week_total = best_week(weeks)

    outputs = {
        "stats.svg": build_stats_svg(total, weeks, days_active, best_week_total),
        "streak.svg": build_streak_svg(cur_len, cur_range, long_len, long_range),
        "langs.svg": build_langs_svg(langs),
        "year.svg": build_year_svg(days),
    }
    for name, svg in outputs.items():
        path = os.path.join(ROOT, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(svg)
        print(f"wrote {name} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()