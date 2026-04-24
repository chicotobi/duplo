// Track editor canvas + interaction script (pose-based, drag/drop/snap).
// Uses Pointer Events so mouse, touch, and pen share one code path.
// Reads its initial render data from window.EDITOR_DATA.
(function () {
    'use strict';

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
    const PIECE_TYPES = ['straight', 'curve', 'switch', 'crossing'];
    const isCoarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;

    // ====================================================== piece geometry tables (mirror of duplo.services.geometry)
    const W0 = 10;
    const L0 = 40;
    const C0 = L0 * 7 / 2 / Math.sqrt(3);
    const ENDING_COUNT = { straight: 2, curve: 2, switch: 3, crossing: 4 };

    function localStraight() {
        return { points: [[0,0],[W0,0],[W0,L0],[0,L0]],
                 endings: [[[W0,0],[0,0]], [[0,L0],[W0,L0]]] };
    }
    function localCurve() {
        const n = 5;
        const t = []; for (let i = 0; i < n; i++) t.push(i/(n-1)*Math.PI/6);
        const x0 = t.map(Math.cos), y0 = t.map(Math.sin);
        const ri = C0 - W0/2, ro = C0 + W0/2;
        const pts = [];
        for (let i = 0; i < n; i++) pts.push([ri*x0[i], ri*y0[i]]);
        for (let i = n-1; i >= 0; i--) pts.push([ro*x0[i], ro*y0[i]]);
        const c0a = Math.cos(0), s0a = Math.sin(0);
        const c1a = Math.cos(Math.PI/6), s1a = Math.sin(Math.PI/6);
        return { points: pts,
                 endings: [[[ro*c0a, ro*s0a], [ri*c0a, ri*s0a]],
                           [[ri*c1a, ri*s1a], [ro*c1a, ro*s1a]]] };
    }
    function localSwitch() {
        const n = 10;
        const m = Math.round(n*0.6);
        const t = []; for (let i = 0; i < n; i++) t.push(i/(n-1)*Math.PI/6);
        const x0 = t.map(Math.cos), y0 = t.map(Math.sin);
        const ri = C0 - W0/2, ro = C0 + W0/2;
        const pts = [];
        for (let i = 0; i < n; i++) pts.push([ri*x0[i], ri*y0[i]]);
        for (let i = n-1; i > m; i--) pts.push([ro*x0[i], ro*y0[i]]);
        for (let i = m; i < n; i++) pts.push([2*C0 - ro*x0[i], ro*y0[i]]);
        for (let i = n-1; i >= 0; i--) pts.push([2*C0 - ri*x0[i], ri*y0[i]]);
        const c0a = Math.cos(0), s0a = Math.sin(0);
        const c1a = Math.cos(Math.PI/6), s1a = Math.sin(Math.PI/6);
        return { points: pts,
                 endings: [[[ro*c0a, ro*s0a], [ri*c0a, ri*s0a]],
                           [[ri*c1a, ri*s1a], [ro*c1a, ro*s1a]],
                           [[2*C0 - ro*c1a, ro*s1a], [2*C0 - ri*c1a, ri*s1a]]] };
    }
    function localCrossing() {
        const hw = W0/2, hl = L0/2;
        const a1=[-hw,-hl], a2=[hw,-hl], a3=[hw,hl], a4=[-hw,hl];
        const cost=Math.cos(Math.PI/3), sint=Math.sin(Math.PI/3);
        const rot = p => [cost*p[0]+sint*p[1], -sint*p[0]+cost*p[1]];
        const b1=rot(a1), b2=rot(a2), b3=rot(a3), b4=rot(a4);
        const m = (b4[1]-b1[1])/(b4[0]-b1[0]);
        const y0 = b4[1] - m*b4[0];
        const v1 = m*-hw + y0, v2 = m*hw + y0;
        const points = [a1, a2, [hw,-v1], b3, b4, [hw,v2], a3, a4, [-hw,v1], b1, b2, [-hw,-v2]];
        return { points,
                 endings: [[a2,a1],[b2,b1],[a4,a3],[b4,b3]] };
    }
    const LOCAL = {
        straight: localStraight(),
        curve:    localCurve(),
        switch:   localSwitch(),
        crossing: localCrossing(),
    };

    // Re-center each piece type so the local origin (0,0) sits at the
    // centroid of the piece's outline. Mirrors duplo.services.geometry —
    // both sides MUST recenter identically so stored poses align.
    for (const _t of PIECE_TYPES) {
        const lp = LOCAL[_t];
        let sx = 0, sy = 0;
        for (const p of lp.points) { sx += p[0]; sy += p[1]; }
        const cx = sx / lp.points.length, cy = sy / lp.points.length;
        lp.points = lp.points.map(p => [p[0] - cx, p[1] - cy]);
        lp.endings = lp.endings.map(e => e.map(p => [p[0] - cx, p[1] - cy]));
    }

    function poseTransform(type, x, y, rot) {
        const a = (((rot % 12) + 12) % 12) * Math.PI / 6;
        const ca = Math.cos(a), sa = Math.sin(a);
        const lp = LOCAL[type];
        const trafo = p => [ca*p[0]-sa*p[1]+x, sa*p[0]+ca*p[1]+y];
        return {
            points: lp.points.map(trafo),
            endings: lp.endings.map(e => e.map(trafo)),
        };
    }

    function poseAlign(type, anchorIdx, target /* [[T1x,T1y],[T2x,T2y]] */) {
        // Place piece so its anchor ending overlays target reversed.
        const [L1, L2] = LOCAL[type].endings[anchorIdx];
        const [T1, T2] = target;
        const dlx = L2[0]-L1[0], dly = L2[1]-L1[1];
        const dwx = T1[0]-T2[0], dwy = T1[1]-T2[1];
        const angle = Math.atan2(dwy, dwx) - Math.atan2(dly, dlx);
        let steps = Math.round(angle / (Math.PI/6)) % 12;
        if (steps < 0) steps += 12;
        const qa = steps * Math.PI/6;
        const ca = Math.cos(qa), sa = Math.sin(qa);
        return {
            x: T2[0] - (ca*L1[0] - sa*L1[1]),
            y: T2[1] - (sa*L1[0] + ca*L1[1]),
            rot: steps,
        };
    }

    function midpoint(pair) {
        return [(pair[0][0]+pair[1][0])*0.5, (pair[0][1]+pair[1][1])*0.5];
    }

    function localSnap(type, anchorIdx, currentPose, targets, tol) {
        const cw = poseTransform(type, currentPose.x, currentPose.y, currentPose.rot).endings[anchorIdx];
        const cm = midpoint(cw);
        let best = null, bestD = Infinity;
        const tol2 = tol * tol;
        for (const t of targets) {
            const tm = midpoint(t.pair);
            const d = (cm[0]-tm[0])**2 + (cm[1]-tm[1])**2;
            if (d > tol2) continue;
            if (d < bestD) {
                bestD = d;
                best = { pose: poseAlign(type, anchorIdx, t.pair), target: { piece_id: t.piece_id, ending_idx: t.ending_idx } };
            }
        }
        return best;
    }

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
    window.addEventListener('resize', () => { resizeCanvas(); draw(); });

    const VIEW_KEY = 'duplo.editorView';
    let scale = 1, posX = 0, posY = 0;
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

    // ====================================================== scenery (kept from previous version)
    function mulberry32(seed) { return function () { let t = seed += 0x6D2B79F5; t = Math.imul(t ^ t >>> 15, t | 1); t ^= t + Math.imul(t ^ t >>> 7, t | 61); return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
    const _rand = mulberry32(20240507);
    const DECOR_RANGE = 1200;
    const decorations = [];
    for (let i = 0; i < 140; i++) {
        const r = _rand();
        let kind = r < 0.45 ? 'tree' : (r < 0.85 ? 'bush' : 'flower');
        decorations.push({ x: (_rand()-0.5)*2*DECOR_RANGE, y: (_rand()-0.5)*2*DECOR_RANGE, kind, size: 7+_rand()*9, tone: _rand() });
    }
    const riverPath = [];
    for (let i = -DECOR_RANGE; i <= DECOR_RANGE; i += 25) riverPath.push({ x: i, y: -380 + 35*Math.sin(i*0.012) + 10*Math.cos(i*0.04) });

    function drawMeadow() {
        const x0 = -posX/scale, y0 = -posY/scale;
        const w = canvas.width/scale, h = canvas.height/scale;
        ctx.fillStyle = '#7fbf52'; ctx.fillRect(x0, y0, w, h);
        ctx.fillStyle = 'rgba(60,130,60,0.18)';
        const seed = mulberry32(99);
        for (let i = 0; i < 30; i++) {
            const px = (seed()-0.5)*2*DECOR_RANGE, py = (seed()-0.5)*2*DECOR_RANGE;
            const pr = 50 + seed()*100;
            ctx.beginPath(); ctx.arc(wx(px), wy(py), pr, 0, Math.PI*2); ctx.fill();
        }
    }
    function drawRiver() {
        ctx.strokeStyle = '#5dade2'; ctx.lineWidth = 22; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
        ctx.beginPath();
        for (let i = 0; i < riverPath.length; i++) { const p = riverPath[i]; if (i===0) ctx.moveTo(wx(p.x), wy(p.y)); else ctx.lineTo(wx(p.x), wy(p.y)); }
        ctx.stroke();
        ctx.strokeStyle = '#aed6f1'; ctx.lineWidth = 6;
        ctx.beginPath();
        for (let i = 0; i < riverPath.length; i++) { const p = riverPath[i]; if (i===0) ctx.moveTo(wx(p.x), wy(p.y+4)); else ctx.lineTo(wx(p.x), wy(p.y+4)); }
        ctx.stroke();
    }
    function drawTree(d){const cx=wx(d.x),cy=wy(d.y);ctx.fillStyle='#6b3e1f';ctx.fillRect(cx-d.size*0.18,cy,d.size*0.36,d.size*0.7);ctx.fillStyle=d.tone<0.5?'#2e7d32':'#388e3c';ctx.beginPath();ctx.arc(cx,cy,d.size,0,Math.PI*2);ctx.fill();ctx.fillStyle='#1b5e20';ctx.beginPath();ctx.arc(cx-d.size*0.35,cy-d.size*0.25,d.size*0.45,0,Math.PI*2);ctx.fill();}
    function drawBush(d){const cx=wx(d.x),cy=wy(d.y);ctx.fillStyle=d.tone<0.5?'#388e3c':'#43a047';ctx.beginPath();ctx.arc(cx-d.size*0.4,cy,d.size*0.6,0,Math.PI*2);ctx.arc(cx+d.size*0.4,cy,d.size*0.6,0,Math.PI*2);ctx.arc(cx,cy-d.size*0.4,d.size*0.6,0,Math.PI*2);ctx.fill();}
    function drawFlower(d){const cx=wx(d.x),cy=wy(d.y);ctx.fillStyle=d.tone<0.33?'#fff59d':(d.tone<0.66?'#f48fb1':'#ce93d8');for(let k=0;k<5;k++){const a=k*Math.PI*2/5;ctx.beginPath();ctx.arc(cx+Math.cos(a)*d.size*0.25,cy+Math.sin(a)*d.size*0.25,d.size*0.18,0,Math.PI*2);ctx.fill();}ctx.fillStyle='#fbc02d';ctx.beginPath();ctx.arc(cx,cy,d.size*0.15,0,Math.PI*2);ctx.fill();}
    function drawDecorations(){for(const d of decorations){if(d.kind==='tree')drawTree(d);else if(d.kind==='bush')drawBush(d);else drawFlower(d);}}

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
        // lightweight rails for ghost: skip — keep it cheap
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

        drawMeadow(); drawRiver(); drawDecorations();

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
        if (trainPath) { trainS += 70*dt; draw(); }
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
    let pendingActions = Promise.resolve();
    function action(op, args = {}) {
        const body = JSON.stringify(Object.assign({ op }, args));
        const p = pendingActions.then(() => fetch(ACTION_URL, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
            body,
        }).then(r => r.json()).then(json => {
            if (!json.ok) { console.warn('action failed', op, json.error); return json; }
            if (json.saved) { window.location.href = '/'; return json; }
            if (json.view) applyView(json.view);
            return json;
        }).catch(err => { console.warn('action error', op, err); }));
        pendingActions = p.catch(() => {});
        return p;
    }

    // ====================================================== free endings (excluding a piece)
    function freeEndingsExcluding(pieceId) {
        // Build directly from the current view: any ending marked free that
        // belongs to a piece other than `pieceId`. We re-derive freeness
        // ignoring pieces[pieceId]'s endings — but the server's view already
        // computed it including all pieces. For the snap preview we want to
        // pretend the dragged piece is invisible. Approximate: trust the
        // server's `free`, and additionally allow snapping onto endings that
        // are *currently* connected to the dragged piece (treat them as free).
        const out = [];
        const myConns = new Set(); // endings of other pieces currently locked to me
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
            startScale: scale, startPosX: posX, startPosY: posY,
            // For drag-piece state once promoted:
            dragPiece: null, dragOrigPose: null, dragAnchorIdx: null,
            // For pan:
            panActive: !hit,
            // Long-press timer for piece tap-to-drag.
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
            // store pinch baseline
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
                // Shift+click: toggle piece in/out of multi-selection.
                if (multiSel.has(pid)) {
                    multiSel.delete(pid);
                    // If we removed the primary selection, pick another.
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
                    // Make this the primary selection.
                    selection = { piece_id: pid, ending_idx: desiredEnding };
                    action('select', { piece_id: pid, ending_idx: desiredEnding });
                }
                rec.deferCollapse = false;
            } else if (multiSel.size > 1 && multiSel.has(pid)) {
                // Clicking on a piece already in a group: keep the group for
                // now so a drag moves the whole group.  If the user just
                // clicks (no drag), we collapse to single-select on pointerup.
                selection = { piece_id: pid, ending_idx: desiredEnding };
                rec.deferCollapse = true;
            } else {
                // Normal click: single-select (replaces multi-sel).
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
            // Long-press → start drag (touch friendly). Mouse: drag begins on movement past slop.
            if (isCoarse) {
                rec.longPressTimer = setTimeout(() => {
                    if (rec.cancelled) return;
                    if (!rec.promoted) startDrag(rec);
                }, LONG_PRESS_MS);
            }
        } else {
            // Empty: clear selection on a click (no drag past slop).
            // We commit the selection clear on pointerup if no movement occurred.
        }
    }

    let multiDragOrigPoses = null; // Map<piece_id, {x,y,rot}> when group-dragging

    function startDrag(rec) {
        if (!rec.hit) return;
        rec.promoted = true;
        rec.dragPiece = rec.hit.piece;
        rec.dragOrigPose = { x: rec.dragPiece.x, y: rec.dragPiece.y, rot: rec.dragPiece.rot };
        rec.dragAnchorIdx = rec.hit.endingIdx; // may be null = auto

        // If the dragged piece is in a multi-selection, enter group drag.
        if (multiSel.size > 1 && multiSel.has(rec.dragPiece.id)) {
            multiDragOrigPoses = new Map();
            for (const p of pieces) {
                if (multiSel.has(p.id)) {
                    multiDragOrigPoses.set(p.id, { x: p.x, y: p.y, rot: p.rot });
                }
            }
            dragGhost = null; // no single ghost for group drag
        } else {
            multiDragOrigPoses = null;
            // initial ghost matches the current pose
            dragGhost = { type: rec.dragPiece.type, pose: { ...rec.dragOrigPose }, anchorIdx: rec.dragAnchorIdx, snapTarget: null };
        }
        draw();
    }

    function cancelDrag(rec) {
        if (rec.dragPiece) {
            // Restore group-drag pieces to their original positions.
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
                // Group drag: move all selected pieces in-place for live preview.
                for (const p of pieces) {
                    const orig = multiDragOrigPoses.get(p.id);
                    if (orig) { p.x = orig.x + deltaX; p.y = orig.y + deltaY; }
                }
                // Recompute piece paths for rendering.
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
                // Single-piece drag with snap preview.
                const newPose = {
                    x: rec.dragOrigPose.x + deltaX,
                    y: rec.dragOrigPose.y + deltaY,
                    rot: dragGhost.pose.rot, // preserve manual rotations during drag
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

        if (activePointers.size > 0) return; // still in multi-touch; ignore lift

        if (rec.dragPiece && multiDragOrigPoses) {
            // Group drag commit: send all moved pieces to the server.
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

        // Deferred collapse: user clicked on a group member without dragging.
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
            else {
                // Tap on empty canvas → clear selection.
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
    const pinch = { distance: 0, scale: 1, midX: 0, midY: 0, posX: 0, posY: 0 };
    function handlePinch() {
        const it = [...activePointers.values()];
        if (it.length < 2) return;
        const d = Math.hypot(it[0].curX - it[1].curX, it[0].curY - it[1].curY);
        if (pinch.distance <= 0) return;
        const newScale = Math.min(10, Math.max(0.1, (d / pinch.distance) * pinch.scale));
        const r = canvas.getBoundingClientRect();
        const cx = pinch.midX - r.left, cy = pinch.midY - r.top;
        const ratio = newScale / scale;
        posX = cx - (cx - posX) * ratio;
        posY = cy - (cy - posY) * ratio;
        scale = newScale;
        // Update pan from finger midpoint translation
        const newMidX = (it[0].curX + it[1].curX)/2;
        const newMidY = (it[0].curY + it[1].curY)/2;
        posX += (newMidX - pinch.midX);
        posY += (newMidY - pinch.midY);
        pinch.midX = newMidX; pinch.midY = newMidY;
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
        if (ns < 0.1 || ns > 10) return;
        const r = canvas.getBoundingClientRect();
        const mx = ev.clientX - r.left, my = ev.clientY - r.top;
        posX -= (mx - posX) * (delta - 1);
        posY -= (my - posY) * (delta - 1);
        scale = ns;
        saveView(); draw();
    }, { passive: false });

    // Double-click resets the view.
    canvas.addEventListener('dblclick', (ev) => { ev.preventDefault(); scale = 1; posX = 0; posY = 0; saveView(); draw(); });
    document.getElementById('resetView').addEventListener('click', () => { scale = 1; posX = 0; posY = 0; saveView(); draw(); });

    // ====================================================== palette interactions
    function paletteCenterSpawn(type) {
        // If a piece is selected and has a free ending, snap the new piece there.
        if (selection) {
            const sel = pieces.find(p => p.id === selection.piece_id);
            if (sel) {
                // Prefer the selected ending if it's free; otherwise pick the first free ending.
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
                    // Try every ending of the new piece as anchor; pick the
                    // first one that doesn't visually overlap with the source.
                    const nEndings = ENDING_COUNT[type];
                    let bestPose = null;
                    for (let a = 0; a < nEndings; a++) {
                        const pose = poseAlign(type, a, targetPair);
                        bestPose = bestPose || pose;
                        // Quick overlap test: check if the new polygon shares
                        // interior area with the selected piece.
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
        // Fallback: spawn at the current view center.
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
                    // Determine if drop is over the canvas.
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
    document.getElementById('saveBtn').addEventListener('click', () => action('save'));

    // ====================================================== title rename
    document.getElementById('titlePill').addEventListener('click', () => {
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
            // Select all pieces.
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
