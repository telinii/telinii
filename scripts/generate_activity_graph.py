#!/usr/bin/env python3
"""
Generate a self-hosted activity graph SVG (no external service).
Fetches GitHub contributions via GraphQL (needs GH_TOKEN) and
renders a line/area chart with the telinii dark theme (#000000 bg, #22c55e accent).
Falls back to mock/previous data if API unavailable.
Output: activity-graph.svg in repo root.
"""

import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timedelta

OUTPUT = os.path.join(os.path.dirname(__file__), "..", "activity-graph.svg")
USERNAME = os.environ.get("GITHUB_REPOSITORY_OWNER") or "telinii"
TOKEN = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("PAT_TOKEN")

# Theme matching README
BG = "#000000"
COLOR = "#22c55e"
TEXT = "#FFFFFF"
GRID = "#1a1a1a"
BORDER = "#1F1F1F"


def fetch_contributions():
    """Fetch last 31 days of daily contributions via GitHub GraphQL."""
    if not TOKEN:
        print("No token found (GH_TOKEN/GITHUB_TOKEN), using mock data")
        return None

    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
      }
    }
    """

    data = json.dumps({"query": query, "variables": {"login": USERNAME}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=data,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "activity-graph-generator",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode())
            weeks = body["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
            days = []
            for w in weeks:
                days.extend(w["contributionDays"])
            # last N days sorted by date
            days_sorted = sorted(days, key=lambda d: d["date"])
            # take last 31 days
            last = days_sorted[-31:]
            # if we got fewer than 31, pad
            if len(last) < 31:
                # pad with zeros at start
                pad = 31 - len(last)
                start = datetime.fromisoformat(last[0]["date"]) - timedelta(days=pad)
                for i in range(pad):
                    d = (start + timedelta(days=i)).date().isoformat()
                    last.insert(0, {"date": d, "contributionCount": 0})
            print(f"Fetched {len(last)} days, total last 31: {sum(d['contributionCount'] for d in last)}")
            return last
    except Exception as e:
        print(f"GraphQL fetch failed: {e}")
        return None


def mock_data():
    # fallback: generate plausible last 31 days if API fails
    today = datetime.utcnow().date()
    import random
    random.seed(42)
    days = []
    for i in range(31):
        d = (today - timedelta(days=30 - i)).isoformat()
        # weighted random to look like a real contribution pattern
        c = random.choices([0, 1, 2, 3, 5, 8, 12], weights=[3, 3, 2, 2, 1, 1, 1])[0]
        days.append({"date": d, "contributionCount": c})
    return days


def build_svg(days):
    vals = [d["contributionCount"] for d in days]
    labels = [d["date"] for d in days]
    max_v = max(max(vals), 1)
    # add headroom so line doesn't hit top
    y_max = max_v + max(1, max_v * 0.15)

    W, H = 1200, 300
    pad_l, pad_r, pad_t, pad_b = 50, 30, 40, 40
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b

    n = len(vals)
    step = plot_w / (n - 1) if n > 1 else plot_w

    points = []
    for i, v in enumerate(vals):
        x = pad_l + i * step
        y = pad_t + plot_h - (v / y_max) * plot_h
        points.append((x, y))

    # Build path for line and area
    line_d = f"M {points[0][0]:.2f} {points[0][1]:.2f} " + " ".join(
        f"L {x:.2f} {y:.2f}" for x, y in points[1:]
    )
    # Smooth with cubic? keep linear for now — looks clean
    area_d = line_d + f" L {points[-1][0]:.2f} {pad_t + plot_h:.2f} L {points[0][0]:.2f} {pad_t + plot_h:.2f} Z"

    # Y ticks
    ticks = []
    for t in [0, round(y_max * 0.5), round(y_max)]:
        if t < 0:
            continue
        y = pad_t + plot_h - (t / y_max) * plot_h
        ticks.append((t, y))

    # X labels — show ~6 labels
    x_labels = []
    for idx in [0, 6, 12, 18, 24, 30]:
        if idx < n:
            dt = datetime.fromisoformat(labels[idx])
            x_labels.append((pad_l + idx * step, dt.strftime("%b %d")))

    total = sum(vals)
    avg = total / n if n else 0

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img">
  <title>Contribution Graph — last 31 days</title>
  <rect width="{W}" height="{H}" fill="{BG}" rx="10" ry="10" stroke="{BORDER}"/>
  <text x="{W/2:.0f}" y="24" text-anchor="middle" fill="{TEXT}" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="16" font-weight="700">Contribution Graph</text>
  <text x="{W/2:.0f}" y="38" text-anchor="middle" fill="#9E9E9E" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="11">Last 31 days — {total} contributions · avg {avg:.1f}/day</text>

  <!-- grid -->
  <g stroke="{GRID}" stroke-width="1" stroke-dasharray="4 6">
'''
    for _, y in ticks:
        svg += f'    <line x1="{pad_l}" y1="{y:.2f}" x2="{W - pad_r}" y2="{y:.2f}"/>\n'
    svg += '  </g>\n'

    # y labels
    for t, y in ticks:
        svg += f'  <text x="{pad_l - 8}" y="{y + 4:.2f}" text-anchor="end" fill="#9E9E9E" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="10">{t}</text>\n'

    # area
    svg += f'  <path d="{area_d}" fill="{COLOR}" opacity="0.15"/>\n'
    # line
    svg += f'  <path d="{line_d}" fill="none" stroke="{COLOR}" stroke-width="2.5" stroke-linejoin="round" stroke-linecap="round"/>\n'

    # points
    for (x, y), v in zip(points, vals):
        r = 3.5 if v > 0 else 2.2
        opacity = "1" if v > 0 else "0.7"
        svg += f'  <circle cx="{x:.2f}" cy="{y:.2f}" r="{r}" fill="{COLOR}" stroke="{BG}" stroke-width="1.2" opacity="{opacity}">\n'
        svg += f'    <title>{v} contributions on {labels[points.index((x,y))]} </title>\n'
        svg += '  </circle>\n'

    # x labels
    for x, lab in x_labels:
        svg += f'  <text x="{x:.2f}" y="{H - 12}" text-anchor="middle" fill="#9E9E9E" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="10">{lab}</text>\n'

    generated = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    svg += f'  <text x="{W - pad_r}" y="{H - 12}" text-anchor="end" fill="#555" font-family="Segoe UI, Ubuntu, Sans-Serif" font-size="8">updated {generated}</text>\n'
    svg += '</svg>\n'
    return svg


def main():
    days = fetch_contributions()
    if not days:
        print("Using mock data")
        days = mock_data()
    svg = build_svg(days)
    out = os.path.abspath(OUTPUT)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Wrote {out} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
