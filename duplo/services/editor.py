"""``LayoutEditor`` — pose-based, independent-pieces state machine.

State
-----
* ``pieces``    — list of ``{"id": int, "type": str, "x": float, "y": float, "rot": int}``
                  in stable id-order. Persisted-piece ids are positive (the DB pk),
                  unsaved pieces have negative provisional ids assigned client-side
                  by the editor. Ids are stable across the session.
* ``selection`` — ``{"piece_id": int, "ending_idx": int|None} | None``
* ``track_id``

Operations
----------
``add_piece``, ``move_piece``, ``commit_move``, ``rotate_piece``,
``delete_piece``, ``select`` / ``clear_selection``, ``save``.

Snapping is handled by :func:`snap_pose`. Connections are derived at view
time from coincident world endings.
"""

from ..repositories.layouts import (
    layouts_build,
    layouts_connections,
    layouts_free_endings,
    layouts_parse,
    pieces_update,
)
from ..repositories.tracks import (
    tracks_read_forced_connections,
    tracks_update_forced_connections,
)

from .geometry import (
    PIECE_TYPES,
    SNAP_TOLERANCE,
    _pose_to_align,
    ending_count,
    polygons_overlap,
    snap_pose,
    w0,
    world_polygon,
)
from .thumbnails import generate_thumbnail


