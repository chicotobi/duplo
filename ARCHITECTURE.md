# Duplo Track Editor — Architecture

## Overview

A Flask web application for designing toy train track layouts on an HTML5 Canvas.
Users build tracks from four piece types, snap them together, and save layouts to a database.

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ track_edit_  │  │ track_edit_  │  │   track_edit.js   │  │
│  │ geometry.js  │→ │ scenery.js   │→ │  (canvas, state,  │  │
│  │ (piece math) │  │ (tile bg)    │  │   gestures, API)  │  │
│  └──────────────┘  └──────────────┘  └────────┬──────────┘  │
│                                       JSON actions (fetch)  │
└───────────────────────────────────────────────┼─────────────┘
                                                │
                        POST /track_edit/action  │
                        {op: "...", ...args}      │
┌───────────────────────────────────────────────┼─────────────┐
│                     Flask Server              ▼             │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────────┐ │
│  │ Blueprints │→ │  Services  │→ │     Repositories       │ │
│  │ (routes)   │  │ (logic)    │  │     (SQL queries)      │ │
│  └────────────┘  └────────────┘  └────────────────────────┘ │
│                                          │                  │
│                                     SQLite DB               │
└─────────────────────────────────────────────────────────────┘
```

---

## Layered Architecture

```mermaid
graph TD
    subgraph Client["Client (Browser)"]
        GEO[track_edit_geometry.js<br/>Piece shapes, snapping math]
        SCN[track_edit_scenery.js<br/>Background tile loading]
        TE[track_edit.js<br/>Canvas rendering, gestures,<br/>state, server API]
        GEO -->|window.TE| TE
        SCN -->|window.TE| TE
    end

    subgraph Server["Flask Server"]
        BP_C[core.py<br/>/ sandbox]
        BP_T[tracks.py<br/>/track_edit /track_open]
        BP_U[users.py<br/>/user_*]
        BP_L[library.py<br/>/library_set /room_set]

        SVC_ED[LayoutEditor<br/>editor.py]
        SVC_ST[editor_storage.py<br/>Session or DB backend]
        SVC_GE[geometry.py<br/>Transforms, snapping]
        SVC_TH[thumbnails.py<br/>SVG generation]
        SVC_TT[track_types.py<br/>Piece type definitions]

        RP_LA[layouts.py<br/>pieces, connections]
        RP_TR[tracks.py<br/>track CRUD]
        RP_US[users.py<br/>users, library, room]
        RP_ES[editor_states.py<br/>in-progress state]
    end

    DB[(SQLite)]

    TE -->|JSON actions| BP_T
    TE -->|JSON actions| BP_C
    BP_T --> SVC_ED
    BP_C --> SVC_ED
    BP_T --> SVC_ST
    BP_U --> RP_US
    BP_L --> RP_US
    SVC_ED --> SVC_GE
    SVC_ED --> RP_LA
    SVC_ED --> SVC_TH
    SVC_ST --> RP_ES
    RP_LA --> DB
    RP_TR --> DB
    RP_US --> DB
    RP_ES --> DB
