// Track editor — main entry point (state, canvas, rendering, gestures).
// Depends on track_edit_geometry.js and track_edit_scenery.js being loaded
// first via <script> tags (they populate window.TE).
(function () {
    'use strict';

    // ====================================================== imports from geometry / scenery modules
    const { W0, L0, C0, ENDING_COUNT, PIECE_TYPES, MM_PER_UNIT, MAX_WORLD,
            poseTransform, poseAlign, midpoint, localSnap } = window.TE;
    const sceneryTile = window.TE.sceneryTile;  // Image element (tiles/meadow.png)

    // ====================================================== state & data
    let view = window.EDITOR_DATA || {};
    let pieces = view.pieces || [];
    let connections = view.connections || [];
    let selection = view.selection || null;
    let multiSel = new Set();  // piece IDs in the group selection
    let isClosed = !!view.is_closed;
    let snapTol = view.snap_tolerance || 6;
    let userLib = window.EDITOR_USER_LIB || {};

    /** Return the piece_id of a neighbor connected to `pid`, or null. */
    function connectedNeighbor(pid) {
        for (const [a, b] of connections) {
            if (a.piece_id === pid) return b.piece_id;
            if (b.piece_id === pid) return a.piece_id;
        }
        return null;
    }
    const ACTION_URL = window.EDITOR_ACTION_URL;
    const csrfToken = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    const isCoarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

    // ====================================================== canvas / view
    const canvas = document.getElementById('drawingCanvas');
    const ctx = canvas.getContext('2d');

    function resizeCanvas() {
        const nav = document.querySelector('nav');
        if (nav) document.documentElement.style.setProperty('--nav-h', nav.getBoundingClientRect().height + 'px');
        const rect = canvas.getBoundingClientRect();
        canvas.width = rect.width;
        canvas.height = rect.height;
    }
    resizeCanvas();
    window.addEventListener('resize', () => { resizeCanvas(); clampPan(); draw(); });
    let needsInitialCenter = true;
    new ResizeObserver(() => {
        resizeCanvas();
        if (needsInitialCenter && canvas.width > 0 && canvas.height > 0) {
            needsInitialCenter = false;
            if (!sessionStorage.getItem(VIEW_KEY)) centerView();
            else clampPan();
        }
        draw();
    }).observe(canvas);

    const VIEW_KEY = 'duplo.editorView';
    const DEFAULT_SCALE = 2;
    let scale = DEFAULT_SCALE, posX = 0, posY = 0;
    function centerView() {
        posX = canvas.width / 2 * (1 - scale);
        posY = canvas.height / 2 * (1 - scale);
        if (canvas.width > 0) clampPan();
    }
    try {
        const saved = JSON.parse(sessionStorage.getItem(VIEW_KEY) || 'null');
        if (saved && typeof saved.scale === 'number') { scale = saved.scale; posX = saved.posX; posY = saved.posY; }
    } catch (_) {}
    const saveView = () => {
        try { sessionStorage.setItem(VIEW_KEY, JSON.stringify({ scale, posX, posY })); } catch (_) {}
    };

    const wx = x => canvas.width / 2 + x;
    const wy = y => canvas.height / 2 - y;
    function clientToWorld(cx, cy) {
        const r = canvas.getBoundingClientRect();
        const sx = (cx - r.left - posX) / scale;
        const sy = (cy - r.top  - posY) / scale;
        return { x: sx - canvas.width/2, y: -(sy - canvas.height/2) };
    }

    // ====================================================== room / world constants
    const roomWMeters = window.EDITOR_ROOM_W || 6;
    const roomHMeters = window.EDITOR_ROOM_H || 4;
    const ROOM_W = roomWMeters * 1000 / MM_PER_UNIT;
    const ROOM_H = roomHMeters * 1000 / MM_PER_UNIT;

    // ====================================================== scenery (tiled bitmap)
    function drawScenery() {
        const vx = -posX / scale, vy = -posY / scale;
        const vw = canvas.width / scale, vh = canvas.height / scale;
        // Grey background
        ctx.fillStyle = '#d0d0d0';
        ctx.fillRect(vx, vy, vw, vh);

        if (!sceneryTile.complete) return;  // image not loaded yet

        const TILE_W = window.TE.TILE_W;
        const TILE_H = window.TE.TILE_H;
        if (!TILE_W || !TILE_H) return;  // dimensions not yet derived

        // Clip scenery to the 10×10 m world boundary.
        const whw = MAX_WORLD / 2, whh = MAX_WORLD / 2;
        const bx = wx(-whw), by = wy(whh);
        ctx.save();
        ctx.beginPath();
        ctx.rect(bx, by, MAX_WORLD, MAX_WORLD);
        ctx.clip();

        // Visible world bounds
        const worldL = vx - canvas.width / 2;
        const worldT = -(vy - canvas.height / 2);

        // Tile the image. The tile origin aligns with the room centre:
        //   tile (0,0) sits at world (-TILE_W/2, TILE_H/2)  (top-left corner of room).
        const startCol = Math.floor((worldL + TILE_W / 2) / TILE_W);
        const endCol   = Math.floor((worldL + vw + TILE_W / 2) / TILE_W);
        const startRow = Math.floor((-worldT + TILE_H / 2) / TILE_H);
        const endRow   = Math.floor((-worldT + vh + TILE_H / 2) / TILE_H);

        for (let row = startRow; row <= endRow; row++) {
            for (let col = startCol; col <= endCol; col++) {
                const tx = wx(-TILE_W / 2 + col * TILE_W);
                const ty = wy(TILE_H / 2 - row * TILE_H);
                ctx.drawImage(sceneryTile, tx, ty, TILE_W, TILE_H);
            }
        }
        ctx.restore();

        // Solid black border around the world boundary.
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 2 / scale;
        ctx.strokeRect(bx, by, MAX_WORLD, MAX_WORLD);
    }

    // ====================================================== room outline

    /** Clamp posX/posY so the viewport stays within the 10×10 m region. */
    function clampPan() {
        // Allow a small margin (20% of canvas) of grey beyond the world edge.
        const margin = 0.2;
        const hw = MAX_WORLD / 2, hh = MAX_WORLD / 2;
        const cw2 = canvas.width / 2, ch2 = canvas.height / 2;
        const mx = canvas.width * margin, my = canvas.height * margin;
        const minPosX = -(scale * (cw2 + hw)) + canvas.width - mx;
        const maxPosX = -(scale * (cw2 - hw)) + mx;
        const minPosY = -(scale * (ch2 + hh)) + canvas.height - my;
        const maxPosY = -(scale * (ch2 - hh)) + my;
        posX = Math.max(Math.min(minPosX, maxPosX), Math.min(Math.max(minPosX, maxPosX), posX));
        posY = Math.max(Math.min(minPosY, maxPosY), Math.min(Math.max(minPosY, maxPosY), posY));
    }

    function drawRoom() {
        const rx = wx(-ROOM_W / 2), ry = wy(ROOM_H / 2);
        const vx = -posX / scale, vy = -posY / scale;
        const vw = canvas.width / scale, vh = canvas.height / scale;

        // Fog outside the room: fill the visible area, then cut out the room
        ctx.fillStyle = 'rgba(255,255,255,0.35)';
        ctx.beginPath();
        ctx.rect(vx, vy, vw, vh);           // outer (visible canvas)
        ctx.rect(rx, ry, ROOM_W, ROOM_H);   // inner (room) — wound opposite
        ctx.fill('evenodd');

        // Dashed border
        ctx.strokeStyle = 'rgba(0,0,0,0.18)';
        ctx.lineWidth = 1.5 / scale;
        ctx.setLineDash([8 / scale, 6 / scale]);
        ctx.strokeRect(rx, ry, ROOM_W, ROOM_H);
        ctx.setLineDash([]);

        // Label
        ctx.fillStyle = 'rgba(0,0,0,0.22)';
        ctx.font = `${12 / scale}px sans-serif`;
        ctx.textAlign = 'left'; ctx.textBaseline = 'top';
        ctx.fillText(`${roomWMeters} × ${roomHMeters} m`, rx + 6 / scale, ry + 4 / scale);
    }

    // ====================================================== piece rendering
    function fillPolygon(path, color) {
        ctx.fillStyle = color; ctx.beginPath();
        for (let i = 0; i < path.length; i++) {
            const p = path[i];
            if (i===0) ctx.moveTo(wx(p.x), wy(p.y)); else ctx.lineTo(wx(p.x), wy(p.y));
        }
        ctx.closePath(); ctx.fill();
    }

    function railColor(c) { if (c==='red') return '#c62828'; if (c==='green') return '#2e7d32'; if (c==='ghost') return '#1565c0'; return '#bdbdbd'; }

    function drawTiesAndRails(centerlines, color) {
        const tieSpacing = 7, tieHalfLen = 6.5, railOffset = 4;
        for (const cl of centerlines) {
            if (cl.length < 2) continue;
            const segs = []; let total = 0;
            for (let i = 1; i < cl.length; i++) {
                const dx = cl[i].x-cl[i-1].x, dy = cl[i].y-cl[i-1].y;
                const len = Math.hypot(dx, dy);
                segs.push({ p0: cl[i-1], p1: cl[i], len, cum: total }); total += len;
            }
            ctx.strokeStyle = '#5d4037'; ctx.lineWidth = 2.2; ctx.lineCap = 'butt';
            let segIdx = 0;
            for (let s = tieSpacing/2; s < total; s += tieSpacing) {
                while (segIdx < segs.length-1 && s > segs[segIdx].cum + segs[segIdx].len) segIdx++;
                const sg = segs[segIdx];
                const t = (s - sg.cum) / (sg.len || 1);
                const x = sg.p0.x + t*(sg.p1.x - sg.p0.x);
                const y = sg.p0.y + t*(sg.p1.y - sg.p0.y);
                const len = sg.len || 1;
                const nx = -(sg.p1.y - sg.p0.y)/len, ny = (sg.p1.x - sg.p0.x)/len;
                ctx.beginPath();
                ctx.moveTo(wx(x + nx*tieHalfLen), wy(y + ny*tieHalfLen));
                ctx.lineTo(wx(x - nx*tieHalfLen), wy(y - ny*tieHalfLen));
                ctx.stroke();
            }
            ctx.strokeStyle = railColor(color); ctx.lineWidth = 1.4; ctx.lineCap = 'round';
            for (const side of [-1, 1]) {
                ctx.beginPath();
                for (let i = 0; i < cl.length; i++) {
                    let dx, dy;
                    if (i===0) { dx = cl[1].x-cl[0].x; dy = cl[1].y-cl[0].y; }
                    else if (i===cl.length-1) { dx = cl[i].x-cl[i-1].x; dy = cl[i].y-cl[i-1].y; }
                    else { dx = cl[i+1].x-cl[i-1].x; dy = cl[i+1].y-cl[i-1].y; }
                    const len = Math.hypot(dx, dy) || 1;
                    const nx = -dy/len, ny = dx/len;
                    const x = cl[i].x + side*railOffset*nx;
                    const y = cl[i].y + side*railOffset*ny;
                    if (i===0) ctx.moveTo(wx(x), wy(y)); else ctx.lineTo(wx(x), wy(y));
                }
                ctx.stroke();
            }
        }
    }

    // ====================================================== train (only when closed)
    let trainPath = null, trainS = 0, lastFrameT = performance.now();
    function buildTrainPath() {
        if (!isClosed) { trainPath = null; return; }
        const segs = [];
        for (const p of pieces) for (const cl of p.centerlines || []) if (cl.length >= 2) segs.push(cl.map(q => ({ x: q.x, y: q.y })));
        if (!segs.length) { trainPath = null; return; }
        const used = new Array(segs.length).fill(false);
        const chain = segs[0].slice(); used[0] = true;
        const FIT = 6;
        while (true) {
            const tail = chain[chain.length-1];
            let bI = -1, bRev = false, bD = Infinity;
            for (let i = 0; i < segs.length; i++) { if (used[i]) continue;
                const s = segs[i];
                const d1 = Math.hypot(s[0].x-tail.x, s[0].y-tail.y);
                const d2 = Math.hypot(s[s.length-1].x-tail.x, s[s.length-1].y-tail.y);
                if (d1 < bD) { bD = d1; bI = i; bRev = false; }
                if (d2 < bD) { bD = d2; bI = i; bRev = true; }
            }
            if (bI < 0 || bD > FIT) break;
            const next = bRev ? segs[bI].slice().reverse() : segs[bI];
            for (let j = 1; j < next.length; j++) chain.push(next[j]);
            used[bI] = true;
        }
        const head = chain[0], tail = chain[chain.length-1];
        if (Math.hypot(head.x-tail.x, head.y-tail.y) > 0.1) chain.push({x:head.x,y:head.y});
        const cum = [0];
        for (let i = 1; i < chain.length; i++) cum.push(cum[i-1] + Math.hypot(chain[i].x-chain[i-1].x, chain[i].y-chain[i-1].y));
        trainPath = { pts: chain, cum, total: cum[cum.length-1] };
    }
    function trainPosAt(s) {
        if (!trainPath || trainPath.total <= 0) return null;
        s = ((s % trainPath.total) + trainPath.total) % trainPath.total;
        const cum = trainPath.cum, pts = trainPath.pts;
        let lo = 0, hi = cum.length-1;
        while (lo < hi-1) { const m = (lo+hi)>>1; if (cum[m] <= s) lo = m; else hi = m; }
        const span = Math.max(cum[hi]-cum[lo], 1e-6);
        const t = (s-cum[lo])/span;
        return { x: pts[lo].x+t*(pts[hi].x-pts[lo].x), y: pts[lo].y+t*(pts[hi].y-pts[lo].y), ang: Math.atan2(pts[hi].y-pts[lo].y, pts[hi].x-pts[lo].x) };
    }
    function drawCar(off, color, len) {
        ctx.fillStyle = color; ctx.fillRect(-len/2, -5, len, 10);
        ctx.fillStyle = '#111'; ctx.beginPath(); ctx.arc(-len/2+3,6,2,0,Math.PI*2); ctx.arc(len/2-3,6,2,0,Math.PI*2); ctx.fill();
    }
    function drawTrain(s) {
        const carSpec = [{color:'#c62828',len:22,kind:'loco'},{color:'#1565c0',len:18,kind:'car'},{color:'#f9a825',len:18,kind:'car'}];
        let off = 0;
        for (const car of carSpec) {
            const pos = trainPosAt(s - off - car.len/2);
            if (!pos) return;
            ctx.save(); ctx.translate(wx(pos.x), wy(pos.y)); ctx.rotate(-pos.ang);
            drawCar(0, car.color, car.len);
            if (car.kind==='loco') { ctx.fillStyle = '#212121'; ctx.fillRect(-car.len/2+3,-8,4,4); ctx.fillStyle = '#37474f'; ctx.fillRect(car.len/2-8,-7,6,4); }
            ctx.restore(); off += car.len + 4;
        }
    }

    // ====================================================== hit testing
    function pointInPoly(x, y, poly) {
        let inside = false;
        for (let i = 0, j = poly.length-1; i < poly.length; j = i++) {
            const xi = poly[i].x, yi = poly[i].y;
            const xj = poly[j].x, yj = poly[j].y;
            const intersect = ((yi > y) !== (yj > y)) && (x < (xj-xi)*(y-yi)/(yj-yi+1e-12) + xi);
            if (intersect) inside = !inside;
        }
        return inside;
    }
    const ENDING_HIT_RADIUS = (isCoarse ? 22 : 12);
    function hitTest(worldX, worldY) {
        // Endings first (priority over body so a tap near the end picks the ending).
        const r = ENDING_HIT_RADIUS / scale;
        const r2 = r * r;
        for (let i = pieces.length-1; i >= 0; i--) {
            const p = pieces[i];
            for (let e = 0; e < p.endings.length; e++) {
                const m = midpoint([[p.endings[e].a.x, p.endings[e].a.y], [p.endings[e].b.x, p.endings[e].b.y]]);
                const dx = worldX - m[0], dy = worldY - m[1];
                if (dx*dx + dy*dy <= r2) return { piece: p, endingIdx: e };
            }
        }
        for (let i = pieces.length-1; i >= 0; i--) {
            const p = pieces[i];
            if (pointInPoly(worldX, worldY, p.path)) return { piece: p, endingIdx: null };
        }
        return null;
    }

    // ====================================================== drawing
    function drawEndingHandle(p, eIdx, end, isSelected) {
        const m = midpoint([[end.a.x, end.a.y], [end.b.x, end.b.y]]);
        const r = (isSelected ? 6.5 : 4.5) / scale;
        ctx.save();
        ctx.fillStyle = end.free ? (isSelected ? '#ff8f00' : 'rgba(255, 143, 0, 0.7)') : 'rgba(255,255,255,0.6)';
        ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.5/scale;
        ctx.beginPath(); ctx.arc(wx(m[0]), wy(m[1]), r*scale > 3 ? r : 3/scale, 0, Math.PI*2);
        ctx.fill(); ctx.stroke();
        ctx.restore();
    }

    function outlinePiece(piece, color, width) {
        ctx.save(); ctx.strokeStyle = color; ctx.lineWidth = width / scale;
        ctx.beginPath();
        for (let i = 0; i < piece.path.length; i++) { const p = piece.path[i]; if (i===0) ctx.moveTo(wx(p.x), wy(p.y)); else ctx.lineTo(wx(p.x), wy(p.y)); }
        ctx.closePath(); ctx.stroke(); ctx.restore();
    }

    function drawConnections() {
        // Build a lookup: piece_id -> piece object.
        const byId = {};
        for (const p of pieces) byId[p.id] = p;
        ctx.save();
        for (const [a, b] of connections) {
            const pa = byId[a.piece_id], pb = byId[b.piece_id];
            if (!pa || !pb) continue;
            const ea = pa.endings[a.ending_idx], eb = pb.endings[b.ending_idx];
            if (!ea || !eb) continue;
            // Midpoint of the connection (average of both ending midpoints).
            const ma = midpoint([[ea.a.x, ea.a.y], [ea.b.x, ea.b.y]]);
            const mb = midpoint([[eb.a.x, eb.a.y], [eb.b.x, eb.b.y]]);
            const cx = (ma[0] + mb[0]) * 0.5, cy = (ma[1] + mb[1]) * 0.5;
            // Direction perpendicular to the ending edge.
            const dx = ea.b.x - ea.a.x, dy = ea.b.y - ea.a.y;
            const len = Math.hypot(dx, dy) || 1;
            const nx = -dy / len, ny = dx / len;
            // Draw a short bridge bar across the joint.
            const hw = W0 * 0.55;  // half-width of the bar
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = Math.max(2.5 / scale, 1);
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(wx(cx - nx * hw), wy(cy - ny * hw));
            ctx.lineTo(wx(cx + nx * hw), wy(cy + ny * hw));
            ctx.stroke();
            // Inner colored line.
            ctx.strokeStyle = 'rgba(76,175,80,0.85)';
            ctx.lineWidth = Math.max(1.5 / scale, 0.7);
            ctx.beginPath();
            ctx.moveTo(wx(cx - nx * hw), wy(cy - ny * hw));
            ctx.lineTo(wx(cx + nx * hw), wy(cy + ny * hw));
            ctx.stroke();
        }
        ctx.restore();
    }

    let dragGhost = null;       // { type, pose, anchorIdx, snapTarget }
    let paletteGhost = null;    // { type, pose }

    function drawGhost(type, pose, snapped) {
        const tr = poseTransform(type, pose.x, pose.y, pose.rot);
        const path = tr.points.map(p => ({ x: p[0], y: p[1] }));
        ctx.save();
        ctx.globalAlpha = snapped ? 0.85 : 0.55;
        fillPolygon(path, snapped ? '#90caf9' : '#bbdefb');
        ctx.restore();
        ctx.save();
        ctx.strokeStyle = snapped ? '#1565c0' : '#5c6bc0';
        ctx.lineWidth = 2/scale;
        ctx.setLineDash(snapped ? [] : [4/scale, 3/scale]);
        ctx.beginPath();
        for (let i = 0; i < path.length; i++) { const p = path[i]; if (i===0) ctx.moveTo(wx(p.x), wy(p.y)); else ctx.lineTo(wx(p.x), wy(p.y)); }
        ctx.closePath(); ctx.stroke();
        ctx.restore();
    }

    function draw() {
        ctx.save();
        ctx.setTransform(scale, 0, 0, scale, posX, posY);
        ctx.clearRect(-posX/scale, -posY/scale, canvas.width/scale, canvas.height/scale);

        drawScenery();
        drawRoom();

        for (const p of pieces) {
            fillPolygon(p.path, '#616161');
            drawTiesAndRails(p.centerlines || [], p.color);
        }

        // Connection indicators at joined endings.
        drawConnections();

        // Free ending indicators on all pieces (subtle open-end dots).
        for (const p of pieces) {
            for (let e = 0; e < p.endings.length; e++) {
                if (!p.endings[e].free) continue;
                const m = midpoint([[p.endings[e].a.x, p.endings[e].a.y], [p.endings[e].b.x, p.endings[e].b.y]]);
                const r = 3 / scale;
                ctx.save();
                ctx.fillStyle = 'rgba(255,143,0,0.5)';
                ctx.beginPath(); ctx.arc(wx(m[0]), wy(m[1]), Math.max(r, 2/scale), 0, Math.PI*2); ctx.fill();
                ctx.restore();
            }
        }

        // Selection outline.
        if (multiSel.size > 1) {
            for (const p of pieces) {
                if (multiSel.has(p.id)) outlinePiece(p, '#ff8f00', 2.5);
            }
        } else if (selection) {
            const sel = pieces.find(p => p.id === selection.piece_id);
            if (sel) outlinePiece(sel, '#ff8f00', 3);
        }

        // Ending handles for selected piece (only when single-selected).
        if (selection && multiSel.size <= 1) {
            const sel = pieces.find(p => p.id === selection.piece_id);
            if (sel) for (let e = 0; e < sel.endings.length; e++)
                drawEndingHandle(sel, e, sel.endings[e], selection.ending_idx === e);
        }

        if (dragGhost) drawGhost(dragGhost.type, dragGhost.pose, !!dragGhost.snapTarget);
        if (paletteGhost) drawGhost(paletteGhost.type, paletteGhost.pose, false);

        if (trainPath) drawTrain(trainS);

        ctx.restore();
    }

    function animate(now) {
        const dt = Math.min((now - lastFrameT)/1000, 0.05);
        lastFrameT = now;
        if (trainPath) { trainS += 70*dt; }
        draw();
        requestAnimationFrame(animate);
    }

    // ====================================================== view-model wiring
    function applyView(v) {
        view = v;
        pieces = v.pieces || [];
        connections = v.connections || [];
        selection = v.selection || null;
        isClosed = !!v.is_closed;
        snapTol = v.snap_tolerance || snapTol;
        document.querySelectorAll('.palette-tile').forEach(el => {
            const t = el.getAttribute('data-piece');
            const c = (v.counter || {})[t] ?? 0;
            const lib = (userLib || {})[t] ?? 0;
            const b = el.querySelector('.badge'); if (b) b.textContent = `${c}/${lib}`;
            el.classList.toggle('over', c > lib);
        });
        const badge = document.getElementById('closedBadge');
        if (badge) {
            badge.classList.toggle('closed', isClosed);
            badge.innerHTML = isClosed ? '\u2714 Closed loop' : '\u26A0 Open ends';
        }
        const hasSel = !!selection || multiSel.size > 0;
        // Rotate only for single selection; delete works for any selection.
        ['rotateCcw','rotateCw'].forEach(id => { document.getElementById(id).disabled = !(selection && multiSel.size <= 1); });
        document.getElementById('deleteSel').disabled = !hasSel;
        // Prune multiSel: remove IDs for pieces that no longer exist.
        const currentIds = new Set(pieces.map(p => p.id));
        for (const id of [...multiSel]) { if (!currentIds.has(id)) multiSel.delete(id); }
        buildTrainPath();
        draw();
    }

    // ====================================================== JSON action helper
    const isAnonymous = !!window.EDITOR_ANONYMOUS;
    let pendingActions = Promise.resolve();
    function action(op, args = {}) {
        const body = JSON.stringify(Object.assign({ op }, args));
        const p = pendingActions.then(() => fetch(ACTION_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body,
        }).then(r => r.json()).then(json => {
            if (json.login_required) {
                if (confirm('Register a free account to save your tracks!\n\nGo to registration page?')) {
                    window.location.href = '/user_register';
                }
                return json;
            }
            if (!json.ok) { console.warn('action failed', op, json.error); return json; }
            if (json.saved) { window.location.href = '/track_open'; return json; }
            if (json.view) applyView(json.view);
            return json;
        }).catch(err => { console.warn('action error', op, err); }));
        pendingActions = p.catch(() => {});
        return p;
    }

    // ====================================================== free endings (excluding a piece)
    function freeEndingsExcluding(pieceId) {
        const out = [];
        const myConns = new Set();
        for (const c of connections) {
            if (c[0].piece_id === pieceId) myConns.add(`${c[1].piece_id}:${c[1].ending_idx}`);
            else if (c[1].piece_id === pieceId) myConns.add(`${c[0].piece_id}:${c[0].ending_idx}`);
        }
        for (const p of pieces) {
            if (p.id === pieceId) continue;
            for (let e = 0; e < p.endings.length; e++) {
                const end = p.endings[e];
                if (end.free || myConns.has(`${p.id}:${e}`)) {
                    out.push({ piece_id: p.id, ending_idx: e, pair: [[end.a.x, end.a.y], [end.b.x, end.b.y]] });
                }
            }
        }
        return out;
    }

    // ====================================================== gestures
    const SLOP_PX = isCoarse ? 8 : 4;
    const LONG_PRESS_MS = 250;
    const activePointers = new Map(); // id -> { startX,startY, role, ... }

    function pointerStartOnCanvas(ev) {
        canvas.setPointerCapture(ev.pointerId);
        const world = clientToWorld(ev.clientX, ev.clientY);
        const hit = hitTest(world.x, world.y);
        const rec = {
            startX: ev.clientX, startY: ev.clientY,
            curX: ev.clientX, curY: ev.clientY,
            startWorld: world,
            hit,
            shiftKey: ev.shiftKey,
            startScale: scale, startPosX: posX, startPosY: posY,
            dragPiece: null, dragOrigPose: null, dragAnchorIdx: null,
            panActive: !hit,
            longPressTimer: null,
            promoted: false,
            cancelled: false,
        };
        activePointers.set(ev.pointerId, rec);

        // Two-finger gesture: cancel any drag.
        if (activePointers.size === 2) {
            for (const r of activePointers.values()) {
                if (r.dragPiece) cancelDrag(r);
                if (r.longPressTimer) { clearTimeout(r.longPressTimer); r.longPressTimer = null; }
                r.panActive = false;
            }
            const it = [...activePointers.values()];
            pinch.distance = Math.hypot(it[0].curX - it[1].curX, it[0].curY - it[1].curY);
            pinch.scale = scale;
            pinch.midX = (it[0].curX + it[1].curX)/2;
            pinch.midY = (it[0].curY + it[1].curY)/2;
            pinch.posX = posX; pinch.posY = posY;
            return;
        }

        if (hit) {
            const pid = hit.piece.id;
            const desiredEnding = hit.endingIdx;

            if (ev.shiftKey) {
                if (multiSel.has(pid)) {
                    multiSel.delete(pid);
                    if (selection && selection.piece_id === pid) {
                        if (multiSel.size > 0) {
                            const next = multiSel.values().next().value;
                            selection = { piece_id: next, ending_idx: null };
                            action('select', { piece_id: next, ending_idx: null });
                        } else {
                            selection = null;
                            action('clear_selection');
                        }
                    }
                } else {
                    multiSel.add(pid);
                    selection = { piece_id: pid, ending_idx: desiredEnding };
                    action('select', { piece_id: pid, ending_idx: desiredEnding });
                }
                rec.deferCollapse = false;
            } else if (multiSel.size > 1 && multiSel.has(pid)) {
                selection = { piece_id: pid, ending_idx: desiredEnding };
                rec.deferCollapse = true;
            } else {
                multiSel.clear();
                multiSel.add(pid);
                selection = { piece_id: pid, ending_idx: desiredEnding };
                action('select', { piece_id: pid, ending_idx: desiredEnding });
                rec.deferCollapse = false;
            }
            const hasSel = !!selection || multiSel.size > 0;
            ['rotateCcw','rotateCw'].forEach(id => { document.getElementById(id).disabled = !(selection && multiSel.size <= 1); });
            document.getElementById('deleteSel').disabled = !hasSel;
            draw();
            if (isCoarse) {
                rec.longPressTimer = setTimeout(() => {
                    if (rec.cancelled) return;
                    if (!rec.promoted) startDrag(rec);
                }, LONG_PRESS_MS);
            }
        }
    }

    let multiDragOrigPoses = null;

    function startDrag(rec) {
        if (!rec.hit) return;
        rec.promoted = true;
        rec.dragPiece = rec.hit.piece;
        rec.dragOrigPose = { x: rec.dragPiece.x, y: rec.dragPiece.y, rot: rec.dragPiece.rot };
        rec.dragAnchorIdx = rec.hit.endingIdx;

        if (multiSel.size > 1 && multiSel.has(rec.dragPiece.id)) {
            multiDragOrigPoses = new Map();
            for (const p of pieces) {
                if (multiSel.has(p.id)) {
                    multiDragOrigPoses.set(p.id, { x: p.x, y: p.y, rot: p.rot });
                }
            }
            dragGhost = null;
        } else {
            multiDragOrigPoses = null;
            dragGhost = { type: rec.dragPiece.type, pose: { ...rec.dragOrigPose }, anchorIdx: rec.dragAnchorIdx, snapTarget: null };
        }
        draw();
    }

    function cancelDrag(rec) {
        if (rec.dragPiece) {
            if (multiDragOrigPoses) {
                for (const p of pieces) {
                    const orig = multiDragOrigPoses.get(p.id);
                    if (orig) { p.x = orig.x; p.y = orig.y; p.rot = orig.rot; }
                }
                multiDragOrigPoses = null;
            }
            dragGhost = null;
            draw();
        }
        rec.dragPiece = null;
        rec.cancelled = true;
    }

    function pointerMoveOnCanvas(ev) {
        const rec = activePointers.get(ev.pointerId);
        if (!rec) return;
        rec.curX = ev.clientX; rec.curY = ev.clientY;

        if (activePointers.size >= 2) {
            handlePinch();
            return;
        }

        const dx = rec.curX - rec.startX;
        const dy = rec.curY - rec.startY;
        const dist = Math.hypot(dx, dy);

        if (rec.panActive) {
            posX = rec.startPosX + dx;
            posY = rec.startPosY + dy;
            clampPan();
            draw();
            return;
        }

        if (rec.hit && !rec.promoted && dist > SLOP_PX) {
            if (rec.longPressTimer) { clearTimeout(rec.longPressTimer); rec.longPressTimer = null; }
            startDrag(rec);
        }

        if (rec.dragPiece) {
            const world = clientToWorld(ev.clientX, ev.clientY);
            const startWorld = rec.startWorld;
            const deltaX = world.x - startWorld.x;
            const deltaY = world.y - startWorld.y;

            if (multiDragOrigPoses) {
                for (const p of pieces) {
                    const orig = multiDragOrigPoses.get(p.id);
                    if (orig) { p.x = orig.x + deltaX; p.y = orig.y + deltaY; }
                }
                for (const p of pieces) {
                    if (!multiDragOrigPoses.has(p.id)) continue;
                    const tr = poseTransform(p.type, p.x, p.y, p.rot);
                    p.path = tr.points.map(pt => ({ x: pt[0], y: pt[1] }));
                    p.endings = p.endings.map((end, ei) => ({
                        a: { x: tr.endings[ei][0][0], y: tr.endings[ei][0][1] },
                        b: { x: tr.endings[ei][1][0], y: tr.endings[ei][1][1] },
                        free: end.free,
                    }));
                }
            } else {
                const newPose = {
                    x: rec.dragOrigPose.x + deltaX,
                    y: rec.dragOrigPose.y + deltaY,
                    rot: dragGhost.pose.rot,
                };
                const tol = snapTol + (isCoarse ? 14 : 6) / scale;
                const targets = freeEndingsExcluding(rec.dragPiece.id);
                const anchors = rec.dragAnchorIdx != null ? [rec.dragAnchorIdx] : [...Array(ENDING_COUNT[rec.dragPiece.type]).keys()];
                let bestSnap = null, bestD = Infinity;
                for (const a of anchors) {
                    const s = localSnap(rec.dragPiece.type, a, newPose, targets, tol);
                    if (!s) continue;
                    const dd = (s.pose.x - newPose.x)**2 + (s.pose.y - newPose.y)**2;
                    if (dd < bestD) { bestD = dd; bestSnap = { res: s, anchor: a }; }
                }
                if (bestSnap) {
                    dragGhost = { type: rec.dragPiece.type, pose: bestSnap.res.pose, anchorIdx: bestSnap.anchor, snapTarget: bestSnap.res.target };
                } else {
                    dragGhost = { type: rec.dragPiece.type, pose: newPose, anchorIdx: rec.dragAnchorIdx, snapTarget: null };
                }
            }
            draw();
        }
    }

    function pointerUpOnCanvas(ev) {
        const rec = activePointers.get(ev.pointerId);
        activePointers.delete(ev.pointerId);
        if (!rec) return;
        if (rec.longPressTimer) { clearTimeout(rec.longPressTimer); rec.longPressTimer = null; }
        canvas.releasePointerCapture && canvas.releasePointerCapture(ev.pointerId);

        if (activePointers.size > 0) return;

        if (rec.dragPiece && multiDragOrigPoses) {
            const moves = [];
            for (const p of pieces) {
                if (!multiDragOrigPoses.has(p.id)) continue;
                moves.push({ piece_id: p.id, x: p.x, y: p.y, rot: p.rot });
            }
            multiDragOrigPoses = null;
            action('move_pieces', { moves });
            saveView();
            return;
        }

        if (rec.dragPiece && dragGhost) {
            const dropPose = dragGhost.pose;
            const anchor = dragGhost.anchorIdx;
            dragGhost = null;
            action('commit_move', {
                piece_id: rec.dragPiece.id,
                x: dropPose.x, y: dropPose.y, rot: dropPose.rot,
                anchor_ending_idx: anchor,
            });
            saveView();
            return;
        }

        if (rec.deferCollapse && !rec.promoted) {
            const pid = rec.hit && rec.hit.piece ? rec.hit.piece.id : null;
            if (pid !== null) {
                multiSel.clear();
                multiSel.add(pid);
                selection = { piece_id: pid, ending_idx: rec.hit.endingIdx };
                ['rotateCcw','rotateCw'].forEach(id => { document.getElementById(id).disabled = false; });
                document.getElementById('deleteSel').disabled = false;
                draw();
                action('select', { piece_id: pid, ending_idx: rec.hit.endingIdx });
            }
            return;
        }

        const dist = Math.hypot(rec.curX - rec.startX, rec.curY - rec.startY);
        if (rec.panActive) {
            if (dist > SLOP_PX) saveView();
            else if (!rec.shiftKey) {
                if (selection || multiSel.size > 0) {
                    selection = null;
                    multiSel.clear();
                    ['rotateCcw','rotateCw','deleteSel'].forEach(id => { document.getElementById(id).disabled = true; });
                    draw();
                    action('clear_selection');
                }
            }
        }
    }

    function pointerCancelOnCanvas(ev) {
        const rec = activePointers.get(ev.pointerId);
        activePointers.delete(ev.pointerId);
        if (!rec) return;
        if (rec.longPressTimer) clearTimeout(rec.longPressTimer);
        if (rec.dragPiece) {
            if (multiDragOrigPoses) {
                for (const p of pieces) {
                    const orig = multiDragOrigPoses.get(p.id);
                    if (orig) { p.x = orig.x; p.y = orig.y; p.rot = orig.rot; }
                }
                multiDragOrigPoses = null;
            }
            dragGhost = null; draw();
        }
    }

    // ----- pinch zoom -----
    function minScale() {
        const larger = isCoarse ? canvas.height : canvas.width;
        return larger > 0 ? larger / MAX_WORLD : 0.1;
    }
    const pinch = { distance: 0, scale: 1, midX: 0, midY: 0, posX: 0, posY: 0 };
    function handlePinch() {
        const it = [...activePointers.values()];
        if (it.length < 2) return;
        const d = Math.hypot(it[0].curX - it[1].curX, it[0].curY - it[1].curY);
        if (pinch.distance <= 0) return;
        const newScale = Math.min(10, Math.max(minScale(), (d / pinch.distance) * pinch.scale));
        const r = canvas.getBoundingClientRect();
        const cx = pinch.midX - r.left, cy = pinch.midY - r.top;
        const ratio = newScale / scale;
        posX = cx - (cx - posX) * ratio;
        posY = cy - (cy - posY) * ratio;
        scale = newScale;
        const newMidX = (it[0].curX + it[1].curX)/2;
        const newMidY = (it[0].curY + it[1].curY)/2;
        posX += (newMidX - pinch.midX);
        posY += (newMidY - pinch.midY);
        pinch.midX = newMidX; pinch.midY = newMidY;
        clampPan();
        draw();
    }

    canvas.addEventListener('pointerdown', pointerStartOnCanvas);
    canvas.addEventListener('pointermove', pointerMoveOnCanvas);
    canvas.addEventListener('pointerup', pointerUpOnCanvas);
    canvas.addEventListener('pointercancel', pointerCancelOnCanvas);
    canvas.addEventListener('contextmenu', e => e.preventDefault());

    // Wheel zoom (mouse / trackpad).
    canvas.addEventListener('wheel', (ev) => {
        ev.preventDefault();
        const delta = ev.deltaY < 0 ? 1.1 : 0.9;
        const ns = scale * delta;
        if (ns < minScale() || ns > 10) return;
        const r = canvas.getBoundingClientRect();
        const mx = ev.clientX - r.left, my = ev.clientY - r.top;
        posX -= (mx - posX) * (delta - 1);
        posY -= (my - posY) * (delta - 1);
        scale = ns;
        clampPan();
        saveView(); draw();
    }, { passive: false });

    // Double-click resets the view.
    canvas.addEventListener('dblclick', (ev) => { ev.preventDefault(); scale = DEFAULT_SCALE; centerView(); saveView(); draw(); });
    document.getElementById('resetView').addEventListener('click', () => { scale = DEFAULT_SCALE; centerView(); saveView(); draw(); });

    // ====================================================== palette interactions
    function paletteCenterSpawn(type) {
        if (selection) {
            const sel = pieces.find(p => p.id === selection.piece_id);
            if (sel) {
                let freeIdx = -1;
                if (selection.ending_idx != null && sel.endings[selection.ending_idx] && sel.endings[selection.ending_idx].free) {
                    freeIdx = selection.ending_idx;
                } else {
                    for (let e = 0; e < sel.endings.length; e++) {
                        if (sel.endings[e].free) { freeIdx = e; break; }
                    }
                }
                if (freeIdx >= 0) {
                    const end = sel.endings[freeIdx];
                    const targetPair = [[end.a.x, end.a.y], [end.b.x, end.b.y]];
                    const nEndings = ENDING_COUNT[type];
                    let bestPose = null;
                    for (let a = 0; a < nEndings; a++) {
                        const pose = poseAlign(type, a, targetPair);
                        bestPose = bestPose || pose;
                        const newPts = poseTransform(type, pose.x, pose.y, pose.rot).points;
                        const selPts = sel.path.map(p => [p.x, p.y]);
                        if (!polyOverlap(newPts, selPts)) {
                            bestPose = pose;
                            break;
                        }
                    }
                    action('add_piece', { type, x: bestPose.x, y: bestPose.y, rot: bestPose.rot });
                    return;
                }
            }
        }
        const r = canvas.getBoundingClientRect();
        const world = clientToWorld(r.left + r.width/2, r.top + r.height/2);
        action('add_piece', { type, x: world.x, y: world.y, rot: 0 });
    }

    // Lightweight polygon overlap test (mirrors server-side polygons_overlap).
    function _segsCross(a1, a2, b1, b2) {
        const cross = (o, a, b) => (a[0]-o[0])*(b[1]-o[1]) - (a[1]-o[1])*(b[0]-o[0]);
        const d1 = cross(b1,b2,a1), d2 = cross(b1,b2,a2);
        const d3 = cross(a1,a2,b1), d4 = cross(a1,a2,b2);
        return ((d1>0)!==(d2>0)) && ((d3>0)!==(d4>0));
    }
    function _ptInPoly(px, py, poly) {
        let inside = false;
        for (let i = 0, j = poly.length-1; i < poly.length; j = i++) {
            const [xi,yi] = poly[i], [xj,yj] = poly[j];
            if (((yi>py)!==(yj>py)) && (px < (xj-xi)*(py-yi)/(yj-yi+1e-12)+xi)) inside = !inside;
        }
        return inside;
    }
    function polyOverlap(a, b) {
        for (let i = 0; i < a.length; i++) {
            const a1 = a[i], a2 = a[(i+1)%a.length];
            for (let j = 0; j < b.length; j++) {
                if (_segsCross(a1, a2, b[j], b[(j+1)%b.length])) return true;
            }
        }
        return _ptInPoly(a[0][0], a[0][1], b) || _ptInPoly(b[0][0], b[0][1], a);
    }

    function attachPalette() {
        document.querySelectorAll('.palette-tile').forEach(tile => {
            const type = tile.getAttribute('data-piece');
            let pdownId = null;
            let dragging = false;
            let startX = 0, startY = 0;
            tile.addEventListener('pointerdown', (ev) => {
                pdownId = ev.pointerId;
                dragging = false;
                startX = ev.clientX; startY = ev.clientY;
                try { tile.setPointerCapture(ev.pointerId); } catch (_) {}
            });
            tile.addEventListener('pointermove', (ev) => {
                if (pdownId !== ev.pointerId) return;
                const dx = ev.clientX - startX, dy = ev.clientY - startY;
                if (!dragging && Math.hypot(dx, dy) > SLOP_PX) {
                    dragging = true;
                    paletteGhost = { type, pose: { x: 0, y: 0, rot: 0 } };
                }
                if (dragging) {
                    const world = clientToWorld(ev.clientX, ev.clientY);
                    paletteGhost.pose.x = world.x; paletteGhost.pose.y = world.y;
                    draw();
                }
            });
            tile.addEventListener('pointerup', (ev) => {
                if (pdownId !== ev.pointerId) return;
                try { tile.releasePointerCapture(ev.pointerId); } catch (_) {}
                pdownId = null;
                if (dragging) {
                    const r = canvas.getBoundingClientRect();
                    if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
                        const world = clientToWorld(ev.clientX, ev.clientY);
                        paletteGhost = null;
                        action('add_piece', { type, x: world.x, y: world.y, rot: 0 });
                    } else {
                        paletteGhost = null; draw();
                    }
                } else {
                    paletteCenterSpawn(type);
                }
                dragging = false;
            });
            tile.addEventListener('pointercancel', () => {
                pdownId = null; dragging = false; paletteGhost = null; draw();
            });
        });
    }
    attachPalette();

    // ====================================================== selection toolbar
    document.getElementById('rotateCw').addEventListener('click', () => {
        if (selection && multiSel.size <= 1) action('rotate_piece', { piece_id: selection.piece_id, delta_steps: -1 });
    });
    document.getElementById('rotateCcw').addEventListener('click', () => {
        if (selection && multiSel.size <= 1) action('rotate_piece', { piece_id: selection.piece_id, delta_steps: 1 });
    });
    document.getElementById('deleteSel').addEventListener('click', () => {
        if (multiSel.size > 1) {
            action('delete_pieces', { piece_ids: [...multiSel] });
            multiSel.clear(); selection = null;
        } else if (selection) {
            const neighbor = connectedNeighbor(selection.piece_id);
            multiSel.delete(selection.piece_id);
            action('delete_piece', { piece_id: selection.piece_id });
            if (neighbor) {
                selection = { piece_id: neighbor, ending_idx: null };
                multiSel.add(neighbor);
            } else {
                selection = null;
            }
        }
    });
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) saveBtn.addEventListener('click', () => action('save'));
    const closeBtn = document.getElementById('closeBtn');
    if (closeBtn) closeBtn.addEventListener('click', () => {
        if (!confirm('Close without saving? Unsaved changes will be lost.')) return;
        const form = document.createElement('form');
        form.method = 'POST';
        form.action = ACTION_URL.replace(/\/action$/, '/close');
        const tok = document.createElement('input');
        tok.type = 'hidden'; tok.name = 'csrf_token'; tok.value = csrfToken;
        form.appendChild(tok);
        document.body.appendChild(form);
        form.submit();
    });

    // ====================================================== title rename
    document.getElementById('titlePill').addEventListener('click', () => {
        if (isAnonymous) return;
        const cur = document.getElementById('titleText').textContent;
        const n = prompt('Rename track:', cur);
        if (!n || n === cur) return;
        if (!/^[A-Za-z0-9 ()]+$/.test(n)) { alert('Letters, numbers, spaces and parentheses only.'); return; }
        fetch(ACTION_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body: JSON.stringify({ op: 'rename', title: n }),
        }).then(r => r.json()).then(json => {
            if (json.ok) document.getElementById('titleText').textContent = json.title;
            else alert(json.error || 'Rename failed');
        });
    });

    // ====================================================== keyboard
    document.addEventListener('keydown', (ev) => {
        if (ev.target && (ev.target.tagName === 'INPUT' || ev.target.tagName === 'TEXTAREA')) return;
        if (ev.ctrlKey && ev.key.toLowerCase() === 's') { ev.preventDefault(); action('save'); return; }
        if (ev.ctrlKey && ev.key.toLowerCase() === 'a') {
            ev.preventDefault();
            multiSel.clear();
            for (const p of pieces) multiSel.add(p.id);
            if (!selection && pieces.length) selection = { piece_id: pieces[0].id, ending_idx: null };
            ['rotateCcw','rotateCw'].forEach(id => { document.getElementById(id).disabled = true; });
            document.getElementById('deleteSel').disabled = multiSel.size === 0;
            draw();
            return;
        }
        if (!selection && multiSel.size === 0) return;
        switch (ev.key) {
            case 'r': case 'R': case 'e': case 'E':
                if (selection && multiSel.size <= 1) {
                    ev.preventDefault(); action('rotate_piece', { piece_id: selection.piece_id, delta_steps: -1 });
                } break;
            case 'q': case 'Q':
                if (selection && multiSel.size <= 1) {
                    ev.preventDefault(); action('rotate_piece', { piece_id: selection.piece_id, delta_steps: 1 });
                } break;
            case 'Backspace': case 'Delete':
                ev.preventDefault();
                if (multiSel.size > 1) {
                    action('delete_pieces', { piece_ids: [...multiSel] });
                    multiSel.clear(); selection = null;
                } else if (selection) {
                    const neighbor = connectedNeighbor(selection.piece_id);
                    multiSel.delete(selection.piece_id);
                    action('delete_piece', { piece_id: selection.piece_id });
                    if (neighbor) {
                        selection = { piece_id: neighbor, ending_idx: null };
                        multiSel.add(neighbor);
                    } else {
                        selection = null;
                    }
                }
                break;
            case 'Escape':
                ev.preventDefault(); selection = null; multiSel.clear();
                ['rotateCcw','rotateCw','deleteSel'].forEach(id => { document.getElementById(id).disabled = true; });
                draw(); action('clear_selection'); break;
        }
    });

    // ====================================================== boot
    applyView(view);
    requestAnimationFrame(animate);
})();
