"""Build the "block by block" contribution board (board_dark.svg / board_light.svg).

Reads cache/calendar.json (written by tools/fetch_calendar.py) and renders two
SVGs: one for GitHub's light theme, one for its dark theme. The README stacks
them with <picture>, so the board always matches the viewer's theme.

The idea: a pixel miner walks the calendar one day at a time, and every cell
pops into place behind him. Cells are drawn as GitHub's rounded calendar
squares, so the finished board still reads as a real contribution graph.
Everything is CSS/SMIL inside a static SVG -- no JavaScript, no third-party
image service, no server.

Usage:
    python tools/build_board.py
    python tools/build_board.py --preview 200   # frozen frame, for eyeballing

The animation is open-ended: all timelines share one duration and start at 0,
so the cells, the counter, and the miner never drift apart.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "calendar.json"

# --- Canvas -----------------------------------------------------------------
W = 1014
H = 238
MARGIN = 14
LABEL_COL = 32
PITCH = 18
CELL = 13
GRID_X = MARGIN + LABEL_COL
GRID_Y = 84
HEADER_Y = 24
MONTH_Y = GRID_Y - 14

# --- Timing (seconds) -------------------------------------------------------
STEP = 0.05      # time per day cell
INTRO = 1.2      # miner waits on the first cell before walking
HOLD = 2.2       # finished board stays up before the loop restarts
FADE = 0.6       # the board clears at the end of the loop

# --- Sprite -----------------------------------------------------------------
U = 1.4          # one sprite pixel, in SVG units

MINER = [
    ".....ohhhhhho.....",
    "....ohhhhhhhho....",
    "...ohhhhhhhhhho...",
    "...ohhhhlhhhhho...",
    "...ohhhlllhhhho...",
    "...osssssssssso...",
    "...osesssssseso...",
    "...osesssssseso...",
    "...osssssssssso...",
    "....obbbbbbbbo....",
    "...obbbbbbbbbbo...",
    "...obbbbbbbbbbo...",
    "...obbhhbbhhbbo...",
    "...obbbbbbbbbbo...",
    "....obbo..obbo....",
    "....obbo..obbo....",
    "....oggo..oggo....",
    "....oooo..oooo....",
]

PICKAXE = [
    "..mmmmmm..",
    ".mmmmmmmm.",
    ".mmmmmmmm.",
    "..mmmmmm..",
    "...wwww...",
    "...wwww...",
    "...wwww...",
    "...wwww...",
    "...wwww...",
    "...wwww...",
]

# Handle bottom, in sprite pixels from the feet, at the right hand.
PICKAXE_AT = (14.5, -6.5)

assert len({len(row) for row in MINER}) == 1, "MINER rows must be equal width"
assert len({len(row) for row in PICKAXE}) == 1, "PICKAXE rows must be equal width"

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "fg": "#c9d1d9",
        "muted": "#8b949e",
        "empty": "#21262d",
        "levels": ["#21262d", "#5a2a08", "#923f0a", "#c25e0d", "#f7931a"],
        "accent": "#f7931a",
        "sprite": {
            "o": "#0d1117",
            "h": "#f7931a",
            "l": "#ffe0a3",
            "s": "#e0a97e",
            "e": "#0d1117",
            "b": "#6e7681",
            "g": "#c9d1d9",
            "m": "#c9d1d9",
            "w": "#9a6a43",
        },
    },
    "light": {
        "bg": "#ffffff",
        "fg": "#24292f",
        "muted": "#57606a",
        "empty": "#ebedf0",
        "levels": ["#ebedf0", "#ffd9b3", "#ffab57", "#e07b12", "#b35f00"],
        "accent": "#b35f00",
        "sprite": {
            "o": "#24292f",
            "h": "#f7931a",
            "l": "#ffe0a3",
            "s": "#e0a97e",
            "e": "#24292f",
            "b": "#6e7681",
            "g": "#57606a",
            "m": "#6e7781",
            "w": "#9a6a43",
        },
    },
}


def load() -> dict:
    data = json.loads(CACHE.read_text())
    weeks = data["weeks"]
    last = dt.date.fromisoformat(max(d["date"] for w in weeks for d in w))
    days = []
    for wi, week in enumerate(weeks):
        for day in week:
            date = dt.date.fromisoformat(day["date"])
            if date > last:
                continue
            days.append(
                {
                    "week": wi,
                    "weekday": day["weekday"],
                    "date": date,
                    "count": day["contributionCount"],
                }
            )
    data["days"] = days
    data["total"] = sum(d["count"] for d in days)
    data["as_of"] = last
    return data


def levels(days: list[dict]) -> dict[str, int]:
    """Bucket counts into four levels with GitHub-style quartile cut-offs."""
    counts = sorted(d["count"] for d in days if d["count"] > 0)
    if not counts:
        return {"q1": 1, "q2": 2, "q3": 3}
    pick = lambda p: counts[min(len(counts) - 1, int(len(counts) * p))]  # noqa: E731
    return {"q1": pick(0.25), "q2": pick(0.5), "q3": pick(0.75)}


def level_of(count: int, q: dict[str, int]) -> int:
    if count <= 0:
        return 0
    if count <= q["q1"]:
        return 1
    if count <= q["q2"]:
        return 2
    if count <= q["q3"]:
        return 3
    return 4


def cell_xy(day: dict) -> tuple[float, float]:
    x = GRID_X + day["week"] * PITCH + (PITCH - CELL) / 2
    y = GRID_Y + day["weekday"] * PITCH + (PITCH - CELL) / 2
    return x, y


def walk(days: list[dict]) -> list[dict]:
    """Serpentine order: Sunday left-to-right, Monday right-to-left, ..."""
    by_weekday: dict[int, list[dict]] = {w: [] for w in range(7)}
    for day in days:
        by_weekday[day["weekday"]].append(day)
    ordered = []
    for weekday in range(7):
        row = sorted(by_weekday[weekday], key=lambda d: d["week"])
        if weekday % 2:
            row.reverse()
        ordered.extend(row)
    return ordered


def sprite_path(rows: list[str], colors: dict[str, str]) -> str:
    """Merge a pixel grid into one path per colour (no anti-aliased seams)."""
    by_colour: dict[str, list[str]] = {}
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            ch = row[x]
            if ch == ".":
                x += 1
                continue
            run = x
            while run < len(row) and row[run] == ch:
                run += 1
            by_colour.setdefault(ch, []).append(
                f"M{x * U:.2f} {(y - len(rows)) * U:.2f}"
                f"h{(run - x) * U:.2f}v{U:.2f}h-{(run - x) * U:.2f}z"
            )
            x = run
    out = []
    for ch, segments in by_colour.items():
        colour = colors[ch]
        out.append(f'<path fill="{colour}" d="{"".join(segments)}"/>')
    return "".join(out)


def month_labels(data: dict, theme: dict) -> list[str]:
    labels = []
    last_x = -999.0
    last_month = None
    for wi, week in enumerate(data["weeks"]):
        for day in week:
            date = dt.date.fromisoformat(day["date"])
            if date > data["as_of"]:
                continue
            month = date.strftime("%b")
            if month != last_month:
                x = GRID_X + wi * PITCH
                if x - last_x >= 3 * PITCH:
                    labels.append(
                        f'<text x="{x:.1f}" y="{MONTH_Y}" fill="{theme["muted"]}"'
                        f' font-size="11">{month}</text>'
                    )
                    last_x = x
                last_month = month
            break
    return labels


def build(theme_name: str, data: dict, preview_at: int | None = None) -> str:
    theme = THEMES[theme_name]
    days = data["days"]
    order = walk(days)
    q = levels(days)
    n = len(order)
    total = data["total"]
    as_of = data["as_of"].isoformat()

    cumulative = 0
    for day in order:
        cumulative += day["count"]
        day["running"] = cumulative

    end = INTRO + n * STEP
    duration = round(end + HOLD + FADE, 1)

    css = [
        "text{font-family:Consolas,'Liberation Mono',Menlo,monospace}",
        ".cell{transform-box:fill-box;transform-origin:center}",
    ]
    cells = []
    for i, day in enumerate(order):
        x, y = cell_xy(day)
        colour = theme["levels"][level_of(day["count"], q)]
        if preview_at is None:
            t = INTRO + i * STEP
            p0 = max(0.0, (t - 0.18) / duration * 100)
            p1 = t / duration * 100
            p2 = (duration - FADE) / duration * 100
            pop = min(p1 + 0.5, 99.9)
            if colour == theme["empty"]:
                css.append(
                    f".c{i}{{animation:c{i} {duration}s linear infinite}}"
                    f"@keyframes c{i}{{0%,{p0:.2f}%{{transform:scale(.92)}}"
                    f"{p1:.2f}%{{transform:scale(1.2)}}"
                    f"{pop:.2f}%{{transform:scale(1)}}100%{{transform:scale(1)}}}}"
                )
            else:
                css.append(
                    f".c{i}{{animation:c{i} {duration}s linear infinite}}"
                    f"@keyframes c{i}{{0%,{p0:.2f}%{{transform:scale(.92);fill:{theme['empty']}}}"
                    f"{p1:.2f}%{{transform:scale(1.2);fill:{colour}}}"
                    f"{pop:.2f}%{{transform:scale(1)}}"
                    f"{p2:.2f}%{{fill:{colour}}}"
                    f"100%{{transform:scale(1);fill:{theme['empty']}}}}}"
                )
            klass = f' class="cell c{i}"'
            fill = theme["empty"]
        else:
            klass = ' class="cell"'
            fill = colour
        cells.append(
            f'<rect{klass} x="{x:.1f}" y="{y:.1f}" width="{CELL}"'
            f' height="{CELL}" rx="2.4" fill="{fill}"/>'
        )

    # --- Miner position animation -------------------------------------------
    points = []
    for day in order:
        x, y = cell_xy(day)
        points.append((x + CELL / 2, y + CELL - 2))
    if preview_at is not None:
        current = points[min(preview_at, n - 1)]
        miner_transform = f'transform="translate({current[0]:.1f} {current[1]:.1f})"'
        miner_motion = ""
    else:
        key_times = ["0", f"{(INTRO / duration):.5f}"]
        values = [points[0], points[0]]
        for i in range(1, n):
            key_times.append(f"{(INTRO + i * STEP) / duration:.5f}")
            values.append(points[i])
        vals = ";".join(f"{x:.1f} {y:.1f}" for x, y in values)
        kts = ";".join(key_times)
        miner_transform = ""
        miner_motion = (
            f'<animateTransform attributeName="transform" type="translate"'
            f' values="{vals}" keyTimes="{kts}" calcMode="discrete"'
            f' dur="{duration}s" repeatCount="indefinite"/>'
        )

    # --- Counter (one label per milestone; SMIL swaps them) -----------------
    milestones = []
    steps = 24
    indexes = sorted({round(k * (n - 1) / (steps - 1)) for k in range(steps)})
    for k, idx in enumerate(indexes):
        value = order[idx]["running"]
        label = f"{value} contribution{'s' if value != 1 else ''} in the last year"
        if preview_at is not None:
            if idx <= preview_at:
                milestones.append((idx, value, label))
            continue
        start = (INTRO + idx * STEP) / duration
        stop = (
            (INTRO + indexes[k + 1] * STEP) / duration
            if k + 1 < len(indexes)
            else (duration - FADE) / duration
        )
        milestones.append((start, stop, label))

    counter_xml = []
    if preview_at is not None:
        value = order[min(preview_at, n - 1)]["running"]
        text = f"{value} contribution{'s' if value != 1 else ''} in the last year"
        counter_xml.append(
            f'<text x="{MARGIN}" y="{HEADER_Y}" fill="{theme["fg"]}"'
            f' font-size="14">{escape(text)}</text>'
        )
    else:
        for k, (start, stop, label) in enumerate(milestones):
            if k == 0:
                anim = (
                    f'<animate attributeName="opacity" values="1;0"'
                    f' keyTimes="0;{stop:.5f}" calcMode="discrete"'
                    f' dur="{duration}s" repeatCount="indefinite"/>'
                )
            else:
                anim = (
                    f'<animate attributeName="opacity" values="0;1;0"'
                    f' keyTimes="0;{start:.5f};{stop:.5f}" calcMode="discrete"'
                    f' dur="{duration}s" repeatCount="indefinite"/>'
                )
            counter_xml.append(
                f'<text x="{MARGIN}" y="{HEADER_Y}" fill="{theme["fg"]}"'
                f' font-size="14" opacity="0">{escape(label)}{anim}</text>'
            )

    # --- Static chrome ------------------------------------------------------
    weekday_labels = "".join(
        f'<text x="{GRID_X - 8}" y="{GRID_Y + row * PITCH + 11}"'
        f' text-anchor="end" fill="{theme["muted"]}" font-size="10.5">'
        f"{name}</text>"
        for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri"))
    )

    legend_x = W - MARGIN - 5 * 14 - 40
    legend = (
        f'<text x="{legend_x - 8}" y="{H - 12}" text-anchor="end"'
        f' fill="{theme["muted"]}" font-size="10.5">Less</text>'
        + "".join(
            f'<rect x="{legend_x + i * 14}" y="{H - 22}" width="11" height="11"'
            f' rx="2" fill="{theme["levels"][i]}"/>'
            for i in range(5)
        )
        + f'<text x="{legend_x + 5 * 14 + 4}" y="{H - 12}"'
        f' fill="{theme["muted"]}" font-size="10.5">More</text>'
    )

    sprite_w = len(MINER[0]) * U
    miner = (
        f'<g {"class=\"miner\"" if preview_at is None else ""} {miner_transform}>'
        f"{miner_motion}"
        f'<g {"class=\"hop\"" if preview_at is None else ""}>'
        f'<g transform="translate({-sprite_w / 2:.1f} 0)">'
        f"{sprite_path(MINER, theme['sprite'])}"
        f'<g transform="translate({PICKAXE_AT[0] * U:.1f} {PICKAXE_AT[1] * U:.1f})">'
        + (
            '<g>'
            '<animateTransform attributeName="transform" type="rotate"'
            ' values="8;46;8" keyTimes="0;0.55;1" dur="0.42s"'
            ' repeatCount="indefinite"/>'
            f"{sprite_path(PICKAXE, theme['sprite'])}</g>"
            if preview_at is None
            else f'<g transform="rotate(18)">{sprite_path(PICKAXE, theme["sprite"])}</g>'
        )
        + "</g></g></g></g>"
    )

    animations = ""
    if preview_at is None:
        animations = (
            "<style>"
            + "".join(css)
            + f".miner{{animation:fade {duration}s linear infinite}}"
            + f".hop{{animation:hop .42s ease-in-out infinite}}"
            + f"@keyframes fade{{0%,97%{{opacity:1}}99%,100%{{opacity:0}}}}"
            + "@keyframes hop{0%,100%{transform:translateY(0)}50%{transform:translateY(-2.4px)}}"
            + "</style>"
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
<title id="title">{total} contributions in the last year, mined block by block</title>
<desc id="desc">An animated contribution calendar. A pixel miner walks the grid and each day pops into place behind him.</desc>
{animations}
<rect width="{W}" height="{H}" fill="{theme['bg']}"/>
{''.join(counter_xml)}
<text x="{W - MARGIN}" y="{HEADER_Y}" text-anchor="end" fill="{theme['accent']}" font-size="12" letter-spacing="2">BLOCK BY BLOCK</text>
{weekday_labels}
{''.join(month_labels(data, theme))}
{''.join(cells)}
{legend}
<text x="{MARGIN}" y="{H - 12}" fill="{theme['muted']}" font-size="10.5">updated {as_of}</text>
{miner}
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=int, default=None, metavar="N",
                        help="write preview_<theme>.svg frozen at walk step N")
    args = parser.parse_args()

    data = load()
    for theme_name in THEMES:
        if args.preview is None:
            out = ROOT / f"board_{theme_name}.svg"
        else:
            out = ROOT / f"preview_{theme_name}.svg"
        out.write_text(build(theme_name, data, args.preview))
        print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
