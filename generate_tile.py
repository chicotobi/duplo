#!/usr/bin/env python3
"""Generate the scenery tile for the Duplo track editor.

1. Reads cartoon icons from  static/tile_assets/
2. Removes their light-grey background, saves cleaned PNGs to static/tile_assets_clean/
3. Renders a room-sized tile (1875×1250 world-units at 2×) with:
     - flat green meadow
     - river + tributary + lake
     - scattered asset sprites (mountains, houses, trees, flowers,
       sheep, cows, horses, birds)
4. Saves the result to  static/tiles/meadow.png

Run:  python generate_tile.py
"""

import argparse, math, os, random
from PIL import Image, ImageDraw

# ── world constants (must match app) ──
MM_PER_UNIT = 3.2
ROOM_W_M, ROOM_H_M = 6, 4
TILE_W = ROOM_W_M * 1000 / MM_PER_UNIT   # 1875 world-units
TILE_H = ROOM_H_M * 1000 / MM_PER_UNIT   # 1250 world-units
RES = 2
PX_W, PX_H = int(TILE_W * RES), int(TILE_H * RES)

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(HERE, 'static', 'tile_assets')
CLEAN_DIR  = os.path.join(HERE, 'static', 'tile_assets_clean')
OUT_DIR    = os.path.join(HERE, 'static', 'tiles')


# ══════════════════════════════════════════════════════════
#  STEP 1 — Background removal
# ══════════════════════════════════════════════════════════

def remove_background(img, tolerance=8):
    """Flood-fill from all four corners to make the background transparent.

    Pixels within `tolerance` of the corner colour are made transparent,
    using a simple connected-component flood-fill so interior pixels of
    similar colour are preserved.
    """
    img = img.convert('RGBA')
    pixels = img.load()
    w, h = img.size

    bg_color = pixels[0, 0][:3]  # sample from top-left corner

    def close_enough(c):
        return all(abs(c[i] - bg_color[i]) <= tolerance for i in range(3))

    visited = set()
    queue = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    for seed in list(queue):
        if close_enough(pixels[seed[0], seed[1]]):
            visited.add(seed)
        else:
            queue.remove(seed)

    while queue:
        x, y = queue.pop()
        pixels[x, y] = (0, 0, 0, 0)
        for nx, ny in [(x-1, y), (x+1, y), (x, y-1), (x, y+1)]:
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                visited.add((nx, ny))
                if close_enough(pixels[nx, ny]):
                    queue.append((nx, ny))

    return img


def prepare_assets():
    """Load all tile assets (already cleaned PNGs with transparency)."""
    assets = {}
    for fname in sorted(os.listdir(ASSETS_DIR)):
        if not fname.lower().endswith('.png'):
            continue
        name = os.path.splitext(fname)[0]
        img = Image.open(os.path.join(ASSETS_DIR, fname)).convert('RGBA')
        print(f'  {fname:15s}  {img.width}x{img.height}')
        assets[name] = img
    return assets


# ══════════════════════════════════════════════════════════
#  STEP 2 — Render the base tile (meadow + water)
# ══════════════════════════════════════════════════════════

def px(x): return x * RES
def py(y): return y * RES


def rotated_ellipse(draw, cx, cy, rx, ry, angle, fill):
    pts = []
    for i in range(48):
        a = i * math.pi * 2 / 48
        x = rx * math.cos(a)
        y = ry * math.sin(a)
        xr = x * math.cos(angle) - y * math.sin(angle)
        yr = x * math.sin(angle) + y * math.cos(angle)
        pts.append((cx + xr, cy + yr))
    draw.polygon(pts, fill=fill)


