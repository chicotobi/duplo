# The Closed Design Algorithm

Notes from working out how to generate a **closed** Duplo track layout from a
given box of pieces. The conclusion is at the top; the failed approach is
written up too, because knowing why it fails is most of the value.

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

## 5. State of the code

Working and tested:

* `duplo/services/designer.py` — the piece-by-piece searcher. Produces closed,
  non-overlapping, room-fitting **plain loops** reliably (~14k nodes for a
  20-piece loop). Does *not* produce switch or crossing layouts.
* `geometry.endings_fit` / `ending_heading` — the connection predicate lifted
  out of the repository layer so the designer and the editor cannot disagree
  about what "connected" means.
* Near-miss joints: the designer may leave a joint inside the force-connect
  tolerance and returns it as a forced connection, so the layout still reads as
  closed. Verified end-to-end.
* Scoring weights switches (0.34) and crossings (0.30) above coverage (0.16).
* `design_track` op on both the logged-in and sandbox endpoints, plus a
  toolbar button.

### Next step

Replace the topology *search* with topology *choice*, per section 3. Steps 1
and 2 are enumeration. Step 4 is the existing router, which already closes
paths reliably — but it needs to aim for a target path length rather than the
shortest route. Step 3, where to place the specials, is the genuinely open
question; the hand-built layouts show no obvious rule, so the most promising
approach is to place the first special at the origin and let each completed
path determine the next one's pose.
