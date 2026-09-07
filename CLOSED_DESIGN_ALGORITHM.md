# The Closed Design Algorithm

Notes from working out how to get a Duplo track layout **closed** with a given
box of pieces.

Sections 1–4 are about designing a layout from nothing, which is where this
started and which is genuinely hard. Section 5 is where it ended up: the
designer takes the pieces already on the floor as given and only fills in the
rest. That is both what people actually want and a far easier problem — and it
is what the app does now. Read section 5 first if you only read one.

---

## 1. What "closed" means here

`LayoutEditor.is_closed()` is true only when **every ending of every piece is
consumed** — by a coincident-ending connection, or by a forced connection.
There is no partial credit: one ending left over and the track is not closed.

Endings per piece type:

| piece | endings | internal routes a train can take |
| --- | --- | --- |
| straight | 2 | 0–1 |
| curve | 2 | 0–1 |
| switch | 3 | toe–legA, toe–legB (**never** legA–legB) |
| crossing | 4 | 0–2 and 1–3 (two strands, straight through) |

Two consequences fall straight out:

* the total ending count must be even, so **switches only work in pairs**;
* a **crossing must be traversed twice**, once per strand.

---

## 2. Measured geometry

All of this was measured from the code, not assumed. Worth keeping, because
several of these numbers contradicted my initial guesses.

| quantity | value |
| --- | --- |
| world unit | 3.2 mm (`MM_PER_UNIT`) |
| straight length | 40 units = 128 mm |
| rotation step | 30° (`rot` is 0–11) |
| curve arc | exactly 30°, so **12 curves = full circle** |
| curve centre-line radius | `c0` ≈ 80.83 units |
| curve chord (entry→exit) | ≈ 41.84 units |
| switch legs | diverge by 60° from each other |
| **crossing strands** | cross at **60°**, not 90° |
| force-connect tolerance | 12.8 units (≈ 4 cm) and 10° |

Because headings are quantised to 30°, the 10° angular part of the force
tolerance never relaxes anything — two endings are either exactly anti-parallel
or at least 30° out. **Force connection relaxes position only.**

### Turning numbers

A simple closed curve turns through exactly 360° = 12 steps. So a plain loop
must spend **12 turning pieces all in the same direction**. Every direction
reversal (an S-bend) costs **two further curves** on top of those 12.

This is why the original 12-curve default library could only ever produce
ovals: there was no spare curve with which to turn back. The default library
has since been doubled to 16 straight / 24 curve / 4 switch / 2 crossing.

A loop that returns to a *switch leg* is cheaper: the two legs already diverge
by 60°, so a balloon loop needs only 240°, not 360°.

---

## 3. The algorithm

Derived from seven layouts built by hand in the app. Every one of them fits
this model exactly:

> **A closed layout is a set of special pieces (switches and crossings), plus a
> perfect matching of all their endings into pairs, where each pair is joined
> by a routed path of plain track.**

So:

1. **Choose a multiset of specials.** Their endings must total an even number,
   which forces switches to come in pairs.
2. **Choose a typed perfect matching** of those endings. Typed matters: a
   switch ending is a *toe* or a *leg*, and joining toe–toe gives a different
   layout from joining toe–leg. A pair on the *same* piece is a balloon loop.
3. **Place the specials.**
4. **Route each pair** with a point-to-point path of straights and curves.

A plain oval is the degenerate case: no specials, one path from a piece back to
itself.

The number of matchings is small enough to **enumerate and score**, which is
the whole point — topology becomes an explicit choice rather than something a
search has to stumble onto.

### Evidence

| track | specials | endings | paths | shape |
| --- | --- | --- | --- | --- |
| 3 | 1 crossing | 4 | 2 | figure-eight: two balloons, joined *across* the strands (0–1, 2–3) |
| 1 | 2 switches | 6 | 3 | dumbbell: toe–toe, plus a balloon on each switch |
| 2 | 2 switches | 6 | 3 | theta: toe–toe, legA–legB, legB–legA |
| 4 | 2 switches | 6 | 3 | theta |
| 6 | 2 switches | 6 | 3 | **in series**: toe–legB, legA–legA, legB–toe |
| 5 | 4 switches | 12 | 6 | network |
| 7 | 1 crossing + 2 switches | 10 | **5** | crossing in the middle, a switch either side |

