// Pre-rendered scenery bitmap (meadow, rivers, lake, trees, rocks, etc.).
// Renders once at load time to an offscreen canvas; the main editor
// blits it each frame with a single drawImage() call.
(function () {
    'use strict';

    const MAX_WORLD = window.TE.MAX_WORLD;
    const DECOR_RANGE = MAX_WORLD / 2;

    function mulberry32(seed) {
        return function () {
            let t = seed += 0x6D2B79F5;
            t = Math.imul(t ^ t >>> 15, t | 1);
            t ^= t + Math.imul(t ^ t >>> 7, t | 61);
            return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
    }

    // Bitmap resolution multiplier (2 = twice the pixel density).
    const RES = 2;

    // Coordinate helpers: world → bitmap pixel.
    const sx = x => MAX_WORLD / 2 + x;
    const sy = y => MAX_WORLD / 2 - y;

    // ====================================================== data generation

    const _rand = mulberry32(20240507);

    // Decoration positions
    const decorations = [];
    for (let i = 0; i < 900; i++) {
        const r = _rand();
        const kind = r < 0.40 ? 'tree'
                   : r < 0.65 ? 'bigtree'
                   : r < 0.80 ? 'bush'
                   : r < 0.92 ? 'flower' : 'rock';
        decorations.push({
            x: (_rand() - 0.5) * 2 * DECOR_RANGE,
            y: (_rand() - 0.5) * 2 * DECOR_RANGE,
            kind, size: 7 + _rand() * 9, tone: _rand(), angle: _rand() * Math.PI * 2,
        });
    }

    // River paths (start → end with perpendicular wobble)
    function makeRiver(seed, x0, y0, x1, y1, nPts, amp1, freq1, amp2, freq2) {
        const rng = mulberry32(seed);
        const dx = x1 - x0, dy = y1 - y0;
        const len = Math.sqrt(dx * dx + dy * dy);
        const tx = dx / len, ty = dy / len, nx = -ty, ny = tx;
        const pts = [];
        for (let i = 0; i <= nPts; i++) {
            const t = i / nPts, along = t * len;
            const wobble = amp1 * Math.sin(along * freq1) + amp2 * Math.cos(along * freq2) + (rng() - 0.5) * 8;
            pts.push({ x: x0 + tx * along + nx * wobble, y: y0 + ty * along + ny * wobble });
        }
        return pts;
    }

    const mainRiver = makeRiver(101, -DECOR_RANGE, -200, DECOR_RANGE, -500, 80, 35, 0.012, 10, 0.04);
    const tribLeft  = makeRiver(202, -DECOR_RANGE * 0.8, 500, -200, -280, 50, 20, 0.018, 6, 0.05);
    const tribRight = makeRiver(303, DECOR_RANGE * 0.9, -900, 300, -420, 55, 22, 0.014, 8, 0.04);

    // Lake outline
    const lakeRng = mulberry32(444);
    const LAKE_CX = 300, LAKE_CY = -420, LAKE_RX = 120, LAKE_RY = 70;
    const lakeShape = [];
    for (let a = 0; a < Math.PI * 2; a += 0.15) {
        lakeShape.push({
            x: LAKE_CX + (LAKE_RX + (lakeRng() - 0.5) * 25) * Math.cos(a),
            y: LAKE_CY + (LAKE_RY + (lakeRng() - 0.5) * 15) * Math.sin(a),
        });
    }

    // ====================================================== render to offscreen canvas

    const sceneryCanvas = document.createElement('canvas');
    sceneryCanvas.width = Math.round(MAX_WORLD * RES);
    sceneryCanvas.height = Math.round(MAX_WORLD * RES);
    const ctx = sceneryCanvas.getContext('2d');
    ctx.scale(RES, RES);

    // --- meadow base ---
    ctx.fillStyle = '#7fbf52';
    ctx.fillRect(0, 0, sceneryCanvas.width, sceneryCanvas.height);

    // Dark grass patches
    ctx.fillStyle = 'rgba(60,130,60,0.15)';
    { const seed = mulberry32(99);
      for (let i = 0; i < 100; i++) {
          const px = (seed() - 0.5) * 2 * DECOR_RANGE, py = (seed() - 0.5) * 2 * DECOR_RANGE;
          const pr = 40 + seed() * 120;
          ctx.beginPath(); ctx.ellipse(sx(px), sy(py), pr, pr * 0.6, seed() * Math.PI, 0, Math.PI * 2); ctx.fill();
      }
    }
    // Light grass patches
    ctx.fillStyle = 'rgba(140,200,80,0.12)';
    { const s2 = mulberry32(77);
      for (let i = 0; i < 50; i++) {
          const px = (s2() - 0.5) * 2 * DECOR_RANGE, py = (s2() - 0.5) * 2 * DECOR_RANGE;
          ctx.beginPath(); ctx.ellipse(sx(px), sy(py), 30 + s2() * 80, 20 + s2() * 50, s2() * Math.PI, 0, Math.PI * 2); ctx.fill();
      }
    }

    // --- water ---
    function strokeRiver(pts, width, color) {
        ctx.strokeStyle = color; ctx.lineWidth = width; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < pts.length; i++) {
            if (i === 0) ctx.moveTo(sx(pts[i].x), sy(pts[i].y));
            else ctx.lineTo(sx(pts[i].x), sy(pts[i].y));
        }
        ctx.stroke();
    }
    function traceLake() {
        ctx.beginPath();
        for (let i = 0; i < lakeShape.length; i++) {
            if (i === 0) ctx.moveTo(sx(lakeShape[i].x), sy(lakeShape[i].y));
            else ctx.lineTo(sx(lakeShape[i].x), sy(lakeShape[i].y));
        }
        ctx.closePath();
    }

    // Lake fill
    ctx.fillStyle = '#4ba3c7'; traceLake(); ctx.fill();
    // Lake highlight
    ctx.fillStyle = 'rgba(174,214,241,0.4)';
    ctx.beginPath(); ctx.ellipse(sx(LAKE_CX - 20), sy(LAKE_CY + 10), LAKE_RX * 0.5, LAKE_RY * 0.35, -0.2, 0, Math.PI * 2); ctx.fill();
    // Rivers: base colour then highlight
    strokeRiver(mainRiver, 22, '#4ba3c7');
    strokeRiver(tribLeft, 14, '#4ba3c7');
    strokeRiver(tribRight, 14, '#4ba3c7');
    strokeRiver(mainRiver, 6, '#aed6f1');
    strokeRiver(tribLeft, 4, '#aed6f1');
    strokeRiver(tribRight, 4, '#aed6f1');
    // Lake shore
    ctx.strokeStyle = 'rgba(40,100,50,0.25)'; ctx.lineWidth = 2;
    traceLake(); ctx.stroke();

    // --- decorations ---
    for (const d of decorations) {
        const cx = sx(d.x), cy = sy(d.y), s = d.size;

        if (d.kind === 'tree') {
            ctx.fillStyle = '#5d4037';
            ctx.beginPath();
            ctx.moveTo(cx - s * 0.12, cy); ctx.lineTo(cx - s * 0.08, cy + s * 0.7);
            ctx.lineTo(cx + s * 0.08, cy + s * 0.7); ctx.lineTo(cx + s * 0.12, cy); ctx.fill();
            ctx.fillStyle = 'rgba(0,0,0,0.08)';
            ctx.beginPath(); ctx.ellipse(cx + s * 0.2, cy + s * 0.65, s * 0.7, s * 0.2, 0.2, 0, Math.PI * 2); ctx.fill();
            const g = d.tone < 0.5
                ? ['#1b5e20', '#2e7d32', '#388e3c', '#43a047']
                : ['#33691e', '#558b2f', '#689f38', '#7cb342'];
            ctx.fillStyle = g[0]; ctx.beginPath(); ctx.arc(cx - s * 0.25, cy - s * 0.1, s * 0.55, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[1]; ctx.beginPath(); ctx.arc(cx + s * 0.2, cy - s * 0.05, s * 0.50, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[2]; ctx.beginPath(); ctx.arc(cx, cy - s * 0.35, s * 0.55, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[3]; ctx.beginPath(); ctx.arc(cx + s * 0.1, cy - s * 0.45, s * 0.35, 0, Math.PI * 2); ctx.fill();

        } else if (d.kind === 'bigtree') {
            const bs = s * 1.6;
            ctx.fillStyle = '#4e342e';
            ctx.beginPath();
            ctx.moveTo(cx - bs * 0.10, cy);
            ctx.quadraticCurveTo(cx - bs * 0.14, cy + bs * 0.4, cx - bs * 0.06, cy + bs * 0.8);
            ctx.lineTo(cx + bs * 0.06, cy + bs * 0.8);
            ctx.quadraticCurveTo(cx + bs * 0.14, cy + bs * 0.4, cx + bs * 0.10, cy);
            ctx.fill();
            ctx.fillStyle = 'rgba(0,0,0,0.07)';
            ctx.beginPath(); ctx.ellipse(cx + bs * 0.25, cy + bs * 0.75, bs * 0.9, bs * 0.25, 0.15, 0, Math.PI * 2); ctx.fill();
            const g = d.tone < 0.5 ? ['#1b5e20', '#2e7d32', '#388e3c'] : ['#33691e', '#558b2f', '#689f38'];
            ctx.fillStyle = g[0]; ctx.beginPath(); ctx.arc(cx - bs * 0.3, cy - bs * 0.1, bs * 0.55, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[0]; ctx.beginPath(); ctx.arc(cx + bs * 0.3, cy - bs * 0.05, bs * 0.50, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[1]; ctx.beginPath(); ctx.arc(cx, cy - bs * 0.35, bs * 0.65, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[2]; ctx.beginPath(); ctx.arc(cx - bs * 0.15, cy - bs * 0.55, bs * 0.4, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = g[2]; ctx.beginPath(); ctx.arc(cx + bs * 0.2, cy - bs * 0.5, bs * 0.35, 0, Math.PI * 2); ctx.fill();

        } else if (d.kind === 'bush') {
            ctx.fillStyle = 'rgba(0,0,0,0.05)';
            ctx.beginPath(); ctx.ellipse(cx, cy + s * 0.15, s * 0.7, s * 0.15, 0, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = d.tone < 0.5 ? '#388e3c' : '#43a047';
            ctx.beginPath();
            ctx.arc(cx - s * 0.35, cy, s * 0.5, 0, Math.PI * 2);
            ctx.arc(cx + s * 0.35, cy, s * 0.5, 0, Math.PI * 2);
            ctx.arc(cx, cy - s * 0.3, s * 0.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = d.tone < 0.5 ? '#2e7d32' : '#388e3c';
            ctx.beginPath(); ctx.arc(cx, cy - s * 0.1, s * 0.35, 0, Math.PI * 2); ctx.fill();

        } else if (d.kind === 'flower') {
            ctx.strokeStyle = '#558b2f'; ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(cx, cy + s * 0.5); ctx.stroke();
            ctx.fillStyle = d.tone < 0.33 ? '#fff59d' : (d.tone < 0.66 ? '#f48fb1' : '#ce93d8');
            for (let k = 0; k < 5; k++) {
                const a = k * Math.PI * 2 / 5 + d.angle;
                ctx.beginPath(); ctx.ellipse(cx + Math.cos(a) * s * 0.2, cy + Math.sin(a) * s * 0.2, s * 0.14, s * 0.08, a, 0, Math.PI * 2); ctx.fill();
            }
            ctx.fillStyle = '#fbc02d';
            ctx.beginPath(); ctx.arc(cx, cy, s * 0.1, 0, Math.PI * 2); ctx.fill();

        } else if (d.kind === 'rock') {
            const rs = s * 0.7;
            ctx.fillStyle = 'rgba(0,0,0,0.06)';
            ctx.beginPath(); ctx.ellipse(cx + rs * 0.1, cy + rs * 0.2, rs * 0.6, rs * 0.15, 0.1, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = d.tone < 0.5 ? '#9e9e9e' : '#bdbdbd';
            ctx.beginPath(); ctx.ellipse(cx, cy, rs * 0.5, rs * 0.35, d.angle, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = 'rgba(255,255,255,0.15)';
            ctx.beginPath(); ctx.ellipse(cx - rs * 0.1, cy - rs * 0.08, rs * 0.2, rs * 0.12, d.angle, 0, Math.PI * 2); ctx.fill();
        }
    }

    // Export the finished bitmap
    window.TE.sceneryCanvas = sceneryCanvas;
})();
