// Piece geometry tables and snap helpers (pure math, no DOM).
// Mirrors duplo.services.geometry on the client side.
(function () {
    'use strict';

    const W0 = 10;
    const L0 = 40;
    const C0 = L0 * 7 / 2 / Math.sqrt(3);
    const ENDING_COUNT = { straight: 2, curve: 2, switch: 3, crossing: 4 };
    const PIECE_TYPES = ['straight', 'curve', 'switch', 'crossing'];
    const MM_PER_UNIT = 128 / L0;  // 3.2
    const MAX_WORLD = 10 * 1000 / MM_PER_UNIT;  // ~3125 units

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

    function poseAlign(type, anchorIdx, target) {
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

    window.TE = {
        W0, L0, C0, ENDING_COUNT, PIECE_TYPES, MM_PER_UNIT, MAX_WORLD,
        poseTransform, poseAlign, midpoint, localSnap,
    };
})();