Notes that shaped the model:

* **Balloons are optional, not characteristic.** Only tracks 1 and 3 use them.
* **Specials mix.** Track 7 combines a crossing with two switches, which rules
  out any fixed catalogue of named motifs — "dumbbell" and "theta" are just
  particular matchings.
* **The crossing figure-eight joins the two strands** (0–1 and 2–3). Joining
  along a strand would give two loops merely touching at a point.
* **Path lengths are short and deliberately uneven**: 3, 10, 10, 3, 12 in
  track 7. A router that always takes the shortest way home will not reproduce
  these — it needs a *target length* per path.
* **Specials are not always adjacent.** Gaps between them are 0, 1, 3, 6 and
  12 pieces across the seven layouts.

---

## 4. Why the search-first approach failed

The first implementation grew a layout piece by piece: take an open ending,
either attach a piece or dock onto another open ending, and stop when nothing
is open. It reliably produces plain loops. It **never once produced a switch or
crossing layout**, across hundreds of thousands of search nodes.

The reason is structural, not a tuning problem: **a piece-by-piece search can
only discover topology by accident.** Placing a crossing part-way through a
walk fixes its pose from whatever came before, and the second pass then has
almost no freedom left. The hand-built layouts show the topology is *chosen
first* and the paths filled in afterwards.

Bugs found and fixed along the way — all real, all worth keeping:

* **Same-piece targets.** Endings on the seed piece were excluded from the
  goal list, so at the first step the search saw nothing to aim at and gave up.
* **Loose piece cap.** Capping the search at the whole box makes the
  "how many pieces do I still need" bound useless and the DFS thrashes at
  maximum depth. Fixing an exact piece count sharpens it enormously.
* **Winding.** The killer. A thread aiming at an ending computed the *shortest*
  rotation that lines the two up — but a loop returning near its start always
  needs a full turn, a figure-eight lobe needs +300°, and a balloon off a
  switch needs 240°. Aiming at the shortest equivalent sends the search after
  a shape that cannot exist. Threads must commit to a specific winding.
* **Allowance vs requirement.** Permitting a switch is not enough; the plain
  loop is always easier, so the search returns that instead. The allowance has
  to be a *requirement*.
* **Lone-ending dead end.** After a balloon closes, exactly one ending is left.
  The search treated that as failure, when it is precisely where the second
  switch belongs.
* **Budget starvation.** The first thread would spend every piece, leaving
  nothing to join the endings left over. The bound has to reserve pieces for
  threads still pending.

Performance work that did pay off, for reference: memoising pairwise overlap
tests by placement gave a **2.8× speed-up** (5,160 → 14,653 nodes/s;
`polygons_overlap` was 76% of runtime), and the turning-number prune roughly
halved the nodes needed for a plain loop.

---

## 5. Completion: don't design the topology, inherit it

Section 4 concluded the search has to be replaced by topology *choice*. The
better answer turned out to be: **don't choose the topology at all — take the
user's.**

The pieces already on the floor are given. They are never moved, rotated or
removed; the designer only *adds*, out of what is left in the box. This is a
far smaller problem than designing from nothing, because the endings left open
already pin down where the answer has to go — and the topology, the thing a
piece-by-piece search can only stumble onto, has already been decided by hand.

`complete_track` is now the entry point the app uses. `design_track` survives
for the one case with nothing to inherit: an empty floor.

### The clock is hard

The search runs under a wall-clock limit and honours it whatever the outcome.
When it expires with nothing closed, the answer is not an error — it is an
arbitrary non-overlapping continuation of the track, marked `closed: False`,
for the user to keep or trim. One greedy pass, no backtracking, each step
taking whichever piece lands nearest another open ending so the continuation
heads home rather than wandering off.

