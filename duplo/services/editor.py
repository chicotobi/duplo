"""``LayoutEditor`` — encapsulates the track editor state machine.

The editor holds three pieces of working state for a given user/track:

  * ``pieces``       — list of piece-type strings, in placement order
  * ``connections``  — list of dicts ``{"p1", "e1", "p2", "e2"}``
  * ``cursor_idx``   — index into the current free-endings list

Mutating operations (:meth:`add_piece`, :meth:`delete_last`,
:meth:`next_ending`, :meth:`rotate_last`) update those fields and reposition
the cursor sensibly. :meth:`save` persists to the canonical pieces /
connections tables and regenerates the thumbnail.
"""

from ..repositories.layouts import (
    connections_update,
    layouts_build,
    layouts_free_endings,
    layouts_parse,
    pieces_update,
)
from .geometry import PIECE_TYPES, add_piece
from .thumbnails import generate_thumbnail


_GHOST_SPECS = [
    ("straight", "straight", 0),
    ("right",    "curve",    0),
    ("left",     "curve",    1),
    ("switch",   "switch",   0),
    ("crossing", "crossing", 0),
]


class LayoutEditor:
    """Pure-Python state machine for track editing."""

    def __init__(self, track_id, pieces, connections, cursor_idx):
        self.track_id = track_id
        self.pieces = list(pieces)
        # Always store as a fresh list of plain dicts.
        self.connections = [
            {"p1": int(c["p1"]), "e1": int(c["e1"]),
             "p2": int(c["p2"]), "e2": int(c["e2"])}
            for c in connections
        ]
        self.cursor_idx = cursor_idx

    # ------------------------------------------------------------------ load

    @classmethod
    def load_from_db(cls, track_id):
        """Initialise an editor from the persisted layout."""
        pieces, connections = layouts_parse(track_id)
        return cls(track_id, pieces, connections, cursor_idx=0)

    @classmethod
    def from_session(cls, track_id, pieces, connections, cursor_idx):
        """Restore editor state previously stashed in the session cookie."""
        return cls(track_id, pieces, connections, cursor_idx)

    def to_session(self):
        """Return a JSON-able dict suitable for stashing in the session."""
        return {
            "pieces": self.pieces,
            "connections": list(self.connections),
            "cursor_idx": self.cursor_idx,
        }

    # ----------------------------------------------------------------- query

    def _build(self):
        return layouts_build(self.pieces, self.connections)

    def _free_endings(self, endings):
        return layouts_free_endings(endings, self.connections)

    def is_closed(self):
        _, endings, _ = self._build()
        return len(self._free_endings(endings)) == 0

    # ------------------------------------------------------------- mutations

    def apply_action(self, action):
        """Apply a UI action token (the form key submitted by the editor).

        Returns ``"saved"`` if the editor persisted to the DB, else ``None``.
        """
        if action in ("left", "right"):
            self.add_piece("curve", e2=(1 if action == "right" else 0))
        elif action in PIECE_TYPES:
            self.add_piece(action, e2=0)
        elif action == "delete":
            self.delete_last()
        elif action == "next_ending":
            self.next_ending()
        elif action == "rotate":
            self.rotate_last()
        elif action == "save":
            self.save()
            return "saved"
        return None

    def add_piece(self, piece_type, e2=0):
        _, endings, _ = self._build()
        free_endings = self._free_endings(endings)
        if not free_endings:
            return
        p1, e1 = free_endings[self.cursor_idx]
        p2 = len(self.pieces)
        self.pieces.append(piece_type)
        self.connections.append({"p1": p1, "e1": e1, "p2": p2, "e2": e2})
        self._snap_cursor_to_last()

    def delete_last(self):
        if not self.pieces:
            return
        self.pieces.pop()
        last = len(self.pieces)
        self.connections = [
            c for c in self.connections if c["p1"] != last and c["p2"] != last
        ]
        self._snap_cursor_to_last()

    def next_ending(self):
        _, endings, _ = self._build()
        free_endings = self._free_endings(endings)
        if free_endings:
            self.cursor_idx = (self.cursor_idx + 1) % len(free_endings)

    def rotate_last(self):
        if not self.pieces:
            return
        _, endings, _ = self._build()
        current_piece = len(self.pieces) - 1
        n = len(endings[current_piece])
        for c in self.connections:
            if c["p2"] == current_piece:
                c["e2"] = (c["e2"] + 1) % n
        self._snap_cursor_to_last()

    def save(self):
        pieces_update(track_id=self.track_id, pieces=self.pieces)
        connections_update(track_id=self.track_id, connections=self.connections)
        generate_thumbnail(self.track_id)

    # ----------------------------------------------------------------- view

    def view_model(self, user_lib):
        """Build the dict consumed by ``track_edit.html``.

        Returns a dict with keys ``pathes``, ``counter``, ``is_closed``,
        ``ghosts``. The caller is responsible for adding ``title`` /
        ``user_lib`` before passing to ``render_template``.
        """
        pathes, endings, centerlines_list = self._build()
        free_endings = self._free_endings(endings)
        is_closed = len(free_endings) == 0

        pathes2 = []
        counter = {p: 0 for p in PIECE_TYPES}
        all_possible = True
        for piece, path, cls in zip(self.pieces, pathes, centerlines_list):
            counter[piece] += 1
            if counter[piece] > user_lib[piece]:
                col = "red"
                all_possible = False
            else:
                col = "black"
            pathes2.append({"path": path, "color": col, "centerlines": cls, "type": piece})

        ghosts = {}
        cursor = None
        if not is_closed:
            current_ending = free_endings[self.cursor_idx]
            cursor_pos = endings[current_ending[0]][current_ending[1]]
            (x1, y1), (x2, y2) = cursor_pos
            cursor = [{"x": x1, "y": y1}, {"x": x2, "y": y2}]
            for action, piece_type, e2 in _GHOST_SPECS:
                try:
                    pts, _, cls = add_piece(piece_type, cursor_pos, e2)
                    ghosts[action] = {"path": pts, "centerlines": cls}
                except Exception:
                    pass
        elif all_possible:
            for p in pathes2:
                p["color"] = "green"

        return {
            "pathes": pathes2,
            "counter": counter,
            "is_closed": is_closed,
            "ghosts": ghosts,
            "cursor": cursor,
        }

    # --------------------------------------------------------------- helpers

    def _snap_cursor_to_last(self):
        """Move the cursor to the highest-indexed free ending, or ``None`` if closed."""
        _, endings, _ = self._build()
        free_endings = self._free_endings(endings)
        if not free_endings:
            self.cursor_idx = None
            return
        tmp = max(i for (i, _) in free_endings)
        self.cursor_idx = [i for (i, (j, _)) in enumerate(free_endings) if j == tmp][0]