```

---

## Database Schema

```mermaid
erDiagram
    users {
        int id PK
        text name
        text hash
        int straight
        int curve
        int switch
        int crossing
        int room_w
        int room_h
    }
    tracks {
        int id PK
        int user_id FK
        text title
    }
    pieces {
        int id PK
        int track_id FK
        text piece
        float x
        float y
        int rot
    }
    editor_states {
        int user_id FK
        int track_id FK
        text pieces_json
        text selection_json
        timestamp updated_at
    }

    users ||--o{ tracks : "owns"
    tracks ||--o{ pieces : "contains"
    users ||--o{ editor_states : "has in-progress"
    tracks ||--o| editor_states : "editing"
```

- **`rot`** — integer 0–11, each step = 30°
- **`pieces.piece`** — one of: `straight`, `curve`, `switch`, `crossing`
- **`editor_states`** — optional DB-backed editor state (alternative to session storage)

---

## Piece Types

| Type | Shape | Endings | Geometry |
|------|-------|---------|----------|
| **straight** | Rectangle | 2 | 10 × 40 units |
| **curve** | Arc sector | 2 | radius ≈ 77.5, 30° arc |
| **switch** | Y-junction | 3 | 1 input, 2 diverging outputs |
| **crossing** | X-intersection | 4 | 4 bidirectional endings |

**Coordinate system:** pieces are defined in local space, then transformed to
world space via `(x, y, rot)` where `rot` is in 30° steps.

**Connections** are implicit — derived at view time by finding coincident endings
(within `SNAP_TOLERANCE = 6` units).

---

## Editor Action API

Single endpoint: `POST /track_edit/action` (or `/sandbox/action` for anonymous).

Every request: `{ "op": "<name>", ...args }`
Every response: `{ "ok": true, "view": <full view_model>, "extra": {...} }`

```mermaid
sequenceDiagram
    participant C as Client (JS)
    participant S as Server (Flask)
    participant DB as SQLite

    Note over C: User clicks palette tile
    C->>S: POST {op: "add_piece", type, x, y, rot}
    S->>S: editor_storage.load()
    S->>S: editor.add_piece()
    S->>S: editor_storage.save()
    S->>S: editor.view_model()
    S-->>C: {ok, view: {pieces, connections, selection, ...}}
    Note over C: applyView() — redraw canvas

    Note over C: User drags piece
    C->>S: POST {op: "commit_move", piece_id, x, y, rot, anchor}
    S->>S: snap_pose() → align to neighbor
    S-->>C: {ok, view, extra: {snapped: true}}

    Note over C: User presses Delete
    C->>S: POST {op: "delete_piece", piece_id}
    S->>S: Find neighbor → set as selection
    S-->>C: {ok, view: {selection: neighbor}}
    Note over C: applyView() — server decides selection
```

### Operations

| Op | Args | Server behavior |
|----|------|-----------------|
| `add_piece` | type, x, y, rot | Nudge to avoid overlap, mint provisional ID, auto-select |
| `move_piece` | piece_id, x, y, rot | Live drag update (no snap) |
| `commit_move` | piece_id, x, y, rot, anchor_ending_idx | Drop with snap attempt |
| `move_pieces` | moves[] | Group drag (no snap) |
| `rotate_piece` | piece_id, delta_steps | Smart rotate around connection point |
| `delete_piece` | piece_id | Select connected neighbor or clear |
| `delete_pieces` | piece_ids[] | Batch delete, clear selection |
| `select` | piece_id, ending_idx | |
| `clear_selection` | — | |
| `save` | — | Persist to DB, remap IDs, generate thumbnail |
| `rename` | title | Validate `[A-Za-z0-9 ()]+` |

---

## State Management

```mermaid
stateDiagram-v2
    state "Canonical DB" as DB
    state "Editor Storage<br/>(session or editor_states table)" as ES
    state "LayoutEditor<br/>(in-memory, per request)" as LE
    state "Client JS<br/>(pieces, selection, multiSel)" as CL

    DB --> LE: First load (GET /track_edit)
    ES --> LE: Subsequent loads (has in-progress state)
    LE --> ES: After every action (save state)
    LE --> DB: On "save" op (persist + remap IDs)
    LE --> CL: view_model JSON in response
    CL --> LE: JSON action (next request)
```

### Ownership Rules

| State | Owner | Notes |
|-------|-------|-------|
| `pieces` | Server | Authoritative. Client receives full list via `view_model`. |
| `connections` | Server | Derived from coincident endings. Sent to client read-only. |
| `selection` | Server | Server decides post-delete/add selection. Client trusts `applyView()`. |
| `multiSel` | Client | Multi-select set. Pruned by `applyView()` to match server state. |
| `is_closed` | Server | Derived: true when all endings are consumed by connections. |
| `counter` | Server | Per-type piece count vs. user library. |

**Server-authoritative selection:** the client does not predict selection after
mutations (add, delete). It clears local selection, sends the action, and lets
`applyView()` apply whatever the server decided.

---

## Client-Side Rendering Pipeline

```mermaid
flowchart LR
    subgraph Server
        VM[view_model]
    end

    subgraph "applyView()"
        P[pieces array<br/>id, path, centerlines,<br/>endings, color]
        CO[connections]
        SE[selection]
    end

    subgraph "draw() — Canvas 2D"
        BG[Tiled scenery<br/>meadow.png]
        RM[Room outline<br/>dashed border + fog]
        PI[Piece polygons<br/>grey fill + ties/rails]
        CN[Connection bridges<br/>green bars at joints]
        FE[Free ending dots<br/>orange indicators]
        SL[Selection outline<br/>orange highlight]
        EH[Ending handles<br/>clickable circles]
        GH[Drag ghost<br/>snap preview]
        TR[Train animation<br/>on closed loops]
    end

    VM --> P
    VM --> CO
    VM --> SE
    P --> BG --> RM --> PI --> CN --> FE --> SL --> EH --> GH --> TR
```

### Piece Color Coding

| Color | Meaning |
|-------|---------|
| **Grey** (`#616161`) | Piece fill (all pieces) |
| **Black** rails | Default (open track or within inventory) |
| **Red** rails | Piece count exceeds user's library inventory |
| **Green** rails | Closed loop AND all pieces within inventory |

---

## Authentication

```mermaid
flowchart TD
    A["Visit /"] --> B{Logged in?}
    B -->|No| C["Sandbox editor<br/>session-based state"]
    B -->|Yes| D["track_open<br/>list saved tracks"]

    C --> E["user_register"]
    E --> F["Adopt sandbox → saved track"]
    F --> D

    D --> G["track_edit?id=X"]
    G --> H["Full editor<br/>save/rename enabled"]
```

- **Session-based auth** — `session["user_id"]`, no Flask-Login
- **`@login_required`** decorator on all track/library routes
- **Password hashing** via Werkzeug `generate_password_hash()`
- **Sandbox** — anonymous users get a fully functional editor (session-stored),
  adopted into their account on registration

---

## Directory Structure

```
duplo/
├── __init__.py              App factory (create_app)
├── auth.py                  @login_required decorator
├── extensions.py            csrf, db, limiter instances
├── blueprints/
│   ├── core.py              / and /sandbox/action
│   ├── tracks.py            /track_edit, /track_open, /track_create
│   ├── users.py             /user_register, /user_login, etc.
│   └── library.py           /library_set, /room_set
├── services/
│   ├── editor.py            LayoutEditor state machine
│   ├── editor_storage.py    Session/DB persistence
│   ├── geometry.py          Piece transforms, snapping, overlap
│   ├── thumbnails.py        SVG thumbnail generation
│   └── track_types.py       Piece type constants
└── repositories/
    ├── layouts.py            pieces table, connection derivation
    ├── tracks.py             tracks CRUD
    ├── users.py              users, library, room settings
    └── editor_states.py      in-progress editor state table

static/js/
├── track_edit_geometry.js   Client-side piece math (mirrors geometry.py)
├── track_edit_scenery.js    Background tile loading
└── track_edit.js            Canvas rendering, gestures, server API

templates/
├── track_edit.html          Editor page (canvas + palette + toolbar)
├── track_open.html          Track list with thumbnails
└── ...                      Login, register, library, etc.
```