def cubic_bspline(control_pts, n_out=200):
    """Evaluate a cubic B-spline through `control_pts`, returning `n_out` smooth points."""
    cp = list(control_pts)
    # clamp ends by tripling first/last point
    cp = [cp[0], cp[0]] + cp + [cp[-1], cp[-1]]
    segments = len(cp) - 3
    pts = []
    for i in range(segments):
        p0, p1, p2, p3 = cp[i], cp[i+1], cp[i+2], cp[i+3]
        steps = max(1, n_out // segments)
        for j in range(steps):
            t = j / steps
            t2, t3 = t*t, t*t*t
            # cubic B-spline basis
            b0 = (-t3 + 3*t2 - 3*t + 1) / 6
            b1 = (3*t3 - 6*t2 + 4) / 6
            b2 = (-3*t3 + 3*t2 + 3*t + 1) / 6
            b3 = t3 / 6
            x = b0*p0[0] + b1*p1[0] + b2*p2[0] + b3*p3[0]
            y = b0*p0[1] + b1*p1[1] + b2*p2[1] + b3*p3[1]
            pts.append((x, y))
    pts.append(cp[-2])  # ensure we end at the last control point
    return pts


def make_river(seed, x0, y0, x1, y1, n_ctrl, amp1, freq1, amp2, freq2):
    """Generate a smooth river path using spline-interpolated control points."""
    r = random.Random(seed)
    ddx, ddy = x1 - x0, y1 - y0
    length = math.hypot(ddx, ddy)
    tx, ty = ddx / length, ddy / length
    nx, ny = -ty, tx
    ctrl = []
    for i in range(n_ctrl + 1):
        t = i / n_ctrl
        along = t * length
        wobble = (amp1 * math.sin(along * freq1) +
                  amp2 * math.cos(along * freq2) +
                  (r.random() - 0.5) * 15)
        ctrl.append((x0 + tx * along + nx * wobble,
                      y0 + ty * along + ny * wobble))
    return cubic_bspline(ctrl, n_out=300)


def make_lake_shape(seed, cx, cy, rx, ry, wobble_r, wobble_a, n_ctrl=16):
    """Generate a smooth lake outline using spline-interpolated control points."""
    r = random.Random(seed)
    ctrl = []
    for i in range(n_ctrl):
        a = i * math.pi * 2 / n_ctrl
        ctrl.append((
            cx + (rx + (r.random() - 0.5) * wobble_r) * math.cos(a),
            cy + (ry + (r.random() - 0.5) * wobble_a) * math.sin(a),
        ))
    # close the loop: repeat first few points
    ctrl_loop = ctrl + ctrl[:3]
    smooth = cubic_bspline(ctrl_loop, n_out=200)
    return smooth


def draw_thick_spline(draw, pts, width, fill):
    """Draw a spline path as a series of overlapping circles for rounded edges."""
    r = width // 2
    for x, y in pts:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)
    # also draw line segments for fill between circles
    draw.line(pts, fill=fill, width=width, joint='curve')


def render_base(seed=42):
    """Return an RGBA image with meadow + water."""
    img = Image.new('RGBA', (PX_W, PX_H), (127, 191, 82, 255))
    draw = ImageDraw.Draw(img)

    # Lake in bottom-left quadrant
    lake_cx, lake_cy = TILE_W * 0.25, TILE_H * 0.72
    lake = make_lake_shape(seed + 3, lake_cx, lake_cy,
                           120, 80, 35, 25, n_ctrl=16)

    # Wide river — gentle curves, from bottom-right to lake (bottom-left)
    wide = make_river(seed,
                      TILE_W * 0.85, TILE_H * 0.80,
                      lake_cx + 60, lake_cy,
                      12, 20, 0.008, 8, 0.02)

    # Narrow river 1 — curvy, from top-left into the lake
    narrow1 = make_river(seed + 1,
                         TILE_W * 0.08, TILE_H * 0.02,
                         lake_cx - 40, lake_cy - 50,
                         20, 40, 0.015, 18, 0.05)

    # Narrow river 2 — curvy, from right side into the wide river (bottom center)
    narrow2 = make_river(seed + 2,
                         TILE_W * 0.95, TILE_H * 0.55,
                         TILE_W * 0.55, TILE_H * 0.78,
                         18, 35, 0.02, 15, 0.06)

    # Draw narrow2 first, then wide river on top to cover junction
    water = (75, 163, 199)
    hilite = (174, 214, 241)
    for pts, w_base, w_hi in [(narrow2, 10, 3), (narrow1, 10, 3), (wide, 22, 7)]:
        pixel_pts = [(px(x), py(y)) for x, y in pts]
        draw_thick_spline(draw, pixel_pts, int(w_base * RES), water)
    for pts, w_base, w_hi in [(narrow2, 10, 3), (narrow1, 10, 3), (wide, 22, 7)]:
        pixel_pts = [(px(x), py(y)) for x, y in pts]
        draw_thick_spline(draw, pixel_pts, int(w_hi * RES), hilite)

    # Lake on top — covers river endpoints
    lake_px = [(px(x), py(y)) for x, y in lake]
    draw.polygon(lake_px, fill=(75, 163, 199))
    # Lake highlight
    rotated_ellipse(draw, px(lake_cx - 15), py(lake_cy + 5),
                    px(50), py(22), -0.2, fill=(174, 214, 241, 100))

    return img