### What had to change, and what it was worth

Every one of these was found by knocking holes in the seven real layouts and
watching what failed. All five were doing real damage:

* **Overlap at a joint.** The killer, and the most surprising. In the user's
  own saved tracks, connected pieces routinely *interpenetrate* by a unit or
  two: `endings_fit` accepts a Manhattan corner sum under 6.0, which permits
  ~3 units of centre offset, while `polygons_overlap` shrank by only 0.3.
  Piece 13 and piece 15 of track 1 are connected on screen and overlapping by
  this test. So the designer could not rebuild the user's own track. Pairs that
  meet at a joint now get `JOINT_OVERLAP_MARGIN` (= `SNAP_TOLERANCE / 2`)
  instead: **51 → 54** of 63 knock-outs.
* **Reserved pieces.** `_reserve_for_pending` holds pieces back for the open
  endings a thread is not aiming at. It is a heuristic, not a bound — it pairs
  endings greedily rather than optimally, and assumes each pair needs its own
  chain of track when one switch serves several endings at once. Knock a switch
  out and four endings are open, not two; the reserve then demanded more track
  than the box held, the budget went negative, and the search died at the root
  having looked at **two nodes**. Off when completing: **54 → 63** of 63.
* **Parity.** Every ending gets paired, and only the switch has an odd number
  (three). So *the number of switches added must match the parity of the open
  endings*. Knock a switch out — three endings open — and **no amount of plain
  track can ever close it**. The allowance ladder now starts at one switch
  rather than none in that case. With a well-stocked library: **58 → 63**.
* **Specials first.** `_SPECIAL_BONUS` drags switches and crossings to the
  front of the move ordering. From nothing they are the whole point; in a gap
  they are merely what is left in the box, and a crossing dropped into a hole
  opens *three more* endings than it closes, so the search fans out instead of
  converging. Plain track first, specials only if parity or failure demands
  them: **42 → 58** with a large library.
* **Sweep horizon.** The gap-size sweep ran 0..24 on every pass, most of it
  spent on sizes far larger than the hole. Horizon now doubles alongside the
  node budget, starting at 6. A three-piece gap with a big library went from
  **timing out at 20s to 0.06s**.

One genuine geometry bug fell out of this too: `_segments_intersect` compared
raw cross-product signs, so two pieces laid end to end — whose edges are
collinear, cross product exactly zero, computed value ~1e-13 — read as
crossing. Non-monotonic in the shrink margin, which is how it was spotted:
overlap `True` at margin 3, `False` at 2 and 4. Now thresholded at 1e-9.

`LayoutEditor.is_closed()` also ignored forced connections while `view_model`
counted them, so a track the app drew green and called closed was reported
open. Fixed.

### Where it stands

Measured over all seven layouts × gaps of 3, 4 and 5 pieces × 10 seeds
(210 cases each), with a 5-second limit:

| box | solved | median | p90 | worst |
| --- | --- | --- | --- | --- |
| exactly the pieces removed | **210 / 210** | 0.01 s | 0.06 s | 0.21 s |
| a well-stocked library (40/40/4/2) | **210 / 210** | 0.01 s | 0.73 s | 3.8 s |

Stable across three repeats of the whole sweep. Gaps of 6, 7 and 8 pieces also
solve 70/70 each — median 0.06 s, 0.12 s, 0.13 s; worst 3.1 s at eight.

`tests/test_completion.py` runs the 3–5 range as 63 cases and checks each for
closure *through the editor's own* `layouts_connections`, that the user's
pieces are untouched, that only pieces they still own were used, that nothing
collides, and that any joint left loose is one force-connection would accept.

### Still open

`design_track`, the empty-floor path, is unchanged and still cannot produce
switch or crossing layouts from nothing. Section 3's model is the way to fix
that if it ever matters — but it matters much less now, because the interesting
topologies come from the user and the designer's job is to finish them.
