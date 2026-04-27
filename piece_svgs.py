"""Generate stylized SVG icons for the four track piece types.

Each function returns an SVG string. The CLI writes them to
``static/pieces_svg/<name>.svg`` so they can be referenced from templates with
a plain ``<img>`` tag.

Run with:
    python piece_svgs.py
"""
import os
from math import cos, pi, sin


# Shared style constants
STROKE_TIE = "#6d4c41"       # brown sleepers
STROKE_BALLAST = "#9e9e9e"   # grey track bed
STROKE_RAIL = "#37474f"      # dark grey rails
TIE_W = 34                   # wide brown stroke width (sleepers stick out the sides)
BALLAST_W = 22               # grey stroke width on top of ties
RAIL_W = 1.6                 # rail line width
RAIL_OFFSET = 7              # rails sit at +/- this from the centerline
TIE_DASH = "5 6"             # dash pattern for ties

VIEWBOX = "-50 -50 100 100"


def _svg(body: str, viewbox: str = VIEWBOX) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}" '
        f'preserveAspectRatio="xMidYMid meet">{body}</svg>'
    )


def _ties_line(x1, y1, x2, y2):
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{STROKE_TIE}" stroke-width="{TIE_W}" '
        f'stroke-dasharray="{TIE_DASH}"/>'
    )


def _ballast_line(x1, y1, x2, y2):
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{STROKE_BALLAST}" stroke-width="{BALLAST_W}"/>'
    )


def _rail_line(x1, y1, x2, y2):
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
        f'stroke="{STROKE_RAIL}" stroke-width="{RAIL_W}"/>'
    )


def _ties_arc(d):
    return (
        f'<path d="{d}" fill="none" stroke="{STROKE_TIE}" '
        f'stroke-width="{TIE_W}" stroke-dasharray="{TIE_DASH}"/>'
    )


def _ballast_arc(d):
    return (
        f'<path d="{d}" fill="none" stroke="{STROKE_BALLAST}" '
        f'stroke-width="{BALLAST_W}"/>'
    )


def _rail_arc(d):
    return (
        f'<path d="{d}" fill="none" stroke="{STROKE_RAIL}" '
        f'stroke-width="{RAIL_W}"/>'
    )


def straight_svg() -> str:
    body = (
        _ties_line(0, -48, 0, 48)
        + _ballast_line(0, -48, 0, 48)
        + _rail_line(-RAIL_OFFSET, -48, -RAIL_OFFSET, 48)
        + _rail_line(RAIL_OFFSET, -48, RAIL_OFFSET, 48)
    )
    return _svg(body)


def curve_svg() -> str:
    # 90 deg arc: center (40, 40), radius R; from (-30,40) to (40,-30).
    R = 70
    body = (
        _ties_arc(f"M -30 40 A {R} {R} 0 0 1 40 -30")
        + _ballast_arc(f"M -30 40 A {R} {R} 0 0 1 40 -30")
        + _rail_arc(f"M -23 40 A {R - RAIL_OFFSET} {R - RAIL_OFFSET} 0 0 1 40 -23")
        + _rail_arc(f"M -37 40 A {R + RAIL_OFFSET} {R + RAIL_OFFSET} 0 0 1 40 -37")
    )
    return _svg(body)


