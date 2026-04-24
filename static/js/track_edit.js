// Track editor canvas + interaction script.
// Reads its render data from window.EDITOR_DATA, populated by an inline
// bootstrap script in track_edit.html (the only place Jinja still touches JS).
(function () {
    const data = window.EDITOR_DATA || {};
    const pieces = data.pathes || [];
    const isClosed = !!data.isClosed;
    const ghosts = data.ghosts || {};
    const cursor = data.cursor || null;

    const canvas = document.getElementById('drawingCanvas');
    const ctx = canvas.getContext('2d');

    let ghostName = null;
    let highlightLast = false;

    function resizeCanvas() {
        const nav = document.querySelector('nav');
        if (nav) document.documentElement.style.setProperty('--nav-h', nav.getBoundingClientRect().height + 'px');
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
    }

    resizeCanvas();
    window.addEventListener('resize', () => { resizeCanvas(); draw(); }, false);

    const VIEW_KEY = 'duplo.editorView';
    let scale = 1;
    let posX = 0;
    let posY = 0;
    try {
        const saved = JSON.parse(sessionStorage.getItem(VIEW_KEY) || 'null');
        if (saved && typeof saved.scale === 'number') {
            scale = saved.scale;
            posX = saved.posX;
            posY = saved.posY;
        }
    } catch (_) { /* ignore */ }
    const saveView = () => {
        try {
            sessionStorage.setItem(VIEW_KEY, JSON.stringify({ scale, posX, posY }));
        } catch (_) { /* ignore */ }
    };
    let startDistance = 0;
    let startScale = 1;
    let startX = 0;
    let startY = 0;
    let midpointX = 0;
    let midpointY = 0;
    let isDragging = false;
    let lastTouchEnd = 0;

    // ---------- Deterministic decorations (meadow) ----------
    function mulberry32(seed) {
        return function () {
            let t = seed += 0x6D2B79F5;
            t = Math.imul(t ^ t >>> 15, t | 1);
            t ^= t + Math.imul(t ^ t >>> 7, t | 61);
            return ((t ^ t >>> 14) >>> 0) / 4294967296;
        };
    }
    const _rand = mulberry32(20240507);
    const DECOR_RANGE = 1200;
    const decorations = [];
    for (let i = 0; i < 140; i++) {
        const r = _rand();
        let kind;
        if (r < 0.45) kind = 'tree';
        else if (r < 0.85) kind = 'bush';
        else kind = 'flower';
        decorations.push({
            x: (_rand() - 0.5) * 2 * DECOR_RANGE,
            y: (_rand() - 0.5) * 2 * DECOR_RANGE,
            kind,
            size: 7 + _rand() * 9,
            tone: _rand()
        });
    }
    const riverPath = [];
    for (let i = -DECOR_RANGE; i <= DECOR_RANGE; i += 25) {
        riverPath.push({ x: i, y: -380 + 35 * Math.sin(i * 0.012) + 10 * Math.cos(i * 0.04) });
    }

    const wx = x => canvas.width / 2 + x;
    const wy = y => canvas.height / 2 - y;

    function drawMeadow() {
        const x0 = -posX / scale, y0 = -posY / scale;
        const w = canvas.width / scale, h = canvas.height / scale;
        ctx.fillStyle = '#7fbf52';
        ctx.fillRect(x0, y0, w, h);
        ctx.fillStyle = 'rgba(60, 130, 60, 0.18)';
        const seed = mulberry32(99);
        for (let i = 0; i < 30; i++) {
            const px = (seed() - 0.5) * 2 * DECOR_RANGE;
            const py = (seed() - 0.5) * 2 * DECOR_RANGE;
            const pr = 50 + seed() * 100;
            ctx.beginPath();
            ctx.arc(wx(px), wy(py), pr, 0, Math.PI * 2);
            ctx.fill();
        }
    }

    function drawRiver() {
        ctx.strokeStyle = '#5dade2';
        ctx.lineWidth = 22;
        ctx.lineCap = 'round';
        ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < riverPath.length; i++) {
            const p = riverPath[i];
            if (i === 0) ctx.moveTo(wx(p.x), wy(p.y));
            else ctx.lineTo(wx(p.x), wy(p.y));
        }
        ctx.stroke();
        ctx.strokeStyle = '#aed6f1';
        ctx.lineWidth = 6;
        ctx.beginPath();
        for (let i = 0; i < riverPath.length; i++) {
            const p = riverPath[i];
            if (i === 0) ctx.moveTo(wx(p.x), wy(p.y + 4));
            else ctx.lineTo(wx(p.x), wy(p.y + 4));
        }
        ctx.stroke();
    }

    function drawTree(d) {
        const cx = wx(d.x), cy = wy(d.y);
        ctx.fillStyle = '#6b3e1f';
        ctx.fillRect(cx - d.size * 0.18, cy, d.size * 0.36, d.size * 0.7);
        ctx.fillStyle = d.tone < 0.5 ? '#2e7d32' : '#388e3c';
        ctx.beginPath();
        ctx.arc(cx, cy, d.size, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#1b5e20';
        ctx.beginPath();
        ctx.arc(cx - d.size * 0.35, cy - d.size * 0.25, d.size * 0.45, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawBush(d) {
        const cx = wx(d.x), cy = wy(d.y);
        ctx.fillStyle = d.tone < 0.5 ? '#388e3c' : '#43a047';
        ctx.beginPath();
        ctx.arc(cx - d.size * 0.4, cy, d.size * 0.6, 0, Math.PI * 2);
        ctx.arc(cx + d.size * 0.4, cy, d.size * 0.6, 0, Math.PI * 2);
        ctx.arc(cx, cy - d.size * 0.4, d.size * 0.6, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawFlower(d) {
        const cx = wx(d.x), cy = wy(d.y);
        ctx.fillStyle = d.tone < 0.33 ? '#fff59d' : (d.tone < 0.66 ? '#f48fb1' : '#ce93d8');
        for (let k = 0; k < 5; k++) {
            const a = k * Math.PI * 2 / 5;
            ctx.beginPath();
            ctx.arc(cx + Math.cos(a) * d.size * 0.25, cy + Math.sin(a) * d.size * 0.25, d.size * 0.18, 0, Math.PI * 2);
            ctx.fill();
        }
        ctx.fillStyle = '#fbc02d';
        ctx.beginPath();
        ctx.arc(cx, cy, d.size * 0.15, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawDecorations() {
        for (const d of decorations) {
            if (d.kind === 'tree') drawTree(d);
            else if (d.kind === 'bush') drawBush(d);
            else drawFlower(d);
        }
    }

    function fillPolygon(path, color) {
        ctx.fillStyle = color;
        ctx.beginPath();
        for (let i = 0; i < path.length; i++) {
            if (i === 0) ctx.moveTo(wx(path[i].x), wy(path[i].y));
            else ctx.lineTo(wx(path[i].x), wy(path[i].y));
        }
        ctx.closePath();
        ctx.fill();
    }

    function drawCursorMarker(c) {
        // c = [{x,y},{x,y}] -- the two corner points of the active free end.
        const mx = (c[0].x + c[1].x) / 2;
        const my = (c[0].y + c[1].y) / 2;
        // Outward perpendicular (matches old get_path_cursor handedness).
        const px = c[0].y - c[1].y;
        const py = c[1].x - c[0].x;
        const plen = Math.hypot(px, py) || 1;
        const arrowLen = 9;
        const ax = mx + (px / plen) * arrowLen;
        const ay = my + (py / plen) * arrowLen;
        const sx = mx, sy = my;
        const cx = wx(sx), cy = wy(sy);
        const tx = wx(ax), ty = wy(ay);

        ctx.save();
        ctx.lineWidth = 2 / scale;
        ctx.strokeStyle = '#ff8f00';
        ctx.fillStyle = '#ff8f00';
        // Shaft
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(tx, ty);
        ctx.stroke();
        // Arrow head (triangle at tip)
        const head = 4;
        const hx = -(px / plen) * head;
        const hy = -(py / plen) * head;
        const wxn = -py / plen;  // perpendicular to arrow direction (in world)
        const wyn = px / plen;
        ctx.beginPath();
        ctx.moveTo(tx, ty);
        ctx.lineTo(wx(ax + hx + wxn * head * 0.7), wy(ay + hy + wyn * head * 0.7));
        ctx.lineTo(wx(ax + hx - wxn * head * 0.7), wy(ay + hy - wyn * head * 0.7));
        ctx.closePath();
        ctx.fill();
        // Base dot
        ctx.beginPath();
        ctx.arc(cx, cy, 2.5 / scale + 1, 0, Math.PI * 2);
        ctx.fill();
        ctx.restore();
    }

    function railColor(c) {
        if (c === 'red') return '#c62828';
        if (c === 'green') return '#2e7d32';
        if (c === 'ghost') return '#1565c0';
        return '#bdbdbd';
    }

    function drawTiesAndRails(centerlines, color) {
        const tieSpacing = 7;
        const tieHalfLen = 6.5;
        const railOffset = 4;
        for (const cl of centerlines) {
            if (cl.length < 2) continue;
            const segs = [];
            let total = 0;
            for (let i = 1; i < cl.length; i++) {
                const dx = cl[i].x - cl[i - 1].x;
                const dy = cl[i].y - cl[i - 1].y;
                const len = Math.hypot(dx, dy);
                segs.push({ p0: cl[i - 1], p1: cl[i], len, cum: total });
                total += len;
            }
            ctx.strokeStyle = '#5d4037';
            ctx.lineWidth = 2.2;
            ctx.lineCap = 'butt';
            let segIdx = 0;
            for (let s = tieSpacing / 2; s < total; s += tieSpacing) {
                while (segIdx < segs.length - 1 && s > segs[segIdx].cum + segs[segIdx].len) segIdx++;
                const sg = segs[segIdx];
                const t = (s - sg.cum) / (sg.len || 1);
                const x = sg.p0.x + t * (sg.p1.x - sg.p0.x);
                const y = sg.p0.y + t * (sg.p1.y - sg.p0.y);
                const len = sg.len || 1;
                const nx = -(sg.p1.y - sg.p0.y) / len;
                const ny = (sg.p1.x - sg.p0.x) / len;
                ctx.beginPath();
                ctx.moveTo(wx(x + nx * tieHalfLen), wy(y + ny * tieHalfLen));
                ctx.lineTo(wx(x - nx * tieHalfLen), wy(y - ny * tieHalfLen));
                ctx.stroke();
            }
            ctx.strokeStyle = railColor(color);
            ctx.lineWidth = 1.4;
            ctx.lineCap = 'round';
            for (const side of [-1, 1]) {
                ctx.beginPath();
                for (let i = 0; i < cl.length; i++) {
                    let dx, dy;
                    if (i === 0) { dx = cl[1].x - cl[0].x; dy = cl[1].y - cl[0].y; }
                    else if (i === cl.length - 1) { dx = cl[i].x - cl[i - 1].x; dy = cl[i].y - cl[i - 1].y; }
                    else { dx = cl[i + 1].x - cl[i - 1].x; dy = cl[i + 1].y - cl[i - 1].y; }
                    const len = Math.hypot(dx, dy) || 1;
                    const nx = -dy / len, ny = dx / len;
                    const x = cl[i].x + side * railOffset * nx;
                    const y = cl[i].y + side * railOffset * ny;
                    if (i === 0) ctx.moveTo(wx(x), wy(y));
                    else ctx.lineTo(wx(x), wy(y));
                }
                ctx.stroke();
            }
        }
    }

    let trainPath = null;
    function buildTrainPath() {
        if (!isClosed) { trainPath = null; return; }
        const segs = [];
        for (const p of pieces) {
            if (!p.centerlines) continue;
            for (const cl of p.centerlines) if (cl.length >= 2) segs.push(cl.map(q => ({ x: q.x, y: q.y })));
        }
        if (segs.length === 0) { trainPath = null; return; }
        const used = new Array(segs.length).fill(false);
        const chain = segs[0].slice();
        used[0] = true;
        const FIT_TOL = 6;
        while (true) {
            const tail = chain[chain.length - 1];
            let bestIdx = -1, bestRev = false, bestDist = Infinity;
            for (let i = 0; i < segs.length; i++) {
                if (used[i]) continue;
                const s = segs[i];
                const d1 = Math.hypot(s[0].x - tail.x, s[0].y - tail.y);
                const d2 = Math.hypot(s[s.length - 1].x - tail.x, s[s.length - 1].y - tail.y);
                if (d1 < bestDist) { bestDist = d1; bestIdx = i; bestRev = false; }
                if (d2 < bestDist) { bestDist = d2; bestIdx = i; bestRev = true; }
            }
            if (bestIdx < 0 || bestDist > FIT_TOL) break;
            const next = bestRev ? segs[bestIdx].slice().reverse() : segs[bestIdx];
            for (let j = 1; j < next.length; j++) chain.push(next[j]);
            used[bestIdx] = true;
        }
        const head = chain[0], tail = chain[chain.length - 1];
        if (Math.hypot(head.x - tail.x, head.y - tail.y) > 0.1) chain.push({ x: head.x, y: head.y });

        const cum = [0];
        for (let i = 1; i < chain.length; i++) {
            cum.push(cum[i - 1] + Math.hypot(chain[i].x - chain[i - 1].x, chain[i].y - chain[i - 1].y));
        }
        trainPath = { pts: chain, cum, total: cum[cum.length - 1] };
    }

    function trainPosAt(s) {
        if (!trainPath || trainPath.total <= 0) return null;
        s = ((s % trainPath.total) + trainPath.total) % trainPath.total;
        const cum = trainPath.cum, pts = trainPath.pts;
        let lo = 0, hi = cum.length - 1;
        while (lo < hi - 1) {
            const mid = (lo + hi) >> 1;
            if (cum[mid] <= s) lo = mid; else hi = mid;
        }
        const span = Math.max(cum[hi] - cum[lo], 1e-6);
        const t = (s - cum[lo]) / span;
        return {
            x: pts[lo].x + t * (pts[hi].x - pts[lo].x),
            y: pts[lo].y + t * (pts[hi].y - pts[lo].y),
            ang: Math.atan2(pts[hi].y - pts[lo].y, pts[hi].x - pts[lo].x)
        };
    }

    function drawCar(offsetX, color, length) {
        ctx.fillStyle = color;
        ctx.fillRect(-length / 2, -5, length, 10);
        ctx.fillStyle = '#111';
        ctx.beginPath();
        ctx.arc(-length / 2 + 3, 6, 2, 0, Math.PI * 2);
        ctx.arc(length / 2 - 3, 6, 2, 0, Math.PI * 2);
        ctx.fill();
    }

    function drawTrain(s) {
        const carSpec = [
            { color: '#c62828', len: 22, kind: 'loco' },
            { color: '#1565c0', len: 18, kind: 'car' },
            { color: '#f9a825', len: 18, kind: 'car' }
        ];
        let off = 0;
        for (const car of carSpec) {
            const pos = trainPosAt(s - off - car.len / 2);
            if (!pos) return;
            ctx.save();
            ctx.translate(wx(pos.x), wy(pos.y));
            ctx.rotate(-pos.ang);
            drawCar(0, car.color, car.len);
            if (car.kind === 'loco') {
                ctx.fillStyle = '#212121';
                ctx.fillRect(-car.len / 2 + 3, -8, 4, 4);
                ctx.fillStyle = '#37474f';
                ctx.fillRect(car.len / 2 - 8, -7, 6, 4);
            }
            ctx.restore();
            off += car.len + 4;
        }
    }

    const drawElement = (path, color) => {
        ctx.beginPath();
        ctx.strokeStyle = color;
        ctx.lineWidth = 1.5;
        for (let i = 0; i < path.length; i++) {
            const xx = wx(path[i].x);
            const yy = wy(path[i].y);
            if (i === 0) ctx.moveTo(xx, yy); else ctx.lineTo(xx, yy);
        }
        ctx.stroke();
    };

    let trainS = 0;
    let lastFrameT = performance.now();

    const draw = () => {
        ctx.save();
        ctx.setTransform(scale, 0, 0, scale, posX, posY);
        ctx.clearRect(-posX / scale, -posY / scale, canvas.width / scale, canvas.height / scale);

        drawMeadow();
        drawRiver();
        drawDecorations();

        for (const el of pieces) {
            if (el.cursor) {
                drawElement(el.path, el.color);
            } else {
                fillPolygon(el.path, '#616161');
                drawTiesAndRails(el.centerlines || [], el.color);
            }
        }

        if (ghostName && ghosts[ghostName]) {
            const g = ghosts[ghostName];
            ctx.save();
            ctx.globalAlpha = 0.55;
            fillPolygon(g.path, '#90caf9');
            drawTiesAndRails(g.centerlines || [], 'ghost');
            ctx.restore();
        } else if (cursor && !isClosed) {
            drawCursorMarker(cursor);
        }

        if (highlightLast && pieces.length > 0) {
            const last = pieces[pieces.length - 1];
            if (last && last.path && last.path.length) {
                ctx.save();
                ctx.lineWidth = 3 / scale;
                ctx.strokeStyle = '#e53935';
                ctx.beginPath();
                for (let i = 0; i < last.path.length; i++) {
                    const p = last.path[i];
                    if (i === 0) ctx.moveTo(wx(p.x), wy(p.y));
                    else ctx.lineTo(wx(p.x), wy(p.y));
                }
                ctx.closePath();
                ctx.stroke();
                ctx.restore();
            }
        }

        if (trainPath) drawTrain(trainS);

        ctx.restore();
    };

    function animate(now) {
        const dt = Math.min((now - lastFrameT) / 1000, 0.05);
        lastFrameT = now;
        if (trainPath) {
            trainS += 70 * dt;
            draw();
        }
        requestAnimationFrame(animate);
    }

    const handleTouchStart = (evt) => {
        evt.preventDefault();
        if (evt.touches.length === 1) {
            let touch = evt.touches[0];
            startX = touch.pageX - posX;
            startY = touch.pageY - posY;
            isDragging = true;
        }
        if (evt.touches.length === 2) {
            const dx = evt.touches[0].pageX - evt.touches[1].pageX;
            const dy = evt.touches[0].pageY - evt.touches[1].pageY;
            startDistance = Math.sqrt(dx * dx + dy * dy);
            startScale = scale;
            midpointX = (evt.touches[0].pageX + evt.touches[1].pageX) / 2;
            midpointY = (evt.touches[0].pageY + evt.touches[1].pageY) / 2;
        }
    };

    const handleTouchMove = (evt) => {
        evt.preventDefault();
        if (evt.touches.length === 1 && isDragging) {
            let touch = evt.touches[0];
            posX = touch.pageX - startX;
            posY = touch.pageY - startY;
            draw();
        }
        if (evt.touches.length === 2) {
            const dx = evt.touches[0].pageX - evt.touches[1].pageX;
            const dy = evt.touches[0].pageY - evt.touches[1].pageY;
            const newDistance = Math.sqrt(dx * dx + dy * dy);
            const newScale = (newDistance / startDistance) * startScale;
            if (newScale >= 0.1 && newScale <= 10) {
                const scaleRatio = newScale / scale;
                const canvasMidX = midpointX - canvas.offsetLeft;
                const canvasMidY = midpointY - canvas.offsetTop;
                posX = canvasMidX - (canvasMidX - posX) * scaleRatio;
                posY = canvasMidY - (canvasMidY - posY) * scaleRatio;
                scale = newScale;
                draw();
            }
        }
    };

    const handleTouchEnd = (evt) => {
        evt.preventDefault();
        if (isDragging) saveView();
        isDragging = false;
        const now = new Date().getTime();
        if (now - lastTouchEnd <= 300) {
            resetCanvas();
        }
        lastTouchEnd = now;
    };

    const handleMouseDown = (evt) => {
        evt.preventDefault();
        isDragging = true;
        startX = evt.pageX - posX;
        startY = evt.pageY - posY;
    };

    const handleMouseMove = (evt) => {
        if (!isDragging) return;
        evt.preventDefault();
        posX = evt.pageX - startX;
        posY = evt.pageY - startY;
        draw();
    };

    const handleMouseUp = () => {
        if (isDragging) saveView();
        isDragging = false;
    };

    const handleMouseWheel = (evt) => {
        evt.preventDefault();
        const delta = evt.deltaY < 0 ? 1.1 : 0.9;
        const newScale = scale * delta;
        if (newScale >= 0.1 && newScale <= 10) {
            const mouseX = evt.pageX - canvas.offsetLeft;
            const mouseY = evt.pageY - canvas.offsetTop;
            posX -= (mouseX - posX) * (delta - 1);
            posY -= (mouseY - posY) * (delta - 1);
            scale = newScale;
            saveView();
            draw();
        }
    };

    const resetCanvas = () => {
        scale = 1;
        posX = 0;
        posY = 0;
        saveView();
        draw();
    };

    const handleDoubleClick = (evt) => {
        evt.preventDefault();
        resetCanvas();
    };

    canvas.addEventListener('touchstart', handleTouchStart);
    canvas.addEventListener('touchmove', handleTouchMove);
    canvas.addEventListener('touchend', handleTouchEnd);

    canvas.addEventListener('mousedown', handleMouseDown);
    canvas.addEventListener('mousemove', handleMouseMove);
    canvas.addEventListener('mouseup', handleMouseUp);
    canvas.addEventListener('wheel', handleMouseWheel);
    canvas.addEventListener('dblclick', handleDoubleClick);

    buildTrainPath();
    draw();
    if (trainPath) requestAnimationFrame(animate);

    document.getElementById('resetView').addEventListener('click', resetCanvas);

    document.querySelectorAll('.piece-tile').forEach(tile => {
        const name = tile.getAttribute('name');
        const show = () => { ghostName = name; draw(); };
        const hide = () => { if (ghostName === name) { ghostName = null; draw(); } };
        tile.addEventListener('mouseenter', show);
        tile.addEventListener('mouseleave', hide);
        tile.addEventListener('focus', show);
        tile.addEventListener('blur', hide);
    });

    const rotateBtn = document.querySelector('button[name="rotate"]');
    if (rotateBtn) {
        const showRot = () => { highlightLast = true; draw(); };
        const hideRot = () => { highlightLast = false; draw(); };
        rotateBtn.addEventListener('mouseenter', showRot);
        rotateBtn.addEventListener('mouseleave', hideRot);
        rotateBtn.addEventListener('focus', showRot);
        rotateBtn.addEventListener('blur', hideRot);
    }

    const deleteBtn = document.querySelector('button[name="delete"]');
    if (deleteBtn) {
        const showDel = () => { highlightLast = true; draw(); };
        const hideDel = () => { highlightLast = false; draw(); };
        deleteBtn.addEventListener('mouseenter', showDel);
        deleteBtn.addEventListener('mouseleave', hideDel);
        deleteBtn.addEventListener('focus', showDel);
        deleteBtn.addEventListener('blur', hideDel);
    }

    const submitByName = (name) => {
        const btn = document.querySelector(`button[name="${name}"]`);
        if (btn) btn.click();
    };
    document.addEventListener('keydown', (evt) => {
        if (evt.target && (evt.target.tagName === 'INPUT' || evt.target.tagName === 'TEXTAREA')) return;
        if (evt.ctrlKey && evt.key.toLowerCase() === 's') { evt.preventDefault(); submitByName('save'); return; }
        switch (evt.key) {
            case 'ArrowLeft':  evt.preventDefault(); submitByName('left'); break;
            case 'ArrowUp':    evt.preventDefault(); submitByName('straight'); break;
            case 'ArrowRight': evt.preventDefault(); submitByName('right'); break;
            case 's': case 'S': submitByName('switch'); break;
            case 'x': case 'X': submitByName('crossing'); break;
            case 'r': case 'R': submitByName('rotate'); break;
            case 'Tab': evt.preventDefault(); submitByName('next_ending'); break;
            case 'Backspace': case 'Delete': submitByName('delete'); break;
        }
    });
})();
