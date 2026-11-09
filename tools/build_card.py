"""Build the neofetch-style profile card (card_light.svg / card_dark.svg).

The left column is the committed ASCII portrait (assets/ascii-art.txt, see
tools/make_ascii.py). The right column is a dot-leader panel with role, stack,
projects, contacts and a few live GitHub numbers pulled from the same
cache/calendar.json as the contribution board.

Everything is laid out in character cells so the panel stays aligned: values
are right-aligned by padding with dots to PANEL_COLS.
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ART = ROOT / "assets" / "ascii-art.txt"
CACHE = ROOT / "cache" / "calendar.json"

W = 1014
H = 444

ART_X = 24
ART_TOP = 22
ART_FONT = 14.0
ART_LINE = 16.8

PANEL_X = 464
PANEL_COLS = 62
TITLE_Y = 34
FIRST_ROW_Y = 62
LINE = 20

THEMES = {
    "dark": {
        "bg": "#161b22",
        "border": "#30363d",
        "art": "#c9d1d9",
        "fg": "#c9d1d9",
        "muted": "#8b949e",
        "key": "#f7931a",
        "value": "#a5d6ff",
        "dot": "#6e7681",
    },
    "light": {
        "bg": "#ffffff",
        "border": "#d0d7de",
        "art": "#24292f",
        "fg": "#24292f",
        "muted": "#57606a",
        "key": "#b35c00",
        "value": "#0550ae",
        "dot": "#8c959f",
    },
}


def numbers() -> tuple[int | None, int, int]:
    data = json.loads(CACHE.read_text())
    days = [day for week in data["weeks"] for day in week]
    total = sum(day["contributionCount"] for day in days)
    active = sum(1 for day in days if day["contributionCount"] > 0)
    return data.get("repos"), total, active


def art_rows() -> list[str]:
    return ART.read_text().rstrip("\n").split("\n")


def text_row(y: int, spans: list[tuple[str, str, bool]], theme: dict) -> str:
    inner = "".join(
        f'<tspan fill="{colour}"{" font-weight=\"bold\"" if bold else ""}>{escape(text)}</tspan>'
        for text, colour, bold in spans
    )
    return f'<text x="{PANEL_X}" y="{y}" font-size="14" xml:space="preserve">{inner}</text>'


def row(y: int, key: str, value: str, theme: dict) -> str:
    left = f"{key}:"
    dots = PANEL_COLS - len(left) - len(value)
    if dots < 1:
        value = value[: max(1, PANEL_COLS - len(left) - 1)]
        dots = 1
    return text_row(
        y,
        [(left, theme["key"], False), ("." * dots, theme["dot"], False), (value, theme["value"], False)],
        theme,
    )


def section(y: int, label: str, theme: dict) -> str:
    left = f"- {label} "
    dashes = "-" * max(0, PANEL_COLS - len(left))
    return text_row(y, [(left, theme["muted"], False), (dashes, theme["dot"], False)], theme)


def build(theme_name: str) -> str:
    theme = THEMES[theme_name]
    repos, total, active = numbers()

    art = art_rows()
    art_text = (
        f'<text x="{ART_X}" y="{ART_TOP + ART_FONT - 2:.1f}" fill="{theme["art"]}"'
        f' font-size="{ART_FONT}" xml:space="preserve">'
        + escape(art[0])
        + "".join(
            f'<tspan x="{ART_X}" dy="{ART_LINE}">{escape(line)}</tspan>'
            for line in art[1:]
        )
        + "</text>"
    )

    name = "senasgr@dedoo"
    dashes = "-" * (PANEL_COLS - len(name) - 1)
    blocks = [
        text_row(
            TITLE_Y,
            [(name, theme["key"], True), (f" {dashes}", theme["dot"], False)],
            theme,
        )
    ]

    layout: list[tuple] = [
        ("row", "Role", "Blockchain engineer"),
        ("row", "Focus", "Scrypt AuxPoW · UTXO metaprotocols"),
        ("row", "Languages", "Rust, TypeScript, Go, C++, Python"),
        ("blank",),
        ("section", "Projects"),
        ("row", "Dedoo", "dedoo.xyz — explorer, PSOB, wallets"),
        ("blank",),
        ("section", "Contact"),
        ("row", "GitHub", "senasgr-eth"),
        ("row", "Telegram", "@senasgr"),
        ("row", "X", "@senasgr"),
        ("row", "Blog", "blog.s3na.xyz"),
        ("blank",),
        ("section", "GitHub Stats"),
        ("row", "Repos", f"{repos if repos is not None else '—'} public"),
        ("row", "Contributions", f"{total} in the last year"),
        ("row", "Active days", str(active)),
    ]

    y = FIRST_ROW_Y
    for item in layout:
        if item[0] == "row":
            blocks.append(row(y, item[1], item[2], theme))
        elif item[0] == "section":
            blocks.append(section(y, item[1], theme))
        y += LINE

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-labelledby="title desc">
<title id="title">Senasgr — Blockchain engineer</title>
<desc id="desc">An ASCII portrait of Senasgr beside a terminal panel listing role, focus, languages, projects, contacts and GitHub numbers.</desc>
<style>text{{font-family:Consolas,'Liberation Mono',Menlo,monospace}}</style>
<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="10" fill="{theme['bg']}" stroke="{theme['border']}"/>
{art_text}
{''.join(blocks)}
</svg>
"""


def main() -> None:
    for theme_name in THEMES:
        out = ROOT / f"card_{theme_name}.svg"
        out.write_text(build(theme_name))
        print(f"wrote {out.name} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