def switch_svg() -> str:
    # Stem from y=48 up to y=20, then two arcs splitting up-left and up-right.
    R = 60
    inner = R - RAIL_OFFSET
    outer = R + RAIL_OFFSET
    body = (
        # ties (brown)
        f'<g fill="none" stroke="{STROKE_TIE}" stroke-width="{TIE_W}" '
        f'stroke-dasharray="{TIE_DASH}">'
        f'<line x1="0" y1="48" x2="0" y2="20"/>'
        f'<path d="M 0 20 A {R} {R} 0 0 0 -42 -22"/>'
        f'<path d="M 0 20 A {R} {R} 0 0 1 42 -22"/>'
        f'</g>'
        # ballast (grey)
        f'<g fill="none" stroke="{STROKE_BALLAST}" stroke-width="{BALLAST_W}">'
        f'<line x1="0" y1="48" x2="0" y2="20"/>'
        f'<path d="M 0 20 A {R} {R} 0 0 0 -42 -22"/>'
        f'<path d="M 0 20 A {R} {R} 0 0 1 42 -22"/>'
        f'</g>'
        # rails (dark grey)
        f'<g fill="none" stroke="{STROKE_RAIL}" stroke-width="{RAIL_W}">'
        f'<line x1="-{RAIL_OFFSET}" y1="48" x2="-{RAIL_OFFSET}" y2="20"/>'
        f'<line x1="{RAIL_OFFSET}"  y1="48" x2="{RAIL_OFFSET}"  y2="20"/>'
        f'<path d="M -{RAIL_OFFSET} 20 A {inner} {inner} 0 0 0 -44 -15"/>'
        f'<path d="M {RAIL_OFFSET}  20 A {outer} {outer} 0 0 0 -40 -29"/>'
        f'<path d="M -{RAIL_OFFSET} 20 A {outer} {outer} 0 0 1 40 -29"/>'
        f'<path d="M {RAIL_OFFSET}  20 A {inner} {inner} 0 0 1 44 -15"/>'
        f'</g>'
    )
    return _svg(body)


def crossing_svg() -> str:
    # Two straight arms crossed at 60 degrees. Each arm is l0 long total
    # (matches geometry), so half-length matches the straight icon (48 SVG
    # units == l0/2 in geometry-space, scale 2.4).
    H = 48

    # Render ties for both arms first, then ballast, then rails, so the layers
    # stack correctly even at the crossing point.
    body = (
        # ties for both arms
        f'<g>'
        f'<line x1="0" y1="-{H}" x2="0" y2="{H}" stroke="{STROKE_TIE}" '
        f'stroke-width="{TIE_W}" stroke-dasharray="{TIE_DASH}"/>'
        f'<line x1="0" y1="-{H}" x2="0" y2="{H}" stroke="{STROKE_TIE}" '
        f'stroke-width="{TIE_W}" stroke-dasharray="{TIE_DASH}" transform="rotate(60)"/>'
        f'</g>'
        # ballast for both arms
        f'<g>'
        f'<line x1="0" y1="-{H}" x2="0" y2="{H}" stroke="{STROKE_BALLAST}" '
        f'stroke-width="{BALLAST_W}"/>'
        f'<line x1="0" y1="-{H}" x2="0" y2="{H}" stroke="{STROKE_BALLAST}" '
        f'stroke-width="{BALLAST_W}" transform="rotate(60)"/>'
        f'</g>'
        # rails
        f'<g stroke="{STROKE_RAIL}" stroke-width="{RAIL_W}">'
        f'<line x1="-{RAIL_OFFSET}" y1="-{H}" x2="-{RAIL_OFFSET}" y2="{H}"/>'
        f'<line x1="{RAIL_OFFSET}"  y1="-{H}" x2="{RAIL_OFFSET}"  y2="{H}"/>'
        f'<line x1="-{RAIL_OFFSET}" y1="-{H}" x2="-{RAIL_OFFSET}" y2="{H}" transform="rotate(60)"/>'
        f'<line x1="{RAIL_OFFSET}"  y1="-{H}" x2="{RAIL_OFFSET}"  y2="{H}" transform="rotate(60)"/>'
        f'</g>'
    )
    return _svg(body)


PIECE_SVGS = {
    'straight': straight_svg,
    'curve': curve_svg,
    'switch': switch_svg,
    'crossing': crossing_svg,
}


def write_all(out_dir: str) -> None:
    os.makedirs(out_dir, exist_ok=True)
    for name, fn in PIECE_SVGS.items():
        path = os.path.join(out_dir, f'{name}.svg')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(fn())
        print(f'wrote {path}')


if __name__ == '__main__':
    here = os.path.dirname(os.path.abspath(__file__))
    write_all(os.path.join(here, 'static', 'pieces_svg'))