# ══════════════════════════════════════════════════════════
#  STEP 3 — Place sprites on top
# ══════════════════════════════════════════════════════════

def build_hex_grid(spacing):
    """Return list of (cx, cy) world-unit centres on a hex grid
    covering the full tile (including edges for wrap-around)."""
    dx = spacing
    dy = spacing * math.sqrt(3) / 2
    cells = []
    row = 0
    y = 0.0
    while y < TILE_H:
        offset = dx / 2 if row % 2 else 0
        x = offset
        while x < TILE_W:
            cells.append((x, y))
            x += dx
        y += dy
        row += 1
    return cells


def paste_wrapped(base, sprite, px_x, px_y):
    """Paste sprite at (px_x, px_y) with toroidal wrap on all edges."""
    for dx in (0, PX_W, -PX_W):
        for dy in (0, PX_H, -PX_H):
            bx, by = px_x + dx, px_y + dy
            # skip if entirely off-canvas
            if (bx + sprite.width <= 0 or bx >= PX_W or
                    by + sprite.height <= 0 or by >= PX_H):
                continue
            base.paste(sprite, (bx, by), sprite)


def place_sprites(base, assets, seed=42):
    """Paste cleaned asset sprites onto the base image using a hex grid
    with toroidal wrapping so boundary sprites tile seamlessly."""
    rng = random.Random(seed)
    print(f'  seed={seed}')
    cells = build_hex_grid(spacing=200)
    rng.shuffle(cells)
    idx = 0

    def place(name, amount):
        nonlocal idx
        asset = assets[name]
        new_w, new_h = asset.width // 2, asset.height // 2
        resized = asset.resize((new_w, new_h), Image.LANCZOS)
        flipped = resized.transpose(Image.FLIP_LEFT_RIGHT)
        half_w, half_h = new_w // 2, new_h // 2
        for _ in range(amount):
            if idx >= len(cells):
                print(f'  WARNING: ran out of hex cells at {name}')
                break
            cx, cy = cells[idx]
            idx += 1
            sprite = flipped if rng.random() < 0.5 else resized
            # jitter within cell (±40 % of spacing)
            jx = (rng.random() - 0.5) * 200 * 0.4
            jy = (rng.random() - 0.5) * 200 * 0.4
            px_x = int((cx + jx) * RES) - half_w
            px_y = int((cy + jy) * RES) - half_h
            paste_wrapped(base, sprite, px_x, px_y)

    place('mountain', 2)
    place('house',    2)
    place('tree',    10)
    place('flower',  3)
    place('sheep',   5)
    place('cow',     5)
    place('horse',   2)
    place('bird',    2)

    print(f'  Placed sprites in {idx}/{len(cells)} hex cells')

    return base


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

if __name__ == '__main__':
    seed0 = 12345

    print('Loading assets...')
    assets = prepare_assets()

    print(f'Rendering base (meadow + water, seed={seed0})...')
    base = render_base(seed=seed0)

    print('Placing sprites...')
    result = place_sprites(base, assets, seed=seed0)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, 'meadow.png')
    result = result.convert('RGB')
    result.save(out_path, optimize=True)
    print(f'Saved {out_path}  ({result.width}×{result.height}, {os.path.getsize(out_path) / 1024:.0f} KB)')
