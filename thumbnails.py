import os

from helpers import app
from geometry import PIECE_TYPES
from sql_layouts import layouts_parse, layouts_build


def _thumb_dir():
    return os.path.join(app.static_folder, 'thumbnails')


def thumbnail_file(track_id):
    return os.path.join(_thumb_dir(), f'{track_id}.svg')


def thumbnail_url(track_id):
    return f'/static/thumbnails/{track_id}.svg'


def generate_thumbnail(track_id):
    """Generate (or regenerate) an SVG thumbnail for a track layout."""
    pieces, connections = layouts_parse(track_id)

    if len(pieces) == 0:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" '
            'preserveAspectRatio="xMidYMid meet">'
            '<rect width="100" height="100" fill="#f5f5f5"/>'
            '<text x="50" y="54" text-anchor="middle" font-size="12" '
            'fill="#999" font-family="sans-serif">empty</text>'
            '</svg>'
        )
    else:
        pathes, _, _ = layouts_build(pieces, connections)
        xs = [pt['x'] for path in pathes for pt in path]
        ys = [pt['y'] for path in pathes for pt in path]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)

        # Make sure the box is square-ish and add some padding
        w = max(maxx - minx, 1)
        h = max(maxy - miny, 1)
        pad = max(w, h) * 0.08 + 1
        minx -= pad
        maxx += pad
        miny -= pad
        maxy += pad
        w = maxx - minx
        h = maxy - miny

        stroke = max(w, h) * 0.012
        polys = []
        for path in pathes:
            # Canvas inverts y; mirror here so the SVG matches the editor view
            pts = ' '.join(f'{pt["x"]:.2f},{-pt["y"]:.2f}' for pt in path)
            polys.append(
                f'<polygon points="{pts}" fill="none" stroke="#222" '
                f'stroke-width="{stroke:.3f}" stroke-linejoin="round"/>'
            )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="{minx:.2f} {-maxy:.2f} {w:.2f} {h:.2f}" '
            f'preserveAspectRatio="xMidYMid meet">'
            f'<rect x="{minx:.2f}" y="{-maxy:.2f}" width="{w:.2f}" '
            f'height="{h:.2f}" fill="#fafafa"/>'
            f'{"".join(polys)}'
            f'</svg>'
        )

    os.makedirs(_thumb_dir(), exist_ok=True)
    with open(thumbnail_file(track_id), 'w', encoding='utf-8') as f:
        f.write(svg)


def delete_thumbnail(track_id):
    path = thumbnail_file(track_id)
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def piece_counts(track_id):
    from sql_layouts import pieces_read
    pieces = [i['piece'] for i in pieces_read(track_id=track_id)]
    return {p: sum(1 for x in pieces if x == p) for p in PIECE_TYPES}