class LayoutEditor:
    """In-memory state machine for the pose-based track editor."""

    def __init__(self, track_id, pieces, selection=None, next_provisional_id=-1, forced_connections=None):
        self.track_id = track_id
        self.pieces = [
            {"id": int(p["id"]), "type": p["type"],
             "x": float(p["x"]), "y": float(p["y"]), "rot": int(p["rot"]) % 12}
            for p in pieces
        ]
        self.selection = self._normalise_selection(selection)
        # Counter used to mint ids for unsaved pieces (negative, decreasing).
        self._next_provisional = int(next_provisional_id)
        # List of forced connections: [{"piece1_id": int, "ending1_idx": int,
        #                               "piece2_id": int, "ending2_idx": int}, ...]
        self.forced_connections = forced_connections if forced_connections is not None else []

    # ------------------------------------------------------------------ load

    @classmethod
    def load_from_db(cls, track_id):
        pieces = layouts_parse(track_id)
        forced_connections = tracks_read_forced_connections(track_id)
        return cls(track_id, pieces, forced_connections=forced_connections)

    @classmethod
    def from_session(cls, track_id, pieces, selection, next_provisional_id=-1, forced_connections=None):
        return cls(track_id, pieces, selection, next_provisional_id, forced_connections)

    def to_session(self):
        return {
            "pieces": [dict(p) for p in self.pieces],
            "selection": dict(self.selection) if self.selection else None,
            "next_provisional_id": self._next_provisional,
            "forced_connections": [dict(fc) for fc in self.forced_connections],
        }

    # ----------------------------------------------------------- helpers

    def _normalise_selection(self, sel):
        if sel is None:
            return None
        pid = int(sel["piece_id"])
        eidx = sel.get("ending_idx")
        eidx = None if eidx is None else int(eidx)
        # Drop selections referring to pieces that no longer exist.
        if not any(p["id"] == pid for p in self.pieces):
            return None
        return {"piece_id": pid, "ending_idx": eidx}

    def _piece(self, piece_id):
        for p in self.pieces:
            if p["id"] == piece_id:
                return p
        raise KeyError(piece_id)

    def _mint_id(self):
        pid = self._next_provisional
        self._next_provisional -= 1
        return pid

    def _build(self):
        return layouts_build(self.pieces)

    # ------------------------------------------------------------- queries

    def is_closed(self):
        if not self.pieces:
            return False
        _, all_eds, _ = self._build()
        return len(layouts_free_endings(all_eds)) == 0

    def free_endings_excluding(self, piece_id):
        """World-space free endings of every piece except ``piece_id``.

        Used by :meth:`commit_move` and the client-side snap preview.
        """
        _, all_eds, _ = self._build()
        # Recompute "free" while pretending the dragged piece does not exist:
        # otherwise its current position would consume nearby endings.
        others = {pid: eds for pid, eds in all_eds.items() if pid != piece_id}
        free = layouts_free_endings(others)
        out = []
        for (pid, eidx) in free:
            pair = others[pid][eidx]
            out.append({"piece_id": pid, "ending_idx": eidx,
                        "pair": [list(pair[0]), list(pair[1])]})
        return out

    # ------------------------------------------------------------- mutations

    def add_piece(self, piece_type, x, y, rot=0, select=True):
        if piece_type not in PIECE_TYPES:
            raise ValueError(f"unknown piece type: {piece_type}")
        x, y = self._nudge_to_avoid_overlap(
            piece_type, float(x), float(y), int(rot) % 12,
        )
        pid = self._mint_id()
        self.pieces.append({"id": pid, "type": piece_type,
                            "x": x, "y": y,
                            "rot": int(rot) % 12})
        if select:
            self.selection = {"piece_id": pid, "ending_idx": None}
        return pid

    def _nudge_to_avoid_overlap(self, piece_type, x, y, rot, exclude_id=None):
        """Shift ``(x, y)`` to the nearest non-overlapping position."""
        if not self.pieces:
            return x, y
        existing = [
            world_polygon(p["type"], p["x"], p["y"], p["rot"])
            for p in self.pieces
            if p["id"] != exclude_id
        ]
        new_poly = world_polygon(piece_type, x, y, rot)
        if not any(polygons_overlap(new_poly, ep) for ep in existing):
            return x, y
        # Try positions in expanding rings around the original point.
        step = w0  # one piece-width per step
        _dirs = [
            (1, 0), (-1, 0), (0, 1), (0, -1),
            (1, 1), (-1, 1), (1, -1), (-1, -1),
        ]
        for dist in range(1, 30):
            for dx, dy in _dirs:
                nx = x + dx * dist * step
                ny = y + dy * dist * step
                new_poly = world_polygon(piece_type, nx, ny, rot)
                if not any(polygons_overlap(new_poly, ep) for ep in existing):
                    return nx, ny
        return x, y  # fallback: give up after many attempts

    def move_piece(self, piece_id, x, y, rot):
        p = self._piece(piece_id)
        p["x"] = float(x)
        p["y"] = float(y)
        p["rot"] = int(rot) % 12

    def rotate_piece(self, piece_id, delta_steps=1):
        p = self._piece(piece_id)

        # Smart rotate: if the piece has exactly one connected ending and
        # free endings, cycle which ending is connected to the same anchor
        # point on the neighbor.
        _, all_eds, _ = self._build()
        conns = layouts_connections(all_eds)

        # Find which of this piece's endings are connected.
        connected = []  # (my_eidx, other_pid, other_eidx)
        for (a, b) in conns:
            if a[0] == piece_id:
                connected.append((a[1], b[0], b[1]))
            elif b[0] == piece_id:
                connected.append((b[1], a[0], a[1]))

        n_endings = ending_count[p["type"]]
        n_free = n_endings - len(connected)

        if len(connected) == 1 and n_free > 0:
            my_conn_eidx, other_pid, other_eidx = connected[0]
            # The target pair on the neighbor that we must stay connected to.
            pivot_pair = all_eds[other_pid][other_eidx]

            # Try each of the piece's other endings as the new connection.
            candidates = []
            for eidx in range(n_endings):
                if eidx == my_conn_eidx:
                    continue
                x, y, rot = _pose_to_align(p["type"], eidx, pivot_pair)
                # Check no overlap with other pieces.
                new_poly = world_polygon(p["type"], x, y, rot)
                overlap = False
                for op in self.pieces:
                    if op["id"] == piece_id:
                        continue
                    op_poly = world_polygon(op["type"], op["x"], op["y"], op["rot"])
                    if polygons_overlap(new_poly, op_poly):
                        overlap = True
                        break
                if overlap:
                    continue
                candidates.append((eidx, x, y, rot))

            if candidates:
                # Order by ending index relative to current connected ending.
                ds = int(delta_steps)
                if ds > 0:
                    candidates.sort(key=lambda c: (c[0] - my_conn_eidx) % n_endings)
                else:
                    candidates.sort(key=lambda c: (my_conn_eidx - c[0]) % n_endings)
                _, nx, ny, nr = candidates[0]
                p["x"] = float(nx)
                p["y"] = float(ny)
                p["rot"] = int(nr) % 12
                return

        # Fallback: simple rotation.
        p["rot"] = (p["rot"] + int(delta_steps)) % 12

    def delete_piece(self, piece_id):
        # Find a connected neighbor before removing the piece.
        neighbor_id = None
        _, all_eds, _ = self._build()
        conns = layouts_connections(all_eds)
        for (a, b) in conns:
            if a[0] == piece_id:
                neighbor_id = b[0]
                break
            if b[0] == piece_id:
                neighbor_id = a[0]
                break

        self.pieces = [p for p in self.pieces if p["id"] != piece_id]
        if self.selection and self.selection["piece_id"] == piece_id:
            if neighbor_id is not None:
                self.selection = {"piece_id": neighbor_id, "ending_idx": None}
            else:
                self.selection = None

    def delete_pieces(self, piece_ids):
        """Batch-delete several pieces at once."""
        ids = set(int(pid) for pid in piece_ids)
        self.pieces = [p for p in self.pieces if p["id"] not in ids]
        if self.selection and self.selection["piece_id"] in ids:
            self.selection = None

    def move_pieces(self, moves):
        """Batch-move several pieces. Each item: ``{piece_id, x, y, rot}``.

        No snapping is attempted — this is used for group drags.
        """
        for m in moves:
            p = self._piece(int(m["piece_id"]))
            p["x"] = float(m["x"])
            p["y"] = float(m["y"])
            p["rot"] = int(m["rot"]) % 12

    def select(self, piece_id, ending_idx=None):
        # Validate.
        p = self._piece(piece_id)
        if ending_idx is not None:
            ending_idx = int(ending_idx)
            if not (0 <= ending_idx < ending_count[p["type"]]):
                raise ValueError(f"ending_idx out of range: {ending_idx}")
        self.selection = {"piece_id": piece_id, "ending_idx": ending_idx}

    def clear_selection(self):
        self.selection = None

    def commit_move(self, piece_id, x, y, rot, anchor_ending_idx=None):
        """Place ``piece_id`` at ``(x, y, rot)`` then attempt to snap.

        ``anchor_ending_idx`` is the ending the user is actively snapping (if
        ``None``, defaults to the selection's ending if it belongs to this
        piece, otherwise tries every ending and keeps the closest snap).

        Returns ``{"piece": <piece dict>, "snapped": bool, "target": ... or None}``.
        """
        self.move_piece(piece_id, x, y, rot)
        p = self._piece(piece_id)
        targets = self.free_endings_excluding(piece_id)

        # Decide which ending(s) to try as anchor.
        if anchor_ending_idx is None and self.selection \
                and self.selection["piece_id"] == piece_id \
                and self.selection["ending_idx"] is not None:
            anchor_ending_idx = self.selection["ending_idx"]

        if anchor_ending_idx is not None:
            anchors = [int(anchor_ending_idx)]
        else:
            anchors = list(range(ending_count[p["type"]]))

        best = None
        best_dist = float("inf")
        for a in anchors:
            res = snap_pose(p["type"], a, (p["x"], p["y"], p["rot"]), targets)
            if res is None:
                continue
            # Distance from current pose to snapped pose.
            dx = res["pose"][0] - p["x"]
            dy = res["pose"][1] - p["y"]
            d = dx * dx + dy * dy
            if d < best_dist:
                best_dist = d
                best = res

        if best is not None:
            sx, sy, srot = best["pose"]
            p["x"], p["y"], p["rot"] = float(sx), float(sy), int(srot) % 12
            return {"piece": dict(p), "snapped": True, "target": best["target"]}

        # No snap — nudge to avoid overlapping any other piece.
        nx, ny = self._nudge_to_avoid_overlap(
            p["type"], p["x"], p["y"], p["rot"], exclude_id=piece_id,
        )
        p["x"], p["y"] = nx, ny
        return {"piece": dict(p), "snapped": False, "target": None}

    def get_force_connection_candidates(self):
        """Check if exactly 2 pieces are selected with 1 free ending each.

        Returns dict with qualification info, or None if selection doesn't match.

        Returns
        -------
        dict or None
            If matched: ``{"can_force": bool, "piece1_id": int, "ending1_idx": int,
                          "piece2_id": int, "ending2_idx": int, "distance": float,
                          "angle_deg": float, "reason": str (if not can_force)}``
            If no match: ``None``
        """
        from .geometry import can_force_connect

        if self.selection is None:
            return None

        piece1_id = self.selection.get("piece_id")
        if piece1_id is None:
            return None

        # Find two selected pieces
        pieces_sel = [p["id"] for p in self.pieces
                      if p["id"] == piece1_id or
                         (self.selection and p["id"] in getattr(self, '_multi_selection', {}))]

        # For now, we only support checking when selection is single-piece context
        # Check if there are hints about a second piece in the payload (passed from client)
        # For this, we'll return None if selection is unclear
        return None

    def check_force_connection(self, piece1_id, piece2_id):
        """Check if two specific pieces can be force-connected.

        Each piece must have exactly one free ending, and those endings must
        be geometrically close and nearly aligned.

        Returns
        -------
        dict
            ``{"can_force": bool, "distance": float, "angle_deg": float or None,
              "reason": str or None}``
        """
        from .geometry import can_force_connect, ending_count, world_endings_for_pose

        try:
            p1 = self._piece(piece1_id)
            p2 = self._piece(piece2_id)
        except KeyError:
            return {"can_force": False, "distance": None, "angle_deg": None,
                    "reason": "Piece not found"}

        # Compute free endings for both pieces
        _, all_endings, _ = self._build()
        from ..repositories.layouts import layouts_connections
        conns = layouts_connections(all_endings)
        forced_pairs = set(
            ((fc["piece1_id"], fc["ending1_idx"]), (fc["piece2_id"], fc["ending2_idx"]))
            if fc["piece1_id"] < fc["piece2_id"]
            else ((fc["piece2_id"], fc["ending2_idx"]), (fc["piece1_id"], fc["ending1_idx"]))
            for fc in self.forced_connections
        )

        # Find connected and forced endings for each piece
        connected = set()
        for (a, b) in conns:
            connected.add((a[0], a[1]))
            connected.add((b[0], b[1]))
        forced_used = set()
        for fc_pair in forced_pairs:
            forced_used.add(fc_pair[0])
            forced_used.add(fc_pair[1])

        p1_free = []
        for eidx in range(ending_count[p1["type"]]):
            if (p1["id"], eidx) not in connected and (p1["id"], eidx) not in forced_used:
                p1_free.append(eidx)

        p2_free = []
        for eidx in range(ending_count[p2["type"]]):
            if (p2["id"], eidx) not in connected and (p2["id"], eidx) not in forced_used:
                p2_free.append(eidx)

        if len(p1_free) != 1 or len(p2_free) != 1:
            msg = f"Need exactly 1 free ending per piece; got {len(p1_free)}, {len(p2_free)}"
            return {"can_force": False, "distance": None, "angle_deg": None,
                    "reason": msg}

        e1_idx = p1_free[0]
        e2_idx = p2_free[0]
        e1 = all_endings[p1["id"]][e1_idx]
        e2 = all_endings[p2["id"]][e2_idx]

        result = can_force_connect(e1, e2)
        return result

    def force_connect(self, piece1_id, piece2_id, ending1_idx, ending2_idx):
        """Create a forced connection between two pieces.

        Returns ``{"success": bool, "forced_connections": [...], "error": str or None}``
        """
        try:
            self._piece(piece1_id)
            self._piece(piece2_id)
        except KeyError:
            return {"success": False, "forced_connections": self.forced_connections,
                    "error": "Piece not found"}

        # Check if connection already exists
        for fc in self.forced_connections:
            if ((fc["piece1_id"] == piece1_id and fc["ending1_idx"] == ending1_idx and
                 fc["piece2_id"] == piece2_id and fc["ending2_idx"] == ending2_idx) or
                (fc["piece1_id"] == piece2_id and fc["ending1_idx"] == ending2_idx and
                 fc["piece2_id"] == piece1_id and fc["ending2_idx"] == ending1_idx)):
                return {"success": False, "forced_connections": self.forced_connections,
                        "error": "Connection already exists"}

        # Verify geometry
        check_result = self.check_force_connection(piece1_id, piece2_id)
        if not check_result["can_force"]:
            return {"success": False, "forced_connections": self.forced_connections,
                    "error": check_result.get("reason", "Cannot force connection")}

        # Add the connection
        fc = {
            "piece1_id": int(piece1_id),
            "ending1_idx": int(ending1_idx),
            "piece2_id": int(piece2_id),
            "ending2_idx": int(ending2_idx),
        }
        self.forced_connections.append(fc)
        
        # Persist to database immediately
        tracks_update_forced_connections(self.track_id, self.forced_connections)

        return {"success": True, "forced_connections": self.forced_connections, "error": None}

    def resolve_force_connection(self, piece1_id, piece2_id, ending1_idx, ending2_idx):
        """Remove a forced connection between two pieces.

        Returns ``{"success": bool, "forced_connections": [...], "error": str or None}``
        """
        initial_len = len(self.forced_connections)
        self.forced_connections = [
            fc for fc in self.forced_connections
            if not (
                (fc["piece1_id"] == piece1_id and fc["ending1_idx"] == ending1_idx and
                 fc["piece2_id"] == piece2_id and fc["ending2_idx"] == ending2_idx) or
                (fc["piece1_id"] == piece2_id and fc["ending1_idx"] == ending2_idx and
                 fc["piece2_id"] == piece1_id and fc["ending2_idx"] == ending1_idx)
            )
        ]

        removed = initial_len > len(self.forced_connections)
        
        # Persist to database immediately
        if removed:
            tracks_update_forced_connections(self.track_id, self.forced_connections)
        
        return {
            "success": removed,
            "forced_connections": self.forced_connections,
            "error": None if removed else "Connection not found",
        }

    # --------------------------------------------------------------- persist

    def save(self):
        """Persist pieces to the canonical ``pieces`` table.

        After save, every piece has a positive db id; selection is remapped.
        """
        old_ids = [p["id"] for p in self.pieces]
        new_ids = pieces_update(track_id=self.track_id, pieces=self.pieces)
        id_map = {old: int(new) for old, new in zip(old_ids, new_ids)}
        for p, new_id in zip(self.pieces, new_ids):
            p["id"] = int(new_id)
        if self.selection:
            mapped = id_map.get(self.selection["piece_id"])
            if mapped is None:
                self.selection = None
            else:
                self.selection["piece_id"] = mapped
        # Remap forced_connections piece ids
        for fc in self.forced_connections:
            if fc["piece1_id"] in id_map:
                fc["piece1_id"] = id_map[fc["piece1_id"]]
            if fc["piece2_id"] in id_map:
                fc["piece2_id"] = id_map[fc["piece2_id"]]
        # Persist forced_connections to database
        tracks_update_forced_connections(self.track_id, self.forced_connections)
        generate_thumbnail(self.track_id)

    # ----------------------------------------------------------------- view

    def view_model(self, user_lib):
        """Build the dict consumed by ``track_edit.html`` and the JSON action API.

        Returns
        -------
        dict with keys:
          * ``pieces``      — list of ``{id, type, x, y, rot, path, centerlines, endings, color}``
                               where ``endings`` is ``[{a:{x,y}, b:{x,y}, free:bool}, ...]``
          * ``connections`` — list of ``[{piece_id, ending_idx}, {piece_id, ending_idx}]`` pairs
          * ``selection``   — ``{piece_id, ending_idx} | None``
          * ``is_closed``   — bool
          * ``counter``     — ``{piece_type: count}``
          * ``snap_tolerance`` — world-units snap radius (handed to JS)
        """
        pathes, all_eds, cls_per_piece = self._build()
        connections = layouts_connections(all_eds)
        consumed = set()
        for (a, b) in connections:
            consumed.add(a)
            consumed.add(b)
        
        # Also add forced connections to consumed set
        for fc in self.forced_connections:
            consumed.add((fc["piece1_id"], fc["ending1_idx"]))
            consumed.add((fc["piece2_id"], fc["ending2_idx"]))
        
        is_closed = bool(self.pieces) and not any(
            (p["id"], eidx) not in consumed
            for p in self.pieces
            for eidx in range(ending_count[p["type"]])
        )

        counter = {pt: 0 for pt in PIECE_TYPES}
        all_within_lib = True
        for p in self.pieces:
            counter[p["type"]] += 1
        for pt, n in counter.items():
            if n > user_lib[pt]:
                all_within_lib = False
                break

        out_pieces = []
        seen = {pt: 0 for pt in PIECE_TYPES}
        for p, path, cls in zip(self.pieces, pathes, cls_per_piece):
            seen[p["type"]] += 1
            over_limit = seen[p["type"]] > user_lib[p["type"]]
            if is_closed:
                color = "green"
            else:
                color = "black"
            alpha = 0.5 if over_limit else 1.0
            eds_world = all_eds[p["id"]]
            endings_view = []
            for eidx, pair in enumerate(eds_world):
                endings_view.append({
                    "a": {"x": pair[0][0], "y": pair[0][1]},
                    "b": {"x": pair[1][0], "y": pair[1][1]},
                    "free": (p["id"], eidx) not in consumed,
                })
            out_pieces.append({
                "id": p["id"],
                "type": p["type"],
                "x": p["x"], "y": p["y"], "rot": p["rot"],
                "path": path,
                "centerlines": cls,
                "endings": endings_view,
                "color": color,
                "alpha": alpha,
            })

        connections_view = [
            [{"piece_id": a[0], "ending_idx": a[1]},
             {"piece_id": b[0], "ending_idx": b[1]}]
            for (a, b) in connections
        ]

        return {
            "pieces": out_pieces,
            "connections": connections_view,
            "forced_connections": [
                [{"piece_id": fc["piece1_id"], "ending_idx": fc["ending1_idx"]},
                 {"piece_id": fc["piece2_id"], "ending_idx": fc["ending2_idx"]}]
                for fc in self.forced_connections
            ],
            "selection": dict(self.selection) if self.selection else None,
            "is_closed": is_closed,
            "counter": counter,
            "snap_tolerance": SNAP_TOLERANCE,
        }
