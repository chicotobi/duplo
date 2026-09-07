"""Automatic track designer — close off a layout using the pieces in the box.

The problem
-----------
Given the pieces already on the floor, the pieces a user owns
(``{straight, curve, switch, crossing}``) and the size of their room, produce a
layout that is

1. **closed** — every ending consumed, which is exactly what
   :meth:`~duplo.services.editor.LayoutEditor.is_closed` checks, and
2. **buildable** — no two pieces overlap, and it fits in the room, and
3. **interesting** — not the plain oval you get by accident.

Completion, not creation
------------------------
:func:`complete_track` is the entry point that matters. The pieces already
placed are **given**: they are never moved, rotated or removed, and the search
only ever *adds*. That is both what the user wants — their arrangement is the
half of the design they care about — and much the smaller problem, because the
endings left open pin down where the answer has to go.

Designing a whole layout from an empty floor is the degenerate case of the same
question, and it is a genuinely hard search; :func:`design_track` still does it,
but only when there is nothing on the floor to work from.

Both are bounded by a **hard wall clock**. When it runs out with nothing closed,
:func:`complete_track` does not give up empty-handed — it returns an arbitrary
non-overlapping continuation of the track instead, and says so
(``closed: False``), leaving the user to keep as much of it as they like.

The model
---------
A layout is grown from the endings left open by the pieces already down — or,
on an empty floor, from a single seed piece — by repeatedly taking one *open
ending* and either

* **attaching** a fresh piece from the inventory to it, or
* **docking** it onto another open ending that it already meets face-to-face.

The design is finished when no open ending is left over.

Pieces are attached with :func:`~duplo.services.geometry._pose_to_align` — the
very function interactive snapping uses — and docking is decided by
:func:`~duplo.services.geometry.endings_fit`, the same predicate
``layouts_connections`` applies at view time. A finished design therefore
cannot "look connected but not be connected": the editor derives the same
connections the designer intended.

What the piece topology forces
------------------------------
Endings per type are ``straight: 2, curve: 2, switch: 3, crossing: 4``. Since a
closed layout consumes every ending:

* a **crossing** must be traversed *twice* (once per route, ``0-2`` and
  ``1-3``), so it only ever closes as a figure-eight style self-intersection;
* a **switch** has an odd number of endings, so switches can only be used in
  **pairs** — the branch that leaves one switch has to rejoin at another. That
  is the "siding" / "bypass" layout, and it is the most interesting thing the
  inventory can express.

The search
----------
Depth-first, with the active ending chosen LIFO so the walk keeps following one
thread, and with these prunes:

* **forced docking** — if the active ending already meets another open ending,
  they *are* connected as far as the app is concerned, so that move is taken
  with no alternatives explored;
* **overlap** — against every placed piece (bounding-circle prefiltered);
* **room** — the running bounding box may not exceed the room;
* **reach** — the active ending must still be able to get back to some other
  open ending with the pieces left in the box;
* **turn budget** — and it must be able to turn far enough to arrive
  face-to-face, given that only curves and switches change heading.

Move ordering is greedy toward closure with a random jitter, and the first part
of each attempt deliberately wanders *away* from the target so the result is
not a minimal loop. Attempts are restarted under a wall-clock budget and the
best-scoring result is returned.

Pure geometry and search: no Flask, no DB.
"""

from __future__ import annotations

import math
import random
import time

from .geometry import (
    FORCE_CONNECTION_DISTANCE,
    JOINT_OVERLAP_MARGIN,
    PIECE_TYPES,
    _pose_to_align,
    can_force_connect,
    ending_heading,
    endings_fit,
    points,
    polygons_overlap,
    w0,
    world_endings_for_pose,
    world_polygon,
)

# World units are 3.2 mm (a straight is l0 = 40 units = 128 mm).
MM_PER_UNIT = 3.2
UNITS_PER_M = 1000.0 / MM_PER_UNIT

# Routes a train can take through a piece, as (entry ending, exit ending).
# A switch is entered at the toe (0) and leaves by either leg; the leg-to-leg
# route 1-2 is not traversable. A crossing has two independent straight routes.
ROUTES = {
    "straight": ((0, 1), (1, 0)),
    "curve": ((0, 1), (1, 0)),
    "switch": ((0, 1), (1, 0), (0, 2), (2, 0)),
    "crossing": ((0, 2), (2, 0), (1, 3), (3, 1)),
}

# Only these change heading (30 degrees per piece) — used for the turn budget.
_TURNERS = frozenset({"curve", "switch"})

# The pieces that make a layout interesting rather than merely valid.
_SPECIAL = frozenset({"switch", "crossing"})

# Move-ordering bonus for placing a special piece, in the same units as the
# distance-to-goal cost (a piece is about 40 units long).
_SPECIAL_BONUS = 120.0

# Turning steps in a full circle. A simple closed loop turns through exactly
# this much, so it must spend 12 turning pieces all the same way; every
# direction reversal costs two more on top.
_FULL_TURN = 12

# Piece counts tried per allowance in one round before moving to the next
# allowance. Keeps the round-robin turning over instead of one hard allowance
# monopolising the clock.
_SIZES_PER_ROUND = 6

# How much of the piece budget is spent deliberately heading away from home
# before the search turns back. Measured: too little and the design closes
# into a small loop early, too much and it strands itself. This range had both
# the lowest median search cost and much the shortest tail.
_EXPLORE_FRACTION = (0.40, 0.60)

# Near-miss joints allowed by default, for the editor's force connection to
# close. Two is enough to let a switch pair or a crossing come together while
# still leaving a track that is essentially snapped.
_DEFAULT_MAX_FORCED = 2


# Local bounding radius per type, for the overlap prefilter. Piece local
# origins sit at the outline centroid (see geometry.pivots).
_RADIUS = {t: max(math.hypot(px, py) for px, py in points[t]) for t in PIECE_TYPES}

# A synthetic ending sitting at the origin whose outward heading is +y, used to
# measure how far each piece carries the track forward.
_PROBE = ((-w0 / 2, 0.0), (w0 / 2, 0.0))

# Midpoint distance below which two endings may still turn out to dock. Kept
# under SNAP_TOLERANCE so the "pieces still needed" bound stays admissible.
_DOCK_SLACK = 3.0


def _measure_advance():
    """Distance from entry ending to exit ending, per piece type."""
    adv = {}
    for t in PIECE_TYPES:
        best = 0.0
        for e_in, e_out in ROUTES[t]:
            x, y, rot = _pose_to_align(t, e_in, _PROBE)
            eds = world_endings_for_pose(t, x, y, rot)
            mx = (eds[e_out][0][0] + eds[e_out][1][0]) * 0.5
            my = (eds[e_out][0][1] + eds[e_out][1][1]) * 0.5
            best = max(best, math.hypot(mx, my))
        adv[t] = best
    return adv


MAX_ADVANCE = _measure_advance()


class _Budget(Exception):
    """Raised to unwind the DFS when an attempt runs out of nodes or time."""


def _mid(pair):
    return ((pair[0][0] + pair[1][0]) * 0.5, (pair[0][1] + pair[1][1]) * 0.5)


def _poly_box(poly):
    """``(lo_x, hi_x, lo_y, hi_y)`` of a world-space outline."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return (min(xs), max(xs), min(ys), max(ys))


def _share_a_joint(eds_a, eds_b):
    """Could these two placements be meeting at a joint?

    True when any pair of their endings is close enough and square enough that
    the app would let them be connected — which is exactly when the two pieces
    are entitled to overlap a little.
    """
    for pair_a in eds_a:
        ma = _mid(pair_a)
        for pair_b in eds_b:
            mb = _mid(pair_b)
            if abs(ma[0] - mb[0]) > FORCE_CONNECTION_DISTANCE:
                continue
            if abs(ma[1] - mb[1]) > FORCE_CONNECTION_DISTANCE:
                continue
            if can_force_connect(pair_a, pair_b)["can_force"]:
                return True
    return False


def _signed_turn(from_head, to_head):
    """Heading change in 30-degree steps, normalised to [-6, 5]."""
    t = (to_head - from_head) % 12
    return t - 12 if t > 6 else t


class _Attempt:
    """One randomized growth attempt. Holds the mutable search state."""

    def __init__(self, caps, room_w, room_h, rng, min_pieces, max_total,
                 explore_pieces, node_budget, wiggle=None, max_forced=0,
                 require_specials=True):
        self.caps = dict(caps)
        self.room_w = room_w
        self.room_h = room_h
        self.rng = rng
        self.min_pieces = min_pieces
        # Hard cap on the piece count. Fixing it up front is what makes the
        # "how many pieces do I still need to get home" bound sharp enough to
        # prune near the root; without it the search dives to the bottom of
        # the box and thrashes there.
        self.max_total = max_total
        self.explore_pieces = explore_pieces
        self.node_budget = node_budget
        self.nodes = 0

        # placed[i] = dict(type, x, y, rot, poly, radius, turn)
        # Whether every special piece in the allowance *must* end up in the
        # design. True when designing from nothing — see the note in _dfs.
        # False when completing: the box is simply what is left over, and
        # insisting a spare switch be used would reject every honest answer.
        self.require_specials = require_specials
        # placed[:n_fixed] are the user's own pieces: immovable, and never
        # popped by the search.
        self.n_fixed = 0
        self.placed = []
        # open endings: dict(piece, ending, pair, mid, head)
        self.open = []
        self.seen_turn = False
        # Running bounding box of the design, with an undo stack.
        self.bbox = (math.inf, -math.inf, math.inf, -math.inf)
        self.prev_bbox = []
        # Joints left for the editor's "force connection" to close, as
        # (piece_a, ending_a, piece_b, ending_b).
        self.max_forced = max_forced
        self.forced = []
        # Placement interning and memoised pairwise overlap.
        self._pose_ids = {}
        self._overlap_cache = {}
        # Per-attempt style: wiggly attempts prefer to alternate turn
        # direction while exploring, which is where S-curves come from. A
        # simple closed loop already spends 12 curves turning one way, so a
        # reversal costs two spare turners on top of that — below that
        # threshold wiggling only wastes attempts.
        # A reversal costs two turning pieces on top of the 12 a simple loop
        # already spends going one way round, so below that it only wastes
        # attempts. The caller asks for it once it has a design in hand.
        spare = sum(caps[t] for t in _TURNERS) - _FULL_TURN
        want = rng.random() < 0.5 if wiggle is None else wiggle
        self.wiggle = spare >= 2 and want
        # With no switches and no crossings the design can only be a single
        # simple closed curve, which turns through exactly one full circle.
        # That makes the net-turn prune below exact; with a crossing or a
        # switch pair the turning number is no longer fixed, so it is off.
        self.simple_loop = caps["switch"] == 0 and caps["crossing"] == 0
        self.net_turn = 0
        # Whether to hold pieces back for the open endings this thread is not
        # aiming at. See _reserve_for_pending: worth it from nothing, harmful
        # when completing.
        self.reserve_pending = True
        # Whether to try switches and crossings ahead of plain track.
        self.prefer_specials = True
        # Set when the search proved there is no design for this configuration
        # (as opposed to merely running out of nodes).
        self.exhausted = False

    # ------------------------------------------------------------- geometry

    def _bbox_ok(self, box):
        """Would adding *box* push the whole design outside the room?

        The design's own bounding box is maintained incrementally — measuring
        it from every placed piece on every candidate move made this the
        hottest line in the search.
        """
        lo_x, hi_x, lo_y, hi_y = self.bbox
        if box[0] < lo_x:
            lo_x = box[0]
        if box[1] > hi_x:
            hi_x = box[1]
        if box[2] < lo_y:
            lo_y = box[2]
        if box[3] > hi_y:
            hi_y = box[3]
        return (hi_x - lo_x) <= self.room_w and (hi_y - lo_y) <= self.room_h

    def _pose_id(self, ptype, x, y, rot):
        """Small integer id for a placement, so overlap results can be cached."""
        key = (ptype, round(x, 2), round(y, 2), rot)
        pid = self._pose_ids.get(key)
        if pid is None:
            pid = len(self._pose_ids)
            self._pose_ids[key] = pid
        return pid

    def _overlaps(self, pid, x, y, radius, poly, eds):
        """Does this placement clash with anything already down?

        Backtracking re-examines the same pair of placements over and over, and
        the polygon test is by far the most expensive thing in the search, so
        results are memoised per pair. The cheap bounding-circle reject runs
        first and keeps most pairs out of the cache entirely.
        """
        cache = self._overlap_cache
        for pc in self.placed:
            dx = pc["x"] - x
            dy = pc["y"] - y
            reach = radius + pc["radius"]
            if dx * dx + dy * dy > reach * reach:
                continue
            other = pc["pid"]
            key = (pid, other) if pid < other else (other, pid)
            hit = cache.get(key)
            if hit is None:
                hit = polygons_overlap(poly, pc["poly"])
                if hit and _share_a_joint(eds, pc["endings"]):
                    # Two pieces at a joint are allowed to poke into each other
                    # as far as the connection tolerance lets them sit apart.
                    # Without this the designer cannot rebuild the user's own
                    # track: hand-snapped joints routinely land a unit or two
                    # off centre, and every one of them reads as a collision.
                    hit = polygons_overlap(poly, pc["poly"],
                                           margin=JOINT_OVERLAP_MARGIN)
                cache[key] = hit
            if hit:
                return True
        return False

    # -------------------------------------------------------------- budgets

    def _best_advance(self):
        """Furthest any single still-available piece can carry the track."""
        best = 0.0
        for t in PIECE_TYPES:
            if self.caps[t] > 0 and MAX_ADVANCE[t] > best:
                best = MAX_ADVANCE[t]
        return best

    def _closure_cost(self, mid, goal, turn_left, remaining):
        """Cost to reach *goal*, and whether *remaining* pieces can still do it.

        ``turn_left`` is how much more this thread must turn to arrive on the
        winding it committed to — not merely the smallest rotation that lines
        the endings up. The difference matters enormously: a figure-eight lobe
        has to come all the way round, +300 degrees, while the shortest
        equivalent is -60. Aiming at -60 sends the search after a loop that
        cannot exist, which is why crossings never closed.

        The bound is admissible: each remaining 30 degrees needs a curve or a
        switch, and the gap needs ``distance / longest-remaining-piece``
        pieces to cover it.

        Returns ``(feasible, distance, cost)``.
        """
        d = math.hypot(goal["mid"][0] - mid[0], goal["mid"][1] - mid[1])
        k = abs(turn_left)
        cost = d + 30.0 * k

        if k > sum(self.caps[t] for t in _TURNERS):
            return False, d, cost
        # A joint the editor can force closed counts as arriving, so the
        # bound has to allow for that slack or it would prune the very
        # near-misses we are trying to find.
        slack = (FORCE_CONNECTION_DISTANCE
                 if len(self.forced) < self.max_forced else _DOCK_SLACK)
        gap = max(0.0, d - slack)
        if gap <= 0:
            return k <= remaining, d, cost
        max_adv = self._best_advance()
        if not max_adv:
            return False, d, cost
        need = max(k, math.ceil(gap / max_adv))
        return need <= remaining, d, cost

    def _reserve_for_pending(self, active, goal):
        """Estimate of the pieces the *other* open endings will still need.

        Without this the active thread happily spends the entire budget and
        the endings left over — the spare legs of a switch pair, say — have
        nothing left to join them with. The main loop then closes thousands of
        times and the final connection never once succeeds, which is exactly
        the symptom a switch layout was showing.

        It is a heuristic, not a true lower bound: it pairs the pending endings
        off greedily rather than optimally, and it assumes each pair is bridged
        by its own chain of track, when one switch or crossing can serve
        several endings at once. That is a good trade when growing a design
        from nothing, where the budget is large and the risk is squandering it.
        It is the wrong trade when completing a track — see :meth:`adopt`.
        """
        if not self.reserve_pending:
            return 0
        others = [o for o in self.open if o is not active and o is not goal]
        if len(others) < 2:
            return 0
        max_adv = self._best_advance()
        if not max_adv:
            return 0
        total = 0
        taken = set()
        for i, a in enumerate(others):
            if i in taken:
                continue
            nearest = None
            for j in range(i + 1, len(others)):
                if j in taken:
                    continue
                b = others[j]
                d = math.hypot(a["mid"][0] - b["mid"][0],
                               a["mid"][1] - b["mid"][1])
                if nearest is None or d < nearest[0]:
                    nearest = (d, j)
            if nearest is None:
                break
            taken.add(i)
            taken.add(nearest[1])
            gap = max(0.0, nearest[0] - FORCE_CONNECTION_DISTANCE)
            if gap > 0:
                total += math.ceil(gap / max_adv)
        return total

    # ---------------------------------------------------------------- moves

    def _candidate_moves(self, active, goal, turn_left):
        """Legal attachments to *active* that can still reach *goal*.

        ``turn_left`` is the thread's outstanding turn on its committed
        winding; each placed piece spends part of it.
        """
        exploring = len(self.placed) < self.explore_pieces
        remaining = (self.max_total - len(self.placed) - 1
                     - self._reserve_for_pending(active, goal))
        last_turn = self.placed[-1]["turn"] if self.placed else 0
        turners_now = sum(self.caps[t] for t in _TURNERS)
        turners_after_turner = turners_now - 1
        moves = []
        for ptype in PIECE_TYPES:
            if self.caps[ptype] <= 0:
                continue
            for e_in, e_out in ROUTES[ptype]:
                x, y, rot = _pose_to_align(ptype, e_in, active["pair"])
                eds = world_endings_for_pose(ptype, x, y, rot)

                exit_pair = eds[e_out]
                exit_head = ending_heading(exit_pair)
                turn = _signed_turn(active["head"], exit_head)

                # Mirror symmetry break: the first turn of a design is a left.
                if not self.seen_turn and turn < 0:
                    continue

                # Turning-number prune. A simple closed curve turns through
                # exactly one full circle, so the net turn has to land on
                # +/-12 using the turning pieces still in the box. This is
                # what stops the search wandering into states that can never
                # close — with exactly 12 curves it forces every one of them
                # to turn the same way, which is the only thing that closes.
                if self.simple_loop:
                    net = self.net_turn + turn
                    left = turners_after_turner if turn else turners_now
                    if (abs(_FULL_TURN - net) > left
                            and abs(_FULL_TURN + net) > left):
                        continue

                poly = world_polygon(ptype, x, y, rot)
                box = _poly_box(poly)
                if not self._bbox_ok(box):
                    continue
                pid = self._pose_id(ptype, x, y, rot)
                if self._overlaps(pid, x, y, _RADIUS[ptype], poly, eds):
                    continue

                # Feasibility is judged with this piece already spent.
                self.caps[ptype] -= 1
                feasible, dist, cost = self._closure_cost(
                    _mid(exit_pair), goal, turn_left - turn, remaining,
                )
                specials_left = self.caps["switch"] + self.caps["crossing"]
                self.caps[ptype] += 1
                if not feasible:
                    continue
                if self.require_specials and specials_left > remaining:
                    # Every special piece still has to be placed, and there is
                    # no longer room for them.
                    continue

                if exploring:
                    # Deliberately head away, so we do not close immediately.
                    cost = -dist
                    if self.wiggle and turn and last_turn and (turn > 0) != (last_turn > 0):
                        # Reward changing direction: an S-curve is the
                        # difference between a layout and an oval. Only
                        # affordable when the box holds more than the 12
                        # same-way curves a simple loop already needs.
                        cost -= 60.0
                if self.prefer_specials and ptype in _SPECIAL:
                    # Nudge the special pieces in, but only as room runs out.
                    # A flat bonus buries them all in the first few pieces,
                    # which is fatal for a switch pair: both switches end up
                    # side by side and the two legs left over are then in no
                    # position to be joined back together. Scaling by how
                    # tight the remaining budget is spreads them around the
                    # layout instead.
                    urgency = specials_left / max(1, remaining)
                    cost -= _SPECIAL_BONUS * urgency

                cost += self.rng.uniform(0.0, 45.0)

                moves.append((cost, ptype, e_in, e_out, x, y, rot, eds, poly,
                              turn, box, pid, turn_left - turn))

        moves.sort(key=lambda m: m[0])
        return moves

    def _push_piece(self, ptype, e_in, e_out, x, y, rot, eds, poly, turn, box,
                    pid):
        """Place a piece; its non-entry endings become open (exit last)."""
        idx = len(self.placed)
        self.placed.append({
            "type": ptype, "x": x, "y": y, "rot": rot, "poly": poly,
            "endings": eds,
            "radius": _RADIUS[ptype], "turn": turn, "pid": pid,
            "lo_x": box[0], "hi_x": box[1], "lo_y": box[2], "hi_y": box[3],
        })
        self.prev_bbox.append(self.bbox)
        self.bbox = (min(self.bbox[0], box[0]), max(self.bbox[1], box[1]),
                     min(self.bbox[2], box[2]), max(self.bbox[3], box[3]))
        self.caps[ptype] -= 1
        prev_seen = self.seen_turn
        if turn:
            self.seen_turn = True
        self.net_turn += turn

        # The active ending is consumed by the attachment.
        consumed = self.open.pop()
        opened = []
        for eidx in range(len(eds)):
            if eidx == e_in or eidx == e_out:
                continue
            opened.append(eidx)
        opened.append(e_out)  # LIFO: keep walking through the piece
        for eidx in opened:
            pair = eds[eidx]
            self.open.append({
                "piece": idx, "ending": eidx, "pair": pair,
                "mid": _mid(pair), "head": ending_heading(pair),
            })
        return consumed, len(opened), prev_seen

    def _pop_piece(self, ptype, consumed, n_opened, prev_seen):
        for _ in range(n_opened):
            self.open.pop()
        self.open.append(consumed)
        self.caps[ptype] += 1
        self.seen_turn = prev_seen
        self.bbox = self.prev_bbox.pop()
        self.net_turn -= self.placed.pop()["turn"]

    def _extend_lone_ending(self, deadline, active):
        """Grow from the only remaining open ending.

        There is nothing to aim at, so the usual goal-directed bound does not
        apply. Specials go first — they are the only pieces that can open the
        layout back up — and plain pieces are allowed too so the special can be
        carried somewhere it actually fits.
        """
        remaining = self.max_total - len(self.placed)
        specials_left = self.caps["switch"] + self.caps["crossing"]
        if self.require_specials and specials_left > remaining:
            return False

        moves = []
        for ptype in PIECE_TYPES:
            if self.caps[ptype] <= 0:
                continue
            for e_in, e_out in ROUTES[ptype]:
                x, y, rot = _pose_to_align(ptype, e_in, active["pair"])
                eds = world_endings_for_pose(ptype, x, y, rot)
                poly = world_polygon(ptype, x, y, rot)
                box = _poly_box(poly)
                if not self._bbox_ok(box):
                    continue
                pid = self._pose_id(ptype, x, y, rot)
                if self._overlaps(pid, x, y, _RADIUS[ptype], poly, eds):
                    continue
                turn = _signed_turn(active["head"],
                                    ending_heading(eds[e_out]))
                if not self.seen_turn and turn < 0:
                    continue
                cost = self.rng.uniform(0.0, 45.0)
                if ptype not in _SPECIAL:
                    cost += _SPECIAL_BONUS
                moves.append((cost, ptype, e_in, e_out, x, y, rot, eds, poly,
                              turn, box, pid))

        moves.sort(key=lambda m: m[0])
        for mv in moves:
            _, ptype, e_in, e_out, x, y, rot, eds, poly, turn, box, pid = mv
            state = self._push_piece(ptype, e_in, e_out, x, y, rot, eds, poly,
                                     turn, box, pid)
            if self._dfs(deadline, None):
                return True
            self._pop_piece(ptype, *state)
        return False

    # ------------------------------------------------------------------ dfs

    def _dfs(self, deadline, goal, turn_left=0):
        """Extend the newest open ending until nothing is left open.

        *goal* is the open ending the current thread has committed to reaching
        and *turn_left* how far it still has to turn to get there on the
        winding it chose. Both only steer the heuristic and the bound — an
        ending that happens to meet a *different* open ending is still docked,
        because the app would derive that connection regardless of what the
        search intended.
        """
        self.nodes += 1
        if self.nodes > self.node_budget:
            raise _Budget
        if self.nodes % 64 == 0 and time.monotonic() > deadline:
            raise _Budget

        if not self.open:
            # When designing from nothing the allowance is a requirement, not a
            # permission: a variant that offers two switches has to deliver a
            # design that uses both. Otherwise the search always returns the
            # plain loop — it is by far the easiest thing to close — and the
            # special pieces never appear. Completing someone's track is the
            # other way round: the box is simply whatever they have not used
            # yet, and demanding the spare switch be worked in would reject
            # every reasonable way of closing the gap.
            if self.require_specials and (self.caps["switch"] or self.caps["crossing"]):
                return False
            return len(self.placed) >= self.min_pieces

        active = self.open[-1]

        # Forced docking: coincident endings are connected whether we like it
        # or not, so there is no branch to explore here.
        for j in range(len(self.open) - 1):
            other = self.open[j]
            if other["piece"] == active["piece"]:
                continue
            if endings_fit(active["pair"], other["pair"]):
                self.open.pop()
                self.open.pop(j)
                # This thread is finished; the next one picks a fresh goal.
                if self._dfs(deadline, None):
                    return True
                self.open.insert(j, other)
                self.open.append(active)
                return False

        # Starting a thread (or the previous goal was consumed by a dock):
        # choose what this thread is aiming at. This is the only place the
        # search branches over goals, so the bound below stays sharp.
        if goal is None or goal is active or not any(o is goal for o in self.open):
            if len(self.open) == 1:
                # One ending left and nothing to aim it at. A two-ended piece
                # would only move the problem along, so the only way out is a
                # piece that opens more endings — and those can then close on
                # each other. This is how a "dumbbell" is built: two switches
                # joined toe to toe, each closing its own two legs into a
                # balloon loop. Without this the search dead-ends the moment a
                # balloon closes, which is why switch layouts never appeared.
                if not (self.caps["switch"] or self.caps["crossing"]):
                    return False
                return self._extend_lone_ending(deadline, active)

            turners = sum(self.caps[t] for t in _TURNERS)
            for cand in reversed(self.open[:-1]):
                # Lining the endings up leaves the winding open: the thread can
                # take the short way round, or go a full turn further. A plain
                # loop back to the seed needs the +360 option; a figure-eight
                # lobe needs it too. Committing to one up front is what makes
                # the turn bound sharp enough to be worth having.
                base = _signed_turn(active["head"], (cand["head"] + 6) % 12)
                # The winding is a real choice and the right one is not
                # predictable: a plain loop closing on its seed needs a full
                # 360, while a balloon loop off a switch — whose two legs
                # already diverge by 60 — needs only 240. Whichever is tried
                # first consumes the node budget, so the order is randomised
                # and the restarts sample all of them, rather than a fixed
                # guess quietly ruling one shape out.
                cands = [w for w in {base, base + 12, base - 12}
                         if abs(w) <= turners]
                self.rng.shuffle(cands)
                for want in cands:
                    if self._dfs(deadline, cand, want):
                        return True
            return False

        # Near-miss joint. Real Duplo track flexes, and the editor already has
        # a "force connection" for endings that face each other across a small
        # gap. Being allowed to leave one is what makes the interesting
        # layouts reachable at all: landing a switch branch or the second pass
        # of a crossing *exactly* on its target is a needle in a haystack,
        # whereas landing within a few centimetres of it is routine. Unlike an
        # exact dock this is a real choice, so it is tried and then backtracked
        # over rather than taken outright.
        if len(self.forced) < self.max_forced:
            for j in range(len(self.open) - 1):
                other = self.open[j]
                if other["piece"] == active["piece"]:
                    continue
                if not can_force_connect(active["pair"], other["pair"])["can_force"]:
                    continue
                self.open.pop()
                self.open.pop(j)
                self.forced.append((active["piece"], active["ending"],
                                    other["piece"], other["ending"]))
                if self._dfs(deadline, None):
                    return True
                self.forced.pop()
                self.open.insert(j, other)
                self.open.append(active)

        # Docking costs no pieces, so the cap is only checked once no dock is
        # available.
        if len(self.placed) >= self.max_total:
            return False

        for mv in self._candidate_moves(active, goal, turn_left):
            _, ptype, e_in, e_out, x, y, rot, eds, poly, turn, box, pid, left = mv
            state = self._push_piece(ptype, e_in, e_out, x, y, rot, eds, poly,
                                     turn, box, pid)
            if self._dfs(deadline, goal, left):
                return True
            self._pop_piece(ptype, *state)
        return False

    # ----------------------------------------------------------- completion

    def adopt(self, existing, consumed=()):
        """Take the user's pieces as given, and open whatever is not joined up.

        *existing* is ``[{"type", "x", "y", "rot"}, ...]`` in the caller's order
        — the indices reported back in ``forced`` refer to it. *consumed* lists
        ``(index, ending_idx)`` pairs already spoken for by a force connection
        the user made earlier, so the search does not try to fill them again.

        Which of the remaining endings count as *already joined* is decided by
        the same first-match-wins scan
        :func:`~duplo.repositories.layouts.layouts_connections` runs at view
        time. Deriving it any other way would let the designer close a track
        the editor still considers open.
        """
        world = []
        for pc in existing:
            ptype = pc["type"]
            x, y, rot = float(pc["x"]), float(pc["y"]), int(pc["rot"]) % 12
            poly = world_polygon(ptype, x, y, rot)
            box = _poly_box(poly)
            self.placed.append({
                "type": ptype, "x": x, "y": y, "rot": rot, "poly": poly,
                "endings": world_endings_for_pose(ptype, x, y, rot),
                "radius": _RADIUS[ptype], "turn": 0,
                "pid": self._pose_id(ptype, x, y, rot),
                "lo_x": box[0], "hi_x": box[1], "lo_y": box[2], "hi_y": box[3],
                "fixed": True,
            })
            self.bbox = (min(self.bbox[0], box[0]), max(self.bbox[1], box[1]),
                         min(self.bbox[2], box[2]), max(self.bbox[3], box[3]))
            world.append(world_endings_for_pose(ptype, x, y, rot))
        self.n_fixed = len(self.placed)

        flat = [(i, e, world[i][e])
                for i in range(len(world)) for e in range(len(world[i]))]
        taken = {(int(i), int(e)) for (i, e) in consumed}
        for a in range(len(flat)):
            i, ei, pair_a = flat[a]
            if (i, ei) in taken:
                continue
            for b in range(a + 1, len(flat)):
                j, ej, pair_b = flat[b]
                if j == i or (j, ej) in taken:
                    continue
                if endings_fit(pair_a, pair_b):
                    taken.add((i, ei))
                    taken.add((j, ej))
                    break

        opened = [(i, ei, pair) for (i, ei, pair) in flat if (i, ei) not in taken]
        # The walk follows self.open LIFO, so which ending it starts from is
        # decided here. Shuffling it is what makes restarts try genuinely
        # different ways into the same gap.
        self.rng.shuffle(opened)
        for (i, ei, pair) in opened:
            self.open.append({
                "piece": i, "ending": ei, "pair": pair,
                "mid": _mid(pair), "head": ending_heading(pair),
            })

        # Prunes that only make sense for a design grown from nothing:
        # the first-turn mirror break (the user's pieces already fixed the
        # handedness) and the turning-number bound (it counts from a seed).
        self.seen_turn = True
        self.simple_loop = False
        self.wiggle = False
        # And the pending-endings reserve, which is the one that really bites.
        # Knock a switch or a crossing out of a track and four endings are left
        # open, not two; the reserve then demands a chain of track between the
        # two the thread is not aiming at, when in truth the special piece
        # about to go back in will serve them all. With only a few pieces in
        # the box that leaves a negative budget and the search dies at the
        # root, having looked at two nodes. Every gap containing a special
        # piece failed this way.
        self.reserve_pending = False
        # And the bias towards switches and crossings. From nothing they are
        # the whole point of the design; in a gap they are merely what happens
        # to be left in the box, and trying them first makes a user with a
        # well-stocked library much slower to serve than one with three spare
        # curves. If they want a switch there, they can put one there.
        self.prefer_specials = False
        return len(self.open)

    def run_completion(self, deadline):
        """Close the adopted layout. Returns ``(placed, forced)`` or ``None``."""
        try:
            if self._dfs(deadline, None):
                return list(self.placed), list(self.forced)
            # Searched out without being cut short: no completion of exactly
            # this size exists.
            self.exhausted = True
        except _Budget:
            pass
        return None

    def _dock_open(self, active):
        """Consume *active* against another open ending if it already meets one.

        Exact fits first, then — while the allowance lasts — a near miss the
        editor's force connection would close. Returns ``True`` if it docked.
        """
        for j in range(len(self.open) - 1):
            other = self.open[j]
            if other["piece"] == active["piece"]:
                continue
            if endings_fit(active["pair"], other["pair"]):
                self.open.pop()
                self.open.pop(j)
                return True
        if len(self.forced) < self.max_forced:
            for j in range(len(self.open) - 1):
                other = self.open[j]
                if other["piece"] == active["piece"]:
                    continue
                if can_force_connect(active["pair"], other["pair"])["can_force"]:
                    self.open.pop()
                    self.open.pop(j)
                    self.forced.append((active["piece"], active["ending"],
                                        other["piece"], other["ending"]))
                    return True
        return False

    def greedy_continuation(self, deadline, limit):
        """Lay track onward from the open endings without ever backtracking.

        This is the answer when the clock runs out: not a closed design, but a
        real, non-overlapping, room-fitting stretch of track carrying on from
        where the user left off, which they can then keep or trim as they like.
        Each step takes whichever piece ends up nearest another open ending, so
        the continuation heads home rather than wandering off — and if it
        arrives, the track closes and everyone is happy.

        No search, no backtracking: one pass, worst case *limit* pieces.
        """
        added = 0
        stuck = 0
        while added < limit and self.open and stuck <= len(self.open):
            if time.monotonic() > deadline:
                break
            active = self.open[-1]
            if self._dock_open(active):
                stuck = 0
                continue

            others = [o for o in self.open[:-1] if o["piece"] != active["piece"]]
            best = None
            for ptype in PIECE_TYPES:
                if self.caps[ptype] <= 0:
                    continue
                for e_in, e_out in ROUTES[ptype]:
                    x, y, rot = _pose_to_align(ptype, e_in, active["pair"])
                    poly = world_polygon(ptype, x, y, rot)
                    box = _poly_box(poly)
                    if not self._bbox_ok(box):
                        continue
                    eds = world_endings_for_pose(ptype, x, y, rot)
                    pid = self._pose_id(ptype, x, y, rot)
                    if self._overlaps(pid, x, y, _RADIUS[ptype], poly, eds):
                        continue
                    exit_mid = _mid(eds[e_out])
                    cost = min(
                        (math.hypot(exit_mid[0] - o["mid"][0],
                                    exit_mid[1] - o["mid"][1]) for o in others),
                        default=0.0,
                    ) + self.rng.uniform(0.0, 10.0)
                    if best is None or cost < best[0]:
                        turn = _signed_turn(active["head"],
                                            ending_heading(eds[e_out]))
                        best = (cost, ptype, e_in, e_out, x, y, rot, eds, poly,
                                turn, box, pid)
            if best is None:
                # Nothing fits on this ending. Park it and try another thread.
                self.open.insert(0, self.open.pop())
                stuck += 1
                continue

            self._push_piece(*best[1:])
            added += 1
            stuck = 0

        # A final sweep, because docking above only ever looks at the ending
        # the walk happens to be standing on. Running out of pieces with two
        # endings already face to face is common, and reporting that track as
        # open when the editor will draw it closed would be plainly wrong.
        for i in range(len(self.open) - 1, -1, -1):
            if i >= len(self.open):
                continue
            self.open.append(self.open.pop(i))
            if not self._dock_open(self.open[-1]):
                self.open.insert(i, self.open.pop())
        return added

    # ---------------------------------------------------------------- entry

    def run(self, seed_type, deadline):
        """Grow from *seed_type* at the origin. Returns placed pieces or None."""
        x, y, rot = 0.0, 0.0, 0
        poly = world_polygon(seed_type, x, y, rot)
        box = _poly_box(poly)
        # The walk leaves by the last ending pushed below, so the finished loop
        # traverses the seed from its first ending to its last. For a curve
        # that is a left turn, and it has to be counted or the net-turn prune
        # is off by one and rejects every continuation.
        seed_turn = 1 if seed_type in ("curve", "switch") else 0
        self.placed.append({
            "type": seed_type, "x": x, "y": y, "rot": rot, "poly": poly,
            "endings": world_endings_for_pose(seed_type, x, y, rot),
            "radius": _RADIUS[seed_type], "turn": seed_turn,
            "pid": self._pose_id(seed_type, x, y, rot),
            "lo_x": box[0], "hi_x": box[1], "lo_y": box[2], "hi_y": box[3],
        })
        self.bbox = box
        self.net_turn = seed_turn
        self.seen_turn = bool(seed_turn)
        self.caps[seed_type] -= 1
        for eidx, pair in enumerate(world_endings_for_pose(seed_type, x, y, rot)):
            self.open.append({
                "piece": 0, "ending": eidx, "pair": pair,
                "mid": _mid(pair), "head": ending_heading(pair),
            })
        try:
            if self._dfs(deadline, None):
                return list(self.placed), list(self.forced)
            # Fell out of the search without being cut short: there is
            # provably no design for this piece count and allowance.
            self.exhausted = True
        except _Budget:
            pass
        return None


# --------------------------------------------------------------------- score

def _count_reversals(turns):
    """Direction changes in the turn sequence — an oval scores 0."""
    reversals = 0
    last = 0
    for t in turns:
        if t == 0:
            continue
        if last and (t > 0) != (last > 0):
            reversals += 1
        last = t
    return reversals


# Score weights. Switches and crossings dominate deliberately: a branch that
# rejoins, or a track that crosses over itself, is what makes a layout worth
# building. Everything else is a tie-breaker between designs that use the same
# special pieces — a design that uses both switches beats a bigger, tidier oval
# every time.
W_SWITCH = 0.34
W_CROSSING = 0.30
W_COVERAGE = 0.16
W_REVERSALS = 0.10
W_FILL = 0.05
W_ASPECT = 0.05

# Reversals worth counting before the term saturates.
_REVERSAL_TARGET = 6


def score_layout(placed, inventory, room_w, room_h):
    """Rate a finished design. Higher is more interesting.

    The components are deliberately simple and independent so the weights can
    be argued about:

    ``switch``     a branch that leaves the loop and rejoins it — the single
                   most interesting thing a box of Duplo track can express
    ``crossing``   a track that crosses over itself, a figure-eight
    ``coverage``   how much of the box actually ends up on the floor
    ``reversals``  direction changes — a loop that wanders rather than an oval
    ``fill``       how much of the room it uses
    ``aspect``     penalises long thin sausages

    Special pieces are scored against how many the user *owns*, so using both
    of your two switches scores full marks rather than being diluted by a
    notional maximum.
    """
    used = {t: 0 for t in PIECE_TYPES}
    for pc in placed:
        used[pc["type"]] += 1
    n_used = len(placed)
    n_have = sum(inventory[t] for t in PIECE_TYPES) or 1

    lo_x = min(pc["lo_x"] for pc in placed)
    hi_x = max(pc["hi_x"] for pc in placed)
    lo_y = min(pc["lo_y"] for pc in placed)
    hi_y = max(pc["hi_y"] for pc in placed)
    bw, bh = hi_x - lo_x, hi_y - lo_y

    reversals = _count_reversals([pc["turn"] for pc in placed])

    coverage = n_used / n_have
    rev_score = min(reversals, _REVERSAL_TARGET) / _REVERSAL_TARGET
    # Switches only close in pairs, so the achievable number is even.
    switch_have = (inventory["switch"] // 2) * 2
    switch_score = used["switch"] / switch_have if switch_have else 0.0
    cross_score = (used["crossing"] / inventory["crossing"]
                   if inventory["crossing"] else 0.0)
    fill = min(1.0, (bw * bh) / (room_w * room_h) / 0.5)
    aspect = min(bw, bh) / max(bw, bh) if max(bw, bh) > 0 else 0.0

    total = (W_SWITCH * min(1.0, switch_score)
             + W_CROSSING * min(1.0, cross_score)
             + W_COVERAGE * coverage
             + W_REVERSALS * rev_score
             + W_FILL * fill
             + W_ASPECT * aspect)

    return total, {
        "pieces": n_used,
        "used": used,
        "reversals": reversals,
        "coverage": round(coverage, 3),
        "fill": round(fill, 3),
        "aspect": round(aspect, 3),
        "width_m": round(bw / UNITS_PER_M, 2),
        "height_m": round(bh / UNITS_PER_M, 2),
        "score": round(total, 3),
    }


# ---------------------------------------------------------------- completion

# Pieces offered as an arbitrary continuation when the clock beats the search.
# Enough to be worth having and to stand a fair chance of wandering home,
# few enough that trimming it back is not a chore.
_FALLBACK_PIECES = 12

# The continuation is a single pass with no backtracking, so it is quick — but
# it must not be cut off half-built by a budget that has already expired.
_FALLBACK_GRACE = 1.0

# Largest gap the completer will try to fill exactly. Beyond this the search
# is hopeless anyway and the continuation is the better answer.
_MAX_GAP = 24

# Gap sizes covered by the first sweep, before the horizon starts doubling.
# Most real gaps are a handful of pieces, and reaching them on the first pass
# is what keeps the answer instant.
_START_HORIZON = 6

# Slack allowed beyond a layout that has already outgrown its room, in world
# units. Two piece lengths: enough for a patch to bulge past the edge, not
# enough for the design to sprawl.
_ROOM_HEADROOM = 2 * max(MAX_ADVANCE.values())

# How many piece allowances the completer will work through. The ladder is
# ordered cheapest-first, so the tail is both the least likely to be needed
# and the most expensive to search.
_MAX_ALLOWANCES = 6


def _completion_allowances(caps, n_open):
    """Piece allowances to try when filling a gap, cheapest first.

    Two things shape the ladder.

    **Parity.** Every ending in a closed layout is paired off, so the endings
    left open plus the endings of whatever is added must come to an even
    number. Straights, curves and crossings all have an even number of
    endings; only a switch has three. So the number of switches added has to
    match the parity of the open endings — and when a switch has been knocked
    out of a track, leaving three endings open, *no amount of plain track can
    ever close it*. Starting the ladder at one switch rather than none is the
    difference between answering those gaps in a few hundred nodes and not
    answering them at all.

    **Cost.** A switch or a crossing dropped into a gap opens more endings
    than it closes, so the search fans out instead of converging. Offering the
    fewest specials that parity permits, and only widening if that fails,
    keeps the common case instant.
    """
    parity = n_open % 2
    ladder = sorted(
        (sw + cr, sw, cr)
        for sw in range(parity, caps["switch"] + 1, 2)
        for cr in range(caps["crossing"] + 1)
    )
    return [dict(caps, switch=sw, crossing=cr)
            for _, sw, cr in ladder[:_MAX_ALLOWANCES]]


def _layout_extent(pieces):
    """``(width, height)`` of a set of placed pieces, in world units."""
    lo_x = lo_y = math.inf
    hi_x = hi_y = -math.inf
    for pc in pieces:
        for (px, py) in world_polygon(pc["type"], pc["x"], pc["y"], pc["rot"]):
            lo_x = min(lo_x, px)
            hi_x = max(hi_x, px)
            lo_y = min(lo_y, py)
            hi_y = max(hi_y, py)
    return hi_x - lo_x, hi_y - lo_y


def complete_track(existing, inventory, room_w=6.0, room_h=4.0, seed=None,
                   time_budget=5.0, max_new=None, max_forced=_DEFAULT_MAX_FORCED,
                   consumed=(), node_budget=24000,
                   fallback_pieces=_FALLBACK_PIECES):
    """Close off the track the user has already built.

    The pieces in *existing* are **given**: never moved, never rotated, never
    removed. Only additions are proposed, and only out of what is left in the
    box after *existing* has been paid for.

    Parameters
    ----------
    existing : list of dict
        ``{"type", "x", "y", "rot"}`` — the pieces already on the floor, in the
        caller's own order. Indices in the returned ``forced`` list refer to
        ``existing + pieces``, in that order.
    inventory : dict
        ``{"straight": n, ...}`` — everything the user *owns*, not what is
        left. What *existing* already uses is deducted here.
    room_w, room_h : float
        Room size in metres. Never smaller than what is already on the floor:
        a layout that has outgrown the room is the user's business, and
        refusing to extend it would be no help at all.
    seed : int or None
        Seed for reproducible completions.
    time_budget : float
        **Hard** wall-clock limit in seconds, honoured whatever the outcome.
        When it expires with nothing closed, an arbitrary continuation is
        returned instead of nothing — see ``closed`` below.
    max_new : int or None
        Cap on pieces added. Defaults to what is in the box, capped at
        :data:`_MAX_GAP`.
    max_forced : int
        Joints that may be left as near-misses for the editor's force
        connection to close. Real track flexes a few centimetres, and allowing
        this is what makes tight gaps solvable at all.
    consumed : iterable
        ``(existing_index, ending_idx)`` pairs already joined by a force
        connection the user made, so they are not treated as open.
    fallback_pieces : int
        How long an arbitrary continuation to offer when the search times out.

    Returns
    -------
    dict or None
        ``None`` only if *existing* is empty — there is nothing to complete,
        so the caller should design from scratch instead. Otherwise::

            {"pieces": [{"type", "x", "y", "rot"}, ...],   # additions only
             "forced": [{"piece1", "ending1_idx", "piece2", "ending2_idx"}],
             "closed": bool,
             "stats":  {...}}

        ``closed`` is the whole answer: ``True`` means every ending is now
        consumed; ``False`` means the clock ran out and ``pieces`` is a
        continuation to keep or trim, not a solution. Piece coordinates are in
        the same frame as *existing* — nothing is re-centred, because that
        would move the user's track.
    """
    existing = [{"type": p["type"], "x": float(p["x"]), "y": float(p["y"]),
                 "rot": int(p["rot"]) % 12} for p in existing]
    if not existing:
        return None

    inventory = {t: int(inventory.get(t, 0)) for t in PIECE_TYPES}
    used = {t: 0 for t in PIECE_TYPES}
    for pc in existing:
        used[pc["type"]] += 1
    # What is actually left in the box. Clamped at zero: a user may well have
    # built something with pieces they no longer claim to own, and that is no
    # reason to refuse to help them finish it.
    caps = {t: max(0, inventory[t] - used[t]) for t in PIECE_TYPES}
    in_box = sum(caps.values())

    # The room is a real constraint, but a track that has already outgrown it
    # is the user's business, and refusing to help them close it would be no
    # help at all. So the limit is never tighter than what is already on the
    # floor — plus enough slack for the patch itself, since a gap at the very
    # edge has to bulge a little to be filled.
    have_w, have_h = _layout_extent(existing)
    room_w_u = max(room_w * UNITS_PER_M, have_w + _ROOM_HEADROOM)
    room_h_u = max(room_h * UNITS_PER_M, have_h + _ROOM_HEADROOM)

    cap = min(in_box, _MAX_GAP if max_new is None else max_new)
    rng = random.Random(seed)
    started = time.monotonic()
    deadline = started + time_budget

    def _make(allowance, n_new, budget):
        att = _Attempt(
            caps=allowance, room_w=room_w_u, room_h=room_h_u, rng=rng,
            # An exact size, as in design_track: it is what makes the
            # "pieces still needed to get home" bound sharp enough to prune.
            min_pieces=len(existing) + n_new,
            max_total=len(existing) + n_new,
            explore_pieces=0,   # fill the gap, do not go sightseeing
            node_budget=budget,
            wiggle=False,
            max_forced=max_forced,
            require_specials=False,
        )
        att.adopt(existing, consumed)
        return att

    def _report(placed, forced, closed, att):
        added = placed[att.n_fixed:]
        stats = {
            "added": len(added),
            "closed": closed,
            "forced_joints": len(forced),
            "total_pieces": len(placed),
            "added_by_type": {
                t: sum(1 for pc in added if pc["type"] == t) for t in PIECE_TYPES
            },
            "seconds": round(time.monotonic() - started, 2),
        }
        w, h = _layout_extent(placed)
        stats["width_m"] = round(w / UNITS_PER_M, 2)
        stats["height_m"] = round(h / UNITS_PER_M, 2)
        return {
            "pieces": [{"type": pc["type"], "x": pc["x"], "y": pc["y"],
                        "rot": pc["rot"]} for pc in added],
            "forced": [
                {"piece1": a, "ending1_idx": ea, "piece2": b, "ending2_idx": eb}
                for (a, ea, b, eb) in forced
            ],
            "closed": closed,
            "stats": stats,
        }

    # Already closed, or closable with nothing added: answer at once rather
    # than spending the budget proving it.
    probe = _make(caps, 0, 1)
    if not probe.open:
        return _report(probe.placed, [], True, probe)
    allowances = _completion_allowances(caps, len(probe.open))

    # Sweep the gap size upwards, smallest first — the tidiest completion is
    # the one that adds fewest pieces, and small sizes are also cheap to rule
    # out. Iterative broadening on top: a whole sweep at a small node budget
    # and a short horizon, then double both.
    #
    # Broadening the *horizon* as well as the budget is what keeps a
    # well-stocked library fast. The gap is the same three pieces whether the
    # box holds three spare curves or eighty, but the size sweep is not: a full
    # 0..24 pass costs twenty times what 0..4 does, and it is all spent on
    # sizes far larger than the hole being filled. Measured on the real
    # layouts, a three-piece gap went from timing out at twenty seconds to
    # closing in hundredths of a second.
    proven_impossible = set()
    budget = max(256, node_budget // 16)
    horizon = min(cap, _START_HORIZON)
    while time.monotonic() < deadline:
        swept = False
        for level, allowance in enumerate(allowances):
            for n_new in range(horizon + 1):
                if time.monotonic() >= deadline:
                    break
                if (level, n_new) in proven_impossible:
                    continue
                swept = True
                att = _make(allowance, n_new, budget)
                result = att.run_completion(deadline)
                if result is not None:
                    placed, forced = result
                    return _report(placed, forced, True, att)
                if att.exhausted:
                    proven_impossible.add((level, n_new))
        if not swept and horizon >= cap:
            break   # every size searched out: no completion exists at all
        budget *= 2
        horizon = min(cap, horizon * 2)

    # Out of time (or out of hope). Hand back a continuation rather than
    # nothing: the user asked for help finishing, and half a suggestion they
    # can trim beats an error message.
    att = _make(caps, cap, node_budget)
    att.greedy_continuation(deadline + _FALLBACK_GRACE,
                            min(cap, fallback_pieces))
    closed = not att.open
    return _report(att.placed, att.forced, closed, att)


# --------------------------------------------------------------------- entry

def _caps_variants(inventory):
    """Structurally different piece allowances, richest first.

    Switches are only ever offered in even numbers — a switch has three
    endings, so an odd allowance can never close. Fixing the special pieces up
    front rather than leaving them to the search prunes a lot of hopeless
    work, and it lets the caller see a figure-eight and a plain loop as
    genuinely different attempts rather than two points in one search space.
    """
    variants = []
    for sw in range(0, inventory["switch"] + 1, 2):  # even only: see docstring
        for cr in range(inventory["crossing"] + 1):
            variants.append({
                "straight": inventory["straight"],
                "curve": inventory["curve"],
                "switch": sw,
                "crossing": cr,
            })
    # Richest first: switches and crossings are the whole point, so they get
    # the first and best shot at the clock. The plain allowance stays in the
    # list as a guaranteed fallback and is reached quickly, because the size
    # climb starts small and a hopeless allowance is dropped as soon as the
    # search proves it cannot close.
    variants.sort(key=lambda c: -(c["switch"] + c["crossing"]))
    return variants


def _seed_type(caps):
    """Which piece to lay down first.

    A special piece goes first, at the origin, where it still has every
    direction available. Reached part-way through a walk instead, a crossing
    has to be entered on a pose the rest of the layout has already fixed, and
    then its second pass has almost no freedom left — searching that way finds
    nothing at all, even given hundreds of thousands of nodes. Seeding with it
    turns the problem into independent point-to-point routes between its
    endings, which is what the goal-directed search is good at.
    """
    for ptype in ("crossing", "switch", "straight"):
        if caps[ptype] > 0:
            return ptype
    return "curve"


def _score_ceiling(caps, n_pieces, inventory):
    """Best score a design of *n_pieces* from this allowance could reach.

    Used to stop searching where it cannot beat the design already in hand.
    The terms the search does not control are assumed perfect; the special
    pieces are bounded by what this allowance actually permits, which is what
    makes the bound bite — an allowance with no switches can never reach the
    score of one that uses both.
    """
    n_have = sum(inventory[t] for t in PIECE_TYPES) or 1
    switch_have = (inventory["switch"] // 2) * 2
    switch_score = caps["switch"] / switch_have if switch_have else 0.0
    cross_score = (caps["crossing"] / inventory["crossing"]
                   if inventory["crossing"] else 0.0)
    return (W_SWITCH * min(1.0, switch_score)
            + W_CROSSING * min(1.0, cross_score)
            + W_COVERAGE * (n_pieces / n_have)
            + W_REVERSALS
            + W_FILL
            + W_ASPECT)


def design_track(inventory, room_w=6.0, room_h=4.0, seed=None,
                 time_budget=3.0, min_pieces=8, node_budget=24000,
                 keep_best=True, max_forced=_DEFAULT_MAX_FORCED):
    """Design a closed track from *inventory*.

    Parameters
    ----------
    inventory : dict
        ``{"straight": n, "curve": n, "switch": n, "crossing": n}``.
    room_w, room_h : float
        Room size in metres. The design is centred in it.
    seed : int or None
        Seed for reproducible designs.
    time_budget : float
        Wall-clock seconds to spend searching.
    min_pieces : int
        Reject designs smaller than this (stops it returning a bare circle).
    node_budget : int
        DFS nodes per attempt before restarting with new randomness.
    keep_best : bool
        Keep searching for the whole budget and return the best-scoring
        design. With ``False`` the first valid design is returned.
    max_forced : int
        How many joints may be left as near-misses for the editor's force
        connection to close. Real track flexes by a few centimetres, and
        allowing this is what makes switch and crossing layouts reachable —
        with ``0`` every joint must land exactly.

    Returns
    -------
    dict or None
        ``{"pieces": [...], "forced": [...], "stats": {...}}``, centred on the
        origin, or ``None`` if nothing closed in the budget.
    """
    inventory = {t: int(inventory.get(t, 0)) for t in PIECE_TYPES}
    rng = random.Random(seed)
    room_w_u = room_w * UNITS_PER_M
    room_h_u = room_h * UNITS_PER_M
    deadline = time.monotonic() + time_budget

    total_pieces = sum(inventory.values())
    if total_pieces < min_pieces:
        return None

    best = None
    best_score = -math.inf

    # One entry per structurally different piece allowance. There is no need
    # to enumerate piece counts as well: the exploration phase pushes the walk
    # away from home before it turns back, so a search capped at the whole box
    # lands on designs that use nearly all of it anyway.
    schedule = [c for c in _caps_variants(inventory)
                if sum(c.values()) >= min_pieces]
    if not schedule:
        return None
    ceilings = [_score_ceiling(c, sum(c.values()), inventory)
                for c in schedule]

    # Iterative broadening, round-robin over the schedule. Draining one entry
    # at a time is how you end up returning nothing: the configurations that
    # would score best are also the hardest to close. Instead every round
    # sweeps all sizes with a small node allowance, then doubles it — so a
    # cheap design turns up almost immediately and the remaining time is spent
    # improving on it.
    dead = set()
    # Per-allowance cursor over piece counts. Nothing below a full circle's
    # worth of turning can close, and every special piece the allowance
    # requires has to fit on top of that.
    floors = [max(min_pieces, _FULL_TURN + c["switch"] + c["crossing"])
              for c in schedule]
    targets = list(floors)
    # Whether this allowance still has sizes that were cut short rather than
    # proved impossible — i.e. whether it is worth another, deeper sweep.
    unfinished = [False] * len(schedule)
    budget = max(512, node_budget // 3)
    done = False
    while not done and time.monotonic() < deadline:
        tried_any = False
        # With nothing in hand, work up from the plainest allowance so there is
        # always a track to show. Once something exists, go after the switches
        # and crossings first — they are what the score is really about, and
        # the fallback is already banked.
        order = sorted(
            range(len(schedule)),
            key=lambda i: (schedule[i]["switch"] + schedule[i]["crossing"]),
            reverse=best is not None,
        )
        for idx in order:
            caps = schedule[idx]
            if time.monotonic() >= deadline:
                break
            if idx in dead or ceilings[idx] <= best_score:
                # Either proved impossible, or it could not beat the design we
                # already have even if it came out perfect.
                continue
            full = sum(caps.values())
            # Sweep piece counts one at a time, keeping whichever scores best.
            #
            # One at a time, not in fractional steps: which sizes close at all
            # is spiky rather than smooth. A 16-curve box, for instance, closes
            # at 17, 18 and 20 pieces but at nothing above that, and the 18 and
            # 20 piece designs are the ones with S-curves in them. A coarse
            # ladder steps straight over exactly the sizes worth having.
            #
            # Only a few sizes per round, and the cursor always moves on even
            # when an attempt is cut short — sitting on one size until it
            # cracks stalls the sweep completely for anything that needs a lot
            # of pieces, which is precisely the switch and crossing layouts.
            for _ in range(_SIZES_PER_ROUND):
                if time.monotonic() >= deadline:
                    break
                n_target = targets[idx]
                if n_target > full:
                    if not unfinished[idx]:
                        # A whole sweep in which every size was searched to
                        # exhaustion: this allowance provably cannot close.
                        dead.add(idx)
                        break
                    targets[idx] = floors[idx]
                    unfinished[idx] = False
                    break
                targets[idx] = n_target + 1
                if _score_ceiling(caps, n_target, inventory) <= best_score:
                    # Even a perfect design this size could not beat what we
                    # already have, so there is no point building it.
                    continue
                tried_any = True
                attempt = _Attempt(
                    caps=caps, room_w=room_w_u, room_h=room_h_u, rng=rng,
                    # Exact size: a cap alone would let the search settle for a
                    # smaller design and the sweep would never move on.
                    min_pieces=n_target, max_total=n_target,
                    explore_pieces=int(n_target * rng.uniform(*_EXPLORE_FRACTION)),
                    node_budget=budget,
                    max_forced=max_forced,
                )
                result = attempt.run(_seed_type(caps), deadline)
                if result is None:
                    if not attempt.exhausted:
                        unfinished[idx] = True
                    continue
                placed, forced = result
                score, stats = score_layout(placed, inventory,
                                            room_w_u, room_h_u)
                stats["forced_joints"] = len(forced)
                if score > best_score:
                    best_score = score
                    best = (placed, forced, stats)
                if not keep_best:
                    break
            if best is not None and not keep_best:
                done = True
                break
        if not tried_any:
            break
        budget *= 2

    if best is None:
        return None

    placed, forced, stats = best
    # Centre the design in the room.
    lo_x = min(pc["lo_x"] for pc in placed)
    hi_x = max(pc["hi_x"] for pc in placed)
    lo_y = min(pc["lo_y"] for pc in placed)
    hi_y = max(pc["hi_y"] for pc in placed)
    off_x = -(lo_x + hi_x) * 0.5
    off_y = -(lo_y + hi_y) * 0.5

    return {
        "pieces": [
            {"type": pc["type"], "x": pc["x"] + off_x, "y": pc["y"] + off_y,
             "rot": pc["rot"]}
            for pc in placed
        ],
        # Joints the editor's force-connection has to close, as indices into
        # ``pieces``. The caller maps them onto its own piece ids.
        "forced": [
            {"piece1": a, "ending1_idx": ea, "piece2": b, "ending2_idx": eb}
            for (a, ea, b, eb) in forced
        ],
        "stats": stats,
    }
